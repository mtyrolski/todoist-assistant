from loguru import logger

from todoist.features.activity import (
    activity_history_boundary,
    load_activity_cache,
    merge_activity_cache,
    needs_activity_history,
    quick_summarize,
)
from todoist.automations.base import Automation
from todoist.database.base import Database
from todoist.core.types import Event


class Activity(Automation):
    def __init__(
        self, name: str, nweeks_window_size: int, early_stop_after_n_windows: int
    ):
        super().__init__(name, frequency=0.1, is_long=False)  # default to once a day
        self.nweeks = nweeks_window_size
        self.early_stop_after_n_windows = early_stop_after_n_windows
        self.frequency_in_minutes = 0.1

    def _tick(self, db: Database):
        events_so_far = load_activity_cache()
        if hasattr(db, "fetch_activity_recent"):
            recent_events = set(db.fetch_activity_recent(max_pages=2))
            events_history = merge_activity_cache(recent_events)
            new_events = events_history - events_so_far
            logger.info(
                "Activity sync recent phase complete: fetched={}; new={}; cached={}",
                len(recent_events),
                len(new_events),
                len(events_history),
            )

            history_events: set[Event] = set()
            if needs_activity_history(events_history):
                history_boundary = activity_history_boundary(events_history)
                logger.info(
                    "Activity sync history phase starting at boundary={}",
                    history_boundary.isoformat() if history_boundary else "now",
                )
                history_result = db.fetch_activity_history(
                    nweeks_window_size=self.nweeks,
                    early_stop_after_n_windows=self.early_stop_after_n_windows,
                    events_already_fetched=events_history,
                    date_to=history_boundary,
                    progress_desc="Fetching activity history",
                )
                history_events = set(history_result) - events_history
                if history_events:
                    events_history = merge_activity_cache(history_events)
                logger.info(
                    "Activity sync history phase complete: new={}; cached={}",
                    len(history_events),
                    len(events_history),
                )
        else:
            # Compatibility path for small test doubles and older integrations.
            events_history = set(
                db.fetch_activity_adaptively(
                    nweeks_window_size=self.nweeks,
                    early_stop_after_n_windows=self.early_stop_after_n_windows,
                    events_already_fetched=events_so_far,
                )
            )
            new_events = events_history - events_so_far
            merge_activity_cache(new_events)

        quick_summarize(
            events=events_history, new_events=events_history - events_so_far
        )

    def fetch_recent_events(
        self, db: Database, *, max_pages: int = 1
    ) -> tuple[list[Event], dict[str, int]]:
        """Fetch recent activity pages and provide simple statistics."""

        fetch_recent = getattr(db, "fetch_activity_recent", db.fetch_activity)
        events = fetch_recent(max_pages=max_pages)
        stats: dict[str, int] = {"total": len(events)}
        for event in events:
            stats[event.event_type] = stats.get(event.event_type, 0) + 1
        return events, stats
