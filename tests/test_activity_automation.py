from datetime import datetime

from todoist.automations.activity import Activity
from todoist.types import Event, EventEntry


def _build_event(event_id: str, event_type: str, date_str: str) -> Event:
    entry = EventEntry(
        id=event_id,
        object_type="item",
        object_id=event_id,
        event_type=event_type,
        event_date=date_str,
        parent_project_id="proj",
        parent_item_id=event_id,
        initiator_id="user",
        extra_data={},
        extra_data_id=None,
        v2_object_id=None,
        v2_parent_item_id=None,
        v2_parent_project_id=None,
        new_api_kwargs=None,
    )
    return Event(event_entry=entry, id=event_id, date=datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ"))


class _FakeDb:
    def __init__(self, events: list[Event]):
        self.events = events
        self.requested_pages: list[int] = []

    def fetch_activity(self, max_pages: int = 1):
        self.requested_pages.append(max_pages)
        return self.events


def test_activity_fetch_recent_events_returns_stats():
    events = [
        _build_event("1", "added", "2024-01-01T00:00:00Z"),
        _build_event("2", "updated", "2024-01-01T01:00:00Z"),
        _build_event("3", "completed", "2024-01-01T02:00:00Z"),
    ]
    activity = Activity(name="Activity Fetching Automation", nweeks_window_size=1, early_stop_after_n_windows=1)
    db = _FakeDb(events)

    result_events, stats = activity.fetch_recent_events(db, max_pages=2)

    assert result_events == events
    assert stats["total"] == 3
    assert stats["added"] == 1
    assert stats["updated"] == 1
    assert stats["completed"] == 1
    assert db.requested_pages == [2]
