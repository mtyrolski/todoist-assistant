"""Tests for FastAPI dashboard home endpoints."""

from datetime import date

import pandas as pd
from fastapi.testclient import TestClient

from tests.factories import make_project, make_project_entry, make_task
from tests.web_api_helpers import (
    _clear_dashboard_state,
    _set_state_with_df,
    _single_event_df,
    _stub_all_figures,
)
import todoist.web.api as web_api

# pylint: disable=protected-access


def test_load_state_from_disk_cache_restores_payload(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(str(web_api.EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.chdir(tmp_path)

    cache = web_api.Cache()
    cache.activity.save(set())
    df = _single_event_df()
    cache.dashboard_state.save(
        {
            "version": web_api._DASHBOARD_STATE_SCHEMA_VERSION,
            "created_at": "2025-01-01T00:00:00",
            "last_refresh_s": 123.0,
            "demo_mode": False,
            "activity_cache_signature": web_api._activity_cache_signature(),
            "adjustments_cache_signature": [],
            "df_activity": df,
            "active_projects": [],
            "project_colors": {"A": "#123456"},
        }
    )

    _clear_dashboard_state()
    loaded = web_api._load_state_from_disk_cache(demo_mode=False)
    assert loaded is True
    assert web_api._state.df_activity is not None
    assert len(web_api._state.df_activity) == 1
    assert web_api._state.project_colors == {"A": "#123456"}
    assert web_api._state.active_projects == []


def test_load_state_from_disk_cache_rejects_stale_activity_signature(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv(str(web_api.EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.chdir(tmp_path)

    cache = web_api.Cache()
    cache.activity.save(set())
    original_signature = web_api._activity_cache_signature()
    cache.dashboard_state.save(
        {
            "version": web_api._DASHBOARD_STATE_SCHEMA_VERSION,
            "created_at": "2025-01-01T00:00:00",
            "last_refresh_s": 123.0,
            "demo_mode": False,
            "activity_cache_signature": original_signature,
            "adjustments_cache_signature": [],
            "df_activity": _single_event_df(),
            "active_projects": [],
            "project_colors": {},
        }
    )

    # Mutate activity cache so signature no longer matches cached dashboard snapshot.
    cache.activity.save({"new-event"})

    _clear_dashboard_state()
    loaded = web_api._load_state_from_disk_cache(demo_mode=False)
    assert loaded is False


def test_load_state_from_disk_cache_rejects_stale_adjustment_signature(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv(str(web_api.EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.chdir(tmp_path)

    cache = web_api.Cache()
    cache.activity.save(set())
    cache.dashboard_state.save(
        {
            "version": web_api._DASHBOARD_STATE_SCHEMA_VERSION,
            "created_at": "2025-01-01T00:00:00",
            "last_refresh_s": 123.0,
            "demo_mode": False,
            "activity_cache_signature": web_api._activity_cache_signature(),
            "adjustments_cache_signature": [],
            "df_activity": _single_event_df(),
            "active_projects": [],
            "project_colors": {},
        }
    )

    personal_dir = tmp_path / "personal"
    personal_dir.mkdir()
    (personal_dir / "adj_private.py").write_text(
        "link_adjustements = {}\narchived_parent_projects = ['MSFT']\n",
        encoding="utf-8",
    )

    _clear_dashboard_state()
    loaded = web_api._load_state_from_disk_cache(demo_mode=False)
    assert loaded is False


def test_load_state_from_disk_cache_rejects_legacy_demo_snapshot(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv(str(web_api.EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.chdir(tmp_path)

    cache = web_api.Cache()
    cache.activity.save(set())
    cache.dashboard_state.save(
        {
            "version": web_api._DASHBOARD_STATE_SCHEMA_VERSION,
            "created_at": "2025-01-01T00:00:00",
            "last_refresh_s": 123.0,
            "demo_mode": True,
            "demo_state_version": web_api._DEMO_DASHBOARD_STATE_SCHEMA_VERSION - 1,
            "activity_cache_signature": web_api._activity_cache_signature(),
            "adjustments_cache_signature": [],
            "df_activity": _single_event_df(),
            "active_projects": [],
            "project_colors": {"A": "#123456"},
        }
    )

    _clear_dashboard_state()
    loaded = web_api._load_state_from_disk_cache(demo_mode=True)
    assert loaded is False


def test_load_state_from_disk_cache_restores_current_demo_snapshot(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv(str(web_api.EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.chdir(tmp_path)

    cache = web_api.Cache()
    cache.activity.save(set())
    df = _single_event_df()
    cache.dashboard_state.save(
        {
            "version": web_api._DASHBOARD_STATE_SCHEMA_VERSION,
            "created_at": "2025-01-01T00:00:00",
            "last_refresh_s": 123.0,
            "demo_mode": True,
            "demo_state_version": web_api._DEMO_DASHBOARD_STATE_SCHEMA_VERSION,
            "activity_cache_signature": web_api._activity_cache_signature(),
            "adjustments_cache_signature": [],
            "df_activity": df,
            "active_projects": [],
            "project_colors": {"A": "#123456"},
        }
    )

    _clear_dashboard_state()
    loaded = web_api._load_state_from_disk_cache(demo_mode=True)
    assert loaded is True
    assert web_api._state.df_activity is not None
    assert len(web_api._state.df_activity) == 1
    assert web_api._state.project_colors == {"A": "#123456"}
    assert web_api._state.active_projects == []
    assert web_api._state.demo_mode is True


def test_dashboard_home_bootstraps_from_disk_cache_without_refresh(monkeypatch) -> None:
    _stub_all_figures(monkeypatch)
    _clear_dashboard_state()

    def _fake_load_state_from_disk_cache(*, demo_mode: bool) -> bool:
        _ = demo_mode
        _set_state_with_df(_single_event_df())
        web_api._state.demo_mode = False
        return True

    def _unexpected_refresh(*, demo_mode: bool) -> None:
        _ = demo_mode
        raise AssertionError(
            "_refresh_state_sync should not run when disk cache is ready"
        )

    monkeypatch.setattr(
        web_api, "_load_state_from_disk_cache", _fake_load_state_from_disk_cache
    )
    monkeypatch.setattr(web_api, "_refresh_state_sync", _unexpected_refresh)
    monkeypatch.setattr(web_api, "_env_demo_mode", lambda: False)

    client = TestClient(web_api.app)
    res = client.get("/api/dashboard/home?weeks=12&granularity=W")
    assert res.status_code == 200


def test_dashboard_home_validates_weeks(monkeypatch) -> None:
    async def _noop_ensure_state(*, refresh: bool) -> None:
        _ = refresh
        return None

    monkeypatch.setattr(web_api, "_ensure_state", _noop_ensure_state)
    _stub_all_figures(monkeypatch)

    df = pd.DataFrame(
        [
            {
                "date": "2025-01-15",
                "id": "e1",
                "title": "t1",
                "type": "completed",
                "parent_project_name": "A",
                "root_project_name": "A",
                "task_id": "1",
            }
        ]
    )
    df["date"] = pd.to_datetime(df["date"])
    df.set_index("date", inplace=True)
    _set_state_with_df(df)

    client = TestClient(web_api.app)
    res = client.get("/api/dashboard/home?weeks=10000")
    assert res.status_code == 400


def test_dashboard_home_requires_beg_and_end(monkeypatch) -> None:
    async def _noop_ensure_state(*, refresh: bool) -> None:
        _ = refresh
        return None

    monkeypatch.setattr(web_api, "_ensure_state", _noop_ensure_state)
    _stub_all_figures(monkeypatch)

    df = pd.DataFrame(
        [
            {
                "date": "2025-01-15",
                "id": "e1",
                "title": "t1",
                "type": "completed",
                "parent_project_name": "A",
                "root_project_name": "A",
                "task_id": "1",
            }
        ]
    )
    df["date"] = pd.to_datetime(df["date"])
    df.set_index("date", inplace=True)
    _set_state_with_df(df)

    client = TestClient(web_api.app)
    res = client.get("/api/dashboard/home?beg=2025-01-01")
    assert res.status_code == 400


def test_dashboard_home_last_completed_week_parent_share(monkeypatch) -> None:
    async def _noop_ensure_state(*, refresh: bool) -> None:
        _ = refresh
        return None

    monkeypatch.setattr(web_api, "_ensure_state", _noop_ensure_state)
    _stub_all_figures(monkeypatch)

    # Anchor date is 2025-01-15 (Wed). Last completed ISO week is 2025-01-06..2025-01-12.
    df = pd.DataFrame(
        [
            # In last completed week:
            {
                "date": "2025-01-06",
                "id": "c1",
                "title": "x",
                "type": "completed",
                "parent_project_name": "Parent A",
                "root_project_name": "Root 1",
                "task_id": "t1",
            },
            {
                "date": "2025-01-07",
                "id": "c2",
                "title": "y",
                "type": "completed",
                "parent_project_name": "Parent A",
                "root_project_name": "Root 1",
                "task_id": "t2",
            },
            {
                "date": "2025-01-08",
                "id": "c3",
                "title": "z",
                "type": "completed",
                "parent_project_name": "Parent B",
                "root_project_name": "Root 2",
                "task_id": "t3",
            },
            # Not completed:
            {
                "date": "2025-01-09",
                "id": "a1",
                "title": "n",
                "type": "added",
                "parent_project_name": "Parent A",
                "root_project_name": "Root 1",
                "task_id": "t4",
            },
            # Anchor (partial week, should be excluded from last completed week):
            {
                "date": "2025-01-15",
                "id": "c4",
                "title": "w",
                "type": "completed",
                "parent_project_name": "Parent C",
                "root_project_name": "Root 3",
                "task_id": "t5",
            },
        ]
    )
    df["date"] = pd.to_datetime(df["date"])
    df.set_index("date", inplace=True)
    _set_state_with_df(df)

    client = TestClient(web_api.app)
    res = client.get("/api/dashboard/home?weeks=12&granularity=W")
    assert res.status_code == 200
    payload = res.json()

    last_week = payload["leaderboards"]["lastCompletedWeek"]
    assert "weeklyCompletionTrend" in payload["figures"]
    assert "activeProjectHierarchy" in payload["figures"]
    assert "mostPopularLabels" not in payload["figures"]
    assert last_week["label"] == "2025-01-06 to 2025-01-12"
    parent_items = last_week["parentProjects"]["items"]
    assert last_week["parentProjects"]["totalCompleted"] == 3

    by_name = {it["name"]: it for it in parent_items}
    assert by_name["Parent A"]["completed"] == 2
    assert by_name["Parent B"]["completed"] == 1
    assert abs(by_name["Parent A"]["percentOfCompleted"] - 66.67) < 0.02
    assert abs(by_name["Parent B"]["percentOfCompleted"] - 33.33) < 0.02


def test_dashboard_home_handles_empty_activity(monkeypatch) -> None:
    async def _noop_ensure_state(*, refresh: bool) -> None:
        _ = refresh
        return None

    monkeypatch.setattr(web_api, "_ensure_state", _noop_ensure_state)
    _stub_all_figures(monkeypatch)

    df = pd.DataFrame(
        columns=pd.Index(
            [
                "date",
                "id",
                "title",
                "type",
                "parent_project_name",
                "root_project_name",
                "task_id",
            ]
        )
    )
    df["date"] = pd.to_datetime(df["date"])
    df.set_index("date", inplace=True)
    _set_state_with_df(df)

    client = TestClient(web_api.app)
    res = client.get("/api/dashboard/home?weeks=12")
    assert res.status_code == 200
    payload = res.json()
    assert payload["range"]["weeks"] == 12
    assert payload["leaderboards"]["lastCompletedWeek"]["label"]
    assert payload.get("noData") is True


def test_dashboard_home_includes_habit_tracker_summary(monkeypatch) -> None:
    async def _noop_ensure_state(*, refresh: bool) -> None:
        _ = refresh
        return None

    monkeypatch.setattr(web_api, "_ensure_state", _noop_ensure_state)
    _stub_all_figures(monkeypatch)

    df = pd.DataFrame(
        [
            {
                "date": "2025-01-07",
                "id": "c1",
                "title": "Morning walk",
                "type": "completed",
                "parent_project_name": "Health",
                "root_project_name": "Health",
                "task_id": "habit-1",
            },
            {
                "date": "2025-01-08",
                "id": "r1",
                "title": "Morning walk",
                "type": "rescheduled",
                "parent_project_name": "Health",
                "root_project_name": "Health",
                "task_id": "habit-1",
            },
            {
                "date": "2025-01-15",
                "id": "anchor-1",
                "title": "Another task",
                "type": "completed",
                "parent_project_name": "Health",
                "root_project_name": "Health",
                "task_id": "anchor-task",
            },
        ]
    )
    df["date"] = pd.to_datetime(df["date"])
    df.set_index("date", inplace=True)
    web_api._state.df_activity = df
    web_api._state.active_projects = [
        make_project(
            project_id="project-1",
            project_entry=make_project_entry(
                project_id="project-1",
                name="Health",
                color="green",
            ),
            tasks=[
                make_task(
                    "habit-1",
                    content="Morning walk",
                    project_id="project-1",
                    labels=["track_habit"],
                )
            ],
        )
    ]
    web_api._state.project_colors = {"Health": "#00aa88"}
    web_api._state.db = None
    web_api._state.home_payload_cache = {}

    client = TestClient(web_api.app)
    res = client.get("/api/dashboard/home?weeks=12&granularity=W")
    assert res.status_code == 200
    payload = res.json()

    habit_tracker = payload["habitTracker"]
    assert habit_tracker["trackedCount"] == 1
    assert habit_tracker["totals"]["weeklyCompleted"] == 1
    assert habit_tracker["totals"]["weeklyRescheduled"] == 1
    assert habit_tracker["items"][0]["name"] == "Morning walk"
    assert habit_tracker["figure"]["data"]


def test_dashboard_home_normalizes_integer_activity_index(monkeypatch) -> None:
    async def _noop_ensure_state(*, refresh: bool) -> None:
        _ = refresh
        return None

    monkeypatch.setattr(web_api, "_ensure_state", _noop_ensure_state)
    _stub_all_figures(monkeypatch)

    df = pd.DataFrame(
        [
            {
                "date": "2025-01-07",
                "id": "e1",
                "title": "Morning walk",
                "type": "completed",
                "parent_project_name": "Health",
                "root_project_name": "Health",
                "task_id": "habit-1",
            },
            {
                "date": "2025-01-08",
                "id": "e2",
                "title": "Morning walk",
                "type": "rescheduled",
                "parent_project_name": "Health",
                "root_project_name": "Health",
                "task_id": "habit-1",
            },
        ]
    )
    df.index = [0, 1]
    web_api._state.df_activity = df
    web_api._state.active_projects = []
    web_api._state.project_colors = {"Health": "#00aa88"}
    web_api._state.db = None
    web_api._state.home_payload_cache = {}

    client = TestClient(web_api.app)
    res = client.get("/api/dashboard/home?weeks=12&granularity=W")
    assert res.status_code == 200
    payload = res.json()
    assert payload["metrics"]["items"]


def test_dashboard_status_returns_services() -> None:
    client = TestClient(web_api.app)
    res = client.get("/api/dashboard/status")
    assert res.status_code == 200
    payload = res.json()
    assert isinstance(payload.get("services"), list)
    assert any(svc.get("name") == "Todoist token" for svc in payload["services"])
    assert payload["configurableItems"][0]["icon"] == "wrench"


def test_dashboard_home_includes_urgency_status(monkeypatch) -> None:
    async def _noop_ensure_state(*, refresh: bool) -> None:
        _ = refresh
        return None

    monkeypatch.setattr(web_api, "_ensure_state", _noop_ensure_state)
    monkeypatch.setattr(
        web_api,
        "_DASHBOARD_CONFIG_PATH",
        web_api._REPO_ROOT / "configs" / "dashboard.yaml",
    )
    _stub_all_figures(monkeypatch)

    df = _single_event_df()
    web_api._state.df_activity = df
    web_api._state.active_projects = [
        make_project(
            project_id="proj-urgency",
            project_entry=make_project_entry(project_id="proj-urgency", name="Urgency"),
            tasks=[
                make_task("p1-1", content="Priority 1", priority=4),
                make_task(
                    "due-1",
                    content="Due today",
                    due={"date": date.today().isoformat()},
                ),
            ],
        )
    ]
    web_api._state.project_colors = {"Urgency": "#44aa66"}
    web_api._state.db = None
    web_api._state.home_payload_cache = {}

    client = TestClient(web_api.app)
    res = client.get("/api/dashboard/home?weeks=12&granularity=W")

    assert res.status_code == 200
    payload = res.json()
    urgency_status = payload["urgencyStatus"]
    assert urgency_status["state"] == "warn"
    assert urgency_status["badgeLabel"] == "Watch"
    assert urgency_status["total"] == 2
    assert urgency_status["counts"]["p1Tasks"] == 1
    assert urgency_status["counts"]["dueTasks"] == 1
    assert urgency_status["counts"]["fireTasks"] == 0
    assert urgency_status["visibleChips"] == [
        "fireTasks",
        "p1Tasks",
        "p2Tasks",
        "dueTasks",
        "deadlineTasks",
    ]
    assert payload["configurableItems"][0]["icon"] == "wrench"
    assert isinstance(payload["figures"]["activeProjectHierarchy"], dict)
