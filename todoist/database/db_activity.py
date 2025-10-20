from functools import partial

from loguru import logger
from tqdm import tqdm

from todoist.stats import extract_task_due_date
from todoist.types import Event, EventEntry

from todoist.api import RequestSpec, TodoistAPIClient, TodoistEndpoints
from todoist.api.client import EndpointCallResult
from todoist.utils import safe_instantiate_entry, with_retry, RETRY_MAX_ATTEMPTS
from concurrent.futures import ThreadPoolExecutor, as_completed

TIMEOUT_SECONDS = 10

class DatabaseActivity:
    """Database class to fetch activity data from the Todoist API"""
    def __init__(self):
        # Participate in cooperative multiple inheritance so other mixins get initialized
        super().__init__()
        self._api_client = TodoistAPIClient()

    def reset(self):
        pass

    @property
    def last_call_details(self) -> EndpointCallResult | None:
        """Expose metadata about the most recent API call."""

        return self._api_client.last_call_result
    
    def fetch_activity_adaptively(self, nweeks_window_size: int = 3, early_stop_after_n_windows: int = 5, events_already_fetched: set[Event] | None = None) -> list[Event]:
        """
        Fetches activity events from the Todoist API using a sliding window approach.
        This method adaptively fetches activity data going backwards in time window by window(week by week) in fixed windows size(nweeks_window_size arg).
        Fetching stops after a number of consecutive empty windows(early_stop_after_n_windows), which avoids unnecessary fetching far into the past.
        Arg events_already_fetched is a set of events that have already been fetched, to avoid duplicates in the returned result. Events already in this set will be excluded from the final output.
        """
        if events_already_fetched is None:
            events_already_fetched = set()
        
        n_empty_weeks: int = 0
        iterated_weeks: int = 0
        total_events: list[Event] = []
        logger.debug(f"Start fetch_activity_adaptively: window_size={nweeks_window_size}, early_stop={early_stop_after_n_windows}")
        while n_empty_weeks < early_stop_after_n_windows:
            window_events: list[Event] = self.fetch_activity(nweeks_window_size, iterated_weeks)
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
        
        # extending with already fetched events to avoid losing them
        total_events.extend(events_already_fetched)
        total_events = list(set(total_events))  # deduplication
        logger.debug(f"Total events after merging with already fetched and deduplication: {len(total_events)}")
        
        # final sorting
        total_events.sort(key=lambda x: x.event_entry.event_date, reverse=True)  # from newest to oldest
        return total_events

            
    def fetch_activity(self, max_pages: int = 4, starting_page: int = 0) -> list[Event]:
        """
        Fetches the activity data from the Todoist API.
        Returns a list of Event objects, each of those is associated with a date
        type of event (ex. completed, updated, uncompleted, added, ...)
        """
        result: list[Event] = []

        def process_page(page: int) -> list[Event]:
            events: list[EventEntry] = self._fetch_activity_page(page)
            page_events: list[Event] = []
            for event in events:
                # TODO: Implement a factory method to create the correct Event subclass
                event_date = extract_task_due_date(event.event_date)
                assert event_date is not None
                page_events.append(Event(event_entry=event, id=event.id, date=event_date))
            return page_events
        
        def process_page_with_retry(page: int) -> list[Event]:
            """Process page with built-in retry logic."""
            return with_retry(
                partial(process_page, page),
                operation_name=f"fetch events for page {page}",
                max_attempts=RETRY_MAX_ATTEMPTS
            )

        pages = range(starting_page, starting_page + max_pages)
        logger.info(f"Starting activity fetch over pages [{starting_page}, {starting_page + max_pages - 1}] (total={max_pages})")

        # Use ThreadPoolExecutor instead of joblib for simpler, standard concurrency
        results_by_page: dict[int, list[Event]] = {}
        max_workers = min(8, max_pages) if max_pages > 0 else 0
        if max_workers == 0:
            logger.warning("No pages requested (max_pages=0). Returning empty result.")
            return result

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_page = {executor.submit(process_page_with_retry, page): page for page in pages}
            for future in tqdm(as_completed(future_to_page), total=max_pages, desc='Querying activity data', unit='page'):
                page = future_to_page[future]
                page_events = future.result(timeout=TIMEOUT_SECONDS)
                results_by_page[page] = page_events
        
            
        # logger.debug(f"Fetched {len(page_events)} events from page {page}")
        logger.debug(f'Fetched events by page (idx, len): {[ (page, len(events)) for page, events in results_by_page.items() ]}')
        # Preserve page order when extending results
        for page in pages:
            events_for_page = results_by_page.get(page, [])
            if not events_for_page:
                logger.debug(f"No events collected for page {page}")
            result.extend(events_for_page)

        logger.info(f"Finished fetching activity pages. Total events collected: {len(result)}")
        return result

    def _fetch_activity_page(self, page: int) -> list[EventEntry]:
        limit: int = 50

        spec = RequestSpec(
            endpoint=TodoistEndpoints.LIST_ACTIVITY,
            params={"page": page, "limit": limit},
        )
        decoded_result = self._api_client.request_json(
            spec, operation_name=f"fetch activity page {page}"
        )
        if not isinstance(decoded_result, dict):
            raise RuntimeError("Unexpected response payload when fetching activity page")

        total_events_count: int = decoded_result['count']

        events = list(map(lambda event: safe_instantiate_entry(EventEntry, **event), decoded_result['events']))
        if total_events_count > limit:
            for offset in range(limit, total_events_count, limit):
                offset_spec = RequestSpec(
                    endpoint=TodoistEndpoints.LIST_ACTIVITY,
                    params={"page": page, "limit": limit, "offset": offset},
                )
                decoded_result = self._api_client.request_json(
                    offset_spec,
                    operation_name=f"fetch activity page {page} offset {offset}",
                )
                if not isinstance(decoded_result, dict):
                    logger.error(
                        "Unexpected payload when fetching paginated activity",
                        page=page,
                        offset=offset,
                    )
                    continue

                for event_kwargs in decoded_result['events']:
                    dataclass_params = {
                        key: value for key, value in event_kwargs.items() if key in EventEntry.__dataclass_fields__
                    }
                    events.append(EventEntry(
                        **dataclass_params,
                        new_api_kwargs={key: value for key, value in event_kwargs.items()
                                        if key not in EventEntry.__dataclass_fields__}
                    ))


        return events
