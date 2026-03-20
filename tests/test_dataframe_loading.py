import datetime as dt
from typing import cast

import todoist.database.dataframe as dataframe_module
from todoist.database.base import Database
from todoist.types import Event, EventEntry, Project, ProjectEntry


def _project(*, project_id: str, name: str, archived: bool) -> Project:
    entry = ProjectEntry(
        id=project_id,
        name=name,
        color="blue",
        parent_id=None,
        child_order=1,
        view_style="list",
        is_favorite=False,
        is_archived=archived,
        is_deleted=False,
        is_frozen=False,
        can_assign_tasks=True,
        shared=False,
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
        v2_id=project_id,
        v2_parent_id=None,
        sync_id=None,
        collapsed=False,
    )
    return Project(
        id=project_id,
        project_entry=entry,
        tasks=[],
        is_archived=archived,
    )


def test_load_activity_data_prefers_active_root_id_for_adjusted_target(monkeypatch) -> None:
    active_health = _project(project_id="active-health", name="Health", archived=False)
    archived_health = _project(project_id="archived-health", name="Health", archived=True)
    archived_old = _project(project_id="old-health", name="OldHealth", archived=True)

    event_entry = EventEntry(
        id="event-1",
        object_type="item",
        object_id="task-1",
        event_type="completed",
        event_date="2024-02-01T12:00:00Z",
        parent_project_id="old-health",
        parent_item_id="task-1",
        initiator_id="user-1",
        extra_data={"content": "Finish the thing"},
        extra_data_id="extra-1",
        v2_object_id="task-1",
        v2_parent_item_id="task-1",
        v2_parent_project_id="old-health",
    )
    event = Event(
        event_entry=event_entry,
        id="event-1",
        date=dt.datetime(2024, 2, 1, 12, 0, 0),
    )

    class _FakeCache:
        class _ActivityStore:
            @staticmethod
            def load():
                return {event}

        def __init__(self) -> None:
            self.activity = self._ActivityStore()

    class _FakeDatabase:
        @staticmethod
        def fetch_mapping_project_id_to_root():
            return {
                "old-health": archived_old,
                "active-health": active_health,
                "archived-health": archived_health,
            }

        @staticmethod
        def fetch_mapping_project_id_to_name():
            return {
                "old-health": "OldHealth",
                "active-health": "Health",
                "archived-health": "Health",
            }

        @staticmethod
        def fetch_projects(include_tasks: bool = False):
            _ = include_tasks
            return [active_health]

        @staticmethod
        def fetch_archived_projects():
            return [archived_health, archived_old]

    monkeypatch.setattr(dataframe_module, "Cache", _FakeCache)
    monkeypatch.setattr(
        dataframe_module,
        "get_adjusting_mapping",
        lambda specific_file=None: {"OldHealth": "Health"},
    )

    df = dataframe_module.load_activity_data(cast(Database, _FakeDatabase()))

    assert len(df) == 1
    assert df.iloc[0]["root_project_name"] == "Health"
    assert df.iloc[0]["root_project_id"] == "active-health"


def test_load_activity_data_keeps_original_root_id_for_ambiguous_adjusted_target(
    monkeypatch,
) -> None:
    archived_backlog_a = _project(
        project_id="archived-backlog-a", name="backlog", archived=True
    )
    archived_backlog_b = _project(
        project_id="archived-backlog-b", name="backlog", archived=True
    )
    archived_old = _project(project_id="old-project", name="OldRoot", archived=True)

    event_entry = EventEntry(
        id="event-2",
        object_type="item",
        object_id="task-2",
        event_type="completed",
        event_date="2024-03-01T12:00:00Z",
        parent_project_id="old-project",
        parent_item_id="task-2",
        initiator_id="user-1",
        extra_data={"content": "Finish another thing"},
        extra_data_id="extra-2",
        v2_object_id="task-2",
        v2_parent_item_id="task-2",
        v2_parent_project_id="old-project",
    )
    event = Event(
        event_entry=event_entry,
        id="event-2",
        date=dt.datetime(2024, 3, 1, 12, 0, 0),
    )

    class _FakeCache:
        class _ActivityStore:
            @staticmethod
            def load():
                return {event}

        def __init__(self) -> None:
            self.activity = self._ActivityStore()

    class _FakeDatabase:
        @staticmethod
        def fetch_mapping_project_id_to_root():
            return {
                "old-project": archived_old,
                "archived-backlog-a": archived_backlog_a,
                "archived-backlog-b": archived_backlog_b,
            }

        @staticmethod
        def fetch_mapping_project_id_to_name():
            return {
                "old-project": "OldRoot",
                "archived-backlog-a": "backlog",
                "archived-backlog-b": "backlog",
            }

        @staticmethod
        def fetch_projects(include_tasks: bool = False):
            _ = include_tasks
            return []

        @staticmethod
        def fetch_archived_projects():
            return [archived_backlog_a, archived_backlog_b, archived_old]

    monkeypatch.setattr(dataframe_module, "Cache", _FakeCache)
    monkeypatch.setattr(
        dataframe_module,
        "get_adjusting_mapping",
        lambda specific_file=None: {"OldRoot": "backlog"},
    )

    df = dataframe_module.load_activity_data(cast(Database, _FakeDatabase()))

    assert len(df) == 1
    assert df.iloc[0]["root_project_name"] == "backlog"
    assert df.iloc[0]["root_project_id"] == "old-project"
