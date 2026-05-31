from datetime import datetime
from typing import cast

# pylint: disable=protected-access

from todoist.automations.activity import Activity
from todoist.database.base import Database
from todoist.types import Event, EventEntry
from todoist.utils import Cache


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

    result_events, stats = activity.fetch_recent_events(cast(Database, db), max_pages=2)

    assert result_events == events
    assert stats["total"] == 3
    assert stats["added"] == 1
    assert stats["updated"] == 1
    assert stats["completed"] == 1
    assert db.requested_pages == [2]


def test_activity_tick_persists_cache_and_summarizes(tmp_path, monkeypatch):
    """_tick should persist new events and only mark delta events as new on subsequent runs."""
    monkeypatch.chdir(tmp_path)

    events = [
        _build_event("1", "added", "2024-01-01T00:00:00Z"),
        _build_event("2", "completed", "2024-01-02T00:00:00Z"),
    ]

    summary_calls: list[tuple[set[Event], set[Event]]] = []

    def _fake_summary(*, events: set[Event], new_events: set[Event]):
        summary_calls.append((events, new_events))

    monkeypatch.setattr("todoist.automations.activity.automation.quick_summarize", _fake_summary)

    class _FakeDb:
        def __init__(self, events_to_return: list[Event]):
            self.events_to_return = events_to_return
            self.calls: list[tuple[int, int]] = []

        def fetch_activity_adaptively(self, *, nweeks_window_size, early_stop_after_n_windows, events_already_fetched):
            _ = events_already_fetched
            self.calls.append((nweeks_window_size, early_stop_after_n_windows))
            return list(self.events_to_return)

    db = _FakeDb(events)
    activity = Activity(name="Activity Fetching Automation", nweeks_window_size=2, early_stop_after_n_windows=1)

    activity._tick(cast(Database, db))
    cached_after_first = Cache().activity.load()

    assert db.calls == [(2, 1)]
    assert cached_after_first == set(events)
    assert len(summary_calls) == 1
    assert summary_calls[0][0] == set(events)
    assert summary_calls[0][1] == set(events)  # all events are new on first run

    # Second run with same events should treat them as already known
    activity._tick(cast(Database, db))
    cached_after_second = Cache().activity.load()

    assert cached_after_second == set(events)
    assert len(summary_calls) == 2
    assert summary_calls[1][0] == set(events)
    assert summary_calls[1][1] == set()  # no delta events the second time
