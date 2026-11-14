"""Tests for FastAPI admin endpoints."""

import pytest

import todometry.database.dataframe as dataframe_module
from todometry.core.utils import MaxRetriesExceeded
import todometry.web.api as web_api
from todometry.web.services.project_adjustments import _resolve_automatic_project_mappings

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

    automatic, details = _resolve_automatic_project_mappings(
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


@pytest.mark.parametrize(
    "path",
    [
        "/api/admin/automations",
        "/api/admin/observer",
        "/api/admin/multiplication",
        "/api/admin/stale_tasks",
        "/api/dashboard/executive_review",
    ],
)
def test_removed_runtime_features_have_no_routes(api_client, path: str) -> None:
    assert api_client.get(path).status_code == 404


def test_dashboard_settings_create_directory_and_invalidate_home(
    monkeypatch, tmp_path, api_client
):
    path = tmp_path / "new-configs" / "dashboard.yaml"
    monkeypatch.setattr(web_api, "_DASHBOARD_CONFIG_PATH", path)
    monkeypatch.setattr(
        web_api._state, "home_payload_cache", {("home",): {"stale": True}}
    )
    response = api_client.put(
        "/api/admin/dashboard/settings",
        json={
            "fireLabels": [],
            "warnPriorityThresholds": [],
            "dangerOnFireLabel": False,
            "warnOnPriority": False,
            "warnOnDue": False,
            "warnOnDeadline": False,
        },
    )
    assert response.status_code == 200
    assert web_api._state.home_payload_cache == {}
    reread = api_client.get("/api/admin/dashboard/settings").json()["settings"]
    assert reread["fireLabels"] == []
    assert reread["warnPriorityThresholds"] == []
    assert reread["dangerOnFireLabel"] is False
    assert reread["warnOnPriority"] is False
    assert path.exists()


@pytest.mark.parametrize(
    "patch",
    [
        {"enabled": "false"},
        {"warnOnPriority": 0},
        {"fireLabels": "fire"},
        {"warnPriorityThresholds": "43"},
        {"warnPriorityThresholds": [0, 5]},
        {"warnPriorityMinCount": 1.5},
        {"warnDueWithinDays": -1},
        {"warnDueMinCount": 0},
        {"warnDeadlineWithinDays": True},
        {"fireLabels": [None]},
        {"plotEvents": [{"date": "2026-02-30", "label": "Invalid"}]},
        {"plotEvents": [{"date": "2026-11-01", "label": "Launch", "color": "garbage"}]},
    ],
)
def test_invalid_settings_do_not_modify_saved_rules(
    monkeypatch, tmp_path, api_client, patch
):
    path = tmp_path / "dashboard.yaml"
    path.write_text("urgency:\n  enabled: true\n  warn_priority_thresholds: [4]\n")
    monkeypatch.setattr(web_api, "_DASHBOARD_CONFIG_PATH", path)
    before = path.read_bytes()
    response = api_client.put("/api/admin/dashboard/settings", json=patch)
    assert response.status_code == 400
    assert path.read_bytes() == before
    assert response.json()["detail"]


def test_concurrent_partial_settings_updates_preserve_each_other(monkeypatch, tmp_path):
    import asyncio
    import httpx

    path = tmp_path / "dashboard.yaml"
    path.write_text("urgency:\n  enabled: true\n  warn_priority_thresholds: [4]\n")
    monkeypatch.setattr(web_api, "_DASHBOARD_CONFIG_PATH", path)

    async def run():
        lock = asyncio.Lock()
        monkeypatch.setattr(web_api, "_ADMIN_LOCK", lock)
        await lock.acquire()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=web_api.app), base_url="http://test"
        ) as client:
            first = asyncio.create_task(
                client.put("/api/admin/dashboard/settings", json={"enabled": False})
            )
            second = asyncio.create_task(
                client.put(
                    "/api/admin/dashboard/settings",
                    json={"warnPriorityThresholds": [2]},
                )
            )
            await asyncio.sleep(0)
            lock.release()
            responses = await asyncio.gather(first, second)
            assert all(response.status_code == 200 for response in responses)
            settings = (await client.get("/api/admin/dashboard/settings")).json()[
                "settings"
            ]
            assert settings["enabled"] is False
            assert settings["warnPriorityThresholds"] == [2]

    asyncio.run(run())
