"""Small helpers for the agent graph."""

from __future__ import annotations

from collections.abc import Sequence

from todoist.agent.constants import PLANNER_PROMPT, SYSTEM_PROMPT, TOOL_PROMPT


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
    """Build a single system prompt with tool + instruction context."""

    system_parts = [SYSTEM_PROMPT, TOOL_PROMPT]
    if prefab_contents:
        system_parts.append("Prefabs:\n" + "\n---\n".join(prefab_contents))
    system_parts.append(PLANNER_PROMPT)
    system_prompt = "\n".join(part for part in system_parts if part).strip()

    filtered = [msg for msg in messages if msg.get("role") != "system"]
    return [{"role": "system", "content": system_prompt}, *filtered]
