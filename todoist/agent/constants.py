"""Agent constants and enums."""

from __future__ import annotations

from enum import StrEnum


class NodeName(StrEnum):
    INITIAL_PROMPT = "initial_prompt"
    SELECT_INSTRUCTIONS = "select_instructions"
    PLANNER = "planner"
    EXECUTOR = "executor"
    OUTPUT = "output"


class PlannerAction(StrEnum):
    TOOL = "tool"
    FINAL = "final"


PYTHON_TOOL_NAME = "python_repl"

SYSTEM_PROMPT = """You are a local, read-only Todoist activity analyst.

Rules:
- Do NOT modify files, tasks, projects, or caches.
- Do NOT call external services or the Todoist API.
- You may run read-only Python via the provided tool.
"""

TOOL_PROMPT = f"""Tool available: {PYTHON_TOOL_NAME}
- Provide Python code in `tool_code` when computation is required.
- The tool has read-only variables: events, events_df, pd, np.
"""

