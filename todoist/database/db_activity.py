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
            events: list[_Event_API_V9] = self._fetch_activity_page(page)
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

                for event in decoded_result['events']:
                    events.append(_Event_API_V9(**event))

        return events
