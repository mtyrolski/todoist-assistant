"""Project cached task events into effective completion history.

Undoing an ordinary task completion removes its contribution
to completion counts at its original timestamp, even across period boundaries. Recurring
tasks retain every occurrence; advancing/resetting them must not erase history.
The event cache itself is never changed.
"""

from collections.abc import Iterable
from datetime import timezone
from typing import TYPE_CHECKING

from pandas import DataFrame, Series

if TYPE_CHECKING:
    from todometry.core.types import Event


def completion_projection(events: Iterable["Event"]) -> tuple[list["Event"], set[str]]:
    ordered = sorted(
        {event.id: event for event in events}.values(),
        key=lambda event: (
            (
                event.date
                if event.date.tzinfo
                else event.date.replace(tzinfo=timezone.utc)
            ).timestamp(),
            event.id,
        ),
    )
    recurring: dict[str, bool] = {}
    outstanding: dict[str, list[str]] = {}
    cancelled: set[str] = set()
    for event in ordered:
        entry = event.event_entry
        if entry.object_type != "item":
            continue
        extra = entry.extra_data or {}
        due = extra.get("due")
        declared = extra.get("is_recurring")
        if not isinstance(declared, bool):
            declared = due.get("is_recurring") if isinstance(due, dict) else None
        if not isinstance(declared, bool) and extra.get("sub_tasks_reset") is True:
            declared = True
        if isinstance(declared, bool):
            if recurring.get(entry.object_id, False) != declared:
                outstanding.pop(entry.object_id, None)
            recurring[entry.object_id] = declared
        if recurring.get(entry.object_id, False):
            continue
        if entry.event_type == "completed":
            outstanding.setdefault(entry.object_id, []).append(event.id)
        elif entry.event_type == "uncompleted":
            pending = outstanding.get(entry.object_id, [])
            if pending:
                cancelled.add(pending.pop())
    return ordered, cancelled


def reconcile_completions(events: Iterable["Event"]) -> list["Event"]:
    ordered, cancelled = completion_projection(events)
    return [event for event in ordered if event.id not in cancelled]


def effective_completion_mask(frame: DataFrame, type_column: str = "type") -> Series:
    """Select effective completions, preserving raw actions for activity views."""
    mask = frame[type_column].eq("completed")
    if "completion_effective" in frame:
        mask = mask & frame["completion_effective"].fillna(True).astype(bool)
    return mask
