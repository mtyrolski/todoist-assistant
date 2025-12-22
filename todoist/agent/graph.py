"""LangGraph agent builder for local, read-only Todoist analysis."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from langgraph.graph import END, StateGraph

from todoist.agent.constants import NodeName
from todoist.agent.nodes import (
    AgentNodes,
    AgentState,
    ChatModel,
    InstructionSelection,
    PlannerDecision,
    PythonReplTool,
)


@dataclass(frozen=True)
class TodoistAgentGraph:
    llm: ChatModel
    python_repl: PythonReplTool
    prefabs_dir: Path
    max_tool_loops: int

    def compile(self):
        nodes = AgentNodes(
            llm=self.llm,
            python_repl=self.python_repl,
            prefabs_root=self.prefabs_dir,
            max_tool_loops=self.max_tool_loops,
        )

        graph = StateGraph(AgentState)
        graph.add_node(NodeName.INITIAL_PROMPT, nodes.initial_prompt)
        graph.add_node(NodeName.SELECT_INSTRUCTIONS, nodes.select_instructions)
        graph.add_node(NodeName.PLANNER, nodes.planner)
        graph.add_node(NodeName.EXECUTOR, nodes.executor)
        graph.add_node(NodeName.OUTPUT, nodes.output)

        graph.set_entry_point(NodeName.INITIAL_PROMPT)
        graph.add_edge(NodeName.INITIAL_PROMPT, NodeName.SELECT_INSTRUCTIONS)
        graph.add_edge(NodeName.SELECT_INSTRUCTIONS, NodeName.PLANNER)
        graph.add_conditional_edges(
            NodeName.PLANNER,
            nodes.route_after_planner,
            {NodeName.EXECUTOR: NodeName.EXECUTOR, NodeName.OUTPUT: NodeName.OUTPUT},
        )
        graph.add_edge(NodeName.EXECUTOR, NodeName.PLANNER)
        graph.add_edge(NodeName.OUTPUT, END)

        return graph.compile()


def build_agent_graph(
    *,
    llm: ChatModel,
    python_repl: PythonReplTool,
    prefabs_dir: str | Path = "configs/agent_instructions",
    max_tool_loops: int = 8,
):
    return TodoistAgentGraph(
        llm=llm,
        python_repl=python_repl,
        prefabs_dir=Path(prefabs_dir),
        max_tool_loops=max_tool_loops,
    ).compile()


__all__ = [
    "AgentState",
    "InstructionSelection",
    "PlannerDecision",
    "TodoistAgentGraph",
    "build_agent_graph",
]
