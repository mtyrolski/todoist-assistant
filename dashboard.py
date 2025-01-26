import importlib.util
import sys
from datetime import datetime, timedelta
from os import listdir
from os.path import exists
from pathlib import Path

import pandas as pd
import streamlit as st
from joblib import load
from loguru import logger

from todoist.database import Database
from todoist.plots import (cumsum_plot, plot_completed_tasks_biweekly, cumsum_plot_per_project, cumsum_completed_tasks_biweekly)
from todoist.types import SUPPORTED_EVENT_TYPES, Event, events_to_dataframe


def extract_name(event: Event) -> str | None:
    if 'content' in event.event_entry.extra_data:
        return event.event_entry.extra_data['content']
    if 'name' in event.event_entry.extra_data:
        return event.event_entry.extra_data['name']
    return None


# st.title('Uber pickups in NYC')
ADJUSTMENTS_VARIABLE_NAME = 'link_adjustements'


def get_adjusting_mapping() -> dict[str, str]:
    scripts = list(filter(lambda x: x.endswith('.py'), listdir('personal')))

    logger.info(f'Found {len(scripts)} scripts in personal directory')
    final_mapping = {}
    for script in scripts:

        # execute script as module and get the link_adjustements variable
        script_path = Path('personal') / script

        # Module name (can be anything)
        module_name = 'myscript'

        # Load the module using its path
        spec = importlib.util.spec_from_file_location(module_name, script_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        assert module is not None
        assert hasattr(module, ADJUSTMENTS_VARIABLE_NAME), f'No {ADJUSTMENTS_VARIABLE_NAME} variable in {module_name}'

        link_adjustements = getattr(module, ADJUSTMENTS_VARIABLE_NAME)
        assert isinstance(link_adjustements, dict), f'{ADJUSTMENTS_VARIABLE_NAME} is not a dict'

        final_mapping.update(link_adjustements)

    return final_mapping


@st.cache_data
def load_data():
    activity_filename = 'activity.joblib'
    activity_db: set[Event] = load(activity_filename) if exists(activity_filename) else set()
    supported_events = filter(lambda x: x.event_entry.event_type in SUPPORTED_EVENT_TYPES, activity_db)
    lack_of_title = list(filter(lambda x: extract_name(x) is None, supported_events))
    lack_of_title = sorted(lack_of_title, key=lambda x: x.event_entry.event_date)

    if len(lack_of_title) > 0:
        logger.warning(f'Found {len(lack_of_title)} events without title.')

    dbio = Database('.env', 4)
    mapping_project_id_to_root = dbio.fetch_mapping_project_id_to_root()
    mapping_project_id_to_name = dbio.fetch_mapping_project_id_to_name()
    mapping_project_name_to_id = dbio.fetch_mapping_project_name_to_id()

    df = events_to_dataframe(activity_db,
                             project_id_to_name=mapping_project_id_to_name,
                             project_id_to_root=mapping_project_id_to_root)

    root_id_copy = df['root_project_id'].copy()
    link_adjustements = get_adjusting_mapping()
    df['root_project_name'] = df['root_project_name'].apply(lambda x: link_adjustements.get(x, x))
    df['root_project_id'] = df['root_project_name'].apply(lambda x: mapping_project_name_to_id[x])

    diff_count = (root_id_copy != df['root_project_id']).sum()
    logger.info(f'Changed {diff_count} root project ids out of {len(df)} ({diff_count/len(df)*100:.2f}%)')

    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')
    df = df.set_index('date')

    return df


def main():
    df = load_data()
    last_n_months = 3
    oldest_date: datetime = df.index.min().to_pydatetime()
    newest_date: datetime = df.index.max().to_pydatetime()
    beg_range, end_range = st.slider(label='Last N months',
                                     min_value=oldest_date,
                                     max_value=newest_date,
                                     step=timedelta(weeks=2),
                                     value=(newest_date - timedelta(weeks=4 * last_n_months), newest_date))
    st.plotly_chart(plot_completed_tasks_biweekly(df, beg_range, end_range))
    st.plotly_chart(cumsum_completed_tasks_biweekly(df, beg_range, end_range))
    st.plotly_chart(cumsum_plot_per_project(df, beg_range, end_range))
    st.plotly_chart(cumsum_plot(df, beg_range, end_range))


if __name__ == '__main__':
    main()
