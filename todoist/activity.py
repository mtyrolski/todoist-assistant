from loguru import logger

from todoist.database.base import Database
from todoist.types import Event
import typer

from todoist.utils import Cache, LocalStorageError

EventCollection = set[Event]
NWEEKSMAX = 520    # 10 years


def get_last_n_events(events: EventCollection, n: int) -> EventCollection:
    """
    Returns the last n events in the collection.
    """
    sorted_events = sorted(events, key=lambda x: x.event_entry.event_date, reverse=True)
    return set(sorted_events[:n])


def quick_summarize(events: EventCollection, new_events: EventCollection):
    """
    Quick print of summarized events:
    """

    if len(events) == 0:
        logger.warning('No events to summarize')
        return

    summary_count = {}
    new_events_count = {}
    for event in events:
        summary_count[event.event_entry.event_type] = summary_count.get(event.event_entry.event_type, 0) + 1
    for event in new_events:
        new_events_count[event.event_entry.event_type] = new_events_count.get(event.event_entry.event_type,
                                                                              0) + 1 if event in new_events else 0

    summary_percentage = {k: round(v / len(events) * 100, 2) for k, v in summary_count.items()}

    for event_type, count in summary_count.items():
        percentage = summary_percentage[event_type]
        new_count = new_events_count.get(event_type, 0)
        if new_count == 0:
            logger.info(f'{event_type}: {count} ({percentage}%)')
            continue
        logger.info(
            f'{event_type}: {summary_count[event_type]} ({summary_percentage[event_type]}%)\t\t(+{new_events_count.get(event_type, 0)})'
        )


def fetch_activity(dbio: Database, nweeks: int) -> tuple[EventCollection, EventCollection, bool]:
    """Fetches activity from the last n_weeks weeks, updates
    local database, and returns the new items.

    Third param is a is_corrupted flag indicating if internl error occured and database had to be recreated."""
    fetched_activity: list[Event] = dbio.fetch_activity(max_pages=nweeks)
    logger.info(f'Fetched {len(fetched_activity)} events')
    is_corrupted = False
    try:
        all_events: set[Event] = Cache().activity.load()
    except LocalStorageError as e:
        logger.error('No local activity database found, creating a new one.')
        logger.error(str(e))
        is_corrupted = True
        all_events = set()
    new_events: set[Event] = set()
    for fetched_event in fetched_activity:
        if fetched_event not in all_events:
            all_events.add(fetched_event)
            new_events.add(fetched_event)
    logger.info(f'Added {len(new_events)} new events, current size: {len(all_events)}')
    Cache().activity.save(all_events)
    return all_events, new_events, is_corrupted


def remove_last_n_events_from_activity(activity_db: EventCollection, n: int) -> EventCollection:
    events_to_remove = get_last_n_events(activity_db, n)
    for event in events_to_remove:
        activity_db.remove(event)
    Cache().activity.save(activity_db)
    return activity_db


def main(nweeks: int = 3):
    dbio = Database('.env')
    activity_db, new_items, is_corrupted = fetch_activity(dbio, nweeks)
    logger.info(f'Summary of Activity (is_corrupted={is_corrupted}):')
    quick_summarize(activity_db, new_items)


if __name__ == '__main__':
    typer.run(main)
