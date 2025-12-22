"""LangGraph nodes and schemas for the local Todoist agent."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from collections.abc import Sequence
from typing import Protocol, Self, TypedDict, TypeVar

from loguru import logger
from pydantic import BaseModel, Field, field_validator, model_validator

from todoist.agent.constants import NodeName, PlannerAction
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
    def structured_chat(self, messages: Sequence[dict[str, str]], schema: type[T]) -> T:
        raise NotImplementedError


class PythonReplTool(Protocol):
    def run(self, code: str) -> str:
        raise NotImplementedError


def _is_greeting_or_meta_query(query: str) -> bool:
    normalized = (query or "").strip().lower()
    if not normalized:
        return True

    meta_phrases = (
        "who are you",
        "what are you",
        "what can you do",
        "what do you do",
    )
    if any(phrase in normalized for phrase in meta_phrases):
        return True

    greetings = ("hi", "hello", "hey", "help")
    if normalized in greetings:
        return True
    if normalized.startswith(("hi", "hello", "hey")) and len(normalized) <= 30:
        return True

    return False


def _strip_markdown_code_fence(text: str) -> str:
    stripped = (text or "").strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    lines = lines[1:] if lines else []
    while lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _normalize_text_field(value: object, *, dict_keys: Sequence[str]) -> str | None:
    if value is None:
        return None

    if isinstance(value, list):
        lines = [str(item).rstrip() for item in value if str(item).strip()]
        return "\n".join(lines).strip() or None

    if isinstance(value, dict):
        payload = {str(key): val for key, val in value.items()}
        for key in dict_keys:
            candidate = payload.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return _strip_markdown_code_fence(candidate)
        return json.dumps(payload, ensure_ascii=False)

    if isinstance(value, str):
        text = _strip_markdown_code_fence(value)
        return text or None

    return str(value).strip() or None


class InstructionSelection(BaseModel):
    selected_ids: list[str] = Field(default_factory=list)


class PlannerDecision(BaseModel):
    plan: list[str] = Field(default_factory=list)
    action: PlannerAction
    tool_code: str | None = None
    final_answer: str | None = None

    @field_validator("plan", mode="before")
    @classmethod
    def _normalize_plan(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            items: list[str] = []
            for line in value.splitlines():
                line = line.strip()
                if not line:
                    continue
                items.append(line.lstrip("-*• \t").strip())
            return items
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []

    @field_validator("tool_code", mode="before")
    @classmethod
    def _normalize_tool_code(cls, value: object) -> str | None:
        return _normalize_text_field(value, dict_keys=("tool_code", "code", "python", "content", "text"))

    @field_validator("final_answer", mode="before")
    @classmethod
    def _normalize_final_answer(cls, value: object) -> str | None:
        return _normalize_text_field(value, dict_keys=("final_answer", "message", "content", "text"))

    @model_validator(mode="after")
    def _reconcile_action_fields(self) -> Self:
        tool_code = (self.tool_code or "").strip()
        final_answer = (self.final_answer or "").strip()

        update: dict[str, object] = {}
        if self.action == PlannerAction.TOOL:
            if tool_code:
                if self.final_answer is not None:
                    update["final_answer"] = None
            elif final_answer:
                update.update({"action": PlannerAction.FINAL, "tool_code": None})
        else:
            if final_answer:
                if self.tool_code is not None:
                    update["tool_code"] = None
            elif tool_code:
                update.update({"action": PlannerAction.TOOL, "final_answer": None})

        return self.model_copy(update=update) if update else self


@dataclass(frozen=True)
class AgentNodes:
    llm: ChatModel
    python_repl: PythonReplTool
    prefabs_root: Path
    max_tool_loops: int

    def initial_prompt(self, state: AgentState) -> AgentState:
        messages = list(state.get("messages") or [])
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
                "content": "Pick prefab ids that help answer the query; otherwise use an empty list.",
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
        if selected_ids and _is_greeting_or_meta_query(query):
            logger.info("Clearing instruction selection for greeting/meta query: {}", query)
            selected_ids = []
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

        base_messages = build_planner_messages(messages, state.get("selected_prefab_contents") or [])
        try:
            decision = self.llm.structured_chat(base_messages, PlannerDecision)
        except ValueError as exc:
            logger.warning("Planner structured output failed: {}", exc)
            return {"final_answer": "I couldn't parse the model output. Please try again.", "pending_tool_code": None}

        logger.info("Planner action: {} plan_steps={}", decision.action, len(decision.plan))
        next_state: AgentState = {"plan": decision.plan, "pending_tool_code": None, "final_answer": None}

        tool_code = (decision.tool_code or "").strip()
        final_answer = (decision.final_answer or "").strip()

        if decision.action == PlannerAction.TOOL:
            if tool_code:
                next_state["pending_tool_code"] = tool_code
            elif final_answer:
                logger.warning("Planner returned action=tool without tool_code; using final_answer instead.")
                next_state["final_answer"] = final_answer
            else:
                logger.warning("Planner returned action=tool but tool_code/final_answer are empty.")
                next_state["final_answer"] = "I couldn't generate tool code for that request."
        elif final_answer:
            next_state["final_answer"] = final_answer
        elif tool_code:
            logger.warning("Planner returned action=final without final_answer; executing tool_code instead.")
            next_state["pending_tool_code"] = tool_code
        else:
            logger.warning("Planner returned action=final but final_answer/tool_code are empty.")
            next_state["final_answer"] = "I couldn't generate a complete response for that request."
        return next_state

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
