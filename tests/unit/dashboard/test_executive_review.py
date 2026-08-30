from datetime import datetime

import pandas as pd

from tests.factories import make_project, make_project_entry
from todoist.dashboard._plot_project_lifecycle import plot_project_lifecycle_timeline
from todoist.dashboard.executive_review import review_context


def _activity() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "event_type": ["completed", "completed", "added"],
            "parent_project_name": ["Build", "Build", "Build"],
            "root_project_name": ["Product", "Product", "Product"],
        },
        index=pd.to_datetime(
            ["2026-08-24 09:00", "2026-08-25 14:00", "2026-08-26 10:00"]
        ),
    )


def test_review_context_compares_recent_activity() -> None:
    context = review_context(_activity(), [])

    assert context["completions"] == {"current": 2, "previous": 0}
    assert context["project_completions"]["current"] == {"Product": 2}
    assert context["workday_density"]["Monday"] == 1
    assert context["peak_completion_hours"] == [
        {"hour": 9, "count": 1},
        {"hour": 14, "count": 1},
    ]


def test_review_context_accepts_runtime_type_column() -> None:
    activity = _activity().rename(columns={"event_type": "type"})

    context = review_context(activity, [])

    assert context["completions"] == {"current": 2, "previous": 0}


def test_project_lifecycle_timeline_uses_parent_and_subproject_names() -> None:
    root = make_project(
        project_id="root",
        project_entry=make_project_entry(
            project_id="root",
            name="Product",
            created_at="2026-08-01T08:00:00Z",
            updated_at="2026-08-26T08:00:00Z",
        ),
    )
    child = make_project(
        project_id="child",
        project_entry=make_project_entry(
            project_id="child",
            name="Build",
            parent_id="root",
            created_at="2026-08-22T08:00:00Z",
            updated_at="2026-08-26T08:00:00Z",
        ),
    )
    activity = _activity()
    activity["parent_project_id"] = "child"

    figure = plot_project_lifecycle_timeline(
        activity,
        datetime(2026, 8, 20),
        datetime(2026, 8, 31),
        [root, child],
    )

    payload = figure.to_plotly_json()
    traces = payload["data"]
    assert "Product" in payload["layout"]["yaxis"]["ticktext"]
    labels = {label for trace in traces for label in trace.get("text", [])}
    assert "Build" in labels
    assert "Ongoing" in {trace.get("name") for trace in traces}
    assert all(trace["type"] == "scatter" for trace in traces)
