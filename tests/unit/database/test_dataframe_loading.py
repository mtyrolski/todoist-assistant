import datetime as dt
from collections.abc import Sequence
from typing import NamedTuple, cast

import pytest

import todoist.database.dataframe as dataframe_module
from tests.factories import make_project
from todoist.core.types import Event, EventEntry, Project
from todoist.database.base import Database


class ProjectSpec(NamedTuple):
    id: str
    name: str
    archived: bool
    parent_id: str | None = None
    root_id: str | None = None


class LoadCase(NamedTuple):
    projects: Sequence[ProjectSpec]
    event_project_id: str
    adjustments: dict[str, str]
    archived_parents: set[str]
    expected_name: str
    expected_id: str | None


def _project(spec: ProjectSpec) -> Project:
    return make_project(
        project_id=spec.id,
        name=spec.name,
        parent_id=spec.parent_id,
        v2_id=spec.id,
        v2_parent_id=spec.parent_id,
        is_archived=spec.archived,
    )


def _event(project_id: str) -> Event:
    return Event(
        event_entry=EventEntry(
            id=f"event-{project_id}",
            object_type="item",
            object_id=f"task-{project_id}",
            event_type="completed",
            event_date="2024-02-01T12:00:00Z",
            parent_project_id=project_id,
            parent_item_id=f"task-{project_id}",
            initiator_id="user-1",
            extra_data={"content": "Finish the thing"},
            extra_data_id=f"extra-{project_id}",
            v2_object_id=f"task-{project_id}",
            v2_parent_item_id=f"task-{project_id}",
            v2_parent_project_id=project_id,
        ),
        id=f"event-{project_id}",
        date=dt.datetime(2024, 2, 1, 12, 0, 0),
    )


def _load_activity_case(monkeypatch: pytest.MonkeyPatch, case: LoadCase):
    projects = {spec.id: _project(spec) for spec in case.projects}
    specs = {spec.id: spec for spec in case.projects}
    active = [project for spec, project in zip(case.projects, projects.values()) if not spec.archived]
    archived = [project for spec, project in zip(case.projects, projects.values()) if spec.archived]

    class _FakeCache:
        class _ActivityStore:
            @staticmethod
            def load():
                return {_event(case.event_project_id)}

        def __init__(self) -> None:
            self.activity = self._ActivityStore()

    class _FakeDatabase:
        @staticmethod
        def fetch_mapping_project_id_to_root():
            return {
                spec.id: projects[spec.root_id or spec.id]
                for spec in specs.values()
            }

        @staticmethod
        def fetch_mapping_project_id_to_name():
            return {spec.id: spec.name for spec in specs.values()}

        @staticmethod
        def fetch_projects(include_tasks: bool = False):
            _ = include_tasks
            return active

        @staticmethod
        def fetch_archived_projects():
            return archived

    monkeypatch.setattr(dataframe_module, "Cache", _FakeCache)
    monkeypatch.setattr(
        dataframe_module,
        "get_adjusting_mapping",
        lambda specific_file=None: case.adjustments,
    )
    monkeypatch.setattr(
        dataframe_module,
        "get_adjusting_archived_parent_projects",
        lambda specific_file=None: case.archived_parents,
    )
    return dataframe_module.load_activity_data(cast(Database, _FakeDatabase()))


@pytest.mark.parametrize(
    ("case"),
    [
        pytest.param(
            LoadCase(
                projects=[
                    ProjectSpec("old-health", "OldHealth", True),
                    ProjectSpec("active-health", "Health", False),
                    ProjectSpec("archived-health", "Health", True),
                ],
                event_project_id="old-health",
                adjustments={"OldHealth": "Health"},
                archived_parents=set(),
                expected_name="Health",
                expected_id="active-health",
            ),
            id="prefers-active-root-id-for-adjusted-target",
        ),
        pytest.param(
            LoadCase(
                projects=[
                    ProjectSpec("old-project", "OldRoot", True),
                    ProjectSpec("archived-backlog-a", "backlog", True),
                    ProjectSpec("archived-backlog-b", "backlog", True),
                ],
                event_project_id="old-project",
                adjustments={"OldRoot": "backlog"},
                archived_parents=set(),
                expected_name="backlog",
                expected_id="old-project",
            ),
            id="keeps-original-root-id-for-ambiguous-adjusted-target",
        ),
        pytest.param(
            LoadCase(
                projects=[
                    ProjectSpec("archived-root", "OldRoot", True),
                    ProjectSpec("deepflare", "Deepflare", True, "archived-root"),
                    ProjectSpec("deepflare-child", "Deepflare Child", True, "deepflare"),
                ],
                event_project_id="deepflare-child",
                adjustments={"Deepflare Child": "Deepflare"},
                archived_parents={"Deepflare"},
                expected_name="Deepflare",
                expected_id="deepflare",
            ),
            id="maps-archived-child-to-promoted-parent",
        ),
        pytest.param(
            LoadCase(
                projects=[
                    ProjectSpec("archived-root", "OldRoot", True),
                    ProjectSpec("deepflare", "Deepflare", True, "archived-root"),
                ],
                event_project_id="deepflare",
                adjustments={},
                archived_parents={"Deepflare"},
                expected_name="Deepflare",
                expected_id="deepflare",
            ),
            id="uses-promoted-parent-for-direct-archived-tasks",
        ),
        pytest.param(
            LoadCase(
                projects=[
                    ProjectSpec("archived-root", "OldRoot", True),
                    ProjectSpec("deepflare", "DeepFlare", True, "archived-root"),
                    ProjectSpec("experiment", "HLA-BERT2", True, "deepflare"),
                    ProjectSpec("experiment-child", "Evaluation", True, "experiment"),
                ],
                event_project_id="experiment-child",
                adjustments={"DeepFlare": "deepflare"},
                archived_parents={"deepflare"},
                expected_name="deepflare",
                expected_id=None,
            ),
            id="maps-archived-descendant-via-ancestor-adjustment",
        ),
        pytest.param(
            LoadCase(
                projects=[
                    ProjectSpec("academy", "Academy", False),
                    ProjectSpec("deep-mhc-flare", "DeepMhcFlare", False, "academy", "academy"),
                    ProjectSpec("deepflare", "deepflare", True),
                ],
                event_project_id="deep-mhc-flare",
                adjustments={"DeepMhcFlare": "deepflare"},
                archived_parents={"deepflare"},
                expected_name="Academy",
                expected_id="academy",
            ),
            id="does-not-map-active-child-via-archived-adjustment",
        ),
    ],
)
def test_load_activity_data_root_adjustments(
    monkeypatch: pytest.MonkeyPatch, case: LoadCase
) -> None:
    df = _load_activity_case(monkeypatch, case)

    assert len(df) == 1
    assert df.iloc[0]["root_project_name"] == case.expected_name
    if case.expected_id is not None:
        assert df.iloc[0]["root_project_id"] == case.expected_id


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


def test_get_adjusting_mapping_rejects_non_literal_code(monkeypatch, tmp_path) -> None:
    personal_dir = tmp_path / "personal"
    personal_dir.mkdir()
    evil_file = personal_dir / "evil.py"
    evil_file.write_text(
        "\n".join(
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
