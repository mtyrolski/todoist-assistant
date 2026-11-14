from datetime import datetime, timezone

from todometry.core.completions import reconcile_completions, effective_completion_mask
from todometry.core.types import Event, EventEntry, events_to_dataframe


def event(id, kind, date, task="task", **extra):
    return Event(
        id=id,
        date=datetime.fromisoformat(date).replace(tzinfo=timezone.utc),
        event_entry=EventEntry(
            id=id,
            object_type="item",
            object_id=task,
            event_type=kind,
            event_date=date,
            parent_project_id="deleted-project",
            parent_item_id="parent-task",
            initiator_id="user",
            extra_data={"content": task, **extra},
            extra_data_id=None,
        ),
    )


def test_undo_removes_original_completion_across_week_and_month_boundaries():
    original = event("1", "completed", "2026-09-30T12:00:00")
    undo = event("2", "uncompleted", "2026-10-05T12:00:00")
    recompleted = event("3", "completed", "2026-10-06T12:00:00")
    frame = events_to_dataframe({original, undo, recompleted}, {}, {})
    assert frame[effective_completion_mask(frame)]["id"].tolist() == ["3"]
    assert frame[frame["type"] == "uncompleted"]["id"].tolist() == ["2"]
    assert frame["task_id"].tolist() == ["task", "task", "task"]
    assert frame["root_project_name"].tolist() == ["(unknown)"] * 3
    assert frame["id"].tolist() == ["1", "2", "3"]


def test_repeated_undos_do_not_create_negative_counts_or_cancel_other_tasks():
    events = [
        event("1", "completed", "2026-10-01", task="a"),
        event("2", "uncompleted", "2026-10-02", task="a"),
        event("3", "uncompleted", "2026-10-03", task="a"),
        event("4", "completed", "2026-10-01", task="b"),
    ]
    assert [
        e.id for e in reconcile_completions(events) if e.event_type == "completed"
    ] == ["4"]


def test_recurring_occurrences_survive_resets_and_undo_events():
    events = [
        event("1", "completed", "2026-10-01", is_recurring=True),
        event("2", "uncompleted", "2026-10-02"),
        event("3", "completed", "2026-10-03"),
    ]
    frame = events_to_dataframe(set(events), {}, {})
    assert frame[effective_completion_mask(frame)]["id"].tolist() == ["1", "3"]
    assert frame[frame["type"] == "uncompleted"]["id"].tolist() == ["2"]


def test_duplicate_event_ids_are_ignored_but_distinct_completions_remain():
    a = event("1", "completed", "2026-10-01")
    b = event("2", "completed", "2026-10-02")
    assert [e.id for e in reconcile_completions([b, a, a])] == ["1", "2"]


def test_projection_does_not_modify_cache_objects():
    events = {
        event("1", "completed", "2026-10-01"),
        event("2", "uncompleted", "2026-10-02"),
    }
    reconcile_completions(events)
    assert {e.event_type for e in events} == {"completed", "uncompleted"}


def test_shared_android_completion_scenarios():
    import json
    from pathlib import Path

    scenarios = json.loads(
        (Path(__file__).parents[2] / "fixtures/completion_scenarios.json").read_text()
    )
    for scenario in scenarios:
        events = []
        for item in scenario["events"]:
            extra = {}
            if "recurring" in item:
                extra["is_recurring"] = item["recurring"]
            if item.get("reset"):
                extra["sub_tasks_reset"] = True
            events.append(
                event(
                    item["id"], item["type"], item["date"], task=item["task"], **extra
                )
            )
        effective = reconcile_completions(events)
        assert [e.id for e in effective if e.event_type == "completed"] == scenario[
            "completed"
        ], scenario["name"]
        assert [e.id for e in effective if e.event_type == "uncompleted"] == scenario[
            "undone"
        ], scenario["name"]
