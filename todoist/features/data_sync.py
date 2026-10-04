"""File-backed Todoist activity synchronization, independent of dashboard jobs."""

from dataclasses import dataclass

from todoist.core.types import Event
from todoist.database.base import Database
from todoist.features.activity import (
    activity_history_boundary,
    activity_sync_lock,
    load_activity_cache,
    merge_activity_cache,
    needs_activity_history,
)


@dataclass(frozen=True)
class SyncResult:
    events: set[Event]
    new_events: set[Event]


def sync_recent_activity(db: Database) -> SyncResult:
    """Fetch every page since the cached boundary and merge under one lock."""
    with activity_sync_lock():
        previous = load_activity_cache()
        fetched = set(db.fetch_activity_incremental(previous, overlap_days=1))
        merged = merge_activity_cache(fetched)
    return SyncResult(merged, fetched - previous)


def backfill_activity_history(
    db: Database, *, nweeks_window_size: int = 10, early_stop_after_n_windows: int = 2
) -> SyncResult:
    """Checkpoint history windows so an interrupted scan retains fetched events."""
    with activity_sync_lock():
        previous = load_activity_cache()
        if not needs_activity_history(previous):
            return SyncResult(previous, set())
        fetched = set(
            db.fetch_activity_history(
                nweeks_window_size=nweeks_window_size,
                early_stop_after_n_windows=early_stop_after_n_windows,
                events_already_fetched=previous,
                date_to=activity_history_boundary(previous),
                progress_desc="Fetching activity history",
                on_events=merge_activity_cache,
            )
        )
        merged = merge_activity_cache(fetched)
    return SyncResult(merged, fetched - previous)
