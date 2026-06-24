import datetime as dt
from typing import Any

from todoist.core.types import Event, EventEntry


def event_payload(
    event_id: str,
    *,
    event_date: str = "2024-01-01T12:00:00Z",
    parent_project_id: str = "proj1",
    content: str | None = None,
) -> dict[str, Any]:
    return {
        "id": event_id,
        "object_type": "item",
        "object_id": event_id.replace("event", "task"),
        "event_type": "completed",
        "event_date": event_date,
        "parent_project_id": parent_project_id,
        "parent_item_id": None,
        "initiator_id": "user1",
        "extra_data": {"content": content or event_id},
        "extra_data_id": event_id.replace("event", "extra"),
        "v2_object_id": event_id.replace("event", "v2_task"),
        "v2_parent_item_id": None,
        "v2_parent_project_id": f"v2_{parent_project_id}",
    }


def make_event(
    event_id: str,
    *,
    date: dt.datetime | None = None,
    event_date: str = "2024-01-01T12:00:00Z",
    parent_project_id: str = "proj1",
    content: str | None = None,
) -> Event:
    return Event(
        event_entry=EventEntry(
            **event_payload(
                event_id,
                event_date=event_date,
                parent_project_id=parent_project_id,
                content=content,
            )
        ),
        id=event_id,
        date=date or dt.datetime(2024, 1, 1, 12, 0, 0),
    )


def project_payload(**overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": "12345",
        "name": "Test Project",
        "color": "blue",
        "parent_id": None,
        "child_order": 1,
        "view_style": "list",
        "is_favorite": False,
        "is_archived": False,
        "is_deleted": False,
        "is_frozen": False,
        "can_assign_tasks": True,
        "shared": False,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
        "v2_id": "v2_12345",
        "v2_parent_id": None,
        "sync_id": None,
        "collapsed": False,
    }
    payload.update(overrides)
    return payload
