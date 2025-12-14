from todoist.activity import quick_summarize
from todoist.automations.base import Automation
from todoist.database.base import Database
from todoist.types import Event
from todoist.utils import Cache


class Activity(Automation):
    def __init__(self, name: str, nweeks_window_size: int, early_stop_after_n_windows: int):
        super().__init__(name, frequency=0.1, is_long=False)  # default to once a day
        self.nweeks = nweeks_window_size
        self.early_stop_after_n_windows = early_stop_after_n_windows
        self.frequency_in_minutes = 0.1

    def _tick(self, db: Database):
        events_so_far: set[Event] = Cache().activity.load()
        events_history = db.fetch_activity_adaptively(
            nweeks_window_size=self.nweeks,
            early_stop_after_n_windows=self.early_stop_after_n_windows,
            events_already_fetched=events_so_far,
        )
        events_history = set(events_history)
        Cache().activity.save(events_history)
        quick_summarize(events=events_history, new_events=events_history - events_so_far)

    def fetch_recent_events(self, db: Database, *, max_pages: int = 1) -> tuple[list[Event], dict[str, int]]:
        """Fetch recent activity pages and provide simple statistics."""

        events = db.fetch_activity(max_pages=max_pages)
        stats: dict[str, int] = {"total": len(events)}
        for event in events:
            stats[event.event_type] = stats.get(event.event_type, 0) + 1
        return events, stats
