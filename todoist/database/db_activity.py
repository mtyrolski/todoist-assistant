from datetime import datetime, timedelta, timezone

from loguru import logger

from todoist.stats import extract_task_due_date
from todoist.types import Event, EventEntry
from todoist.api import RequestSpec, TodoistAPIClient, TodoistEndpoints
from todoist.api.client import EndpointCallResult
from todoist.utils import safe_instantiate_entry

ACTIVITY_PAGE_LIMIT = 100


class DatabaseActivity:
    """Database class to fetch activity data from the Todoist API."""

    def __init__(self):
        # Participate in cooperative multiple inheritance so other mixins get initialized.
        super().__init__()
        self._api_client = TodoistAPIClient()

    def reset(self):
        pass

    @property
    def last_call_details(self) -> EndpointCallResult | None:
        """Expose metadata about the most recent API call."""

        return self._api_client.last_call_result

    def fetch_activity_adaptively(
        self,
        nweeks_window_size: int = 10,
        early_stop_after_n_windows: int = 5,
        max_pages_per_window: int | None = None,
        events_already_fetched: set[Event] | None = None,
    ) -> list[Event]:
        """
        Fetch activity events from Todoist API in a moving-window pattern.

        Each iteration fetches a chunk of pages and keeps moving backward by
        increasing the starting page offset. The loop stops after enough
        consecutive empty windows to avoid unnecessary deep history scans.
        """
        if events_already_fetched is None:
            events_already_fetched = set()

        n_empty_weeks: int = 0
        iterated_weeks: int = 0
        now_utc = datetime.now(timezone.utc)
        total_events: list[Event] = []
        logger.debug(
            "Start fetch_activity_adaptively: window_size={}, early_stop={}, max_pages_per_window={}",
            nweeks_window_size,
            early_stop_after_n_windows,
            max_pages_per_window,
        )
        while n_empty_weeks < early_stop_after_n_windows:
            window_end = now_utc - timedelta(weeks=iterated_weeks)
            window_start = window_end - timedelta(weeks=nweeks_window_size)
            window_events = self._fetch_activity_range(
                date_from=window_start,
                date_to=window_end,
                max_pages=max_pages_per_window,
            )
            iterated_weeks += nweeks_window_size
            events_not_already_fetched = [e for e in window_events if e not in events_already_fetched]
            if len(events_not_already_fetched) == 0:
                n_empty_weeks += 1
            else:
                n_empty_weeks = 0
            new_events = [e for e in window_events if e not in events_already_fetched]
            total_events.extend(new_events)
            events_already_fetched.update(new_events)
        logger.debug(f"Stopping fetch after {iterated_weeks} weeks processed, total_events={len(total_events)}")

        # Extend with already fetched events to avoid losing them.
        total_events.extend(events_already_fetched)
        total_events = list(set(total_events))  # deduplication
        logger.debug(f"Total events after merging with already fetched and deduplication: {len(total_events)}")

        # Final sorting from newest to oldest.
        total_events.sort(key=lambda x: x.event_entry.event_date, reverse=True)
        return total_events

    def fetch_activity(self, max_pages: int = 4, starting_page: int = 0) -> list[Event]:
        """
        Fetch activity data from Todoist API.

        - `starting_page` skips the first N cursor pages
        - `max_pages` collects up to N cursor pages after that
        """
        if max_pages <= 0:
            logger.warning("No pages requested (max_pages=0). Returning empty result.")
            return []

        if starting_page < 0:
            logger.warning(f"Negative starting_page={starting_page} provided; treating as 0.")
            starting_page = 0

        result: list[Event] = []
        cursor: str | None = None

        logger.info(
            f"Starting activity fetch over pages [{starting_page}, {starting_page + max_pages - 1}] "
            f"(total={max_pages})"
        )

        # Skip preceding pages first so callers can still request a page window.
        current_page_idx = 0
        while current_page_idx < starting_page:
            page_entries, next_cursor = self._fetch_activity_page(
                page_index=current_page_idx,
                cursor=cursor,
            )
            current_page_idx += 1
            _ = page_entries
            if not next_cursor:
                logger.debug(f"No further activity cursor while skipping page {current_page_idx - 1}")
                return []
            cursor = next_cursor

        # Collect the requested page window.
        collected_pages = 0
        while collected_pages < max_pages:
            page_index = starting_page + collected_pages
            page_entries, next_cursor = self._fetch_activity_page(
                page_index=page_index,
                cursor=cursor,
            )
            result.extend(self._events_from_entries(page_entries))
            collected_pages += 1
            if not next_cursor:
                logger.debug(f"No further activity cursor available at page {page_index}")
                break
            cursor = next_cursor

        logger.info(f"Finished fetching activity pages. Total events collected: {len(result)}")
        return result

    def _fetch_activity_range(
        self,
        *,
        date_from: datetime,
        date_to: datetime,
        max_pages: int | None = None,
    ) -> list[Event]:
        if max_pages is not None and max_pages <= 0:
            return []

        cursor: str | None = None
        entries: list[EventEntry] = []
        logger.info(f"Starting activity fetch over range [{date_from.isoformat()} .. {date_to.isoformat()})")
        fetched_pages = 0

        while True:
            if max_pages is not None and fetched_pages >= max_pages:
                if cursor is not None:
                    logger.warning(
                        "Stopping activity range fetch after {} pages (bounded mode); "
                        "results may be truncated for range [{} .. {}).",
                        fetched_pages,
                        date_from.isoformat(),
                        date_to.isoformat(),
                    )
                else:
                    logger.debug(
                        "Stopping activity range fetch after {} pages (bounded mode)",
                        fetched_pages,
                    )
                break

            params: dict[str, str | int] = {
                "limit": ACTIVITY_PAGE_LIMIT,
                "date_from": date_from.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "date_to": date_to.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
            if cursor:
                params["cursor"] = cursor

            spec = RequestSpec(
                endpoint=TodoistEndpoints.LIST_ACTIVITY,
                params=params,
                rate_limited=True,
            )
            decoded_result = self._api_client.request_json(
                spec, operation_name=f"fetch activity range {date_from.isoformat()} {date_to.isoformat()}"
            )
            if not isinstance(decoded_result, dict):
                raise RuntimeError("Unexpected response payload when fetching activity range")

            raw_events = decoded_result.get("results")
            if not isinstance(raw_events, list):
                raise RuntimeError("Unexpected results payload when fetching activity range")
            if not all(isinstance(event, dict) for event in raw_events):
                raise RuntimeError("Unexpected non-object event record in activity range payload")
            entries.extend(safe_instantiate_entry(EventEntry, **event) for event in raw_events)
            fetched_pages += 1

            next_cursor = decoded_result.get("next_cursor")
            if not isinstance(next_cursor, str):
                break
            cursor = next_cursor

        events = self._events_from_entries(entries)
        logger.info(f"Finished activity range fetch. Total events collected: {len(events)}")
        return events

    @staticmethod
    def _events_from_entries(entries: list[EventEntry]) -> list[Event]:
        events: list[Event] = []
        for entry in entries:
            event_date = extract_task_due_date(entry.event_date)
            if event_date is None:
                logger.debug(f"Skipping event {entry.id} due to unparseable date {entry.event_date}")
                continue
            events.append(Event(event_entry=entry, id=entry.id, date=event_date))
        return events

    def _fetch_activity_page(
        self,
        *,
        page_index: int,
        cursor: str | None,
    ) -> tuple[list[EventEntry], str | None]:
        params: dict[str, str | int] = {"limit": ACTIVITY_PAGE_LIMIT}
        if cursor:
            params["cursor"] = cursor

        spec = RequestSpec(
            endpoint=TodoistEndpoints.LIST_ACTIVITY,
            params=params,
            rate_limited=True,
        )
        decoded_result = self._api_client.request_json(
            spec, operation_name=f"fetch activity page {page_index}"
        )
        if not isinstance(decoded_result, dict):
            raise RuntimeError("Unexpected response payload when fetching activity page")

        raw_events = decoded_result.get("results")
        if not isinstance(raw_events, list):
            raise RuntimeError("Unexpected results payload when fetching activity page")
        if not all(isinstance(event, dict) for event in raw_events):
            raise RuntimeError("Unexpected non-object event record in activity page payload")

        events = [safe_instantiate_entry(EventEntry, **event) for event in raw_events]
        next_cursor = decoded_result.get("next_cursor")
        return events, str(next_cursor) if isinstance(next_cursor, str) else None
