"""Tests for FastAPI web dashboard endpoints."""

from datetime import date

import pandas as pd
import plotly.graph_objects as go
from fastapi.testclient import TestClient

from tests.factories import make_project, make_project_entry, make_task
import todoist
import todoist.web.api as web_api

# pylint: disable=protected-access


def _stub_all_figures(monkeypatch) -> None:
    monkeypatch.setattr(
        web_api, "plot_weekly_completion_trend", lambda *args, **kwargs: go.Figure()
    )
    monkeypatch.setattr(
        web_api, "plot_task_lifespans", lambda *args, **kwargs: go.Figure()
    )
    monkeypatch.setattr(
        web_api,
        "plot_completed_tasks_periodically",
        lambda *args, **kwargs: go.Figure(),
    )
    monkeypatch.setattr(
        web_api,
        "cumsum_completed_tasks_periodically",
        lambda *args, **kwargs: go.Figure(),
    )
    monkeypatch.setattr(
        web_api,
        "plot_active_project_hierarchy",
        lambda *args, **kwargs: go.Figure(),
    )
    monkeypatch.setattr(
        web_api,
        "plot_heatmap_of_events_by_day_and_hour",
        lambda *args, **kwargs: go.Figure(),
    )
    monkeypatch.setattr(
        web_api, "plot_events_over_time", lambda *args, **kwargs: go.Figure()
    )


def _set_state_with_df(df: pd.DataFrame) -> None:
    web_api._state.df_activity = df
    web_api._state.active_projects = []
    web_api._state.project_colors = {}
    web_api._state.db = None
    web_api._state.home_payload_cache = {}


def _clear_dashboard_state() -> None:
    web_api._state.df_activity = None
    web_api._state.active_projects = None
    web_api._state.project_colors = None
    web_api._state.db = None
    web_api._state.demo_mode = False
    web_api._state.home_payload_cache = {}


def _single_event_df() -> pd.DataFrame:
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
    return df.set_index("date")


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
            "activity_cache_signature": web_api._activity_cache_signature(),
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
        raise AssertionError("_refresh_state_sync should not run when disk cache is ready")

    monkeypatch.setattr(web_api, "_load_state_from_disk_cache", _fake_load_state_from_disk_cache)
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


def test_admin_timezone_status_uses_system_timezone_when_not_configured(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv(str(web_api.EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(str(web_api.EnvVar.TIMEZONE), raising=False)
    monkeypatch.setattr(web_api, "_detect_system_timezone", lambda: "UTC")

    client = TestClient(web_api.app)
    res = client.get("/api/admin/timezone")
    assert res.status_code == 200
    payload = res.json()
    assert payload["configured"] is False
    assert payload["timezone"] == "UTC"
    assert payload["source"] == "system"
    assert payload["override"] is None
    assert payload["overrideValid"] is True


def test_admin_timezone_set_and_clear(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(str(web_api.EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(web_api, "_detect_system_timezone", lambda: "UTC")

    client = TestClient(web_api.app)

    set_response = client.post(
        "/api/admin/timezone",
        json={"timezone": "Europe/Warsaw"},
    )
    assert set_response.status_code == 200
    set_payload = set_response.json()
    assert set_payload["configured"] is True
    assert set_payload["timezone"] == "Europe/Warsaw"
    assert set_payload["source"] == "env"
    assert set_payload["override"] == "Europe/Warsaw"
    assert set_payload["overrideValid"] is True
    assert web_api.os.getenv(str(web_api.EnvVar.TIMEZONE)) == "Europe/Warsaw"

    env_path = tmp_path / ".env"
    assert env_path.exists()
    env_text = env_path.read_text(encoding="utf-8")
    assert "TODOIST_TIMEZONE" in env_text
    assert "Europe/Warsaw" in env_text

    clear_response = client.delete("/api/admin/timezone")
    assert clear_response.status_code == 200
    clear_payload = clear_response.json()
    assert clear_payload["configured"] is False
    assert clear_payload["timezone"] == "UTC"
    assert clear_payload["source"] == "system"
    assert clear_payload["override"] is None
    assert web_api.os.getenv(str(web_api.EnvVar.TIMEZONE)) is None

    env_text_after_clear = env_path.read_text(encoding="utf-8")
    assert "TODOIST_TIMEZONE" not in env_text_after_clear


def test_admin_timezone_rejects_invalid_timezone(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(str(web_api.EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(web_api, "_detect_system_timezone", lambda: "UTC")

    client = TestClient(web_api.app)
    response = client.post(
        "/api/admin/timezone",
        json={"timezone": "Invalid/Timezone"},
    )
    assert response.status_code == 400
    payload = response.json()
    assert "Invalid timezone" in payload["detail"]


def test_openapi_includes_app_version() -> None:
    client = TestClient(web_api.app)
    res = client.get("/openapi.json")
    assert res.status_code == 200
    payload = res.json()
    assert payload["info"]["version"] == web_api.app.version == todoist.__version__


def test_dashboard_progress_inactive_state() -> None:
    """Test progress endpoint returns correct structure when inactive."""
    # Reset progress state to inactive
    web_api._progress_state.active = False
    web_api._progress_state.stage = None
    web_api._progress_state.step = 0
    web_api._progress_state.total_steps = 0
    web_api._progress_state.started_at = None
    web_api._progress_state.updated_at = "2025-01-01T00:00:00"
    web_api._progress_state.detail = None
    web_api._progress_state.error = None

    client = TestClient(web_api.app)
    res = client.get("/api/dashboard/progress")
    assert res.status_code == 200
    payload = res.json()

    # Verify structure
    assert "active" in payload
    assert "stage" in payload
    assert "step" in payload
    assert "totalSteps" in payload
    assert "startedAt" in payload
    assert "updatedAt" in payload
    assert "detail" in payload
    assert "error" in payload

    # Verify inactive state
    assert payload["active"] is False
    assert payload["stage"] is None
    assert payload["step"] == 0
    assert payload["totalSteps"] == 0
    assert payload["startedAt"] is None
    assert payload["error"] is None


def test_dashboard_progress_active_state() -> None:
    """Test progress endpoint returns correct structure when active."""
    # Set progress state to active
    web_api._progress_state.active = True
    web_api._progress_state.stage = "Loading data"
    web_api._progress_state.step = 2
    web_api._progress_state.total_steps = 5
    web_api._progress_state.started_at = "2025-01-01T10:00:00"
    web_api._progress_state.updated_at = "2025-01-01T10:00:30"
    web_api._progress_state.detail = "Fetching projects"
    web_api._progress_state.error = None

    client = TestClient(web_api.app)
    res = client.get("/api/dashboard/progress")
    assert res.status_code == 200
    payload = res.json()

    # Verify active state with all fields populated
    assert payload["active"] is True
    assert payload["stage"] == "Loading data"
    assert payload["step"] == 2
    assert payload["totalSteps"] == 5
    assert payload["startedAt"] == "2025-01-01T10:00:00"
    assert payload["updatedAt"] == "2025-01-01T10:00:30"
    assert payload["detail"] == "Fetching projects"
    assert payload["error"] is None


def test_dashboard_progress_with_error() -> None:
    """Test progress endpoint returns error state correctly."""
    # Set progress state with error
    web_api._progress_state.active = False
    web_api._progress_state.stage = None
    web_api._progress_state.step = 0
    web_api._progress_state.total_steps = 0
    web_api._progress_state.started_at = None
    web_api._progress_state.updated_at = "2025-01-01T10:05:00"
    web_api._progress_state.detail = None
    web_api._progress_state.error = "Failed to connect to API"

    client = TestClient(web_api.app)
    res = client.get("/api/dashboard/progress")
    assert res.status_code == 200
    payload = res.json()

    # Verify error is captured
    assert payload["active"] is False
    assert payload["error"] == "Failed to connect to API"
    assert payload["updatedAt"] == "2025-01-01T10:05:00"


def test_dashboard_progress_without_error() -> None:
    """Test progress endpoint handles state without error correctly."""
    # Set progress state without error
    web_api._progress_state.active = True
    web_api._progress_state.stage = "Processing"
    web_api._progress_state.step = 1
    web_api._progress_state.total_steps = 3
    web_api._progress_state.started_at = "2025-01-01T12:00:00"
    web_api._progress_state.updated_at = "2025-01-01T12:00:15"
    web_api._progress_state.detail = None
    web_api._progress_state.error = None

    client = TestClient(web_api.app)
    res = client.get("/api/dashboard/progress")
    assert res.status_code == 200
    payload = res.json()

    # Verify no error
    assert payload["active"] is True
    assert payload["error"] is None
    assert payload["stage"] == "Processing"


# LLM Chat endpoint tests


def test_dashboard_llm_chat_returns_structure(monkeypatch, tmp_path) -> None:
    """Test /api/dashboard/llm_chat returns expected structure when model not loaded."""
    monkeypatch.delenv("OPEN_AI_SECRET_KEY", raising=False)
    monkeypatch.delenv("OPEN_AI_KEY_NAME", raising=False)
    monkeypatch.delenv("OPEN_AI_MODEL", raising=False)
    monkeypatch.setattr(web_api, "_resolve_env_path", lambda: tmp_path / ".env")

    # Mock the model status to be disabled
    async def _mock_model_status():
        return False, False  # enabled, loading

    monkeypatch.setattr(web_api, "_llm_chat_model_status", _mock_model_status)

    # Mock storage functions to return empty data
    monkeypatch.setattr(web_api, "_load_llm_chat_queue", lambda: [])
    monkeypatch.setattr(web_api, "_load_llm_chat_conversations", lambda: [])

    client = TestClient(web_api.app)
    res = client.get("/api/dashboard/llm_chat")
    assert res.status_code == 200
    payload = res.json()

    # Verify structure
    assert "enabled" in payload
    assert "loading" in payload
    assert "backend" in payload
    assert "device" in payload
    assert "queue" in payload
    assert "conversations" in payload

    # Verify queue structure
    assert "total" in payload["queue"]
    assert "queued" in payload["queue"]
    assert "running" in payload["queue"]
    assert "done" in payload["queue"]
    assert "failed" in payload["queue"]
    assert "items" in payload["queue"]
    assert "current" in payload["queue"]

    # Verify disabled state
    assert payload["enabled"] is False
    assert payload["loading"] is False
    assert payload["backend"]["selected"] == "transformers_local"
    assert payload["device"]["selected"] == "cpu"
    assert payload["queue"]["total"] == 0
    assert payload["conversations"] == []


def test_llm_chat_update_settings_persists_env_and_resets_runtime(
    monkeypatch, tmp_path
) -> None:
    env_path = tmp_path / ".env"
    monkeypatch.setattr(web_api, "_resolve_env_path", lambda: env_path)
    monkeypatch.setattr(web_api, "_available_llm_chat_devices", lambda: ["cpu", "cuda"])
    monkeypatch.setattr(web_api, "_LLM_CHAT_MODEL", object())
    monkeypatch.setattr(web_api, "_LLM_CHAT_AGENT", object())
    monkeypatch.setattr(web_api, "_LLM_CHAT_MODEL_LOADING", False)

    client = TestClient(web_api.app)
    res = client.put(
        "/api/llm_chat/settings",
        json={"backend": "transformers_local", "device": "cuda"},
    )

    assert res.status_code == 200
    payload = res.json()
    assert payload["backend"] == "transformers_local"
    assert payload["device"] == "cuda"
    assert payload["reloadedRequired"] is True
    assert env_path.read_text(encoding="utf-8").find("TODOIST_AGENT_DEVICE='cuda'") >= 0
    assert web_api._LLM_CHAT_MODEL is None
    assert web_api._LLM_CHAT_AGENT is None


def test_llm_chat_update_settings_rejects_unavailable_device(monkeypatch) -> None:
    monkeypatch.setattr(web_api, "_available_llm_chat_devices", lambda: ["cpu"])

    client = TestClient(web_api.app)
    res = client.put(
        "/api/llm_chat/settings",
        json={"backend": "transformers_local", "device": "cuda"},
    )

    assert res.status_code == 400


def test_dashboard_home_includes_urgency_status(monkeypatch) -> None:
    async def _noop_ensure_state(*, refresh: bool) -> None:
        _ = refresh
        return None

    monkeypatch.setattr(web_api, "_ensure_state", _noop_ensure_state)
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
    assert isinstance(payload["figures"]["activeProjectHierarchy"], dict)


def test_llm_chat_update_settings_supports_openai_backend(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("OPEN_AI_SECRET_KEY", "sk-test")
    monkeypatch.setenv("OPEN_AI_KEY_NAME", "primary-key")
    monkeypatch.setenv("OPEN_AI_MODEL", "gpt-5-mini")
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "OPEN_AI_SECRET_KEY='sk-test'",
                "OPEN_AI_KEY_NAME='primary-key'",
                "OPEN_AI_MODEL='gpt-5-mini'",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(web_api, "_resolve_env_path", lambda: env_path)
    monkeypatch.setattr(web_api, "_available_llm_chat_devices", lambda: ["cpu", "cuda"])
    monkeypatch.setattr(web_api, "_LLM_CHAT_MODEL", object())
    monkeypatch.setattr(web_api, "_LLM_CHAT_AGENT", object())
    monkeypatch.setattr(web_api, "_LLM_CHAT_MODEL_LOADING", False)

    client = TestClient(web_api.app)
    res = client.put(
        "/api/llm_chat/settings",
        json={"backend": "openai", "device": "cpu"},
    )

    assert res.status_code == 200
    payload = res.json()
    assert payload["backend"] == "openai"
    assert payload["openai"]["configured"] is True
    assert payload["openai"]["keyName"] == "primary-key"
    assert payload["openai"]["model"] == "gpt-5-mini"
    assert web_api._LLM_CHAT_MODEL is None
    assert web_api._LLM_CHAT_AGENT is None


def test_llm_chat_send_requires_message() -> None:
    """Test /api/llm_chat/send validates message is required."""
    client = TestClient(web_api.app)
    res = client.post("/api/llm_chat/send", json={})
    assert res.status_code == 400
    payload = res.json()
    assert "message is required" in payload["detail"]


def test_llm_chat_send_requires_model_loaded(monkeypatch) -> None:
    """Test /api/llm_chat/send requires model to be loaded or loading."""

    # Mock the model status to be disabled
    async def _mock_model_status():
        return False, False  # enabled, loading

    monkeypatch.setattr(web_api, "_llm_chat_model_status", _mock_model_status)

    client = TestClient(web_api.app)
    res = client.post("/api/llm_chat/send", json={"message": "Hello"})
    assert res.status_code == 409
    payload = res.json()
    assert "Model not loaded" in payload["detail"]


def test_llm_chat_send_creates_new_conversation(monkeypatch) -> None:
    """Test /api/llm_chat/send creates a new conversation when no conversation_id provided."""

    # Mock the model status to be enabled
    async def _mock_model_status():
        return True, False  # enabled, loading

    # Track what was saved
    saved_queue = []
    saved_conversations = []

    def _mock_save_queue(items):
        saved_queue.clear()
        saved_queue.extend(items)

    def _mock_save_conversations(items):
        saved_conversations.clear()
        saved_conversations.extend(items)

    monkeypatch.setattr(web_api, "_llm_chat_model_status", _mock_model_status)
    monkeypatch.setattr(web_api, "_load_llm_chat_queue", lambda: [])
    monkeypatch.setattr(web_api, "_load_llm_chat_conversations", lambda: [])
    monkeypatch.setattr(web_api, "_save_llm_chat_queue", _mock_save_queue)
    monkeypatch.setattr(
        web_api, "_save_llm_chat_conversations", _mock_save_conversations
    )
    monkeypatch.setattr(web_api, "_prune_queue", lambda q: q)

    # Mock worker start to do nothing
    async def _mock_start_worker():
        pass

    monkeypatch.setattr(web_api, "_maybe_start_llm_chat_worker", _mock_start_worker)

    client = TestClient(web_api.app)
    res = client.post("/api/llm_chat/send", json={"message": "Hello, world!"})
    assert res.status_code == 200
    payload = res.json()

    # Verify response structure
    assert payload["queued"] is True
    assert "item" in payload
    assert "conversationId" in payload

    # Verify a conversation was created
    assert len(saved_conversations) == 1
    conv = saved_conversations[0]
    assert conv["title"] == "Hello, world!"
    assert conv["id"] == payload["conversationId"]
    assert "created_at" in conv
    assert "updated_at" in conv
    assert conv["messages"] == []

    # Verify queue item was created
    assert len(saved_queue) == 1
    item = saved_queue[0]
    assert item["conversation_id"] == payload["conversationId"]
    assert item["content"] == "Hello, world!"
    assert item["status"] == "queued"


def test_llm_chat_send_uses_existing_conversation(monkeypatch) -> None:
    """Test /api/llm_chat/send adds to existing conversation when conversation_id provided."""

    # Mock the model status to be enabled
    async def _mock_model_status():
        return True, False  # enabled, loading

    existing_conv_id = "550e8400-e29b-41d4-a716-446655440000"
    existing_conversations = [
        {
            "id": existing_conv_id,
            "title": "Existing Chat",
            "created_at": "2025-01-01T10:00:00",
            "updated_at": "2025-01-01T10:00:00",
            "messages": [],
        }
    ]

    # Track what was saved
    saved_queue = []
    saved_conversations = []

    def _mock_save_queue(items):
        saved_queue.clear()
        saved_queue.extend(items)

    def _mock_save_conversations(items):
        saved_conversations.clear()
        saved_conversations.extend(items)

    monkeypatch.setattr(web_api, "_llm_chat_model_status", _mock_model_status)
    monkeypatch.setattr(web_api, "_load_llm_chat_queue", lambda: [])
    monkeypatch.setattr(
        web_api, "_load_llm_chat_conversations", lambda: existing_conversations[:]
    )
    monkeypatch.setattr(web_api, "_save_llm_chat_queue", _mock_save_queue)
    monkeypatch.setattr(
        web_api, "_save_llm_chat_conversations", _mock_save_conversations
    )
    monkeypatch.setattr(web_api, "_prune_queue", lambda q: q)

    # Mock worker start to do nothing
    async def _mock_start_worker():
        pass

    monkeypatch.setattr(web_api, "_maybe_start_llm_chat_worker", _mock_start_worker)

    client = TestClient(web_api.app)
    res = client.post(
        "/api/llm_chat/send",
        json={"message": "Follow up", "conversationId": existing_conv_id},
    )
    assert res.status_code == 200
    payload = res.json()

    # Verify response uses existing conversation
    assert payload["conversationId"] == existing_conv_id

    # Verify conversation was updated (not created)
    assert len(saved_conversations) == 1
    assert saved_conversations[0]["id"] == existing_conv_id
    assert saved_conversations[0]["title"] == "Existing Chat"  # Title unchanged


def test_llm_chat_send_rejects_invalid_conversation_id(monkeypatch) -> None:
    """Test /api/llm_chat/send returns 404 for non-existent conversation_id."""

    # Mock the model status to be enabled
    async def _mock_model_status():
        return True, False  # enabled, loading

    monkeypatch.setattr(web_api, "_llm_chat_model_status", _mock_model_status)
    monkeypatch.setattr(web_api, "_load_llm_chat_queue", lambda: [])
    monkeypatch.setattr(web_api, "_load_llm_chat_conversations", lambda: [])

    client = TestClient(web_api.app)
    res = client.post(
        "/api/llm_chat/send",
        json={
            "message": "Test",
            "conversationId": "550e8400-e29b-41d4-a716-446655440000",  # Valid UUID format but doesn't exist
        },
    )
    assert res.status_code == 404
    payload = res.json()
    assert "Conversation not found" in payload["detail"]


def test_llm_chat_conversation_validates_uuid_format() -> None:
    """Test /api/llm_chat/conversations/{id} validates UUID format."""
    client = TestClient(web_api.app)
    res = client.get("/api/llm_chat/conversations/not-a-uuid")
    assert res.status_code == 400
    payload = res.json()
    assert "Invalid conversation ID format" in payload["detail"]


def test_llm_chat_conversation_returns_404_for_missing(monkeypatch) -> None:
    """Test /api/llm_chat/conversations/{id} returns 404 for non-existent conversation."""
    monkeypatch.setattr(web_api, "_load_llm_chat_conversations", lambda: [])

    client = TestClient(web_api.app)
    valid_uuid = "550e8400-e29b-41d4-a716-446655440000"
    res = client.get(f"/api/llm_chat/conversations/{valid_uuid}")
    assert res.status_code == 404
    payload = res.json()
    assert "Conversation not found" in payload["detail"]


def test_llm_chat_conversation_returns_conversation_data(monkeypatch) -> None:
    """Test /api/llm_chat/conversations/{id} returns conversation with messages."""
    conv_id = "550e8400-e29b-41d4-a716-446655440000"
    mock_conversations = [
        {
            "id": conv_id,
            "title": "Test Chat",
            "created_at": "2025-01-01T10:00:00",
            "updated_at": "2025-01-01T10:05:00",
            "messages": [
                {
                    "role": "user",
                    "content": "Hello",
                    "created_at": "2025-01-01T10:00:00",
                },
                {
                    "role": "assistant",
                    "content": "Hi there!",
                    "created_at": "2025-01-01T10:00:05",
                },
            ],
        }
    ]

    monkeypatch.setattr(
        web_api, "_load_llm_chat_conversations", lambda: mock_conversations
    )

    client = TestClient(web_api.app)
    res = client.get(f"/api/llm_chat/conversations/{conv_id}")
    assert res.status_code == 200
    payload = res.json()

    # Verify conversation data
    assert payload["id"] == conv_id
    assert payload["title"] == "Test Chat"
    assert payload["createdAt"] == "2025-01-01T10:00:00"
    assert payload["updatedAt"] == "2025-01-01T10:05:00"
    assert len(payload["messages"]) == 2

    # Verify messages
    assert payload["messages"][0]["role"] == "user"
    assert payload["messages"][0]["content"] == "Hello"
    assert payload["messages"][0]["createdAt"] == "2025-01-01T10:00:00"

    assert payload["messages"][1]["role"] == "assistant"
    assert payload["messages"][1]["content"] == "Hi there!"
    assert payload["messages"][1]["createdAt"] == "2025-01-01T10:00:05"


def test_llm_chat_enable_returns_status(monkeypatch) -> None:
    """Test /api/llm_chat/enable returns model status."""

    # Mock start load to do nothing
    async def _mock_start_load():
        pass

    # Mock status to return loading state
    async def _mock_model_status():
        return False, True  # enabled, loading

    monkeypatch.setattr(web_api, "_start_llm_chat_model_load", _mock_start_load)
    monkeypatch.setattr(web_api, "_llm_chat_model_status", _mock_model_status)

    client = TestClient(web_api.app)
    res = client.post("/api/llm_chat/enable")
    assert res.status_code == 200
    payload = res.json()

    # Verify status structure
    assert "enabled" in payload
    assert "loading" in payload
    assert payload["enabled"] is False
    assert payload["loading"] is True


def test_llm_chat_send_starts_worker_when_loading(monkeypatch) -> None:
    """Test /api/llm_chat/send starts worker when model is loading."""

    # Mock the model status to be loading
    async def _mock_model_status():
        return False, True  # enabled=False, loading=True

    worker_started = []

    async def _mock_start_worker():
        worker_started.append(True)

    monkeypatch.setattr(web_api, "_llm_chat_model_status", _mock_model_status)
    monkeypatch.setattr(web_api, "_load_llm_chat_queue", lambda: [])
    monkeypatch.setattr(web_api, "_load_llm_chat_conversations", lambda: [])
    monkeypatch.setattr(web_api, "_save_llm_chat_queue", lambda x: None)
    monkeypatch.setattr(web_api, "_save_llm_chat_conversations", lambda x: None)
    monkeypatch.setattr(web_api, "_prune_queue", lambda q: q)
    monkeypatch.setattr(web_api, "_maybe_start_llm_chat_worker", _mock_start_worker)

    client = TestClient(web_api.app)
    res = client.post("/api/llm_chat/send", json={"message": "Test"})
    assert res.status_code == 200

    # Verify worker was started (fix for review comment about loading=True)
    assert len(worker_started) == 1


def test_build_chat_messages_filters_system_messages(monkeypatch) -> None:
    """Test _build_chat_messages filters system messages from conversation history."""
    # Set a system prompt
    monkeypatch.setattr(web_api, "_CHAT_SYSTEM_PROMPT", "System instructions")

    conversation = {
        "messages": [
            {"role": "system", "content": "Old system message"},
            {"role": "user", "content": "User message 1"},
            {"role": "assistant", "content": "Assistant response 1"},
            {"role": "user", "content": "User message 2"},
        ]
    }

    messages = web_api._build_chat_messages(conversation, "New user message")

    # Verify system prompt is at the start
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "System instructions"

    # Verify old system message is filtered out
    system_count = sum(1 for msg in messages if msg["role"] == "system")
    assert system_count == 1

    # Verify other messages are included
    assert len(messages) == 5  # system + 2 user + 1 assistant + new user
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "User message 1"
    assert messages[2]["role"] == "assistant"
    assert messages[3]["role"] == "user"
    assert messages[3]["content"] == "User message 2"
    assert messages[4]["role"] == "user"
    assert messages[4]["content"] == "New user message"
