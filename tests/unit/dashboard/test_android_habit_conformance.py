"""Keep Android habit expectations aligned with the actual backend projection."""

import json
from datetime import datetime
from pathlib import Path

from todometry.core.types import Event, EventEntry, events_to_dataframe
from todometry.features.habit_tracker import TrackedHabitTask, summarize_tracked_habits


def test_android_habit_fixture_matches_backend():
    fixture = json.loads((Path(__file__).parents[2] / "fixtures/android_habit_conformance.json").read_text())
    events = []
    for raw in fixture["events"]:
        entry = EventEntry(
            id=raw["id"], object_type=raw["object_type"], object_id=raw["object_id"],
            event_type=raw["event_type"], event_date=raw["event_date"],
            parent_project_id=None, parent_item_id=None, initiator_id=None,
            extra_data=raw["extra_data"], extra_data_id=None,
        )
        # The desktop activity frame uses timezone-naive datetimes.
        date = datetime.fromisoformat(raw["event_date"]).replace(tzinfo=None)
        events.append(Event(event_entry=entry, id=raw["id"], date=date))
    tasks = [
        TrackedHabitTask(task_id="h1", content="Walking", project_id="p", project_name="Health", project_color="green"),
        TrackedHabitTask(task_id="h2", content="Reading", project_id="p", project_name="Health", project_color="green"),
    ]
    result = summarize_tracked_habits(
        events_to_dataframe(events, {}, {}), tasks,
        anchor=datetime.fromisoformat(fixture["anchor"]).replace(tzinfo=None),
    )
    expected = fixture["expected"]
    for key in ("weekBeg", "weekEnd", "trackedCount", "totals"):
        assert result[key] == expected[key]
    for item, expected_item in zip(result["items"], expected["items"], strict=True):
        assert {key: item[key] for key in expected_item} == expected_item
