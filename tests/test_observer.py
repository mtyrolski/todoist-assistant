import datetime as dt
from pathlib import Path
from typing import cast

# pylint: disable=protected-access

from todoist.automations.activity import Activity
from todoist.automations.base import Automation
from todoist.automations.observer import AutomationObserver
from todoist.database.base import Database
from todoist.types import Event, EventEntry


def _event(event_id: str, event_type: str = "added") -> Event:
    entry = EventEntry(
        id=event_id,
        object_type="item",
        object_id=event_id,
        event_type=event_type,
        event_date="2024-01-01T00:00:00Z",
        parent_project_id="p",
        parent_item_id=event_id,
        initiator_id="user",
        extra_data={},
        extra_data_id=None,
        v2_object_id=None,
        v2_parent_item_id=None,
        v2_parent_project_id=None,
        new_api_kwargs=None,
    )
    return Event(event_entry=entry, id=event_id, date=dt.datetime(2024, 1, 1))


class _StubDb:
    def __init__(self):
        self.reset_calls = 0

    def reset(self):
        self.reset_calls += 1


class _StubAutomation(Automation):
    def __init__(self, name: str):
        super().__init__(name, frequency=0)
        self.tick_calls: list[Database] = []

    def _tick(self, db: Database):
        self.tick_calls.append(db)


class _StubActivity(Activity):
    def __init__(self, events, stats):
        super().__init__("Activity Fetching Automation", 1, 1)
        self._events = events
        self._stats = stats
        self.calls: list[int] = []

    def fetch_recent_events(self, db, *, max_pages: int = 1):
        self.calls.append(max_pages)
        return self._events, self._stats


def test_observer_runs_automations_on_new_events(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    events = [_event("1", "added")]
    db = _StubDb()
    activity = _StubActivity(events, {"total": 1, "added": 1})
    automation = _StubAutomation("Auto")

    observer = AutomationObserver(db=cast(Database, db), automations=[automation], activity=activity)
    observer._run_once()

    assert db.reset_calls == 1
    assert len(automation.tick_calls) == 1
    # Cache should contain the event now
    from todoist.utils import Cache
    cached = Cache().activity.load()
    assert len(cached) == 1

    # Running again with the same events should not trigger automations
    observer._run_once()
    assert db.reset_calls == 1  # unchanged
    assert len(automation.tick_calls) == 1


def test_observer_no_new_events_noop(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = _StubDb()
    activity = _StubActivity([], {"total": 0})
    automation = _StubAutomation("Auto")

    observer = AutomationObserver(db=cast(Database, db), automations=[automation], activity=activity)
    observer._run_once()

    assert db.reset_calls == 0
    assert len(automation.tick_calls) == 0


def test_observer_recovers_from_corrupted_cache(tmp_path: Path, monkeypatch):
    from todoist.utils import LocalStorageError

    monkeypatch.chdir(tmp_path)

    class _BrokenStorage:
        def __init__(self):
            self.saved = None

        def load(self):
            raise LocalStorageError("corrupted")

        def save(self, data):
            self.saved = data

    class _FakeCache:
        def __init__(self):
            self.activity = _BrokenStorage()

    monkeypatch.setattr("todoist.automations.observer.automation.Cache", _FakeCache)

    events = [_event("99", "added")]
    db = _StubDb()
    activity = _StubActivity(events, {"total": 1, "added": 1})
    automation = _StubAutomation("Auto")

    observer = AutomationObserver(db=cast(Database, db), automations=[automation], activity=activity)
    observer._run_once()

    # Should still process despite corrupted cache
    assert db.reset_calls == 1
    assert len(automation.tick_calls) == 1
