from datetime import datetime

import pandas as pd

from todoist.dashboard._plot_project_contribution import (
    plot_project_contribution_timeline,
)
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


def test_project_contribution_timeline_uses_parent_and_subproject_names() -> None:
    figure = plot_project_contribution_timeline(
        _activity(),
        datetime(2026, 8, 20),
        datetime(2026, 8, 31),
    )

    heatmap = figure.data[0]
    assert heatmap.y == ("Product → Build",)
    assert sum(heatmap.z[0]) == 2
