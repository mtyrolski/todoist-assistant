from tests.factories import make_project, make_project_entry
from todoist.features.productivity import weekly_completion_counts


def test_productivity_counters_preserve_unknown_projects_and_apply_root_adjustments():
    root = make_project(project_entry=make_project_entry(name="Old root"))
    stats = {
        "week_items": [
            {
                "to": "2026-11-01",
                "total_completed": 349,
                "items": [
                    {"id": "child", "completed": 300},
                    {"id": "deleted", "completed": 49},
                ],
            }
        ]
    }
    counts = weekly_completion_counts(
        stats, {"child": root}, {}, {"Old root": "New root"}
    )
    assert counts == {"2026-11-01": {"New root": 300, "(unknown)": 49}}
