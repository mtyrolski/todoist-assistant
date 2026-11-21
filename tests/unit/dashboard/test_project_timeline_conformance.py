"""Cross-platform fixtures originate from the real desktop lifecycle builder.

Regenerate after an intentional backend semantics change with:
PYTHONPATH=. python tests/unit/dashboard/test_project_timeline_conformance.py --write
"""

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from todometry.core.types import Event, EventEntry, events_to_dataframe
from todometry.dashboard._plot_project_lifecycle import build_project_lifecycle_data

FIXTURE = Path(__file__).parents[2] / "fixtures" / "project_timeline_conformance.json"


def _backend_results(fixture):
    snapshot = fixture["snapshot"]
    tasks = list(snapshot["tasks"])
    for index in range(fixture["subtaskCount"]):
        tasks.append(
            {"id": f"sub-{index}", "parent_id": "parent", "project_id": "renamed"}
        )
    rows = list(snapshot["activities"])
    for index in range(fixture["denseCount"]):
        day = datetime(2026, 1, 1, 12, tzinfo=UTC) + timedelta(days=index)
        rows.append(
            {
                "id": f"dense-{index}",
                "object_type": "item",
                "object_id": f"dense-task-{index}",
                "event_type": "completed",
                "event_date": day.isoformat(),
                "parent_project_id": "renamed",
            }
        )
    # The activity cache may include an overlapping page; event IDs are deduplicated.
    rows.append(snapshot["activities"][0])
    projects = []
    for item in [*snapshot["projects"], *snapshot["knownProjects"]]:
        entry = SimpleNamespace(
            name=item["name"],
            parent_id=item.get("parent_id"),
            v2_parent_id=None,
            created_at=item.get("created_at"),
            updated_at=item.get("updated_at"),
        )
        active = [
            SimpleNamespace(
                task_entry=SimpleNamespace(
                    checked=task.get("checked", False),
                    is_deleted=task.get("is_deleted", False),
                )
            )
            for task in tasks
            if task["project_id"] == item["id"]
        ]
        projects.append(
            SimpleNamespace(
                id=item["id"],
                project_entry=entry,
                tasks=active,
                is_archived=item.get("is_archived", False),
            )
        )
    by_id = {item.id: item for item in projects}
    root_by_id = {
        item.id: by_id.get(item.project_entry.parent_id, item) for item in projects
    }
    events = []
    for item in rows:
        timestamp = datetime.fromisoformat(item["event_date"])
        entry = EventEntry(
            id=item["id"],
            object_type=item["object_type"],
            object_id=item["object_id"],
            event_type=item["event_type"],
            event_date=item["event_date"],
            parent_project_id=item.get("parent_project_id"),
            parent_item_id=item.get("parent_item_id"),
            initiator_id=None,
            extra_data=item.get("extra_data", {}),
            extra_data_id=None,
        )
        events.append(Event(event_entry=entry, id=item["id"], date=timestamp))
    frame = events_to_dataframe(
        events, {p.id: p.project_entry.name for p in projects}, root_by_id
    )
    frame = frame.set_index("date")
    expected = []
    for window in fixture["windows"]:
        result = build_project_lifecycle_data(
            frame,
            datetime.fromisoformat(window["start"]),
            datetime.fromisoformat(window["end"]),
            projects,
        )
        expected.append(
            {
                child["id"]: {
                    "name": child["name"],
                    "archived": child["archived"],
                    "openTasks": child["openTasks"],
                    "completions": child["completions"],
                }
                for parent in result["parents"]
                for child in parent["children"]
            }
        )
    return expected


def test_android_timeline_fixture_matches_backend_lifecycle():
    fixture = json.loads(FIXTURE.read_text())
    assert fixture["expected"]
    assert _backend_results(fixture) == fixture["expected"]


if __name__ == "__main__" and sys.argv[1:] == ["--write"]:
    fixture = json.loads(FIXTURE.read_text())
    fixture["expected"] = _backend_results(fixture)
    FIXTURE.write_text(json.dumps(fixture, indent=2) + "\n")
