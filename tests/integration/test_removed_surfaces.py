"""Check that removed product entry points stay unavailable."""

from importlib.util import find_spec
from pathlib import Path
import re

from fastapi.testclient import TestClient

from todometry.api.client import TodoistAPIClient
from todometry.database.base import Database
from todometry.web.api import app


ROOT = Path(__file__).resolve().parents[2]


def test_database_retains_activity_projects_and_labels_after_task_removal(tmp_path, monkeypatch):
    operations = []

    def empty_page(_client, spec, *, operation_name):
        operations.append(spec.endpoint.name)
        return {"results": [], "next_cursor": None}

    monkeypatch.setattr(TodoistAPIClient, "request_json", empty_page)
    database = Database(str(tmp_path / "missing.env"))
    assert database.list_labels() == []
    assert database.fetch_projects(include_tasks=False) == []
    assert database.fetch_activity(max_pages=1) == []
    assert operations == ["list_labels", "list_projects", "list_activity"]


def test_removed_task_import_and_multiplication_entry_points_are_absent():
    assert find_spec("todometry.features.task_tree_import") is None
    assert find_spec("todometry.database.db_tasks") is None
    assert not hasattr(Database, "insert_task")
    assert not hasattr(Database, "insert_task_from_template")
    assert not hasattr(Database, "insert_tasks_from_templates")
    assert not (ROOT / "scripts" / "create_task_tree.py").exists()
    assert not (ROOT / "frontend" / "app" / "multiplication" / "page.tsx").exists()
    with TestClient(app) as client:
        assert client.get("/api/admin/multiplication").status_code == 404


def test_container_distribution_is_not_offered():
    assert not (ROOT / "Dockerfile.api").exists()
    assert not (ROOT / "compose.yaml").exists()
    assert not (ROOT / ".github" / "workflows" / "docker-image.yml").exists()
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert not re.search(r"^docker[_-][\w-]*\s*:", makefile, re.MULTILINE)
