"""Small helpers for the agent graph."""

from __future__ import annotations

from collections.abc import Sequence

from todoist.agent.constants import SYSTEM_PROMPT, TOOL_PROMPT


def last_user_text(messages: Sequence[dict[str, str]]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content")
            return content if isinstance(content, str) else ""
    return ""


def build_planner_messages(
    messages: Sequence[dict[str, str]],
    prefab_contents: Sequence[str],
) -> list[dict[str, str]]:
    """Insert tool + selected instruction context into the conversation."""

    result = list(messages)
    inserts: list[dict[str, str]] = [{"role": "system", "content": TOOL_PROMPT}]
    if prefab_contents:
        inserts.append({
            "role": "system",
            "content": "Selected instruction prefabs:\n" + "\n\n---\n\n".join(prefab_contents),
        })

    if result and result[0].get("role") == "system":
        result[1:1] = inserts
    else:
        result[0:0] = [{"role": "system", "content": SYSTEM_PROMPT}] + inserts
    return result

