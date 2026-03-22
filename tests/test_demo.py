import pandas as pd
from datetime import datetime, timedelta
from typing import cast

import pytest
from tests.factories import make_project, make_project_entry, make_task

from todoist.database.demo import (
    _ProjectTheme,
    anonymize_activity_dates,
    anonymize_label_names,
    anonymize_project_names,
)


def _duration(index: pd.Index) -> pd.Timedelta:
    if not isinstance(index, pd.DatetimeIndex) or index.empty:
        return cast(pd.Timedelta, pd.Timedelta(0))
    start = index.min()
    end = index.max()
    if not isinstance(start, pd.Timestamp) or not isinstance(end, pd.Timestamp):
        return cast(pd.Timedelta, pd.Timedelta(0))
    return cast(pd.Timedelta, end - start)


def test_anonymize_activity_dates_preserves_task_durations():
    base = datetime(2024, 1, 1, 9, 0, 0)
    data = {
        "task_id": ["task1", "task1", "task2", "task2"],
        "type": ["added", "completed", "added", "completed"],
        "id": ["e1", "e2", "e3", "e4"],
        "title": ["Task 1", "Task 1", "Task 2", "Task 2"],
        "parent_project_id": ["p1"] * 4,
        "parent_project_name": ["Proj"] * 4,
        "root_project_id": ["r1"] * 4,
        "root_project_name": ["Root"] * 4,
        "parent_item_id": ["task1", "task1", "task2", "task2"],
    }
    dates = [
        base,
        base + timedelta(hours=2),
        base + timedelta(days=1),
        base + timedelta(days=3),
    ]
    df = pd.DataFrame(data, index=pd.DatetimeIndex(dates))
    df.index.name = "date"

    result = anonymize_activity_dates(df)

    for task_id in ["task1", "task2"]:
        original = df[df["task_id"] == task_id].sort_index()
        anonymized = result[result["task_id"] == task_id].sort_index()
        assert _duration(original.index) == _duration(anonymized.index)


def test_anonymize_project_names_uses_stable_hierarchy_themes():
    base = datetime(2024, 1, 1, 9, 0, 0)
    active_projects = [
        make_project(
            project_id="root-alpha",
            project_entry=make_project_entry(
                project_id="root-alpha",
                name="Alpha",
                child_order=2,
            ),
        ),
        make_project(
            project_id="child-one",
            project_entry=make_project_entry(
                project_id="child-one",
                name="Alpha Child One",
                parent_id="root-alpha",
                child_order=1,
            ),
        ),
        make_project(
            project_id="grandchild",
            project_entry=make_project_entry(
                project_id="grandchild",
                name="Alpha Grandchild",
                parent_id="child-one",
                child_order=1,
            ),
        ),
        make_project(
            project_id="child-two",
            project_entry=make_project_entry(
                project_id="child-two",
                name="Alpha Child Two",
                parent_id="root-alpha",
                child_order=2,
            ),
        ),
        make_project(
            project_id="root-beta",
            project_entry=make_project_entry(
                project_id="root-beta",
                name="Beta",
                child_order=1,
            ),
        ),
    ]
    df = pd.DataFrame(
        [
            {
                "date": base,
                "id": "e1",
                "type": "completed",
                "parent_project_name": "Alpha",
                "root_project_name": "Alpha",
                "task_id": "t1",
            },
            {
                "date": base + timedelta(days=1),
                "id": "e2",
                "type": "completed",
                "parent_project_name": "Alpha Child One",
                "root_project_name": "Alpha",
                "task_id": "t2",
            },
            {
                "date": base + timedelta(days=2),
                "id": "e3",
                "type": "completed",
                "parent_project_name": "Alpha Grandchild",
                "root_project_name": "Alpha",
                "task_id": "t3",
            },
            {
                "date": base + timedelta(days=3),
                "id": "e4",
                "type": "completed",
                "parent_project_name": "Alpha Child Two",
                "root_project_name": "Alpha",
                "task_id": "t4",
            },
            {
                "date": base + timedelta(days=4),
                "id": "e5",
                "type": "completed",
                "parent_project_name": "Beta",
                "root_project_name": "Beta",
                "task_id": "t5",
            },
            {
                "date": base + timedelta(days=5),
                "id": "e6",
                "type": "completed",
                "parent_project_name": "Legacy Project",
                "root_project_name": "Legacy Project",
                "task_id": "t6",
            },
        ]
    )
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")

    anonymized_df = df.copy()
    result = anonymize_project_names(anonymized_df, active_projects)
    repeat = anonymize_project_names(df.copy(), active_projects)

    assert result == repeat
    assert result["Alpha"] != "Alpha"
    assert result["Beta"] != "Beta"
    assert result["Legacy Project"] != "Legacy Project"
    assert result["Alpha Child One"].startswith(result["Alpha"])
    assert result["Alpha Child Two"].startswith(result["Alpha"])
    assert result["Alpha Grandchild"].startswith(result["Alpha Child One"])
    assert result["Alpha Child One"] != result["Alpha Child Two"]
    original_names = {"Alpha", "Alpha Child One", "Alpha Grandchild", "Alpha Child Two", "Beta", "Legacy Project"}
    assert set(anonymized_df["parent_project_name"]).isdisjoint(original_names)
    assert set(anonymized_df["root_project_name"]).isdisjoint(original_names)
    assert set(result.values()).isdisjoint(
        original_names
    )


def test_anonymize_project_names_uses_theme_specific_subprojects(monkeypatch):
    monkeypatch.setattr(
        "todoist.database.demo._PROJECT_THEME_CATALOG",
        (
            _ProjectTheme(
                "North Star Studio",
                (
                    ("Recordings", "First Album", "Office"),
                    ("Song Ideas", "Tracklist", "Budget"),
                ),
            ),
        ),
    )

    active_projects = [
        make_project(
            project_id="root",
            project_entry=make_project_entry(project_id="root", name="Alpha"),
        ),
        make_project(
            project_id="child-1",
            project_entry=make_project_entry(
                project_id="child-1",
                name="Alpha Child One",
                parent_id="root",
                child_order=1,
            ),
        ),
        make_project(
            project_id="child-2",
            project_entry=make_project_entry(
                project_id="child-2",
                name="Alpha Child Two",
                parent_id="root",
                child_order=2,
            ),
        ),
        make_project(
            project_id="grandchild",
            project_entry=make_project_entry(
                project_id="grandchild",
                name="Alpha Grandchild",
                parent_id="child-1",
                child_order=1,
            ),
        ),
    ]
    df = pd.DataFrame(
        [
            {"parent_project_name": "Alpha", "root_project_name": "Alpha"},
            {"parent_project_name": "Alpha Child One", "root_project_name": "Alpha"},
            {"parent_project_name": "Alpha Child Two", "root_project_name": "Alpha"},
            {"parent_project_name": "Alpha Grandchild", "root_project_name": "Alpha"},
        ]
    )

    result = anonymize_project_names(df, active_projects)

    assert result["Alpha"] == "North Star Studio"
    assert result["Alpha Child One"] == "North Star Studio / Recordings"
    assert result["Alpha Child Two"] == "North Star Studio / First Album"
    assert result["Alpha Grandchild"] == "North Star Studio / Recordings / Song Ideas"


def test_anonymize_label_names_handles_partial_catalog_without_error():
    active_projects = [
        make_project(
            project_id="root",
            project_entry=make_project_entry(project_id="root", name="Alpha"),
            tasks=[
                make_task(task_id="t1", labels=["alpha", "beta"]),
                make_task(task_id="t2", labels=["beta", "gamma"]),
            ],
        )
    ]

    label_mapping = anonymize_label_names(active_projects)

    assert set(label_mapping) == {"alpha", "beta", "gamma"}
    remapped_labels = {label for task in active_projects[0].tasks for label in task.task_entry.labels}
    assert remapped_labels == set(label_mapping.values())


def test_anonymize_label_names_raises_when_catalog_is_too_small(monkeypatch):
    monkeypatch.setattr(
        "todoist.database.demo._LABEL_NAMES",
        ("one", "two"),
    )
    active_projects = [
        make_project(
            project_id="root",
            project_entry=make_project_entry(project_id="root", name="Alpha"),
            tasks=[
                make_task(task_id="t1", labels=["alpha", "beta", "gamma"]),
            ],
        )
    ]

    with pytest.raises(ValueError, match="Not enough unique names"):
        anonymize_label_names(active_projects)
