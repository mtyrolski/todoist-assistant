"""Agent constants and enums."""


from enum import StrEnum

from todoist.agent.graph_nodes.naming import GraphNodeName


NodeName = GraphNodeName


class PlannerAction(StrEnum):
    TOOL = "tool"
    FINAL = "final"


PYTHON_TOOL_NAME = "python_repl"

SYSTEM_PROMPT = (
    "You are a local, read-only Todoist activity analyst. No external calls or modifications. Be brief."
)

TOOL_PROMPT = (
    f"Tool: {PYTHON_TOOL_NAME}. Use only when needed. Python only; no imports, files, or network. "
    "Activity data: events (tuple[Event]) and events_df. Event fields: id, date (datetime), event_type "
    "(added/updated/completed/deleted), name, event_entry{object_type,object_id,event_type,event_date,"
    "parent_project_id,parent_item_id,initiator_id,extra_data}. "
    "events_df index=datetime; columns: event_type,title,object_type,object_id,parent_project_id,parent_item_id,"
    "extra_data. Also available: pd, np."
)

PLANNER_PROMPT = (
    f"If you need {PYTHON_TOOL_NAME}, set action=tool; otherwise action=final. Keep plan empty unless useful."
)
