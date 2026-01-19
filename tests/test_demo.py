import pandas as pd
from datetime import datetime, timedelta

from todoist.database.demo import anonymize_activity_dates


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
        assert original.index.max() - original.index.min() == anonymized.index.max() - anonymized.index.min()
