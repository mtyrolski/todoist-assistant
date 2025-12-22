import json
from collections.abc import Sequence
from pathlib import Path
from typing import TypeVar, cast

from pydantic import BaseModel

from todoist.agent.constants import PlannerAction
from todoist.agent.graph import AgentState, InstructionSelection, PlannerDecision, build_agent_graph


T = TypeVar("T", bound=BaseModel)


class FakeLLM:
    def __init__(self) -> None:
        self.planner_calls = 0

    def structured_chat(
        self,
        messages: Sequence[dict[str, str]],
        schema: type[T],
    ) -> T:
        _ = messages
        if schema is InstructionSelection:
            return cast(T, InstructionSelection(selected_ids=["analysis"]))
        if schema is PlannerDecision:
            self.planner_calls += 1
            if self.planner_calls == 1:
                return cast(
                    T,
                    PlannerDecision(plan=["compute"], action=PlannerAction.TOOL, tool_code="1+1", final_answer=None),
                )
            return cast(
                T,
                PlannerDecision(plan=["answer"], action=PlannerAction.FINAL, tool_code=None, final_answer="done"),
            )
        raise AssertionError(f"Unexpected schema: {schema}")


class FakePythonTool:
    def run(self, code: str) -> str:
        if code.strip() == "1+1":
            return "2"
        return "unexpected"


def test_graph_runs_tool_then_outputs(tmp_path: Path):
    prefabs_dir = tmp_path / "prefabs"
    prefabs_dir.mkdir()
    (prefabs_dir / "analysis.yml").write_text(
        "description: analysis helper\ncontent: use pandas for computations\n",
        encoding="utf-8",
    )

    graph = build_agent_graph(llm=FakeLLM(), python_repl=FakePythonTool(), prefabs_dir=prefabs_dir, max_tool_loops=3)
    state: AgentState = {"messages": [{"role": "user", "content": "please do analysis"}]}
    out = graph.invoke(state)

    assert out["selected_prefab_ids"] == ["analysis"]
    assert out["tool_steps"] == 1
    assert out["final_answer"] == "done"
    assert out["messages"][-1]["role"] == "assistant"
    assert out["messages"][-1]["content"] == "done"
    assert any(m["role"] == "assistant" and "Calling python_repl" in m["content"] for m in out["messages"])
    assert any(m["role"] == "user" and "python_repl output" in m["content"] for m in out["messages"])


def test_planner_decision_normalizes_log_like_output():
    raw = json.dumps(
        {
            "plan": [],
            "action": "tool",
            "tool_code": None,
            "final_answer": {
                "role": "system",
                "message": "I am a read-only Todoist activity analyzer.",
            },
        },
        ensure_ascii=False,
    )
    parsed = PlannerDecision.model_validate_json(raw)
    assert parsed.action == PlannerAction.FINAL
    assert parsed.tool_code is None
    assert parsed.final_answer == "I am a read-only Todoist activity analyzer."


def test_graph_calls_instruction_selection_for_meta_query(tmp_path: Path):
    prefabs_dir = tmp_path / "prefabs"
    prefabs_dir.mkdir()
    (prefabs_dir / "status_update.yml").write_text(
        "description: Status update for a project\ncontent: status update instructions\n",
        encoding="utf-8",
    )

    class PlannerOnlyLLM:
        def __init__(self) -> None:
            self.selection_calls = 0

        def structured_chat(
            self,
            messages: Sequence[dict[str, str]],
            schema: type[T],
        ) -> T:
            _ = messages
            if schema is InstructionSelection:
                self.selection_calls += 1
                return cast(T, InstructionSelection(selected_ids=[]))
            if schema is PlannerDecision:
                return cast(T, PlannerDecision(action=PlannerAction.FINAL, final_answer="hello", plan=[]))
            raise AssertionError(f"Unexpected schema: {schema}")

    llm = PlannerOnlyLLM()
    graph = build_agent_graph(llm=llm, python_repl=FakePythonTool(), prefabs_dir=prefabs_dir, max_tool_loops=1)
    out = graph.invoke(cast(AgentState, {"messages": [{"role": "user", "content": "hi, who are you"}]}))
    assert llm.selection_calls == 1
    assert out["selected_prefab_ids"] == []
    assert out["final_answer"] == "hello"


def test_graph_clears_bad_selection_for_meta_query(tmp_path: Path):
    prefabs_dir = tmp_path / "prefabs"
    prefabs_dir.mkdir()
    (prefabs_dir / "status_update.yml").write_text(
        "description: Status update for a project\ncontent: status update instructions\n",
        encoding="utf-8",
    )

    class BadSelectorLLM:
        def structured_chat(
            self,
            messages: Sequence[dict[str, str]],
            schema: type[T],
        ) -> T:
            _ = messages
            if schema is InstructionSelection:
                return cast(T, InstructionSelection(selected_ids=["status_update"]))
            if schema is PlannerDecision:
                return cast(T, PlannerDecision(action=PlannerAction.FINAL, final_answer="hello", plan=[]))
            raise AssertionError(f"Unexpected schema: {schema}")

    graph = build_agent_graph(llm=BadSelectorLLM(), python_repl=FakePythonTool(), prefabs_dir=prefabs_dir, max_tool_loops=1)
    out = graph.invoke(cast(AgentState, {"messages": [{"role": "user", "content": "hi, who are you"}]}))
    assert out["selected_prefab_ids"] == []
