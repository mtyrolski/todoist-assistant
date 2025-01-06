import json
from functools import partial
from subprocess import DEVNULL, PIPE, run

from loguru import logger
from tqdm import tqdm

from todoist.stats import extract_task_due_date
from todoist.types import Event, _Event_API_V9
from todoist.utils import get_api_key, try_n_times


class DatabaseActivity:
    """Database class to fetch activity data from the Todoist API"""
    def __init__(self, max_pages: int):
        self.max_pages = max_pages

    def fetch_activity(self) -> list[Event]:
        """
        Fetches the activity data from the Todoist API.
        Returns a list of Event objects, each of those is associated with a date
        type of event (ex. completed, updated, uncompleted, added, ...)
        """
        result: list[Event] = []
        for page in tqdm(range(0, self.max_pages + 1), desc='Querying activity data', unit='page',
                         total=self.max_pages):
            events: list[_Event_API_V9] = self._fetch_activity_page(page)
            for event in events:
                # TODO: Implement a factory method to create the correct Event subclass
                event_date = extract_task_due_date(event.event_date)
                assert event_date is not None
                result.append(Event(event_entry=event, id=event.id, date=event_date))
        return result

    def _fetch_activity_page(self, page: int) -> list[_Event_API_V9]:
        events = []
        limit: int = 50

        url = f"https://api.todoist.com/sync/v9/activity/get?page={page}&limit={limit}"
        response = run(["curl", url, "-H", f"Authorization: Bearer {get_api_key()}"],
                       stdout=PIPE,
                       stderr=DEVNULL,
                       check=True)

        decoded_result: dict = json.loads(response.stdout)
        total_events_count: int = decoded_result['count']

        for event in decoded_result['events']:
            events.append(_Event_API_V9(**event))

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
