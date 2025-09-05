import json
from functools import partial
from subprocess import DEVNULL, PIPE, run

from loguru import logger
from tqdm import tqdm

from todoist.stats import extract_task_due_date
from todoist.types import Event, _Event_API_V9
from todoist.utils import get_api_key, safe_instantiate_entry, try_n_times
from joblib import Parallel, delayed


class DatabaseActivity:
    """Database class to fetch activity data from the Todoist API"""
    def __init__(self):
        super().__init__()

    def reset(self):
        pass

    def fetch_activity(self, max_pages: int = 4) -> list[Event]:
        """
        Fetches the activity data from the Todoist API.
        Returns a list of Event objects, each of those is associated with a date
        type of event (ex. completed, updated, uncompleted, added, ...)
        """
        result: list[Event] = []

        def process_page(page: int) -> list[Event]:
            events: list[Event] = self._fetch_activity_page(page)
            page_events: list[Event] = []
            for event in events:
                # TODO: Implement a factory method to create the correct Event subclass
                event_date = extract_task_due_date(event.event_date)
                assert event_date is not None
                page_events.append(Event(event_entry=event, id=event.id, date=event_date))
            return page_events

        pages = range(0, max_pages + 1)
        all_events = Parallel(n_jobs=-1)(
            delayed(process_page)(page)
            for page in tqdm(pages, desc='Querying activity data', unit='page', total=max_pages))
        for events in all_events:
            result.extend(events)
        return result

    def _fetch_activity_page(self, page: int) -> list[_Event_API_V9]:
        limit: int = 50

        url = f"https://api.todoist.com/sync/v9/activity/get?page={page}&limit={limit}"
        response = run(["curl", url, "-H", f"Authorization: Bearer {get_api_key()}"],
                       stdout=PIPE,
                       stderr=DEVNULL,
                       check=True)

        decoded_result: dict = json.loads(response.stdout)
        total_events_count: int = decoded_result['count']

        events = list(map(lambda event: safe_instantiate_entry(_Event_API_V9, **event), decoded_result['events']))
        if total_events_count > limit:
            for offset in range(limit, total_events_count, limit):
                url = f"https://api.todoist.com/sync/v9/activity/get?page={page}&limit={limit}&offset={offset}"
                response = run(["curl", url, "-H", f"Authorization: Bearer {get_api_key()}"],
                               stdout=PIPE,
                               stderr=DEVNULL,
                               check=True)
                load_fn = partial(json.loads, response.stdout)

                decoded_result = try_n_times(load_fn, 3)
                if decoded_result is None:
                    logger.error(f"Could not decode response (page={page}, offset={offset})")
                    logger.error(f'Type: {type(decoded_result)}')
                    logger.error(f'Keys: {decoded_result.keys()}')

                for event_kwargs in decoded_result['events']:
                    dataclass_params = {
                        key: value for key, value in event_kwargs.items() if key in _Event_API_V9.__dataclass_fields__
                    }
                    events.append(_Event_API_V9(
                        **dataclass_params,
                        new_api_kwargs={key: value for key, value in event_kwargs.items()
                                        if key not in _Event_API_V9.__dataclass_fields__}
                    ))


        return events
    
    def fetch_activity_adaptively(self, sliding_window_size: int, early_stopping_after: int) -> list[Event]:
        """
        Fetches activity adaptively using sliding windows and early stopping.
        
        This method fetches activity in sliding windows of `sliding_window_size` pages
        and continues until `early_stopping_after` consecutive windows return no new activity.
        It iteratively calls fetch_activity to get different page ranges moving backwards in time.
        
        Args:
            sliding_window_size: Number of pages to fetch in each sliding window  
            early_stopping_after: Number of consecutive windows with no activity before stopping
            
        Returns:
            List of Event objects from all fetched windows
            
        Example:
            # If we have activity: week0: 15, week1: 130, week2: 0, week3: 95, week4: 100, 
            #                      week5: 0, week6: 0, week7: 0, ...
            # fetch_activity_adaptively(1, 1) will fetch (week0), (week1), (week2) and stop
            # fetch_activity_adaptively(1, 2) will fetch (week0), (week1), (week2), (week3), 
            #                                                    (week4), (week5), (week6) and stop
            # fetch_activity_adaptively(2, 2) will fetch (week0,week1), (week2,week3), 
            #                                             (week4,week5), (week6,week7) and stop
        """
        all_events: list[Event] = []
        seen_event_ids: set[str] = set()
        current_start_page = 0
        consecutive_empty_windows = 0
        
        logger.info(f"Starting adaptive activity fetch with window_size={sliding_window_size}, "
                   f"early_stopping_after={early_stopping_after}")
        
        while consecutive_empty_windows < early_stopping_after:
            # Fetch the current sliding window by getting pages from current_start_page 
            # to current_start_page + sliding_window_size - 1
            logger.debug(f"Fetching window: pages {current_start_page} to "
                        f"{current_start_page + sliding_window_size - 1}")
            
            # Fetch pages for this window
            window_events: list[Event] = []
            for page in range(current_start_page, current_start_page + sliding_window_size):
                page_events = self._fetch_activity_page(page)
                
                # Convert to Event objects (similar to what fetch_activity does)
                for event in page_events:
                    event_date = extract_task_due_date(event.event_date)
                    if event_date is not None:
                        window_events.append(Event(event_entry=event, id=event.id, date=event_date))
            
            # Count new events in this window (events we haven't seen before)
            new_events_count = 0
            for event in window_events:
                if event.id not in seen_event_ids:
                    seen_event_ids.add(event.id)
                    all_events.append(event)
                    new_events_count += 1
            
            logger.debug(f"Window pages {current_start_page}-{current_start_page + sliding_window_size - 1} "
                        f"returned {len(window_events)} total events, {new_events_count} new events")
            
            # Check if this window had any new activity
            if new_events_count == 0:
                consecutive_empty_windows += 1
                logger.debug(f"Empty window detected. Consecutive empty windows: "
                           f"{consecutive_empty_windows}/{early_stopping_after}")
            else:
                consecutive_empty_windows = 0
                logger.debug(f"Window had {new_events_count} new events. "
                           f"Resetting consecutive empty windows counter.")
            
            # Move to the next window
            current_start_page += sliding_window_size
            
        logger.info(f"Adaptive fetch completed. Total unique events fetched: {len(all_events)}. "
                   f"Stopped after {consecutive_empty_windows} consecutive empty windows.")
        
        return all_events
