import datetime as dt
from typing import cast

import pytest

import todoist.database.dataframe as dataframe_module
from todoist.database.base import Database
from todoist.types import Event, EventEntry, Project, ProjectEntry


def _project(
    *, project_id: str, name: str, archived: bool, parent_id: str | None = None
) -> Project:
    entry = ProjectEntry(
        id=project_id,
        name=name,
        color="blue",
        parent_id=parent_id,
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
        v2_parent_id=parent_id,
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
    monkeypatch.setattr(
        dataframe_module,
        "get_adjusting_archived_parent_projects",
        lambda specific_file=None: set(),
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
    monkeypatch.setattr(
        dataframe_module,
        "get_adjusting_archived_parent_projects",
        lambda specific_file=None: set(),
    )

    df = dataframe_module.load_activity_data(cast(Database, _FakeDatabase()))

    assert len(df) == 1
    assert df.iloc[0]["root_project_name"] == "backlog"
    assert df.iloc[0]["root_project_id"] == "old-project"


def test_load_activity_data_maps_archived_child_to_promoted_parent(
    monkeypatch,
) -> None:
    archived_root = _project(project_id="archived-root", name="OldRoot", archived=True)
    deepflare = _project(
        project_id="deepflare",
        name="Deepflare",
        archived=True,
        parent_id="archived-root",
    )
    deepflare_child = _project(
        project_id="deepflare-child",
        name="Deepflare Child",
        archived=True,
        parent_id="deepflare",
    )

    event_entry = EventEntry(
        id="event-3",
        object_type="item",
        object_id="task-3",
        event_type="completed",
        event_date="2023-03-01T12:00:00Z",
        parent_project_id="deepflare-child",
        parent_item_id="task-3",
        initiator_id="user-1",
        extra_data={"content": "Finish archived work"},
        extra_data_id="extra-3",
        v2_object_id="task-3",
        v2_parent_item_id="task-3",
        v2_parent_project_id="deepflare-child",
    )
    event = Event(
        event_entry=event_entry,
        id="event-3",
        date=dt.datetime(2023, 3, 1, 12, 0, 0),
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
                "archived-root": archived_root,
                "deepflare": archived_root,
                "deepflare-child": archived_root,
            }

        @staticmethod
        def fetch_mapping_project_id_to_name():
            return {
                "archived-root": "OldRoot",
                "deepflare": "Deepflare",
                "deepflare-child": "Deepflare Child",
            }

        @staticmethod
        def fetch_projects(include_tasks: bool = False):
            _ = include_tasks
            return []

        @staticmethod
        def fetch_archived_projects():
            return [archived_root, deepflare, deepflare_child]

    monkeypatch.setattr(dataframe_module, "Cache", _FakeCache)
    monkeypatch.setattr(
        dataframe_module,
        "get_adjusting_mapping",
        lambda specific_file=None: {"Deepflare Child": "Deepflare"},
    )
    monkeypatch.setattr(
        dataframe_module,
        "get_adjusting_archived_parent_projects",
        lambda specific_file=None: {"Deepflare"},
    )

    df = dataframe_module.load_activity_data(cast(Database, _FakeDatabase()))

    assert len(df) == 1
    assert df.iloc[0]["root_project_name"] == "Deepflare"
    assert df.iloc[0]["root_project_id"] == "deepflare"


def test_load_activity_data_uses_promoted_parent_for_direct_archived_tasks(
    monkeypatch,
) -> None:
    archived_root = _project(project_id="archived-root", name="OldRoot", archived=True)
    deepflare = _project(
        project_id="deepflare",
        name="Deepflare",
        archived=True,
        parent_id="archived-root",
    )

    event_entry = EventEntry(
        id="event-4",
        object_type="item",
        object_id="task-4",
        event_type="completed",
        event_date="2023-04-01T12:00:00Z",
        parent_project_id="deepflare",
        parent_item_id="task-4",
        initiator_id="user-1",
        extra_data={"content": "Finish direct archived work"},
        extra_data_id="extra-4",
        v2_object_id="task-4",
        v2_parent_item_id="task-4",
        v2_parent_project_id="deepflare",
    )
    event = Event(
        event_entry=event_entry,
        id="event-4",
        date=dt.datetime(2023, 4, 1, 12, 0, 0),
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
                "archived-root": archived_root,
                "deepflare": archived_root,
            }

        @staticmethod
        def fetch_mapping_project_id_to_name():
            return {
                "archived-root": "OldRoot",
                "deepflare": "Deepflare",
            }

        @staticmethod
        def fetch_projects(include_tasks: bool = False):
            _ = include_tasks
            return []

        @staticmethod
        def fetch_archived_projects():
            return [archived_root, deepflare]

    monkeypatch.setattr(dataframe_module, "Cache", _FakeCache)
    monkeypatch.setattr(
        dataframe_module,
        "get_adjusting_mapping",
        lambda specific_file=None: {},
    )
    monkeypatch.setattr(
        dataframe_module,
        "get_adjusting_archived_parent_projects",
        lambda specific_file=None: {"Deepflare"},
    )

    df = dataframe_module.load_activity_data(cast(Database, _FakeDatabase()))

    assert len(df) == 1
    assert df.iloc[0]["root_project_name"] == "Deepflare"
    assert df.iloc[0]["root_project_id"] == "deepflare"


def test_load_activity_data_maps_archived_descendant_via_ancestor_adjustment(
    monkeypatch,
) -> None:
    archived_root = _project(project_id="archived-root", name="OldRoot", archived=True)
    deepflare = _project(
        project_id="deepflare",
        name="DeepFlare",
        archived=True,
        parent_id="archived-root",
    )
    experiment = _project(
        project_id="experiment",
        name="HLA-BERT2",
        archived=True,
        parent_id="deepflare",
    )
    experiment_child = _project(
        project_id="experiment-child",
        name="Evaluation",
        archived=True,
        parent_id="experiment",
    )

    event_entry = EventEntry(
        id="event-5",
        object_type="item",
        object_id="task-5",
        event_type="completed",
        event_date="2023-05-01T12:00:00Z",
        parent_project_id="experiment-child",
        parent_item_id="task-5",
        initiator_id="user-1",
        extra_data={"content": "Finish descendant work"},
        extra_data_id="extra-5",
        v2_object_id="task-5",
        v2_parent_item_id="task-5",
        v2_parent_project_id="experiment-child",
    )
    event = Event(
        event_entry=event_entry,
        id="event-5",
        date=dt.datetime(2023, 5, 1, 12, 0, 0),
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
                "archived-root": archived_root,
                "deepflare": archived_root,
                "experiment": archived_root,
                "experiment-child": archived_root,
            }

        @staticmethod
        def fetch_mapping_project_id_to_name():
            return {
                "archived-root": "OldRoot",
                "deepflare": "DeepFlare",
                "experiment": "HLA-BERT2",
                "experiment-child": "Evaluation",
            }

        @staticmethod
        def fetch_projects(include_tasks: bool = False):
            _ = include_tasks
            return []

        @staticmethod
        def fetch_archived_projects():
            return [archived_root, deepflare, experiment, experiment_child]

    monkeypatch.setattr(dataframe_module, "Cache", _FakeCache)
    monkeypatch.setattr(
        dataframe_module,
        "get_adjusting_mapping",
        lambda specific_file=None: {"DeepFlare": "deepflare"},
    )
    monkeypatch.setattr(
        dataframe_module,
        "get_adjusting_archived_parent_projects",
        lambda specific_file=None: {"deepflare"},
    )

    df = dataframe_module.load_activity_data(cast(Database, _FakeDatabase()))

    assert len(df) == 1
    assert df.iloc[0]["root_project_name"] == "deepflare"


def test_load_activity_data_does_not_map_active_child_via_archived_adjustment(
    monkeypatch,
) -> None:
    academy = _project(project_id="academy", name="Academy", archived=False)
    deep_mhc_flare = _project(
        project_id="deep-mhc-flare",
        name="DeepMhcFlare",
        archived=False,
        parent_id="academy",
    )
    deepflare_archive = _project(
        project_id="deepflare",
        name="deepflare",
        archived=True,
    )

    event_entry = EventEntry(
        id="event-6",
        object_type="item",
        object_id="task-6",
        event_type="completed",
        event_date="2026-02-01T12:00:00Z",
        parent_project_id="deep-mhc-flare",
        parent_item_id="task-6",
        initiator_id="user-1",
        extra_data={"content": "Finish current work"},
        extra_data_id="extra-6",
        v2_object_id="task-6",
        v2_parent_item_id="task-6",
        v2_parent_project_id="deep-mhc-flare",
    )
    event = Event(
        event_entry=event_entry,
        id="event-6",
        date=dt.datetime(2026, 2, 1, 12, 0, 0),
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
                "academy": academy,
                "deep-mhc-flare": academy,
                "deepflare": deepflare_archive,
            }

        @staticmethod
        def fetch_mapping_project_id_to_name():
            return {
                "academy": "Academy",
                "deep-mhc-flare": "DeepMhcFlare",
                "deepflare": "deepflare",
            }

        @staticmethod
        def fetch_projects(include_tasks: bool = False):
            _ = include_tasks
            return [academy, deep_mhc_flare]

        @staticmethod
        def fetch_archived_projects():
            return [deepflare_archive]

    monkeypatch.setattr(dataframe_module, "Cache", _FakeCache)
    monkeypatch.setattr(
        dataframe_module,
        "get_adjusting_mapping",
        lambda specific_file=None: {"DeepMhcFlare": "deepflare"},
    )
    monkeypatch.setattr(
        dataframe_module,
        "get_adjusting_archived_parent_projects",
        lambda specific_file=None: {"deepflare"},
    )

    df = dataframe_module.load_activity_data(cast(Database, _FakeDatabase()))

    assert len(df) == 1
    assert df.iloc[0]["root_project_name"] == "Academy"
    assert df.iloc[0]["root_project_id"] == "academy"


def test_get_adjusting_mapping_uses_env_personal_dir_and_safe_literals(
    monkeypatch, tmp_path
) -> None:
    personal_dir = tmp_path / "personal"
    personal_dir.mkdir()
    adjustment_file = personal_dir / "archived_root_projects.py"
    adjustment_file.write_text(
        dataframe_module.render_adjustments_file_content(
            {
                'Archived "Research"': "Academy / North Wing",
                "Line\nBreak": 'Target "Quoted"',
            },
            ['Parent "One"'],
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TODOIST_PERSONAL_DIR", str(personal_dir))

    mapping = dataframe_module.get_adjusting_mapping()

    assert mapping == {
        'Archived "Research"': "Academy / North Wing",
        "Line\nBreak": 'Target "Quoted"',
    }


def test_get_adjusting_mapping_rejects_non_literal_code(
    monkeypatch, tmp_path
) -> None:
    personal_dir = tmp_path / "personal"
    personal_dir.mkdir()
    evil_file = personal_dir / "evil.py"
    evil_file.write_text(
        '\n'.join(
            [
                'link_adjustements = {"Safe": "Target"}',
                'raise RuntimeError("boom")',
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TODOIST_PERSONAL_DIR", str(personal_dir))

    with pytest.raises(ValueError, match="literal assignments"):
        dataframe_module.get_adjusting_mapping("evil.py")
