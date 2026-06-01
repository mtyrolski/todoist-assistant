"""LangGraph agent builder for local, read-only Todoist analysis."""


from dataclasses import dataclass
from pathlib import Path

from langgraph.graph import END, StateGraph

from todoist.agent.graph_nodes.naming import GraphNodeName
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
        graph.add_node(GraphNodeName.INITIAL_PROMPT, nodes.initial_prompt)
        graph.add_node(GraphNodeName.SELECT_INSTRUCTIONS, nodes.select_instructions)
        graph.add_node(GraphNodeName.PLANNER, nodes.planner)
        graph.add_node(GraphNodeName.EXECUTOR, nodes.executor)
        graph.add_node(GraphNodeName.OUTPUT, nodes.output)

        graph.set_entry_point(GraphNodeName.INITIAL_PROMPT)
        graph.add_edge(GraphNodeName.INITIAL_PROMPT, GraphNodeName.SELECT_INSTRUCTIONS)
        graph.add_edge(GraphNodeName.SELECT_INSTRUCTIONS, GraphNodeName.PLANNER)
        graph.add_conditional_edges(
            GraphNodeName.PLANNER,
            nodes.route_after_planner,
            {
                GraphNodeName.EXECUTOR: GraphNodeName.EXECUTOR,
                GraphNodeName.OUTPUT: GraphNodeName.OUTPUT,
            },
        )
        graph.add_edge(GraphNodeName.EXECUTOR, GraphNodeName.PLANNER)
        graph.add_edge(GraphNodeName.OUTPUT, END)

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
