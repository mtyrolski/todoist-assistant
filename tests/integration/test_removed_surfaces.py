"""Check that removed product entry points stay unavailable."""

from importlib.util import find_spec
from pathlib import Path
import re

from fastapi.testclient import TestClient

from todometry.database.db_tasks import DatabaseTasks
from todometry.web.api import app


ROOT = Path(__file__).resolve().parents[2]


def test_removed_task_import_and_multiplication_entry_points_are_absent():
    assert find_spec("todometry.features.task_tree_import") is None
    assert not hasattr(DatabaseTasks, "insert_task_from_template")
    assert not hasattr(DatabaseTasks, "insert_tasks_from_templates")
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
