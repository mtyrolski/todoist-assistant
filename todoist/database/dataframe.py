from todoist.constants import EventExtraField
from todoist.database.base import Database
from todoist.types import SUPPORTED_EVENT_TYPES, Event, events_to_dataframe
import pandas as pd
from loguru import logger
from os import listdir
import os
import importlib.util
import sys
from pathlib import Path

from todoist.utils import Cache

ADJUSTMENTS_VARIABLE_NAME = 'link_adjustements'


def extract_name(event: Event) -> str | None:
    """
    Extracts the event name from the event's extra data.
    """
    extra = event.event_entry.extra_data
    if EventExtraField.CONTENT in extra:
        return extra[EventExtraField.CONTENT]
    if EventExtraField.NAME in extra:
        return extra[EventExtraField.NAME]
    return None


def get_adjusting_mapping(specific_file: str | None = None) -> dict[str, str]:
    """
    Loads mapping adjustments from Python scripts in the 'personal' directory.

    Args:
        specific_file: Optional specific filename to load. If None, loads all Python files.
                      If provided, only loads from that specific file.
    """
    personal_dir = Path('personal')

    if not personal_dir.exists():
        logger.warning(f'Personal directory {personal_dir} does not exist. No adjustments will be made.')
        os.makedirs(personal_dir)
        with open(personal_dir / 'archived_root_projects.py', 'w') as f:
            f.writelines([
                '# Adjustments for archived root projects\n',
                '# This file is auto-generated. Do not edit manually.\n',
                'link_adjustements = {\n',
                '# No adjustments made\n',
                '# "some_archived_project": "some_current_main_project"\n',
                '# "other_archived_project": "other_archived_main_project"\n',
                '}\n\n'
            ])
        logger.info(f'Created empty adjustments file in {personal_dir}')
        return {}

    # Determine which files to load
    if specific_file:
        scripts = [specific_file] if (personal_dir / specific_file).exists() else []
        logger.info(f'Loading specific mapping file: {specific_file}')
    else:
        scripts = [s for s in listdir(personal_dir) if s.endswith('.py')]
        logger.info(f'Found {len(scripts)} scripts in personal directory')

    final_mapping: dict[str, str] = {}
    for script in scripts:
        script_path = personal_dir / script
        module_name = 'personal_script'

        spec = importlib.util.spec_from_file_location(module_name, script_path)
        if spec is None or spec.loader is None:
            logger.warning("Skipping personal mapping file with no module spec: %s", script_path)
            continue
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
    # activity_db: set[Event] = load(activity_filename) if exists(activity_filename) else set()
    activity_db: set[Event] = Cache().activity.load()

    # Filter supported events and check for events with missing titles
    supported_events = list(filter(lambda ev: ev.event_entry.event_type in SUPPORTED_EVENT_TYPES, activity_db))
    no_title_events = sorted(filter(lambda ev: extract_name(ev) is None, supported_events),
                             key=lambda ev: ev.event_entry.event_date)
    if no_title_events:
        logger.warning(f'Found {len(no_title_events)} events without title.')

    logger.info(f'Loaded {len(activity_db)} events from {activity_filename}.')
    mapping_project_id_to_root = _dbio.fetch_mapping_project_id_to_root()
    logger.success(f'Loaded project id to root mapping ({len(mapping_project_id_to_root)} entries)')
    mapping_project_id_to_name = _dbio.fetch_mapping_project_id_to_name()
    logger.success(f'Loaded project id to name mapping ({len(mapping_project_id_to_name)} entries)')
    mapping_project_name_to_id = _dbio.fetch_mapping_project_name_to_id()
    logger.success(f'Loaded project name to id mapping ({len(mapping_project_name_to_id)} entries)')
    logger.info('Creating dataframe from events...')

    df = events_to_dataframe(activity_db,
                             project_id_to_name=mapping_project_id_to_name,
                             project_id_to_root=mapping_project_id_to_root)

    original_root_id = df['root_project_id'].copy()
    link_mapping = get_adjusting_mapping()
    logger.info(f'Loaded {len(link_mapping)} link adjustments')
    logger.info('Adjusting root project names...')
    # Adjust project names and map back to ids
    df['root_project_name'] = df['root_project_name'].apply(lambda name: link_mapping.get(name, name))
    df['root_project_id'] = df['root_project_name'].apply(lambda name: mapping_project_name_to_id[name])

    diff_count = (original_root_id != df['root_project_id']).sum()
    total = len(df)
    ratio = (diff_count / total * 100) if total else 0.0
    logger.info(f'Changed {diff_count} root project ids out of {total} ({ratio:.2f}%)')

    not_adjusted = set(df['root_project_name']) - set(link_mapping.keys())
    if not_adjusted:
        logger.warning('If any of these are neither active nor archived root project, please adjust the mapping')

    df['date'] = pd.to_datetime(df['date'])
    df.sort_values('date', inplace=True)
    df.set_index('date', inplace=True)
    df['id'] = df['id'].astype(str)
    df['root_project_id'] = df['root_project_id'].astype(str)

    return df
