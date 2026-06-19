"""Agent constants and enums."""

from enum import StrEnum

from todoist.agent.graph_nodes.naming import GraphNodeName


NodeName = GraphNodeName


class PlannerAction(StrEnum):
    TOOL = "tool"
    FINAL = "final"


PYTHON_TOOL_NAME = "python_repl"

SYSTEM_PROMPT = (
    "You are a Codex-powered personal Todoist assistant. Answer productivity, "
    "status, planning, and task-ingest questions using local context and the "
    "Python tool when needed. Be brief, concrete, and explicit about assumptions. "
    "Draft Todoist task proposals in chat and iterate with the user before creation. "
    "Only create Todoist tasks when the user explicitly confirms the exact proposal."
)

TOOL_PROMPT = (
    f"Tool: {PYTHON_TOOL_NAME}. Use only when needed. Python only; no imports, direct files, or network. "
    "Activity data: events (tuple[Event]) and events_df. Event fields: id, date (datetime), event_type "
    "(added/updated/completed/deleted), name, event_entry{object_type,object_id,event_type,event_date,"
    "parent_project_id,parent_item_id,initiator_id,extra_data}. "
    "events_df index=datetime; columns: event_type,title,object_type,object_id,parent_project_id,parent_item_id,"
    "extra_data. Also available: pd, np. "
    "Approved helper functions: cache_summary(), load_cache(name), script_catalog(), "
    "run_script(name, args=None), llm_usage(), telemetry_status(), projects(), "
    "create_tasks(project_id, tasks, confirmation='CREATE_TODOIST_TASKS'). "
    "Use create_tasks only after explicit user confirmation; otherwise return or refine a proposal."
)

PLANNER_PROMPT = f"If you need {PYTHON_TOOL_NAME}, set action=tool; otherwise action=final. Keep plan empty unless useful."
