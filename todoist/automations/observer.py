"""Automation observer that triggers short automations for recent updates."""

import datetime as dt
import time
from typing import Sequence

from loguru import logger

from todoist.automations.activity import Activity
from todoist.automations.base import Automation
from todoist.database.base import Database
from todoist.utils import Cache, LocalStorageError

POLL_INTERVAL_SECONDS = 30.0
RECENT_ACTIVITY_PAGES = 1


class AutomationObserver:
    """Background worker that watches Todoist activity and triggers automations."""

    def __init__(
        self,
        *,
        db: Database,
        automations: Sequence[Automation],
        activity: Activity,
        poll_interval_seconds: float = POLL_INTERVAL_SECONDS,
    ) -> None:
        self._db = db
        self._automations = list(automations)
        self._activity = activity
        self._poll_interval_seconds = poll_interval_seconds

    def run_forever(self) -> None:
        logger.info(
            f"Starting automation observer with {len(self._automations)} automations "
            f"(interval={self._poll_interval_seconds}s)"
        )
        try:
            while True:
                start = dt.datetime.now()
                self._run_once()
                end = dt.datetime.now()
                elapsed = (end - start).total_seconds()
                logger.debug(f"Observer iteration finished in {elapsed:.2f}s")
                time.sleep(self._poll_interval_seconds)
        except KeyboardInterrupt:
            logger.info("Observer interrupted by user. Exiting.")

    def _run_once(self) -> None:
        new_events = self._refresh_activity_cache()
        if not new_events:
            logger.debug("Observer tick: no new activity events returned.")
            return

        # Refresh DB caches so automations work on up-to-date tasks/labels.
        self._db.reset()

        logger.debug(
            f"Observer tick: {len(new_events)} new events; running {len(self._automations)} automations."
        )
        for automation in self._automations:
            logger.info(f"Observer triggering automation {automation}")
            automation.tick(self._db)

    def _refresh_activity_cache(self) -> set:
        events, stats = self._activity.fetch_recent_events(self._db, max_pages=RECENT_ACTIVITY_PAGES)
        if stats.get("total"):
            logger.debug(f"Observer activity snapshot: {stats}")
        if not events:
            return set()

        try:
            cached_events: set = Cache().activity.load()
        except LocalStorageError:
            cached_events = set()

        before = len(cached_events)
        cached_events.update(events)
        added = len(cached_events) - before
        Cache().activity.save(cached_events)
        logger.debug(f"Observer activity cache updated; {added} new events saved, total {len(cached_events)}")
        return set(events)
