from todoist.database.base import Database
from todoist.types import SUPPORTED_EVENT_TYPES, Event, events_to_dataframe
from joblib import load
from os.path import exists
import pandas as pd
from loguru import logger
from os import listdir
import importlib.util
import sys
from pathlib import Path

ADJUSTMENTS_VARIABLE_NAME = 'link_adjustements'


def extract_name(event: Event) -> str | None:
    """
    Extracts the event name from the event's extra data.
    """
    extra = event.event_entry.extra_data
    if 'content' in extra:
        return extra['content']
    if 'name' in extra:
        return extra['name']
    return None


def get_adjusting_mapping() -> dict[str, str]:
    """
    Loads mapping adjustments from all Python scripts in the 'personal' directory.
    """
    personal_dir = Path('personal')
    scripts = [s for s in listdir(personal_dir) if s.endswith('.py')]
    logger.info(f'Found {len(scripts)} scripts in personal directory')

    final_mapping: dict[str, str] = {}
    for script in scripts:
        script_path = personal_dir / script
        module_name = 'personal_script'

        spec = importlib.util.spec_from_file_location(module_name, script_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        if not hasattr(module, ADJUSTMENTS_VARIABLE_NAME):
            raise AttributeError(f'Module {module_name} in {script_path} does not contain the '
                                 f'"{ADJUSTMENTS_VARIABLE_NAME}" variable')

        link_adjustements = getattr(module, ADJUSTMENTS_VARIABLE_NAME)
        if not isinstance(link_adjustements, dict):
            raise TypeError(f'"{ADJUSTMENTS_VARIABLE_NAME}" in {script_path} is not a dict')

        final_mapping.update(link_adjustements)

    return final_mapping


def load_activity_data(_dbio: Database) -> pd.DataFrame:
    """
    Loads and processes the activity data from joblib file and database mappings.
    """
    activity_filename = 'activity.joblib'
    activity_db: set[Event] = load(activity_filename) if exists(activity_filename) else set()

    # Filter supported events and check for events with missing titles
    supported_events = list(filter(lambda ev: ev.event_entry.event_type in SUPPORTED_EVENT_TYPES, activity_db))
    no_title_events = sorted(filter(lambda ev: extract_name(ev) is None, supported_events),
                             key=lambda ev: ev.event_entry.event_date)
    if no_title_events:
        logger.warning(f'Found {len(no_title_events)} events without title.')

    mapping_project_id_to_root = _dbio.fetch_mapping_project_id_to_root()
    mapping_project_id_to_name = _dbio.fetch_mapping_project_id_to_name()
    mapping_project_name_to_id = _dbio.fetch_mapping_project_name_to_id()

    df = events_to_dataframe(activity_db,
                             project_id_to_name=mapping_project_id_to_name,
                             project_id_to_root=mapping_project_id_to_root)

    original_root_id = df['root_project_id'].copy()
    link_mapping = get_adjusting_mapping()

    # Adjust project names and map back to ids
    df['root_project_name'] = df['root_project_name'].apply(lambda name: link_mapping.get(name, name))
    df['root_project_id'] = df['root_project_name'].apply(lambda name: mapping_project_name_to_id[name])

    diff_count = (original_root_id != df['root_project_id']).sum()
    logger.info(f'Changed {diff_count} root project ids out of {len(df)} '
                f'({diff_count/len(df)*100:.2f}%)')

    not_adjusted = set(df['root_project_name']) - set(link_mapping.keys())
    if not_adjusted:
        logger.info(f'Not adjusted projects: {not_adjusted}')
        logger.warning('If any of these are neither active nor archived root project, please adjust the mapping')

        subprojects_count = df['root_project_name'].value_counts()
        logger.info(f'Subprojects count: {subprojects_count}')

    df['date'] = pd.to_datetime(df['date'])
    df.sort_values('date', inplace=True)
    df.set_index('date', inplace=True)
    df['id'] = df['id'].astype(str)
    df['root_project_id'] = df['root_project_id'].astype(str)

    return df
