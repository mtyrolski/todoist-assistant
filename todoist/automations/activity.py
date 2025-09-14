from loguru import logger
from todoist.activity import quick_summarize
from todoist.automations.base import Automation
from todoist.database.base import Database
from todoist.utils import Cache, LocalStorageError
from todoist.types import Event

EventCollection = set[Event]


class Activity(Automation):
    def __init__(self, name: str, nweeks_window_size: int = 2, early_stop_after_n_windows: int = 4, frequency_in_minutes: float = 0.1):
        super().__init__(name, frequency_in_minutes, True)  # Always use adaptive approach
        self.nweeks_window_size = nweeks_window_size
        self.early_stop_after_n_windows = early_stop_after_n_windows

    def _tick(self, dbio: Database):
        activity_db, new_items, is_corrupted = self._fetch_activity_adaptive(dbio)
        logger.info(f'Summary of Activity (is_corrupted={is_corrupted}):')
        quick_summarize(activity_db, new_items)

    def _fetch_activity_adaptive(self, dbio: Database) -> tuple[EventCollection, EventCollection, bool]:
        """Fetches activity using adaptive approach with sliding window and early stopping.
        
        Returns: (all_events, new_events, is_corrupted)
        """
        is_corrupted = False
        try:
            all_events: set[Event] = Cache().activity.load()
        except LocalStorageError as e:
            logger.error('No local activity database found, creating a new one.')
            logger.error(str(e))
            is_corrupted = True
            all_events = set()

        # Fetch new events using adaptive approach
        fetched_activity: list[Event] = dbio.fetch_activity_adaptively(
            nweeks_window_size=self.nweeks_window_size,
            early_stop_after_n_windows=self.early_stop_after_n_windows,
            events_already_fetched=all_events
        )
        logger.info(f'Fetched {len(fetched_activity)} new events using adaptive approach')

        new_events: set[Event] = set(fetched_activity)
        all_events.update(new_events)
        
        logger.info(f'Added {len(new_events)} new events, current size: {len(all_events)}')
        Cache().activity.save(all_events)
        return all_events, new_events, is_corrupted
