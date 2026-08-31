"""Tests for FastAPI admin endpoints."""

from datetime import datetime
from typing import cast

import pytest

import todoist.database.dataframe as dataframe_module
from todoist.core.utils import MaxRetriesExceeded
import todoist.web.api as web_api

# pylint: disable=protected-access


def _write_yaml(path, *lines: str) -> None:
    path.write_text("\n".join(lines), encoding="utf-8")


def test_admin_project_adjustments_exposes_remappable_active_roots(
    monkeypatch, api_client
) -> None:
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


def test_automatic_project_mappings_use_parent_ids_and_manual_overrides() -> None:
    records = [
        {
            "id": "active-root",
            "name": "Academy",
            "isArchived": False,
            "ancestors": [{"id": "active-root", "name": "Academy"}],
            "rootId": "active-root",
            "rootName": "Academy",
        },
        {
            "id": "old-root",
            "name": "Old Research",
            "isArchived": True,
            "ancestors": [{"id": "old-root", "name": "Old Research"}],
            "rootId": "old-root",
            "rootName": "Old Research",
        },
        {
            "id": "old-child",
            "name": "Old Experiment",
            "isArchived": True,
            "ancestors": [
                {"id": "old-child", "name": "Old Experiment"},
                {"id": "old-root", "name": "Old Research"},
            ],
            "rootId": "old-root",
            "rootName": "Old Research",
        },
    ]

    automatic, details = web_api._resolve_automatic_project_mappings(
        records,
        manual_mappings={"Old Research": "Academy"},
        archived_parent_projects=set(),
    )

    assert automatic == {"Old Experiment": "Academy"}
    assert details == [
        {
            "sourceProject": "Old Experiment",
            "sourceProjectId": "old-child",
            "parentProject": "Academy",
            "parentProjectId": "active-root",
            "provenance": "automatic",
        }
    ]


def test_admin_project_adjustments_labels_manual_and_automatic_mappings(
    monkeypatch, api_client
) -> None:
    records = [
        {
            "id": "academy",
            "name": "Academy",
            "isArchived": False,
            "ancestors": [{"id": "academy", "name": "Academy"}],
            "rootId": "academy",
            "rootName": "Academy",
        },
        {
            "id": "old-root",
            "name": "Old Root",
            "isArchived": True,
            "ancestors": [{"id": "old-root", "name": "Old Root"}],
            "rootId": "old-root",
            "rootName": "Old Root",
        },
        {
            "id": "old-child",
            "name": "Old Child",
            "isArchived": True,
            "ancestors": [
                {"id": "old-child", "name": "Old Child"},
                {"id": "old-root", "name": "Old Root"},
            ],
            "rootId": "old-root",
            "rootName": "Old Root",
        },
    ]
    monkeypatch.setattr(web_api, "_available_mapping_files", lambda: ["map.py"])
    monkeypatch.setattr(
        web_api, "_load_mapping_file", lambda filename: ({"Old Root": "Academy"}, [])
    )
    monkeypatch.setattr(
        web_api,
        "_load_projects_for_adjustments_sync",
        lambda refresh: (
            ["Academy"],
            ["Old Root"],
            ["Old Child", "Old Root"],
            [],
            records,
        ),
    )

    response = api_client.get("/api/admin/project_adjustments")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mappings"] == {"Old Root": "Academy"}
    assert payload["automaticMappings"] == {"Old Child": "Academy"}
    assert payload["mappingProvenance"] == {
        "Old Child": "automatic",
        "Old Root": "manual",
    }
    assert payload["unmappedSourceProjects"] == []
    details = {item["sourceProject"]: item for item in payload["mappingDetails"]}
    assert details["Old Root"]["parentProjectId"] == "academy"
    assert details["Old Child"]["sourceProjectId"] == "old-child"


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


def test_admin_dashboard_labels_returns_sorted_local_labels(
    monkeypatch, api_client
) -> None:
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


def test_admin_automations_returns_inventory(monkeypatch, api_client) -> None:
    monkeypatch.setattr(
        web_api,
        "_load_automation_inventory",
        lambda: [
            {
                "key": "activity",
                "name": "Activity Fetching Automation",
                "frequencyMinutes": 15,
                "isLong": False,
                "launchCount": 0,
                "lastLaunch": None,
                "enabled": True,
                "defaultEnabled": True,
                "target": "todoist.automations.activity.Activity",
            }
        ],
    )

    res = api_client.get("/api/admin/automations")

    assert res.status_code == 200
    payload = res.json()
    assert payload["automations"][0]["key"] == "activity"
    assert payload["automations"][0]["enabled"] is True
    assert payload["automations"][0]["defaultEnabled"] is True


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


def test_enabled_automation_keys_defaults_to_all_sections() -> None:
    config = {
        "activity": {"_target_": "todoist.automations.activity.Activity"},
        "habit_tracker": {"_target_": "todoist.automations.habit_tracker.HabitTracker"},
    }

    assert web_api._enabled_automation_keys(config) == ["activity", "habit_tracker"]


def test_configured_enabled_automation_keys_supports_resolved_omegaconf_entries(
    tmp_path,
) -> None:
    config_path = tmp_path / "automations.yaml"
    _write_yaml(
        config_path,
        "defaults:",
        "  - _self_",
        "activity:",
        "  _target_: todoist.automations.activity.Activity",
        "habit_tracker:",
        "  _target_: todoist.automations.habit_tracker.HabitTracker",
        "automations:",
        "  - ${activity}",
        "  - ${habit_tracker}",
    )

    config = web_api._read_yaml_config(config_path)

    assert web_api._configured_enabled_automation_keys(config) == [
        "activity",
        "habit_tracker",
    ]


def test_admin_set_automation_enabled_updates_config(
    monkeypatch, tmp_path, api_client
) -> None:
    config_path = tmp_path / "automations.yaml"
    _write_yaml(
        config_path,
        "defaults:",
        "  - _self_",
        "activity:",
        "  _target_: todoist.automations.activity.Activity",
        "  name: Activity Fetching Automation",
        "  early_stop_after_n_windows: 2",
        "  nweeks_window_size: 4",
        "habit_tracker:",
        "  _target_: todoist.automations.habit_tracker.HabitTracker",
        "  name: Habit Tracker",
        "  frequency_in_minutes: 10080",
        "automations:",
        "  - ${activity}",
    )
    monkeypatch.setattr(web_api, "_AUTOMATIONS_PATH", config_path)
    monkeypatch.setattr(web_api, "_CONFIG_DIR", tmp_path)

    res = api_client.post(
        "/api/admin/automations/habit_tracker/enabled", json={"enabled": True}
    )

    assert res.status_code == 200
    saved = config_path.read_text(encoding="utf-8")
    assert "- ${habit_tracker}" in saved


def test_admin_stale_task_settings_roundtrip(monkeypatch, tmp_path, api_client) -> None:
    config_path = tmp_path / "automations.yaml"
    _write_yaml(
        config_path,
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


def test_admin_multiplication_settings_roundtrip_cleanup(
    monkeypatch, tmp_path, api_client
) -> None:
    config_path = tmp_path / "automations.yaml"
    _write_yaml(
        config_path,
        "defaults:",
        "  - _self_",
        "multiply:",
        "  _target_: todoist.automations.multiplicate.Multiply",
        "  frequency_in_minutes: 0.1",
        "automations:",
        "  - ${multiply}",
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
    _write_yaml(
        config_path,
        "defaults:",
        "  - _self_",
        "activity:",
        "  _target_: todoist.automations.activity.Activity",
        "habit_tracker:",
        "  _target_: todoist.automations.habit_tracker.HabitTracker",
        "automations:",
        "  - ${activity}",
        "  - ${habit_tracker}",
    )
    monkeypatch.setattr(web_api, "_AUTOMATIONS_PATH", config_path)

    changed = web_api._set_automation_enabled("habit_tracker", enabled=False)

    assert changed is True
    saved = config_path.read_text(encoding="utf-8")
    assert "- ${habit_tracker}" not in saved


def test_set_automation_enabled_returns_false_for_unknown_key(
    monkeypatch, tmp_path
) -> None:
    config_path = tmp_path / "automations.yaml"
    _write_yaml(
        config_path,
        "defaults:",
        "  - _self_",
        "activity:",
        "  _target_: todoist.automations.activity.Activity",
        "automations:",
        "  - ${activity}",
    )
    monkeypatch.setattr(web_api, "_AUTOMATIONS_PATH", config_path)

    changed = web_api._set_automation_enabled("missing", enabled=True)

    assert changed is False


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
