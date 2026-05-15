"""Tests for FastAPI admin endpoints."""

import os
from datetime import datetime
from typing import cast
from unittest.mock import Mock

import pandas as pd
from fastapi.testclient import TestClient

from tests.factories import make_project, make_project_entry
import todoist.database.dataframe as dataframe_module
from todoist.utils import MaxRetriesExceeded
import todoist.web.api as web_api

# pylint: disable=protected-access


def test_admin_project_adjustments_exposes_remappable_active_roots(monkeypatch) -> None:
    monkeypatch.setattr(web_api, "_available_mapping_files", lambda: ["adj_private.py"])
    monkeypatch.setattr(
        web_api,
        "_load_mapping_file",
        lambda filename: ({"Archived Research": "Academy"}, []),
    )

    def _fake_projects_for_adjustments(refresh: bool):
        _ = refresh
        return (
            ["Academy", "Inbox", "skynet"],
            ["Archived Root"],
            ["Archived Research", "Archived Root"],
            ["Inbox"],
        )

    monkeypatch.setattr(
        web_api, "_load_projects_for_adjustments_sync", _fake_projects_for_adjustments
    )

    client = TestClient(web_api.app)
    res = client.get("/api/admin/project_adjustments")
    assert res.status_code == 200
    payload = res.json()

    assert payload["remappableActiveRootProjects"] == ["Inbox"]
    assert payload["sourceProjects"] == [
        "Archived Research",
        "Archived Root",
        "Inbox",
    ]
    assert payload["unmappedSourceProjects"] == ["Archived Root", "Inbox"]


def test_admin_project_adjustments_rejects_path_traversal(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TODOIST_PERSONAL_DIR", str(tmp_path / "personal"))
    client = TestClient(web_api.app)

    invalid = client.get("/api/admin/project_adjustments", params={"file": "../evil.py"})
    assert invalid.status_code == 400
    assert "path separators" in invalid.json()["detail"]

    saved = client.put(
        "/api/admin/project_adjustments",
        params={"file": "../evil.py"},
        json={"mappings": {}},
    )
    assert saved.status_code == 400
    assert "path separators" in saved.json()["detail"]

def test_admin_save_project_adjustments_roundtrips_safe_literals(
    monkeypatch, tmp_path
) -> None:
    personal_dir = tmp_path / "personal"
    monkeypatch.setenv("TODOIST_PERSONAL_DIR", str(personal_dir))
    monkeypatch.setattr(
        web_api,
        "_load_projects_for_adjustments_sync",
        lambda refresh: (
            ["Academy / North Wing"],
            ["Archived Root"],
            ['Archived "Research"', 'Parent "One"'],
            ["Inbox"],
        ),
    )
    client = TestClient(web_api.app)

    response = client.put(
        "/api/admin/project_adjustments",
        params={"file": "adj_private.py", "refresh": "false"},
        json={
            "mappings": {'Archived "Research"': "Academy / North Wing"},
            "archivedParents": ['Parent "One"'],
        },
    )
    assert response.status_code == 200
    assert response.json()["file"] == "adj_private.py"

    saved = (personal_dir / "adj_private.py").read_text(encoding="utf-8")
    assert "link_adjustements =" in saved
    assert "archived_parent_projects =" in saved

    loaded_mapping, archived_parents = dataframe_module.load_adjustments_file(
        personal_dir / "adj_private.py"
    )
    assert loaded_mapping == {'Archived "Research"': "Academy / North Wing"}
    assert archived_parents == ['Parent "One"']

def test_admin_save_project_adjustments_succeeds_when_refresh_fails(
    monkeypatch, tmp_path
) -> None:
    personal_dir = tmp_path / "personal"
    monkeypatch.setenv("TODOIST_PERSONAL_DIR", str(personal_dir))
    monkeypatch.setattr(
        web_api,
        "_load_projects_for_adjustments_sync",
        lambda refresh: (
            ["Academy"],
            ["Archived Root"],
            ["Archived Research"],
            ["Inbox"],
        ),
    )

    async def _boom(*, refresh: bool) -> None:
        _ = refresh
        raise MaxRetriesExceeded("Failed to execute list labels after 3 retry attempts")

    monkeypatch.setattr(web_api, "_ensure_state", _boom)

    client = TestClient(web_api.app)
    response = client.put(
        "/api/admin/project_adjustments",
        params={"file": "adj_private.py"},
        json={"mappings": {"Archived Research": "Academy"}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["saved"] is True
    assert payload["warning"] == "Saved, but dashboard refresh failed (MaxRetriesExceeded)."
    loaded_mapping, archived_parents = dataframe_module.load_adjustments_file(
        personal_dir / "adj_private.py"
    )
    assert loaded_mapping == {"Archived Research": "Academy"}
    assert archived_parents == []


def test_admin_save_project_adjustments_rejects_active_child_source(
    monkeypatch, tmp_path
) -> None:
    personal_dir = tmp_path / "personal"
    monkeypatch.setenv("TODOIST_PERSONAL_DIR", str(personal_dir))
    monkeypatch.setattr(
        web_api,
        "_load_projects_for_adjustments_sync",
        lambda refresh: (
            ["Academy"],
            ["deepflare"],
            ["deepflare"],
            ["Inbox"],
        ),
    )
    client = TestClient(web_api.app)

    response = client.put(
        "/api/admin/project_adjustments",
        params={"file": "adj_private.py", "refresh": "false"},
        json={"mappings": {"DeepMhcFlare": "deepflare"}},
    )

    assert response.status_code == 400
    assert "Mapping sources must be archived projects" in response.json()["detail"]


def test_admin_save_project_adjustments_rejects_active_archived_parent(
    monkeypatch, tmp_path
) -> None:
    personal_dir = tmp_path / "personal"
    monkeypatch.setenv("TODOIST_PERSONAL_DIR", str(personal_dir))
    monkeypatch.setattr(
        web_api,
        "_load_projects_for_adjustments_sync",
        lambda refresh: (
            ["Academy"],
            ["deepflare"],
            ["deepflare"],
            ["Inbox"],
        ),
    )
    client = TestClient(web_api.app)

    response = client.put(
        "/api/admin/project_adjustments",
        params={"file": "adj_private.py", "refresh": "false"},
        json={"mappings": {}, "archivedParents": ["DeepMhcFlare"]},
    )

    assert response.status_code == 400
    assert "archivedParents must contain archived projects only" in response.json()["detail"]


def test_admin_dashboard_settings_roundtrip(monkeypatch, tmp_path) -> None:
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    (config_dir / "dashboard.yaml").write_text(
        "urgency:\n  enabled: true\n  warn_priority_thresholds: [4, 3]\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(web_api, "_DASHBOARD_CONFIG_PATH", config_dir / "dashboard.yaml")

    client = TestClient(web_api.app)
    res = client.get("/api/admin/dashboard/settings")
    assert res.status_code == 200
    payload = res.json()
    assert payload["settings"]["enabled"] is True
    assert payload["editTargets"][0]["icon"] == "wrench"
    assert payload["settings"]["fireLabels"] == [web_api.DEFAULT_URGENCY_SETTINGS["fire_label"]]

    update = client.put(
        "/api/admin/dashboard/settings",
        json={
            "enabled": False,
            "fireLabels": ["fire 🧯🚒", "hot"],
            "warnPriorityThresholds": [4],
            "warnPriorityMinCount": 2,
            "warnDueWithinDays": 2,
            "warnDueMinCount": 3,
            "warnDeadlineMinCount": 2,
            "badgeLabels": {"warn": "Check"},
            "plotEvents": [
                {"date": "2025-01-05", "label": "Kickoff", "color": "#00ffaa"}
            ],
        },
    )
    assert update.status_code == 200
    updated = update.json()
    assert updated["settings"]["enabled"] is False
    assert updated["settings"]["fireLabels"] == ["fire 🧯🚒", "hot"]
    assert updated["settings"]["warnPriorityThresholds"] == [4]
    assert updated["settings"]["warnPriorityMinCount"] == 2
    assert updated["settings"]["warnDueWithinDays"] == 2
    assert updated["settings"]["warnDueMinCount"] == 3
    assert updated["settings"]["warnDeadlineMinCount"] == 2
    assert updated["settings"]["badgeLabels"]["warn"] == "Check"
    assert updated["settings"]["plotEvents"] == [
        {"date": "2025-01-05", "label": "Kickoff", "color": "#00ffaa"}
    ]

    saved_text = (config_dir / "dashboard.yaml").read_text(encoding="utf-8")
    assert "fire_labels:" in saved_text
    assert "- hot" in saved_text
    assert "warn_priority_min_count: 2" in saved_text
    assert "warn_due_within_days: 2" in saved_text
    assert "warn_due_min_count: 3" in saved_text
    assert "warn_deadline_min_count: 2" in saved_text
    assert "enabled: false" in saved_text
    assert "plot_events:" in saved_text
    assert "label: Kickoff" in saved_text

def test_admin_dashboard_labels_returns_sorted_local_labels(monkeypatch) -> None:
    class _FakeDatabase:
        def __init__(self, dotenv_path: str) -> None:
            _ = dotenv_path
            self._items = [{"name": "zeta", "color": "red"}, {"name": "alpha", "color": "blue"}]

        def fetch_label_colors(self) -> dict[str, str]:
            return {"alpha": "#0000ff", "zeta": "#ff0000"}

        def list_labels(self) -> list[dict[str, str]]:
            return list(self._items)

    monkeypatch.setattr(web_api, "Database", _FakeDatabase)

    client = TestClient(web_api.app)
    res = client.get("/api/admin/dashboard/labels")
    assert res.status_code == 200
    payload = res.json()
    assert payload["labels"] == [
        {"name": "alpha", "color": "#0000ff"},
        {"name": web_api.DEFAULT_URGENCY_SETTINGS["fire_label"], "color": None},
        {"name": "zeta", "color": "#ff0000"},
    ]

def test_admin_automations_returns_enabled_and_connection(monkeypatch) -> None:
    monkeypatch.setattr(
        web_api,
        "_load_automation_inventory",
        lambda: [
            {
                "key": "gmail_tasks",
                "name": "Gmail Tasks",
                "frequencyMinutes": 60,
                "isLong": False,
                "launchCount": 0,
                "lastLaunch": None,
                "enabled": False,
                "authRequired": True,
                "defaultEnabled": False,
                "target": "todoist.automations.gmail_tasks.GmailTasksAutomation",
                "connection": {
                    "credentialsPresent": False,
                    "tokenPresent": False,
                    "connected": False,
                    "credentialsPath": "gmail_credentials.json",
                    "tokenPath": "gmail_token.json",
                    "detail": "Missing Gmail credentials file",
                    "setupDocPath": "docs/gmail_setup.md",
                },
            }
        ],
    )

    client = TestClient(web_api.app)
    res = client.get("/api/admin/automations")

    assert res.status_code == 200
    payload = res.json()
    assert payload["automations"][0]["key"] == "gmail_tasks"
    assert payload["automations"][0]["enabled"] is False
    assert payload["automations"][0]["authRequired"] is True
    assert payload["automations"][0]["connection"]["connected"] is False

class _ApiStubAutomation(web_api.Automation):
    def __init__(self, name: str):
        super().__init__(name, frequency=15)

    def _tick(self, db):
        _ = db
        return []

class _ApiFailingAutomation(_ApiStubAutomation):
    def _tick(self, db):
        _ = db
        raise RuntimeError("boom")

def test_automation_launch_metadata_includes_run_signal(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(str(web_api.EnvVar.CACHE_DIR), str(tmp_path))
    cache = web_api.Cache()
    cache.automation_launches.save({"Signal Auto": [datetime(2026, 4, 18, 15, 0, 0)]})
    cache.automation_run_signals.save(
        {
            "Signal Auto": {
                "attemptCount": 3,
                "successCount": 2,
                "failureCount": 1,
                "skipCount": 0,
                "lastStatus": "failed",
                "lastStartedAt": "2026-04-18T15:01:00",
                "lastFinishedAt": "2026-04-18T15:01:02",
                "lastDurationSeconds": 2.0,
                "lastError": "RuntimeError: boom",
                "lastSuccessAt": "2026-04-18T14:59:59",
            }
        }
    )

    payload = web_api._automation_launch_metadata(_ApiStubAutomation("Signal Auto"))

    assert payload["launchCount"] == 1
    assert payload["lastLaunch"] == "2026-04-18T15:00:00"
    assert payload["lastStatus"] == "failed"
    assert payload["attemptCount"] == 3
    assert payload["successCount"] == 2
    assert payload["failureCount"] == 1
    assert payload["lastError"] == "RuntimeError: boom"

def test_run_all_automations_sync_continues_after_failure(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(str(web_api.EnvVar.CACHE_DIR), str(tmp_path))

    class _DbStub:
        def __init__(self) -> None:
            self.reset_calls = 0

        def reset(self) -> None:
            self.reset_calls += 1

    db = _DbStub()
    monkeypatch.setattr(
        web_api,
        "_load_automations",
        lambda: [_ApiFailingAutomation("broken"), _ApiStubAutomation("healthy")],
    )

    result = web_api._run_all_automations_sync(dbio=cast(web_api.Database, db))

    assert result["summary"] == {"completed": 1, "failed": 1, "skipped": 0}
    assert [item["name"] for item in result["results"]] == ["broken", "healthy"]
    assert result["results"][0]["status"] == "failed"
    assert result["results"][0]["error"] == "RuntimeError: boom"
    assert result["results"][1]["status"] == "completed"
    assert result["results"][1]["error"] is None
    assert db.reset_calls == 2

def test_enabled_automation_keys_defaults_non_auth_sections() -> None:
    config = {
        "activity": {"_target_": "todoist.automations.activity.Activity"},
        "gmail_tasks": {"_target_": "todoist.automations.gmail_tasks.GmailTasksAutomation"},
        "habit_tracker": {"_target_": "todoist.automations.habit_tracker.HabitTracker"},
    }

    assert web_api._enabled_automation_keys(config) == ["activity", "habit_tracker"]

def test_configured_enabled_automation_keys_supports_resolved_omegaconf_entries(tmp_path) -> None:
    config_path = tmp_path / "automations.yaml"
    config_path.write_text(
        "\n".join(
            [
                "defaults:",
                "  - _self_",
                "activity:",
                "  _target_: todoist.automations.activity.Activity",
                "gmail_tasks:",
                "  _target_: todoist.automations.gmail_tasks.GmailTasksAutomation",
                "habit_tracker:",
                "  _target_: todoist.automations.habit_tracker.HabitTracker",
                "automations:",
                "  - ${activity}",
                "  - ${gmail_tasks}",
            ]
        ),
        encoding="utf-8",
    )

    config = web_api._read_yaml_config(config_path)

    assert web_api._configured_enabled_automation_keys(config) == ["activity", "gmail_tasks"]

def test_admin_set_automation_enabled_updates_config(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "automations.yaml"
    config_path.write_text(
        "\n".join(
            [
                "defaults:",
                "  - _self_",
                "activity:",
                "  _target_: todoist.automations.activity.Activity",
                "  name: Activity Fetching Automation",
                "  early_stop_after_n_windows: 2",
                "  nweeks_window_size: 4",
                "gmail_tasks:",
                "  _target_: todoist.automations.gmail_tasks.GmailTasksAutomation",
                "  name: Gmail Tasks",
                "  frequency_in_minutes: 60",
                "automations:",
                "  - ${activity}",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(web_api, "_AUTOMATIONS_PATH", config_path)
    monkeypatch.setattr(web_api, "_CONFIG_DIR", tmp_path)

    client = TestClient(web_api.app)
    res = client.post("/api/admin/automations/gmail_tasks/enabled", json={"enabled": True})

    assert res.status_code == 200
    saved = config_path.read_text(encoding="utf-8")
    assert "- ${gmail_tasks}" in saved

def test_set_automation_enabled_disables_config_entry(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "automations.yaml"
    config_path.write_text(
        "\n".join(
            [
                "defaults:",
                "  - _self_",
                "activity:",
                "  _target_: todoist.automations.activity.Activity",
                "gmail_tasks:",
                "  _target_: todoist.automations.gmail_tasks.GmailTasksAutomation",
                "automations:",
                "  - ${activity}",
                "  - ${gmail_tasks}",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(web_api, "_AUTOMATIONS_PATH", config_path)

    changed = web_api._set_automation_enabled("gmail_tasks", enabled=False)

    assert changed is True
    saved = config_path.read_text(encoding="utf-8")
    assert "- ${gmail_tasks}" not in saved

def test_set_automation_enabled_returns_false_for_unknown_key(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "automations.yaml"
    config_path.write_text(
        "\n".join(
            [
                "defaults:",
                "  - _self_",
                "activity:",
                "  _target_: todoist.automations.activity.Activity",
                "automations:",
                "  - ${activity}",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(web_api, "_AUTOMATIONS_PATH", config_path)

    changed = web_api._set_automation_enabled("gmail_tasks", enabled=True)

    assert changed is False

def test_admin_gmail_connect_requires_credentials(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(web_api, "_REPO_ROOT", tmp_path)
    monkeypatch.setenv(str(web_api.EnvVar.CONFIG_DIR), str(tmp_path))

    client = TestClient(web_api.app)
    res = client.post("/api/admin/automations/gmail/connect")

    assert res.status_code == 400
    assert "gmail_credentials.json is required" in res.json()["detail"]

def test_admin_gmail_connect_reports_connected(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(web_api, "_REPO_ROOT", tmp_path)
    monkeypatch.setenv(str(web_api.EnvVar.CONFIG_DIR), str(tmp_path))
    (tmp_path / "gmail_credentials.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        web_api,
        "_start_gmail_manual_auth_session",
        lambda: web_api._PendingGmailAuthSession(
            state="state-1",
            auth_url="http://127.0.0.1:9999/auth",
            redirect_uri="http://127.0.0.1:9999/",
            started_at="2026-03-29T12:00:00",
        ),
    )
    monkeypatch.setattr(
        web_api,
        "_gmail_automation_status",
        lambda: {
            "credentialsPresent": True,
            "tokenPresent": False,
            "connected": False,
            "credentialsPath": "gmail_credentials.json",
            "tokenPath": "gmail_token.json",
            "detail": "Pending authorization",
            "setupDocPath": "docs/gmail_setup.md",
            "pendingAuth": {
                "active": True,
                "authUrl": "http://127.0.0.1:9999/auth",
                "redirectUri": "http://127.0.0.1:9999/",
                "startedAt": "2026-03-29T12:00:00",
                "error": None,
            },
        },
    )

    client = TestClient(web_api.app)
    res = client.post("/api/admin/automations/gmail/connect")

    assert res.status_code == 200
    payload = res.json()
    assert payload["credentialsPresent"] is True
    assert payload["connected"] is False
    assert payload["authUrl"] == "http://127.0.0.1:9999/auth"
    assert payload["pendingAuth"]["active"] is True

def test_admin_gmail_connect_accepts_repo_root_credentials_by_default(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(web_api, "_REPO_ROOT", tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(str(web_api.EnvVar.CONFIG_DIR), raising=False)
    (tmp_path / "gmail_credentials.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        web_api,
        "_start_gmail_manual_auth_session",
        lambda: web_api._PendingGmailAuthSession(
            state="state-2",
            auth_url="http://127.0.0.1:9998/auth",
            redirect_uri="http://127.0.0.1:9998/",
            started_at="2026-03-29T12:05:00",
        ),
    )
    monkeypatch.setattr(
        web_api,
        "_gmail_automation_status",
        lambda: {
            "credentialsPresent": True,
            "tokenPresent": False,
            "connected": False,
            "credentialsPath": "gmail_credentials.json",
            "tokenPath": "gmail_token.json",
            "detail": "Pending authorization",
            "setupDocPath": "docs/gmail_setup.md",
            "pendingAuth": {
                "active": True,
                "authUrl": "http://127.0.0.1:9998/auth",
                "redirectUri": "http://127.0.0.1:9998/",
                "startedAt": "2026-03-29T12:05:00",
                "error": None,
            },
        },
    )

    client = TestClient(web_api.app)
    res = client.post("/api/admin/automations/gmail/connect")

    assert res.status_code == 200
    payload = res.json()
    assert payload["credentialsPresent"] is True
    assert payload["authUrl"] == "http://127.0.0.1:9998/auth"

def test_gmail_automation_status_uses_safe_path_labels(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(web_api, "_REPO_ROOT", tmp_path)
    monkeypatch.setenv(str(web_api.EnvVar.CONFIG_DIR), str(tmp_path))
    (tmp_path / "gmail_credentials.json").write_text("{}", encoding="utf-8")
    (tmp_path / "gmail_token.json").write_text("{}", encoding="utf-8")

    payload = web_api._gmail_automation_status()

    assert payload["credentialsPath"] == "gmail_credentials.json"
    assert payload["tokenPath"] == "gmail_token.json"
    assert payload["setupDocPath"] == "docs/gmail_setup.md"

def test_start_gmail_manual_auth_session_enables_insecure_transport_temporarily(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(web_api, "_REPO_ROOT", tmp_path)
    monkeypatch.setenv(str(web_api.EnvVar.CONFIG_DIR), str(tmp_path))
    monkeypatch.delenv("OAUTHLIB_INSECURE_TRANSPORT", raising=False)
    (tmp_path / "gmail_credentials.json").write_text("{}", encoding="utf-8")

    flow = Mock()

    def _authorization_url(**kwargs):
        assert kwargs["access_type"] == "offline"
        assert kwargs["include_granted_scopes"] == "true"
        assert kwargs["prompt"] == "consent"
        assert os.environ["OAUTHLIB_INSECURE_TRANSPORT"] == "1"
        return ("http://127.0.0.1:9999/auth", "state-1")

    flow.authorization_url.side_effect = _authorization_url
    monkeypatch.setattr(
        web_api.InstalledAppFlow,
        "from_client_secrets_file",
        lambda *_args, **_kwargs: flow,
    )

    session = web_api._start_gmail_manual_auth_session()

    assert session.auth_url == "http://127.0.0.1:9999/auth"
    assert "OAUTHLIB_INSECURE_TRANSPORT" not in os.environ

def test_admin_task_ingest_projects_returns_sorted_projects(monkeypatch) -> None:
    monkeypatch.setattr(
        web_api,
        "_load_task_ingest_projects_sync",
        lambda refresh: [
            {"id": "p1", "name": "Alpha", "label": "Work / Alpha", "parentId": "root"},
            {"id": "p2", "name": "Inbox", "label": "Inbox", "parentId": None},
        ],
    )

    client = TestClient(web_api.app)
    res = client.get("/api/admin/task_ingest/projects")

    assert res.status_code == 200
    payload = res.json()
    assert payload["projects"][0]["label"] == "Work / Alpha"
    assert payload["projects"][1]["label"] == "Inbox"

def test_task_ingest_project_payload_includes_only_active_projects() -> None:
    active_root = make_project(project_id="root", name="Root")
    active_child = make_project(project_id="child", name="Child", parent_id="root")
    archived = make_project(
        project_id="archived",
        project_entry=make_project_entry(
            project_id="archived", name="Archived", is_archived=True
        ),
        is_archived=True,
    )
    deleted = make_project(project_id="deleted", name="Deleted", is_deleted=True)

    payload = web_api._task_ingest_project_payload(
        [archived, deleted, active_child, active_root]
    )

    assert [project["id"] for project in payload] == ["root", "child"]
    assert [project["label"] for project in payload] == ["Root", "Root / Child"]

def test_admin_task_ingest_preview_builds_nested_outline(monkeypatch) -> None:
    monkeypatch.setattr(
        web_api,
        "_task_ingest_rewrite_with_llm_sync",
        lambda raw, *, max_depth, granularity, preference, include_descriptions: None,
    )

    client = TestClient(web_api.app)
    res = client.post(
        "/api/admin/task_ingest/preview",
        json={
            "rawContent": "Launch update\n- Prepare release notes\n  - Draft internal note\n- QA pass",
            "options": {
                "maxDepth": 2,
                "granularity": "detailed",
                "preference": "milestone-driven",
                "includeDescriptions": False,
            },
        },
    )

    assert res.status_code == 200
    payload = res.json()
    assert payload["source"] == "outline"
    assert payload["maxDepth"] == 2
    assert payload["granularity"] == "detailed"
    assert payload["preference"] == "milestone-driven"
    assert payload["includeDescriptions"] is False
    assert payload["topLevelCount"] == 1
    assert payload["totalCount"] == 3
    assert payload["tasks"][0]["content"] == "Launch update"
    assert payload["tasks"][0]["children"][0]["content"] == "Prepare release notes"
    assert "children" not in payload["tasks"][0]["children"][0]

def test_admin_task_ingest_create_uses_explicit_tasks_payload(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_create(project_id: str, tasks: list[dict[str, object]]) -> list[dict[str, object]]:
        captured["project_id"] = project_id
        captured["tasks"] = tasks
        return [
            {"id": "1", "content": "Top level", "projectId": project_id, "parentId": None},
            {"id": "2", "content": "Child", "projectId": project_id, "parentId": "1"},
        ]

    monkeypatch.setattr(
        web_api,
        "_task_ingest_create_sync",
        _fake_create,
    )

    client = TestClient(web_api.app)
    res = client.post(
        "/api/admin/task_ingest/create",
        json={
            "projectId": "project-1",
            "tasks": [
                {
                    "content": "Top level",
                    "description": "ignored when descriptions are off",
                    "children": [{"content": "Child"}],
                }
            ],
            "options": {"maxDepth": 3, "granularity": "balanced", "includeDescriptions": False},
        },
    )

    assert res.status_code == 200
    payload = res.json()
    assert payload["createdCount"] == 2
    assert payload["topLevelCount"] == 1
    assert payload["created"][1]["parentId"] == "1"
    assert captured["project_id"] == "project-1"
    assert captured["tasks"] == [{"content": "Top level", "children": [{"content": "Child"}]}]

def test_admin_status_update_projects_returns_sorted_projects(monkeypatch) -> None:
    monkeypatch.setattr(
        web_api,
        "load_status_update_projects",
        lambda dbio: [
            {"id": "p1", "name": "Alpha", "label": "Work / Alpha", "parentId": "root"},
            {"id": "p2", "name": "Inbox", "label": "Inbox", "parentId": None},
        ],
    )
    monkeypatch.setattr(web_api._state, "db", object())

    client = TestClient(web_api.app)
    res = client.get("/api/admin/status_update/projects")

    assert res.status_code == 200
    payload = res.json()
    assert payload["projects"][0]["label"] == "Work / Alpha"
    assert payload["projects"][1]["label"] == "Inbox"

def test_admin_status_update_generate_builds_report_and_validates_input(monkeypatch) -> None:
    async def _noop_ensure_state(*, refresh: bool, demo_mode: bool | None = None) -> None:
        _ = (refresh, demo_mode)
        return None

    monkeypatch.setattr(web_api, "_ensure_state", _noop_ensure_state)

    projects = [
        make_project(project_id="root-a", name="Alpha"),
        make_project(project_id="child-a", name="Alpha Child", parent_id="root-a"),
        make_project(project_id="other", name="Other"),
    ]

    class _FakeDatabase:
        def fetch_projects(self, include_tasks: bool = False):
            _ = include_tasks
            return list(projects)

        def fetch_archived_projects(self):
            return []

        def fetch_task_comments(self, task_id: str):
            comments_by_task = {
                "task-1": [
                    {
                        "id": "c1",
                        "content": "Shared the launch notes with the team",
                        "posted_at": "2025-01-02T12:00:00Z",
                    }
                ],
                "task-2": [
                    {
                        "id": "c2",
                        "content": "Closed follow-up actions with QA",
                        "posted_at": "2025-01-03T12:00:00Z",
                    }
                ],
            }
            return comments_by_task.get(task_id, [])

    monkeypatch.setattr(web_api._state, "db", _FakeDatabase())
    monkeypatch.setattr(web_api._state, "df_activity", None)
    df = pd.DataFrame(
        [
            {
                "date": "2025-01-02T10:00:00",
                "id": "e1",
                "title": "Launch notes",
                "type": "completed",
                "parent_project_id": "root-a",
                "parent_project_name": "Alpha",
                "root_project_id": "root-a",
                "root_project_name": "Alpha",
                "task_id": "task-1",
            },
            {
                "date": "2025-01-03T10:00:00",
                "id": "e2",
                "title": "Draft follow-up",
                "type": "completed",
                "parent_project_id": "child-a",
                "parent_project_name": "Alpha Child",
                "root_project_id": "root-a",
                "root_project_name": "Alpha",
                "task_id": "task-2",
            },
            {
                "date": "2025-01-04T10:00:00",
                "id": "e3",
                "title": "Ignored task",
                "type": "completed",
                "parent_project_id": "other",
                "parent_project_name": "Other",
                "root_project_id": "other",
                "root_project_name": "Other",
                "task_id": "task-3",
            },
        ]
    )
    df["date"] = pd.to_datetime(df["date"])
    activity_df = df.set_index("date")
    monkeypatch.setattr("todoist.status_update.load_activity_data", lambda db: activity_df)

    client = TestClient(web_api.app)
    res = client.post(
        "/api/admin/status_update/generate",
        json={
            "projectIds": ["root-a"],
            "beg": "2025-01-01",
            "end": "2025-01-05",
            "syncLabel": "Weekly sync",
            "preset": "weekly",
        },
    )

    assert res.status_code == 200
    payload = res.json()
    assert payload["syncLabel"] == "Weekly sync"
    assert payload["range"] == {
        "beg": "2025-01-01T00:00:00",
        "end": "2025-01-06T00:00:00",
    }
    assert payload["selection"]["syncLabel"] == "Weekly sync"
    assert payload["selection"]["preset"] == "weekly"
    assert payload["selection"]["projectIds"] == ["root-a"]
    assert payload["selection"]["requestedProjectIds"] == ["root-a"]
    assert payload["selection"]["requestedProjects"][0]["label"] == "Alpha"
    assert payload["selection"]["expandedProjectIds"] == ["root-a", "child-a"]
    assert payload["selection"]["expandedProjects"][1]["label"] == "Alpha / Alpha Child"
    assert payload["selectedProjects"][0]["label"] == "Alpha"
    assert payload["summary"] == {
        "selectedProjectCount": 1,
        "expandedProjectCount": 2,
        "completedEventCount": 2,
        "completedTaskCount": 2,
        "commentedTaskCount": 2,
        "commentCount": 2,
    }
    assert payload["summaryText"] == "Completed 2 tasks across 2 projects, grounded by 2 comments."
    assert payload["stats"] == {
        "completedCount": 2,
        "commentCount": 2,
        "projectCount": 2,
        "activityCount": 2,
    }
    assert payload["completedTasks"][0]["content"] == "Launch notes"
    assert payload["completedTasks"][0]["comments"][0]["content"] == "Shared the launch notes with the team"
    assert "Weekly sync" in payload["markdown"]
    assert "Alpha Child" in payload["markdown"]

    invalid = client.post(
        "/api/admin/status_update/generate",
        json={"projectIds": [], "beg": "2025-01-01", "end": "2025-01-05"},
    )
    assert invalid.status_code == 400

    reversed_range = client.post(
        "/api/admin/status_update/generate",
        json={"projectIds": ["root-a"], "beg": "2025-01-05", "end": "2025-01-01"},
    )
    assert reversed_range.status_code == 400

def test_admin_observer_settings_roundtrip(monkeypatch, tmp_path) -> None:
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    (config_dir / "dashboard.yaml").write_text(
        "observer:\n  enabled: true\n  refresh_interval_minutes: 0.5\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(web_api, "_DASHBOARD_CONFIG_PATH", config_dir / "dashboard.yaml")

    client = TestClient(web_api.app)
    res = client.get("/api/admin/observer")
    assert res.status_code == 200
    payload = res.json()
    assert payload["settings"]["enabled"] is True
    assert payload["settings"]["refreshIntervalMinutes"] == 0.5
    assert payload["editTargets"][0]["icon"] == "wrench"

    update = client.post(
        "/api/admin/observer",
        json={"enabled": False, "refreshIntervalMinutes": 2},
    )
    assert update.status_code == 200
    updated = update.json()
    assert updated["state"]["enabled"] is False
    assert updated["settings"]["refreshIntervalMinutes"] == 2.0

    saved_text = (config_dir / "dashboard.yaml").read_text(encoding="utf-8")
    assert "refresh_interval_minutes: 2.0" in saved_text or "refresh_interval_minutes: 2" in saved_text
    assert "enabled: false" in saved_text

def test_admin_run_observer_reports_idle_polling_automations(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(str(web_api.EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.chdir(tmp_path)

    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    (config_dir / "dashboard.yaml").write_text(
        "observer:\n  enabled: true\n  refresh_interval_minutes: 0.5\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(web_api, "_DASHBOARD_CONFIG_PATH", config_dir / "dashboard.yaml")

    class _FakeDatabase:
        def __init__(self, dotenv_path: str) -> None:
            self.dotenv_path = dotenv_path

        def pull(self) -> None:
            return None

        def reset(self) -> None:
            return None

    class _FakeRunResult:
        def __init__(self) -> None:
            self.new_events = 0
            self.automations_ran = 1

    class _FakeObserver:
        def run_once(self) -> _FakeRunResult:
            return _FakeRunResult()

    monkeypatch.setattr(web_api, "Database", _FakeDatabase)
    monkeypatch.setattr(web_api, "_build_observer", lambda db: _FakeObserver())

    client = TestClient(web_api.app)
    res = client.post("/api/admin/observer/run")
    assert res.status_code == 200
    payload = res.json()
    assert payload["state"]["lastStatus"] == "ran"
    assert payload["state"]["lastEvents"] == 0
    assert payload["state"]["lastAutomationsRan"] == 1

def test_task_ingest_rewrite_uses_selected_local_model_when_runtime_is_idle(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _FakeTransformers:
        def __init__(self, config):
            captured["config"] = config

        def structured_chat(self, _messages, _schema):
            return web_api.TaskBreakdown(
                children=[web_api.BreakdownNode(content="Draft roadmap", description="from llm")]
            )

    monkeypatch.setattr(web_api, "_LLM_CHAT_MODEL", None)
    monkeypatch.setattr(
        web_api,
        "_resolve_llm_chat_settings",
        lambda: {
            "backend": "transformers_local",
            "device": "cpu",
            "localModelId": "mistralai/Mistral-Nemo-Instruct-2407",
            "openai": {"configured": False, "keyName": None, "model": "gpt-5-mini"},
            "triton": {
                "baseUrl": "http://127.0.0.1:8003",
                "modelName": "todoist_llm",
                "modelId": "Qwen/Qwen2.5-0.5B-Instruct",
            },
        },
    )
    monkeypatch.setattr(web_api, "TransformersMistral3ChatModel", _FakeTransformers)

    result = web_api._task_ingest_rewrite_with_llm_sync(
        "Plan launch",
        max_depth=2,
        granularity="balanced",
        preference="action-first",
        include_descriptions=True,
    )

    assert result is not None
    tasks, source = result
    assert source == "transformers"
    assert tasks[0]["content"] == "Draft roadmap"
    config = captured["config"]
    assert getattr(config, "model_id") == "mistralai/Mistral-Nemo-Instruct-2407"
    assert getattr(config, "max_new_tokens") == 768
