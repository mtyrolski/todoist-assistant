from unittest.mock import MagicMock, patch

from tests.factories import make_project, make_project_entry
from tests.unit.database.helpers import project_payload
from todoist.api import TodoistEndpoints
from todoist.api.client import RequestSpec
from todoist.core.types import Project
from todoist.database.db_projects import DatabaseProjects


def _project(project_id: str, parent_id: str | None = None, *, archived: bool = False):
    return make_project(
        project_id=project_id,
        project_entry=make_project_entry(
            project_id=project_id, parent_id=parent_id, is_archived=archived
        ),
        is_archived=archived,
    )


def test_database_projects_initialization(db_projects):
    assert db_projects.archived_projects_cache is None
    assert db_projects.projects_cache is None
    assert db_projects.mapping_project_name_to_color is None


def test_anonymize_sub_db_rewrites_project_cache_and_colors(db_projects):
    root = make_project(
        project_id="root",
        project_entry=make_project_entry(project_id="root", name="Alpha"),
    )
    child = make_project(
        project_id="child",
        project_entry=make_project_entry(
            project_id="child",
            name="Alpha Child",
            parent_id="root",
        ),
    )
    db_projects.projects_cache = [root, child]
    db_projects.archived_projects_cache = {}
    db_projects.mapping_project_name_to_color = {
        "Alpha": "red",
        "Alpha Child": "blue",
    }

    DatabaseProjects.anonymize_sub_db(
        db_projects,
        {
            "Alpha": "North Star Studio",
            "Alpha Child": "North Star Studio / Planning",
        },
    )

    assert [project.project_entry.name for project in db_projects.projects_cache] == [
        "North Star Studio",
        "North Star Studio / Planning",
    ]
    assert "Alpha" not in db_projects.mapping_project_name_to_color
    assert "Alpha Child" not in db_projects.mapping_project_name_to_color
    assert db_projects.mapping_project_name_to_color["North Star Studio"] == "red"
    assert (
        db_projects.mapping_project_name_to_color["North Star Studio / Planning"]
        == "blue"
    )


@patch("todoist.database.db_projects.TodoistAPIClient.request_json")
def test_fetch_archived_projects_caching(mock_request_json, db_projects):
    mock_request_json.return_value = {
        "results": [project_payload(name="Archived Project", is_archived=True)],
        "next_cursor": None,
    }

    result1 = db_projects.fetch_archived_projects()
    assert len(result1) == 1
    assert result1[0].id == "12345"
    assert result1[0].is_archived is True
    mock_request_json.assert_called_once()
    spec_arg = mock_request_json.call_args.args[0]
    assert isinstance(spec_arg, RequestSpec)
    assert spec_arg.endpoint == TodoistEndpoints.LIST_ARCHIVED_PROJECTS

    mock_request_json.reset_mock()
    result2 = db_projects.fetch_archived_projects()

    assert result1 == result2
    mock_request_json.assert_not_called()


def test_reset_clears_caches(db_projects):
    db_projects.archived_projects_cache = {"test": "value"}
    db_projects.projects_cache = ["test"]

    with patch.object(db_projects, "pull"):
        db_projects.reset()

    assert db_projects.archived_projects_cache is None
    assert db_projects.projects_cache is None


@patch("todoist.database.db_projects.safe_instantiate_entry")
@patch("todoist.database.db_projects.TodoistAPIClient.request_json")
def test_fetch_project_by_id(mock_request_json, mock_safe_instantiate, db_projects):
    mock_request_json.return_value = project_payload()
    mock_project_entry = MagicMock()
    mock_project_entry.id = "12345"
    mock_safe_instantiate.return_value = mock_project_entry

    result = db_projects.fetch_project_by_id("12345")

    assert isinstance(result, Project)
    assert result.id == "12345"
    assert result.is_archived is False
    assert len(result.tasks) == 0
    mock_request_json.assert_called_once()
    spec_arg = mock_request_json.call_args.args[0]
    assert isinstance(spec_arg, RequestSpec)
    assert spec_arg.endpoint == TodoistEndpoints.GET_PROJECT.format(project_id="12345")


def test_fetch_mapping_project_id_to_root_uses_in_memory_parent_links(db_projects):
    root = _project("root")
    child = _project("child", "root")
    grandchild = _project("grandchild", "child")
    archived_root = _project("archived_root", archived=True)
    archived_child = _project("archived_child", "archived_root", archived=True)

    with (
        patch.object(
            db_projects, "fetch_projects", return_value=[root, child, grandchild]
        ) as mock_fetch_projects,
        patch.object(
            db_projects,
            "fetch_archived_projects",
            return_value=[archived_root, archived_child],
        ) as mock_fetch_archived,
        patch.object(db_projects, "fetch_project_by_id") as mock_fetch_project_by_id,
    ):
        mapping = db_projects.fetch_mapping_project_id_to_root()

    assert mapping["root"].id == "root"
    assert mapping["child"].id == "root"
    assert mapping["grandchild"].id == "root"
    assert mapping["archived_root"].id == "archived_root"
    assert mapping["archived_child"].id == "archived_root"
    mock_fetch_projects.assert_called_once_with(include_tasks=False)
    mock_fetch_archived.assert_called_once()
    mock_fetch_project_by_id.assert_not_called()


def test_fetch_mapping_project_id_to_root_uses_cache_after_first_call(db_projects):
    root = _project("root")
    child = _project("child", "root")

    with (
        patch.object(
            db_projects, "fetch_projects", return_value=[root, child]
        ) as mock_fetch_projects,
        patch.object(
            db_projects, "fetch_archived_projects", return_value=[]
        ) as mock_fetch_archived,
    ):
        mapping_first = db_projects.fetch_mapping_project_id_to_root()
        mapping_second = db_projects.fetch_mapping_project_id_to_root()

    assert mapping_first["child"].id == "root"
    assert mapping_second["child"].id == "root"
    mock_fetch_projects.assert_called_once_with(include_tasks=False)
    mock_fetch_archived.assert_called_once()


def test_fetch_mapping_project_id_to_root_falls_back_only_for_missing_parent(
    db_projects,
):
    orphan = _project("orphan", "missing_parent")
    fetched_root = _project("remote_root")

    with (
        patch.object(db_projects, "fetch_projects", return_value=[orphan]),
        patch.object(db_projects, "fetch_archived_projects", return_value=[]),
        patch.object(
            db_projects, "fetch_project_by_id", return_value=fetched_root
        ) as mock_fetch_project_by_id,
    ):
        mapping = db_projects.fetch_mapping_project_id_to_root()

    assert mapping["orphan"].id == "remote_root"
    mock_fetch_project_by_id.assert_called_once_with("missing_parent", True)
