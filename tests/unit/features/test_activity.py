from tests.unit.database.helpers import make_event
from todoist.features.activity import activity_project_ids


def test_activity_project_ids_includes_direct_v2_and_moved_project_ids() -> None:
    event = make_event("event-1", parent_project_id="current-project")
    event.event_entry.extra_data.update(
        {
            "from_project_id": "previous-project",
            "nested": {"project_id": "nested-project"},
        }
    )

    assert activity_project_ids([event]) == {
        "current-project",
        "v2_current-project",
        "previous-project",
        "nested-project",
    }
