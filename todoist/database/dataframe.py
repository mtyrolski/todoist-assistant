from collections import Counter, defaultdict
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
from typing import cast

from todoist.utils import Cache, LocalStorageError

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
                '}\n\n',
                'archived_parent_projects = [\n',
                '# Optional: archived root projects allowed as mapping targets\n',
                '# "Some archived root project",\n',
                ']\n\n'
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


def _find_duplicate_project_names(
    mapping_project_id_to_name: dict[str, str]
) -> dict[str, list[str]]:
    grouped_ids: dict[str, list[str]] = defaultdict(list)
    for project_id, project_name in mapping_project_id_to_name.items():
        grouped_ids[project_name].append(project_id)
    return {
        project_name: sorted(project_ids)
        for project_name, project_ids in grouped_ids.items()
        if len(project_ids) > 1
    }


def _resolve_root_project_name_to_id(
    _dbio: Database,
) -> tuple[dict[str, str], dict[str, list[str]], set[str], set[str]]:
    active_roots = [
        project
        for project in _dbio.fetch_projects(include_tasks=False)
        if project.project_entry.parent_id is None
    ]
    archived_roots = [
        project
        for project in _dbio.fetch_archived_projects()
        if project.project_entry.parent_id is None
    ]

    active_by_name: dict[str, list[str]] = defaultdict(list)
    archived_by_name: dict[str, list[str]] = defaultdict(list)
    for project in active_roots:
        active_by_name[project.project_entry.name].append(project.id)
    for project in archived_roots:
        archived_by_name[project.project_entry.name].append(project.id)

    resolved: dict[str, str] = {}
    ambiguous: dict[str, list[str]] = {}
    all_root_names = set(active_by_name) | set(archived_by_name)
    for project_name in sorted(all_root_names):
        active_ids = sorted(active_by_name.get(project_name, []))
        archived_ids = sorted(archived_by_name.get(project_name, []))
        if len(active_ids) == 1:
            resolved[project_name] = active_ids[0]
            continue
        if len(active_ids) > 1:
            ambiguous[project_name] = active_ids + archived_ids
            continue
        if len(archived_ids) == 1:
            resolved[project_name] = archived_ids[0]
            continue
        if len(archived_ids) > 1:
            ambiguous[project_name] = archived_ids

    return resolved, ambiguous, set(active_by_name), set(archived_by_name)


def _summarize_counter(counter: Counter[str], *, limit: int = 10) -> str:
    if not counter:
        return '(none)'
    parts = [f'{name}={count}' for name, count in counter.most_common(limit)]
    if len(counter) > limit:
        parts.append(f'... (+{len(counter) - limit} more)')
    return ', '.join(parts)


def load_activity_data(_dbio: Database) -> pd.DataFrame:
    """
    Loads and processes the activity data from joblib file and database mappings.
    """
    activity_filename = 'activity.joblib'
    # activity_db: set[Event] = load(activity_filename) if exists(activity_filename) else set()
    try:
        activity_db: set[Event] = Cache().activity.load()
    except LocalStorageError as exc:
        logger.warning("Failed to load activity cache; using empty set: {}", exc)
        activity_db = set()

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
    duplicate_project_names = _find_duplicate_project_names(mapping_project_id_to_name)
    if duplicate_project_names:
        logger.warning(
            'Detected {} duplicate project names in id->name mapping: {}',
            len(duplicate_project_names),
            _summarize_counter(Counter({
                project_name: len(project_ids)
                for project_name, project_ids in duplicate_project_names.items()
            })),
        )
    root_name_to_id, ambiguous_root_names, active_root_names, archived_root_names = (
        _resolve_root_project_name_to_id(_dbio)
    )
    logger.success(
        'Resolved root name to id mapping (resolved={}, active_roots={}, archived_roots={}, ambiguous_roots={})',
        len(root_name_to_id),
        len(active_root_names),
        len(archived_root_names),
        len(ambiguous_root_names),
    )
    if ambiguous_root_names:
        logger.warning(
            'Ambiguous root project names detected: {}',
            _summarize_counter(Counter({
                project_name: len(project_ids)
                for project_name, project_ids in ambiguous_root_names.items()
            })),
        )
    logger.info('Creating dataframe from events...')

    df = events_to_dataframe(activity_db,
                             project_id_to_name=mapping_project_id_to_name,
                             project_id_to_root=mapping_project_id_to_root)

    original_root_id = df['root_project_id'].copy()
    original_root_name = df['root_project_name'].astype(str).copy()
    link_mapping = get_adjusting_mapping()
    effective_link_mapping = {
        source_name: target_name
        for source_name, target_name in link_mapping.items()
        if source_name != target_name
    }
    logger.info(
        'Loaded {} link adjustments ({} effective renames, {} self-maps)',
        len(link_mapping),
        len(effective_link_mapping),
        len(link_mapping) - len(effective_link_mapping),
    )
    logger.info('Adjusting root project names...')
    adjustment_sources = cast(
        pd.Series,
        original_root_name[original_root_name.isin(link_mapping)],
    )
    effective_adjustment_sources = cast(
        pd.Series,
        original_root_name[original_root_name.isin(effective_link_mapping)],
    )
    logger.info(
        'Adjustment rules matched {} rows across {} source root names',
        len(adjustment_sources),
        adjustment_sources.nunique(),
    )
    if len(adjustment_sources):
        logger.debug(
            'Adjustment source row counts: {}',
            _summarize_counter(Counter(adjustment_sources.to_list())),
        )
    logger.info(
        'Effective rename rules matched {} rows across {} source root names',
        len(effective_adjustment_sources),
        effective_adjustment_sources.nunique(),
    )
    if len(effective_adjustment_sources):
        logger.debug(
            'Effective rename source row counts: {}',
            _summarize_counter(Counter(effective_adjustment_sources.to_list())),
        )
    unused_effective_sources = sorted(
        set(effective_link_mapping) - set(effective_adjustment_sources.astype(str).unique())
    )
    if unused_effective_sources:
        logger.debug(
            'Configured effective rename sources not present in current activity data: {}',
            _summarize_counter(Counter({source_name: 1 for source_name in unused_effective_sources})),
        )

    # Adjust project names and map back to root ids.
    df['root_project_name'] = original_root_name.map(
        lambda name: link_mapping.get(name, name)
    )
    mapped_ids = cast(
        pd.Series,
        df['root_project_name'].map(lambda name: root_name_to_id.get(str(name))),
    )
    df['root_project_id'] = mapped_ids.fillna(original_root_id)
    changed_name_mask = original_root_name != df['root_project_name']
    changed_id_mask = original_root_id != df['root_project_id']

    if changed_name_mask.any():
        logger.debug(
            'Adjustment target row counts: {}',
            _summarize_counter(Counter(df.loc[changed_name_mask, 'root_project_name'].astype(str).to_list())),
        )

    ambiguous_targets = sorted(
        set(df.loc[changed_name_mask, 'root_project_name'].astype(str)) & set(ambiguous_root_names)
    )
    if ambiguous_targets:
        logger.warning(
            'Adjustment targets with ambiguous root ids kept their original ids: {}',
            ', '.join(ambiguous_targets[:10]),
        )

    missing_names = sorted(set(df.loc[changed_name_mask & mapped_ids.isna(), 'root_project_name'].astype(str)))
    if missing_names:
        logger.warning(
            'Missing root project ids for {} adjusted target names: {}',
            len(missing_names),
            ', '.join(missing_names[:10]),
        )

    diff_count = int(changed_id_mask.sum())
    total = len(df)
    ratio = (diff_count / total * 100) if total else 0.0
    logger.info(f'Changed {diff_count} root project ids out of {total} ({ratio:.2f}%)')

    known_root_names = set(root_name_to_id) | set(ambiguous_root_names)
    unresolved_original_roots = sorted(
        {
            root_name
            for root_name in original_root_name.unique()
            if root_name not in known_root_names and root_name not in link_mapping
        }
    )
    if unresolved_original_roots:
        logger.warning(
            'Observed {} root names that are neither current roots nor adjustment sources: {}',
            len(unresolved_original_roots),
            ', '.join(unresolved_original_roots[:10]),
        )
    else:
        logger.debug('All observed root names are current roots or explicitly adjusted.')

    df['date'] = pd.to_datetime(df['date'])
    df.sort_values('date', inplace=True)
    # df.set_index('date', inplace=True)
    df['id'] = df['id'].astype(str)
    df['root_project_id'] = df['root_project_id'].astype(str)

    return df
