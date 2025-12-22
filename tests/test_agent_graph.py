from pathlib import Path

from todoist.agent.graph import InstructionSelection, PlannerDecision, build_agent_graph


class FakeLLM:
    def __init__(self) -> None:
        self.planner_calls = 0

    def structured_chat(self, _messages, schema):
        if schema is InstructionSelection:
            return InstructionSelection(selected_ids=["analysis"])
        if schema is PlannerDecision:
            self.planner_calls += 1
            if self.planner_calls == 1:
                return PlannerDecision(plan=["compute"], action="tool", tool_code="1+1", final_answer=None)
            return PlannerDecision(plan=["answer"], action="final", tool_code=None, final_answer="done")
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
    state = {"messages": [{"role": "user", "content": "hi"}]}
    out = graph.invoke(state)

    assert out["selected_prefab_ids"] == ["analysis"]
    assert out["tool_steps"] == 1
    assert out["final_answer"] == "done"
    assert out["messages"][-1]["role"] == "assistant"
    assert out["messages"][-1]["content"] == "done"
    assert any(m["role"] == "assistant" and "Calling python_repl" in m["content"] for m in out["messages"])
    assert any(m["role"] == "user" and "python_repl output" in m["content"] for m in out["messages"])
