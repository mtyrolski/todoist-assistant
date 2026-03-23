"""Automation observer that triggers short automations for recent updates."""

import datetime as dt
import time
from collections.abc import Callable, Mapping, Sequence
from threading import Event
from typing import Any

from loguru import logger

from todoist.automations.activity import Activity
from todoist.automations.base import Automation
from todoist.database.base import Database
from todoist.utils import Cache

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

    def run_forever(
        self,
        *,
        settings_provider: Callable[[], Mapping[str, Any] | None] | None = None,
        stop_event: Event | None = None,
    ) -> None:
        logger.info(
            f"Starting automation observer with {len(self._automations)} automations "
            f"(interval={self._poll_interval_seconds}s)"
        )
        try:
            while True:
                if stop_event is not None and stop_event.is_set():
                    logger.info("Observer stop requested. Exiting.")
                    return
                start = dt.datetime.now()
                enabled, poll_interval_seconds = self._runtime_settings(
                    settings_provider=settings_provider
                )
                if not enabled:
                    logger.debug("Observer disabled; skipping tick.")
                    self._sleep(poll_interval_seconds, stop_event=stop_event)
                    continue
                self.run_once()
                end = dt.datetime.now()
                elapsed = (end - start).total_seconds()
                logger.debug(f"Observer iteration finished in {elapsed:.2f}s")
                self._sleep(poll_interval_seconds, stop_event=stop_event)
        except KeyboardInterrupt:
            logger.info("Observer interrupted by user. Exiting.")

    def run_once(self) -> int:
        new_events = self._refresh_activity_cache()
        if not new_events:
            logger.debug("Observer tick: no new activity events returned.")
            return 0

        # Refresh DB caches so automations work on up-to-date tasks/labels.
        self._db.reset()

        logger.debug(
            f"Observer tick: {len(new_events)} new events; running {len(self._automations)} automations."
        )
        for automation in self._automations:
            logger.info(f"Observer triggering automation {automation}")
            automation.tick(self._db)
        return len(new_events)

    def _refresh_activity_cache(self) -> set:
        events, stats = self._activity.fetch_recent_events(self._db, max_pages=RECENT_ACTIVITY_PAGES)
        if stats.get("total"):
            logger.debug(f"Observer activity snapshot: {stats}")
        if not events:
            return set()

        cached_events: set = Cache().activity.load()

        new_events = {event for event in events if event not in cached_events}
        if not new_events:
            logger.debug("Observer activity cache unchanged; no new events detected.")
            return set()

        cached_events.update(new_events)
        added = len(new_events)
        Cache().activity.save(cached_events)
        logger.debug(f"Observer activity cache updated; {added} new events saved, total {len(cached_events)}")
        return new_events

    @staticmethod
    def _sleep(seconds: float, *, stop_event: Event | None = None) -> None:
        delay = max(0.0, float(seconds))
        if stop_event is None:
            time.sleep(delay)
            return
        stop_event.wait(timeout=delay)

    def _runtime_settings(
        self,
        *,
        settings_provider: Callable[[], Mapping[str, Any] | None] | None = None,
    ) -> tuple[bool, float]:
        if settings_provider is not None:
            payload = settings_provider() or {}
            if not isinstance(payload, Mapping):
                payload = {}
            enabled = bool(payload.get("enabled", True))
            try:
                poll_interval_seconds = float(
                    payload.get("refreshIntervalSeconds", self._poll_interval_seconds)
                )
            except (TypeError, ValueError):
                poll_interval_seconds = self._poll_interval_seconds
            return enabled, poll_interval_seconds

        payload = Cache().observer_state.load()
        if not isinstance(payload, dict):
            return True, self._poll_interval_seconds
        enabled = bool(payload.get("enabled", True))
        raw_interval = payload.get("refreshIntervalSeconds")
        if raw_interval is None:
            raw_interval = float(payload.get("refreshIntervalMinutes", 0.0) or 0.0) * 60.0
        try:
            poll_interval_seconds = float(raw_interval) if raw_interval else self._poll_interval_seconds
        except (TypeError, ValueError):
            poll_interval_seconds = self._poll_interval_seconds
        return enabled, poll_interval_seconds
