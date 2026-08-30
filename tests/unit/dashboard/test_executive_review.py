from datetime import datetime

import pandas as pd

from tests.factories import make_project, make_project_entry
from todoist.dashboard._plot_project_lifecycle import (
    build_project_lifecycle_data,
    plot_project_lifecycle_timeline,
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
    assert any("Product" in label for label in payload["layout"]["yaxis"]["ticktext"])
    assert any("Build" in label for label in payload["layout"]["yaxis"]["ticktext"])
    assert "Ongoing" in {trace.get("name") for trace in traces}
    assert all(trace["type"] == "bar" for trace in traces)


def test_project_lifecycle_keeps_archived_child_in_active_parent_group() -> None:
    root = make_project(
        project_id="root",
        project_entry=make_project_entry(
            project_id="root", name="Product", created_at="2026-01-01T00:00:00Z"
        ),
    )
    child = make_project(
        project_id="archived-child",
        project_entry=make_project_entry(
            project_id="archived-child",
            name="Shipped work",
            parent_id="root",
            created_at="2026-08-02T00:00:00Z",
            updated_at="2026-08-20T00:00:00Z",
        ),
        is_archived=True,
    )
    activity = pd.DataFrame(
        {"event_type": ["completed"], "parent_project_id": ["archived-child"]},
        index=pd.to_datetime(["2026-08-18T12:00:00"]),
    )

    payload = plot_project_lifecycle_timeline(
        activity, datetime(2026, 8, 1), datetime(2026, 9, 1), [root, child]
    ).to_plotly_json()

    assert "Completed / archived" in {trace.get("name") for trace in payload["data"]}
    assert any(
        "Shipped work" in label for label in payload["layout"]["yaxis"]["ticktext"]
    )
    completed = next(
        trace
        for trace in payload["data"]
        if trace.get("name") == "Completed / archived"
    )
    assert completed["customdata"][0][8] == "Yes"


def test_project_lifecycle_recovers_archived_child_parent_from_activity() -> None:
    root = make_project(
        project_id="root",
        project_entry=make_project_entry(
            project_id="root", name="Product", created_at="2026-01-01T00:00:00Z"
        ),
    )
    child = make_project(
        project_id="archived-child",
        project_entry=make_project_entry(
            project_id="archived-child",
            name="Shipped work",
            parent_id=None,
            created_at="2026-08-02T00:00:00Z",
            updated_at="2026-08-20T00:00:00Z",
        ),
        is_archived=True,
    )
    activity = pd.DataFrame(
        {
            "event_type": ["completed"],
            "parent_project_id": ["archived-child"],
            "root_project_id": ["root"],
            "root_project_name": ["Product"],
        },
        index=pd.to_datetime(["2026-08-18T12:00:00"]),
    )

    payload = build_project_lifecycle_data(
        activity, datetime(2026, 8, 1), datetime(2026, 9, 1), [root, child]
    )

    assert payload["parents"][0]["id"] == "root"
    assert payload["parents"][0]["children"][0]["id"] == "archived-child"
    assert payload["parents"][0]["children"][0]["status"] == "completed"


def test_project_lifecycle_data_is_uncapped_and_groups_by_parent_id() -> None:
    roots = [
        make_project(
            project_id=root_id,
            project_entry=make_project_entry(
                project_id=root_id,
                name="Same display name",
                created_at="2026-01-01T00:00:00Z",
            ),
        )
        for root_id in ("root-a", "root-b")
    ]
    children = [
        make_project(
            project_id=f"child-{index}",
            project_entry=make_project_entry(
                project_id=f"child-{index}",
                name=f"Child {index}",
                parent_id="root-a" if index < 9 else "root-b",
                created_at="2026-08-01T00:00:00Z",
                updated_at="2026-08-20T00:00:00Z",
            ),
        )
        for index in range(12)
    ]
    activity = pd.DataFrame(
        {
            "event_type": ["added"] * len(children),
            "parent_project_id": [child.id for child in children],
        },
        index=pd.to_datetime(["2026-08-18T12:00:00"] * len(children)),
    )

    payload = build_project_lifecycle_data(
        activity,
        datetime(2026, 8, 1),
        datetime(2026, 9, 1),
        [*roots, *children],
    )

    parents = payload["parents"]
    assert len(parents) == 2
    assert {parent["id"] for parent in parents} == {"root-a", "root-b"}
    assert sum(len(parent["children"]) for parent in parents) == 12
    assert all(
        child["status"] == "unresolved"
        for parent in parents
        for child in parent["children"]
    )


def test_project_lifecycle_data_exposes_all_statuses_and_real_dates() -> None:
    root = make_project(
        project_id="root",
        project_entry=make_project_entry(
            project_id="root", name="Product", created_at="2025-01-01T00:00:00Z"
        ),
    )
    children = [
        make_project(
            project_id="ongoing",
            project_entry=make_project_entry(
                project_id="ongoing", name="Ongoing", parent_id="root",
                created_at="2025-11-01T00:00:00Z", updated_at="2026-08-20T00:00:00Z",
            ),
        ),
        make_project(
            project_id="unresolved",
            project_entry=make_project_entry(
                project_id="unresolved", name="Unresolved", parent_id="root",
                created_at="2026-08-02T00:00:00Z", updated_at="2026-08-20T00:00:00Z",
            ),
        ),
        make_project(
            project_id="inactive",
            project_entry=make_project_entry(
                project_id="inactive", name="Inactive", parent_id="root",
                created_at="2026-08-02T00:00:00Z", updated_at="2026-08-20T00:00:00Z",
            ),
        ),
        make_project(
            project_id="completed",
            project_entry=make_project_entry(
                project_id="completed", name="Completed", parent_id="root",
                created_at="2026-08-02T00:00:00Z", updated_at="2026-08-19T00:00:00Z",
            ),
            is_archived=True,
        ),
    ]
    activity = pd.DataFrame(
        {
            "event_type": ["completed", "added", "completed"],
            "parent_project_id": ["ongoing", "unresolved", "completed"],
        },
        index=pd.to_datetime(["2026-08-18T12:00:00"] * 3),
    )

    payload = build_project_lifecycle_data(
        activity, datetime(2026, 8, 1), datetime(2026, 9, 1), [root, *children]
    )
    rows = {child["id"]: child for child in payload["parents"][0]["children"]}

    assert {row["status"] for row in rows.values()} == {
        "completed", "ongoing", "unresolved", "inactive"
    }
    assert rows["ongoing"]["startDate"] == "2025-11-01"
    assert rows["ongoing"]["visualStart"] == "2026-08-01"
    assert rows["completed"]["archived"] is True
    assert rows["completed"]["archiveDate"] == "2026-08-19"
