"""LangGraph nodes and schemas for the local Todoist agent."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Protocol, TypedDict, TypeVar

from loguru import logger
from pydantic import BaseModel, Field

from todoist.agent.constants import NodeName, PlannerAction, SYSTEM_PROMPT
from todoist.agent.prefabs import load_instruction_prefabs
from todoist.agent.utils import build_planner_messages, last_user_text


T = TypeVar("T", bound=BaseModel)


class AgentState(TypedDict, total=False):
    messages: list[dict[str, str]]
    selected_prefab_ids: list[str]
    selected_prefab_contents: list[str]
    plan: list[str]
    pending_tool_code: str | None
    tool_steps: int
    final_answer: str | None


class ChatModel(Protocol):
    def structured_chat(self, messages: list[dict[str, str]], schema: type[T]) -> T: ...


class PythonReplTool(Protocol):
    def run(self, code: str) -> str: ...


class InstructionSelection(BaseModel):
    selected_ids: list[str] = Field(default_factory=list)


class PlannerDecision(BaseModel):
    plan: list[str] = Field(default_factory=list)
    action: PlannerAction
    tool_code: str | None = None
    final_answer: str | None = None


@dataclass(frozen=True)
class AgentNodes:
    llm: ChatModel
    python_repl: PythonReplTool
    prefabs_root: Path
    max_tool_loops: int

    def initial_prompt(self, state: AgentState) -> AgentState:
        messages = list(state.get("messages") or [])
        if not messages or messages[0].get("role") != "system":
            messages.insert(0, {"role": "system", "content": SYSTEM_PROMPT})
        return {"messages": messages, "tool_steps": int(state.get("tool_steps") or 0)}

    def select_instructions(self, state: AgentState) -> AgentState:
        messages = list(state.get("messages") or [])
        if not messages:
            raise ValueError("select_instructions requires state.messages")

        prefabs = load_instruction_prefabs(self.prefabs_root)
        if not prefabs:
            return {"selected_prefab_ids": [], "selected_prefab_contents": []}

        query = last_user_text(messages)
        available = [{"id": p.prefab_id, "description": p.description} for p in prefabs]
        selector_messages = [
            {
                "role": "system",
                "content": "Select 0..N instruction prefab ids that help answer the query.",
            },
            {
                "role": "user",
                "content": json.dumps({"query": query, "available_prefabs": available}, ensure_ascii=False),
            },
        ]

        try:
            selection = self.llm.structured_chat(selector_messages, InstructionSelection)
        except ValueError as exc:
            logger.error("Instruction selection failed: {}", exc)
            return {"selected_prefab_ids": [], "selected_prefab_contents": []}

        allowed = {p.prefab_id for p in prefabs}
        selected_ids = [pid for pid in selection.selected_ids if pid in allowed]
        selected_contents = [p.content for p in prefabs if p.prefab_id in selected_ids]
        logger.info("Selected prefabs: {}", selected_ids)
        return {"selected_prefab_ids": selected_ids, "selected_prefab_contents": selected_contents}

    def planner(self, state: AgentState) -> AgentState:
        messages = list(state.get("messages") or [])
        if not messages:
            raise ValueError("planner requires state.messages")

        tool_steps = int(state.get("tool_steps") or 0)
        if tool_steps >= self.max_tool_loops:
            return {
                "final_answer": "Max tool iterations reached. Please narrow the question.",
                "pending_tool_code": None,
            }

        planner_messages = build_planner_messages(messages, state.get("selected_prefab_contents") or [])
        try:
            decision = self.llm.structured_chat(planner_messages, PlannerDecision)
        except ValueError as exc:
            logger.error("Planner structured output failed: {}", exc)
            return {
                "final_answer": "Model returned invalid structured output. Please rephrase and try again.",
                "pending_tool_code": None,
            }

        logger.info("Planner action: {} plan_steps={}", decision.action, len(decision.plan))
        if decision.action == PlannerAction.TOOL:
            if not decision.tool_code:
                raise ValueError("Planner returned action=tool but tool_code is empty")
            return {"plan": decision.plan, "pending_tool_code": decision.tool_code, "final_answer": None}

        if not decision.final_answer:
            raise ValueError("Planner returned action=final but final_answer is empty")
        return {"plan": decision.plan, "pending_tool_code": None, "final_answer": decision.final_answer}

    def executor(self, state: AgentState) -> AgentState:
        code = (state.get("pending_tool_code") or "").strip()
        if not code:
            raise ValueError("Executor called without pending_tool_code")

        logger.info("Executing python_repl")
        output = self.python_repl.run(code)

        messages = list(state.get("messages") or [])
        if not messages:
            raise ValueError("executor requires state.messages")
        messages.append({"role": "assistant", "content": f"Calling python_repl with code:\n```python\n{code}\n```"})
        messages.append({"role": "user", "content": f"python_repl output:\n{output}"})
        return {
            "messages": messages,
            "pending_tool_code": None,
            "tool_steps": int(state.get("tool_steps") or 0) + 1,
        }

    def output(self, state: AgentState) -> AgentState:
        final_answer = state.get("final_answer")
        if not final_answer:
            raise ValueError("Output node called without final_answer")
        messages = list(state.get("messages") or [])
        if not messages:
            raise ValueError("output requires state.messages")
        messages.append({"role": "assistant", "content": final_answer})
        return {"messages": messages}

    def route_after_planner(self, state: AgentState) -> str:
        return NodeName.EXECUTOR if state.get("pending_tool_code") else NodeName.OUTPUT

