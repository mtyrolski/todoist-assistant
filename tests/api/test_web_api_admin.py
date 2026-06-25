"""Tests for FastAPI admin endpoints."""

import os
from datetime import datetime
from typing import cast
from unittest.mock import Mock

import pytest

import todoist.database.dataframe as dataframe_module
from todoist.core.utils import MaxRetriesExceeded
import todoist.web.api as web_api

# pylint: disable=protected-access


def _pending_gmail_status(port: int, started_at: str) -> dict[str, object]:
    auth_url = f"http://127.0.0.1:{port}/auth"
    redirect_uri = f"http://127.0.0.1:{port}/"
    return {
        "credentialsPresent": True,
        "tokenPresent": False,
        "connected": False,
        "credentialsPath": "gmail_credentials.json",
        "tokenPath": "gmail_token.json",
        "detail": "Pending authorization",
        "setupDocPath": "docs/gmail_setup.md",
        "pendingAuth": {
            "active": True,
            "authUrl": auth_url,
            "redirectUri": redirect_uri,
            "startedAt": started_at,
            "error": None,
        },
    }


def test_admin_project_adjustments_exposes_remappable_active_roots(monkeypatch, api_client) -> None:
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

    res = api_client.get("/api/admin/project_adjustments")
    assert res.status_code == 200
    payload = res.json()

    assert payload["remappableActiveRootProjects"] == ["Inbox"]
    assert payload["sourceProjects"] == [
        "Archived Research",
        "Archived Root",
        "Inbox",
    ]
    assert payload["unmappedSourceProjects"] == ["Archived Root", "Inbox"]


def test_admin_project_adjustments_rejects_path_traversal(
    monkeypatch, tmp_path, api_client
) -> None:
    monkeypatch.setenv("TODOIST_PERSONAL_DIR", str(tmp_path / "personal"))
    client = api_client
    invalid = client.get(
        "/api/admin/project_adjustments", params={"file": "../evil.py"}
    )
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
    monkeypatch, tmp_path, api_client
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
    response = api_client.put(
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
    monkeypatch, tmp_path, api_client
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

    response = api_client.put(
        "/api/admin/project_adjustments",
        params={"file": "adj_private.py", "refresh": "true"},
        json={"mappings": {"Archived Research": "Academy"}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["saved"] is True
    assert (
        payload["warning"]
        == "Saved, but dashboard refresh failed (MaxRetriesExceeded)."
    )
    loaded_mapping, archived_parents = dataframe_module.load_adjustments_file(
        personal_dir / "adj_private.py"
    )
    assert loaded_mapping == {"Archived Research": "Academy"}
    assert archived_parents == []


@pytest.mark.parametrize(
    ("body", "expected_detail"),
    [
        (
            {"mappings": {"DeepMhcFlare": "deepflare"}},
            "Mapping sources must be archived projects",
        ),
        (
            {"mappings": {}, "archivedParents": ["DeepMhcFlare"]},
            "archivedParents must contain archived projects only",
        ),
    ],
)
def test_admin_save_project_adjustments_rejects_active_project_inputs(
    monkeypatch, tmp_path, body, expected_detail, api_client
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

    response = api_client.put(
        "/api/admin/project_adjustments",
        params={"file": "adj_private.py", "refresh": "false"},
        json=body,
    )

    assert response.status_code == 400
    assert expected_detail in response.json()["detail"]


def test_admin_dashboard_settings_roundtrip(monkeypatch, tmp_path, api_client) -> None:
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    (config_dir / "dashboard.yaml").write_text(
        "urgency:\n  enabled: true\n  warn_priority_thresholds: [4, 3]\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        web_api, "_DASHBOARD_CONFIG_PATH", config_dir / "dashboard.yaml"
    )

    client = api_client
    res = client.get("/api/admin/dashboard/settings")
    assert res.status_code == 200
    payload = res.json()
    assert payload["settings"]["enabled"] is True
    assert payload["editTargets"][0]["icon"] == "wrench"
    assert payload["settings"]["fireLabels"] == [
        web_api.DEFAULT_URGENCY_SETTINGS["fire_label"]
    ]

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


def test_admin_dashboard_labels_returns_sorted_local_labels(monkeypatch, api_client) -> None:
    class _FakeDatabase:
        def __init__(self, dotenv_path: str) -> None:
            _ = dotenv_path
            self._items = [
                {"name": "zeta", "color": "red"},
                {"name": "alpha", "color": "blue"},
            ]

        def fetch_label_colors(self) -> dict[str, str]:
            return {"alpha": "#0000ff", "zeta": "#ff0000"}

        def list_labels(self) -> list[dict[str, str]]:
            return list(self._items)

    monkeypatch.setattr(web_api, "Database", _FakeDatabase)

    res = api_client.get("/api/admin/dashboard/labels")
    assert res.status_code == 200
    payload = res.json()
    assert payload["labels"] == [
        {"name": "alpha", "color": "#0000ff"},
        {"name": web_api.DEFAULT_URGENCY_SETTINGS["fire_label"], "color": None},
        {"name": "zeta", "color": "#ff0000"},
    ]


def test_admin_automations_returns_enabled_and_connection(monkeypatch, api_client) -> None:
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

    res = api_client.get("/api/admin/automations")

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


def test_run_all_automations_sync_continues_after_failure(
    monkeypatch, tmp_path
) -> None:
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
        "gmail_tasks": {
            "_target_": "todoist.automations.gmail_tasks.GmailTasksAutomation"
        },
        "habit_tracker": {"_target_": "todoist.automations.habit_tracker.HabitTracker"},
    }

    assert web_api._enabled_automation_keys(config) == ["activity", "habit_tracker"]


def test_configured_enabled_automation_keys_supports_resolved_omegaconf_entries(
    tmp_path,
) -> None:
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

    assert web_api._configured_enabled_automation_keys(config) == [
        "activity",
        "gmail_tasks",
    ]


def test_admin_set_automation_enabled_updates_config(monkeypatch, tmp_path, api_client) -> None:
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

    res = api_client.post(
        "/api/admin/automations/gmail_tasks/enabled", json={"enabled": True}
    )

    assert res.status_code == 200
    saved = config_path.read_text(encoding="utf-8")
    assert "- ${gmail_tasks}" in saved


def test_admin_stale_task_settings_roundtrip(monkeypatch, tmp_path, api_client) -> None:
    config_path = tmp_path / "automations.yaml"
    config_path.write_text(
        "\n".join(
            [
                "defaults:",
                "  - _self_",
                "stale_tasks:",
                "  _target_: todoist.automations.stale_tasks.StaleTasksAutomation",
                "  name: Stale Tasks",
                "  frequency_in_minutes: 1440",
                "  config:",
                "    old_after_days: 30",
                "    very_old_after_days: 90",
                "    old_label: old",
                "    very_old_label: very-old",
                "  dry_run: true",
                "  max_updates_per_tick: 25",
                "automations:",
                "  - ${stale_tasks}",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(web_api, "_AUTOMATIONS_PATH", config_path)

    res = api_client.put(
        "/api/admin/stale_tasks",
        json={
            "oldAfterDays": 14,
            "veryOldAfterDays": 45,
            "warningLabel": "stale-warning",
            "veryOldLabel": "stale-critical",
            "deleteAfterWarningDays": 5,
            "dryRun": False,
            "maxUpdatesPerTick": 10,
        },
    )

    assert res.status_code == 200
    payload = res.json()
    assert payload["settings"]["deleteAfterWarningDays"] == 5
    assert payload["settings"]["dryRun"] is False
    saved = config_path.read_text(encoding="utf-8")
    assert "old_label: stale-warning" in saved
    assert "delete_after_warning_days: 5" in saved
    assert "dry_run: false" in saved


def test_admin_multiplication_settings_roundtrip_cleanup(monkeypatch, tmp_path, api_client) -> None:
    config_path = tmp_path / "automations.yaml"
    config_path.write_text(
        "\n".join(
            [
                "defaults:",
                "  - _self_",
                "multiply:",
                "  _target_: todoist.automations.multiplicate.Multiply",
                "  frequency_in_minutes: 0.1",
                "automations:",
                "  - ${multiply}",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(web_api, "_AUTOMATIONS_PATH", config_path)

    res = api_client.put(
        "/api/admin/multiplication",
        json={
            "flatLeafTemplate": "{base} #{i}",
            "deepLeafTemplate": "{base} - {i}/{n}",
            "deepChildLabel": "effort-point",
            "cleanupUnusedLabels": True,
            "cleanupUnusedLabelsAfterDays": 3,
        },
    )

    assert res.status_code == 200
    payload = res.json()
    assert payload["settings"]["cleanupUnusedLabels"] is True
    assert payload["settings"]["cleanupUnusedLabelsAfterDays"] == 3
    assert payload["settings"]["deepChildLabel"] == "effort-point"
    saved = config_path.read_text(encoding="utf-8")
    assert "deep_child_label: effort-point" in saved
    assert "cleanup_unused_labels_after_days: 3" in saved


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


def test_set_automation_enabled_returns_false_for_unknown_key(
    monkeypatch, tmp_path
) -> None:
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


def test_admin_gmail_connect_requires_credentials(monkeypatch, tmp_path, api_client) -> None:
    monkeypatch.setattr(web_api, "_REPO_ROOT", tmp_path)
    monkeypatch.setenv(str(web_api.EnvVar.CONFIG_DIR), str(tmp_path))

    res = api_client.post("/api/admin/automations/gmail/connect")

    assert res.status_code == 400
    assert "gmail_credentials.json is required" in res.json()["detail"]


@pytest.mark.parametrize(
    ("port", "state", "started_at", "use_config_dir"),
    [
        (9999, "state-1", "2026-03-29T12:00:00", True),
        (9998, "state-2", "2026-03-29T12:05:00", False),
    ],
)
def test_admin_gmail_connect_reports_pending_auth(
    monkeypatch, tmp_path, port, state, started_at, use_config_dir, api_client
) -> None:
    monkeypatch.setattr(web_api, "_REPO_ROOT", tmp_path)
    if use_config_dir:
        monkeypatch.setenv(str(web_api.EnvVar.CONFIG_DIR), str(tmp_path))
    else:
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv(str(web_api.EnvVar.CONFIG_DIR), raising=False)
    (tmp_path / "gmail_credentials.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        web_api,
        "_start_gmail_manual_auth_session",
        lambda: web_api._PendingGmailAuthSession(
            state=state,
            auth_url=f"http://127.0.0.1:{port}/auth",
            redirect_uri=f"http://127.0.0.1:{port}/",
            started_at=started_at,
        ),
    )
    monkeypatch.setattr(
        web_api,
        "_gmail_automation_status",
        lambda: _pending_gmail_status(port, started_at),
    )

    res = api_client.post("/api/admin/automations/gmail/connect")

    assert res.status_code == 200
    payload = res.json()
    assert payload["credentialsPresent"] is True
    assert payload["authUrl"] == f"http://127.0.0.1:{port}/auth"
    assert payload["pendingAuth"]["active"] is True


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



def test_admin_observer_settings_roundtrip(monkeypatch, tmp_path, api_client) -> None:
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    (config_dir / "dashboard.yaml").write_text(
        "observer:\n  enabled: true\n  refresh_interval_minutes: 0.5\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        web_api, "_DASHBOARD_CONFIG_PATH", config_dir / "dashboard.yaml"
    )

    client = api_client
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
    assert (
        "refresh_interval_minutes: 2.0" in saved_text
        or "refresh_interval_minutes: 2" in saved_text
    )
    assert "enabled: false" in saved_text


def test_admin_run_observer_reports_idle_polling_automations(
    monkeypatch, tmp_path, api_client
) -> None:
    monkeypatch.setenv(str(web_api.EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.chdir(tmp_path)

    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    (config_dir / "dashboard.yaml").write_text(
        "observer:\n  enabled: true\n  refresh_interval_minutes: 0.5\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        web_api, "_DASHBOARD_CONFIG_PATH", config_dir / "dashboard.yaml"
    )

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

    res = api_client.post("/api/admin/observer/run")
    assert res.status_code == 200
    payload = res.json()
    assert payload["state"]["lastStatus"] == "ran"
    assert payload["state"]["lastEvents"] == 0
    assert payload["state"]["lastAutomationsRan"] == 1
