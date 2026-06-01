"""Default LangGraph node names."""

from enum import StrEnum


class GraphNodeName(StrEnum):
    INITIAL_PROMPT = "initial_prompt"
    SELECT_INSTRUCTIONS = "select_instructions"
    PLANNER = "planner"
    EXECUTOR = "executor"
    OUTPUT = "output"
