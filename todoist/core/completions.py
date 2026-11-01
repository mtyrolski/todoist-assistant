"""Project cached task events into effective completion history.

Undoing an ordinary task completion removes the
completion at its original timestamp, even across period boundaries. Recurring
tasks retain every occurrence; advancing/resetting them must not erase history.
The event cache itself is never changed.
"""

from collections.abc import Iterable
from datetime import timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from todoist.core.types import Event


def reconcile_completions(events: Iterable["Event"]) -> list["Event"]:
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
    recurring_ids = set()
    for event in ordered:
        extra = event.event_entry.extra_data or {}
        due = extra.get("due")
        if event.event_entry.object_type == "item" and (
            extra.get("is_recurring") is True
            or extra.get("sub_tasks_reset") is True
            or (isinstance(due, dict) and due.get("is_recurring") is True)
        ):
            recurring_ids.add(event.event_entry.object_id)

    outstanding: dict[str, list[str]] = {}
    cancelled: set[str] = set()
    for event in ordered:
        entry = event.event_entry
        if entry.object_type != "item" or entry.object_id in recurring_ids:
            continue
        if entry.event_type == "completed":
            outstanding.setdefault(entry.object_id, []).append(event.id)
        elif entry.event_type == "uncompleted":
            pending = outstanding.get(entry.object_id, [])
            if pending:
                cancelled.add(pending.pop())
    return [event for event in ordered if event.id not in cancelled]
