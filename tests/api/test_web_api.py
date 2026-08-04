"""Tests for FastAPI dashboard home endpoints."""

from datetime import date

import pandas as pd
import plotly.graph_objects as go

from tests.factories import make_project, make_project_entry, make_task
from tests.web_api_helpers import (
    _clear_dashboard_state,
    _set_state_with_df,
    _single_event_df,
    _stub_all_figures,
)
import todoist.web.api as web_api
import todoist.web.routes.dashboard as dashboard_routes

# pylint: disable=protected-access


async def _noop_ensure_state(*, refresh: bool) -> None:
    _ = refresh


def _event_df(rows: list[dict[str, str]]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")


def _empty_event_df() -> pd.DataFrame:
    return _event_df(
        [
            {
                "date": "2025-01-15",
                "id": "anchor",
                "title": "anchor",
                "type": "added",
                "parent_project_name": "A",
                "root_project_name": "A",
                "task_id": "anchor",
            }
        ]
    ).iloc[:0]


def _set_dashboard_df(monkeypatch, df: pd.DataFrame) -> None:
    monkeypatch.setattr(web_api, "_ensure_state", _noop_ensure_state)
    _stub_all_figures(monkeypatch)
    _set_state_with_df(df)


def _home(api_client, query: str = "weeks=12&granularity=W"):
    return api_client.get(f"/api/dashboard/home?{query}")


def _dashboard_cache(monkeypatch, tmp_path) -> web_api.Cache:
    monkeypatch.setenv(str(web_api.EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.chdir(tmp_path)
    cache = web_api.Cache()
    cache.activity.save(set())
    return cache


def _save_dashboard_snapshot(cache: web_api.Cache, **overrides) -> None:
    payload = {
        "version": web_api._DASHBOARD_STATE_SCHEMA_VERSION,
        "created_at": "2025-01-01T00:00:00",
        "last_refresh_s": 123.0,
        "demo_mode": False,
        "activity_cache_signature": web_api._activity_cache_signature(),
        "adjustments_cache_signature": [],
        "df_activity": _single_event_df(),
        "active_projects": [],
        "archived_projects": [],
        "project_colors": {},
    }
    payload.update(overrides)
    cache.dashboard_state.save(payload)


def test_load_state_from_disk_cache_restores_payload(monkeypatch, tmp_path) -> None:
    cache = _dashboard_cache(monkeypatch, tmp_path)
    df = _single_event_df()
    _save_dashboard_snapshot(cache, df_activity=df, project_colors={"A": "#123456"})

    _clear_dashboard_state()
    loaded = web_api._load_state_from_disk_cache(demo_mode=False)
    assert loaded is True
    assert web_api._state.df_activity is not None
    assert len(web_api._state.df_activity) == 1
    assert web_api._state.project_colors == {"A": "#123456"}
    assert web_api._state.active_projects == []
    assert web_api._state.archived_projects == []


def test_load_state_from_disk_cache_rejects_stale_activity_signature(
    monkeypatch, tmp_path
) -> None:
    cache = _dashboard_cache(monkeypatch, tmp_path)
    _save_dashboard_snapshot(cache)

    # Mutate activity cache so signature no longer matches cached dashboard snapshot.
    cache.activity.save({"new-event"})

    _clear_dashboard_state()
    loaded = web_api._load_state_from_disk_cache(demo_mode=False)
    assert loaded is False


def test_load_state_from_disk_cache_rejects_stale_adjustment_signature(
    monkeypatch, tmp_path
) -> None:
    cache = _dashboard_cache(monkeypatch, tmp_path)
    _save_dashboard_snapshot(cache)

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
    _save_dashboard_snapshot(
        _dashboard_cache(monkeypatch, tmp_path),
        demo_mode=True,
        demo_state_version=web_api._DEMO_DASHBOARD_STATE_SCHEMA_VERSION - 1,
        project_colors={"A": "#123456"},
    )

    _clear_dashboard_state()
    loaded = web_api._load_state_from_disk_cache(demo_mode=True)
    assert loaded is False


def test_load_state_from_disk_cache_restores_current_demo_snapshot(
    monkeypatch, tmp_path
) -> None:
    cache = _dashboard_cache(monkeypatch, tmp_path)
    df = _single_event_df()
    _save_dashboard_snapshot(
        cache,
        demo_mode=True,
        demo_state_version=web_api._DEMO_DASHBOARD_STATE_SCHEMA_VERSION,
        df_activity=df,
        project_colors={"A": "#123456"},
    )

    _clear_dashboard_state()
    loaded = web_api._load_state_from_disk_cache(demo_mode=True)
    assert loaded is True
    assert web_api._state.df_activity is not None
    assert len(web_api._state.df_activity) == 1
    assert web_api._state.project_colors == {"A": "#123456"}
    assert web_api._state.active_projects == []
    assert web_api._state.archived_projects == []
    assert web_api._state.demo_mode is True


def test_dashboard_home_bootstraps_from_disk_cache_without_refresh(
    monkeypatch, api_client
) -> None:
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

    res = _home(api_client)
    assert res.status_code == 200


def test_dashboard_home_validates_weeks(monkeypatch, api_client) -> None:
    _set_dashboard_df(
        monkeypatch,
        _event_df(
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
        ),
    )

    res = _home(api_client, "weeks=10000")
    assert res.status_code == 400


def test_dashboard_home_requires_beg_and_end(monkeypatch, api_client) -> None:
    _set_dashboard_df(
        monkeypatch,
        _event_df(
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
        ),
    )

    res = _home(api_client, "beg=2025-01-01")
    assert res.status_code == 400


def test_dashboard_home_last_completed_week_parent_share(
    monkeypatch, api_client
) -> None:
    _set_dashboard_df(
        monkeypatch,
        _event_df(
            [
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
        ),
    )

    res = _home(api_client)
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


def test_dashboard_home_handles_empty_activity(monkeypatch, api_client) -> None:
    _set_dashboard_df(monkeypatch, _empty_event_df())

    res = _home(api_client, "weeks=12")
    assert res.status_code == 200
    payload = res.json()
    assert payload["range"]["weeks"] == 12
    assert payload["leaderboards"]["lastCompletedWeek"]["label"]
    assert payload.get("noData") is True


def test_dashboard_home_includes_habit_tracker_summary(monkeypatch, api_client) -> None:
    _set_dashboard_df(
        monkeypatch,
        _event_df(
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
        ),
    )
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

    res = _home(api_client)
    assert res.status_code == 200
    payload = res.json()

    habit_tracker = payload["habitTracker"]
    assert habit_tracker["trackedCount"] == 1
    assert habit_tracker["totals"]["weeklyCompleted"] == 1
    assert habit_tracker["totals"]["weeklyRescheduled"] == 1
    assert habit_tracker["items"][0]["name"] == "Morning walk"
    assert habit_tracker["figure"]["data"]


def test_dashboard_home_normalizes_integer_activity_index(
    monkeypatch, api_client
) -> None:
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
    _set_dashboard_df(monkeypatch, df)
    web_api._state.project_colors = {"Health": "#00aa88"}

    res = _home(api_client)
    assert res.status_code == 200
    payload = res.json()
    assert payload["metrics"]["items"]


def test_dashboard_status_returns_services(api_client) -> None:
    res = api_client.get("/api/dashboard/status")
    assert res.status_code == 200
    payload = res.json()
    assert isinstance(payload.get("services"), list)
    assert any(svc.get("name") == "Todoist token" for svc in payload["services"])
    assert payload["configurableItems"][0]["icon"] == "wrench"


def test_dashboard_home_includes_urgency_status(monkeypatch, api_client) -> None:
    _set_dashboard_df(monkeypatch, _single_event_df())
    monkeypatch.setattr(
        web_api,
        "_DASHBOARD_CONFIG_PATH",
        web_api._REPO_ROOT / "configs" / "dashboard.yaml",
    )

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

    res = _home(api_client)

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


def test_dashboard_home_passes_active_and_archived_projects_to_hierarchy(
    monkeypatch, api_client
) -> None:
    _set_dashboard_df(monkeypatch, _single_event_df())
    active = make_project(
        project_id="active",
        project_entry=make_project_entry(project_id="active", name="Active"),
    )
    archived = make_project(
        project_id="archived",
        project_entry=make_project_entry(
            project_id="archived", name="Archived", parent_id="active"
        ),
        is_archived=True,
    )
    web_api._state.active_projects = [active]
    web_api._state.archived_projects = [archived]
    captured: dict[str, object] = {}

    def _capture_hierarchy(*args, **kwargs):
        captured["projects"] = args[3]
        captured["mappings"] = kwargs["project_mappings"]
        captured["archived_parents"] = kwargs["archived_parent_projects"]
        return go.Figure()

    monkeypatch.setattr(web_api, "plot_active_project_hierarchy", _capture_hierarchy)
    monkeypatch.setattr(
        dashboard_routes, "get_adjusting_mapping", lambda: {"Archived": "Active"}
    )
    monkeypatch.setattr(
        dashboard_routes,
        "get_adjusting_archived_parent_projects",
        lambda: {"Archived"},
    )

    response = _home(api_client)

    assert response.status_code == 200
    assert [project.id for project in captured["projects"]] == [
        "active",
        "archived",
    ]
    assert captured["mappings"] == {"Archived": "Active"}
    assert captured["archived_parents"] == {"Archived"}
