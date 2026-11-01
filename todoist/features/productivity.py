"""Translate Todoist's own productivity counters into root-project totals."""

from collections import defaultdict
from datetime import date
from typing import Any

from todoist.core.types import Project


def weekly_completion_counts(
    stats: dict[str, Any],
    roots: dict[str, Project],
    names: dict[str, str],
    adjustments: dict[str, str],
) -> dict[str, dict[str, int]]:
    result = {}
    for week in stats.get("week_items", []):
        label = date.fromisoformat(week["to"]).isoformat()
        counts: dict[str, int] = defaultdict(int)
        for item in week["items"]:
            project_id = str(item["id"])
            root = roots.get(project_id)
            name = (
                root.project_entry.name if root else names.get(project_id, "(unknown)")
            )
            counts[adjustments.get(name, name)] += int(item["completed"])
        # Keep unresolvable/deleted projects in the total instead of silently dropping them.
        remainder = int(week["total_completed"]) - sum(counts.values())
        if remainder > 0:
            counts["(unknown)"] += remainder
        result[label] = dict(counts)
    return result
