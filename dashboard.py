import importlib.util
import sys
from datetime import timedelta
from os import listdir
from os.path import exists
from pathlib import Path

import pandas as pd
import streamlit as st
from joblib import load
from loguru import logger

from todoist.database.base import Database
from todoist.types import SUPPORTED_EVENT_TYPES, Event, Project, events_to_dataframe
from todoist.plots import (current_tasks_types, plot_event_distribution_by_type, plot_events_over_time, plot_most_popular_labels, plot_top_projects_by_events,
                           plot_event_distribution_by_root_project, plot_heatmap_of_events_by_day_and_hour,
                           plot_event_types_by_project, plot_cumulative_events_over_time, cumsum_plot_per_project,
                           plot_completed_tasks_periodically, cumsum_completed_tasks_periodically)

ADJUSTMENTS_VARIABLE_NAME = 'link_adjustements'


def extract_name(event: Event) -> str | None:
    if 'content' in event.event_entry.extra_data:
        return event.event_entry.extra_data['content']
    if 'name' in event.event_entry.extra_data:
        return event.event_entry.extra_data['name']
    return None


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
def load_data(_dbio: Database):
    activity_filename = 'activity.joblib'
    activity_db: set[Event] = load(activity_filename) if exists(activity_filename) else set()
    supported_events = filter(lambda x: x.event_entry.event_type in SUPPORTED_EVENT_TYPES, activity_db)
    lack_of_title = list(filter(lambda x: extract_name(x) is None, supported_events))
    lack_of_title = sorted(lack_of_title, key=lambda x: x.event_entry.event_date)

    if len(lack_of_title) > 0:
        logger.warning(f'Found {len(lack_of_title)} events without title.')

    mapping_project_id_to_root = _dbio.fetch_mapping_project_id_to_root()
    mapping_project_id_to_name = _dbio.fetch_mapping_project_id_to_name()
    mapping_project_name_to_id = _dbio.fetch_mapping_project_name_to_id()

    df = events_to_dataframe(activity_db,
                             project_id_to_name=mapping_project_id_to_name,
                             project_id_to_root=mapping_project_id_to_root)

    root_id_copy = df['root_project_id'].copy()
    link_adjustements = get_adjusting_mapping()
    df['root_project_name'] = df['root_project_name'].apply(lambda x: link_adjustements.get(x, x))
    df['root_project_id'] = df['root_project_name'].apply(lambda x: mapping_project_name_to_id[x])

    diff_count = (root_id_copy != df['root_project_id']).sum()
    logger.info(f'Changed {diff_count} root project ids out of {len(df)} ({diff_count/len(df)*100:.2f}%)')

    # log not adjusted projects which are not in the mapping but should be
    not_adjusted = set(df['root_project_name']) - set(link_adjustements.keys())
    if len(not_adjusted) > 0:
        logger.info(f'Not adjusted projects: {not_adjusted}')
        logger.warning('If any of those is neither active nor archived root project, please adjust the mapping')

        # counts how many subprojects has each root project
        subprojects_count = df['root_project_name'].value_counts()
        logger.info(f'Subprojects count: {subprojects_count}')

    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')
    df = df.set_index('date')

    return df

@st.cache_resource
def get_db():
    dbio = Database('.env', 4)
    dbio.pull()
    
    return dbio

# Plot functions
def main():
    st.set_page_config(page_title="Todoist Dashboard", layout="wide")

    dbio: Database = get_db()

    with st.spinner('Loading data...'):
        df_activity = load_data(dbio)
        active_projects: list[Project] = dbio.fetch_projects()
              
    # Date range slider
    oldest_date = df_activity.index.min().to_pydatetime()
    newest_date = df_activity.index.max().to_pydatetime()
    beg_range, end_range = st.sidebar.slider(
        label='Date range',
        min_value=oldest_date,
        max_value=newest_date,
        step=timedelta(weeks=2),
        value=(newest_date - timedelta(weeks=4 * 3), newest_date)
    )

    # Granularity selection
    granularity = st.sidebar.selectbox("Select granularity", ["W", "ME", "3ME"],
                                       format_func=lambda x: {
                                           "W": "Week",
                                           "ME": "Month",
                                           "3ME": "Three Months"
                                       }[x])

    pages = {
        "Home": [
            ("Most popular labels", "..."), "Periodically Completed Tasks Per Project",
            "Cumulative Periodically Completed Tasks Per Project", "Events Over Time",            
        ],
        "Project Insights": [
            "Top Projects by Number of Events", "Event Distribution by Root Project", "Event Types by Project", "Event Distribution by Type",
        ],
        "Task Analysis": [
            "Heatmap of Events by Day and Hour", "Cumulative Number of Completed Tasks Over Time",
            "Cumulative Completed Tasks Per Project"
        ],
    }

    st.sidebar.title("Navigation")
    page = st.sidebar.radio("Go to", list(pages.keys()))

    st.title(f"{page} Dashboard")

    for plot in pages[page]:
        st.header(plot)
        if plot == ("Most popular labels", "..."):
            col1, col2 = st.columns(2)
            with col1:
                st.plotly_chart(current_tasks_types(active_projects))
            with col2:
                st.plotly_chart(plot_most_popular_labels(active_projects))
        elif plot == "Events Over Time":
            st.plotly_chart(plot_events_over_time(df_activity, beg_range, end_range, granularity))
        elif plot == "Top Projects by Number of Events":
            st.plotly_chart(plot_top_projects_by_events(df_activity, beg_range, end_range, granularity))
        elif plot == "Event Distribution by Root Project":
            st.plotly_chart(plot_event_distribution_by_root_project(df_activity, beg_range, end_range, granularity))
        elif plot == "Heatmap of Events by Day and Hour":
            st.plotly_chart(plot_heatmap_of_events_by_day_and_hour(df_activity, beg_range, end_range, granularity))
        elif plot == "Event Types by Project":
            st.plotly_chart(plot_event_types_by_project(df_activity, beg_range, end_range, granularity))
        elif plot == "Cumulative Events Over Time":
            st.plotly_chart(plot_cumulative_events_over_time(df_activity, beg_range, end_range, granularity))
        elif plot == "Cumulative Completed Tasks Per Project":
            st.plotly_chart(cumsum_plot_per_project(df_activity, beg_range, end_range, granularity))
        elif plot == "Periodically Completed Tasks Per Project":
            st.plotly_chart(plot_completed_tasks_periodically(df_activity, beg_range, end_range, granularity))
        elif plot == "Cumulative Periodically Completed Tasks Per Project":
            st.plotly_chart(cumsum_completed_tasks_periodically(df_activity, beg_range, end_range, granularity))
        elif plot == "Event Distribution by Type":
            st.plotly_chart(plot_event_distribution_by_type(df_activity, beg_range, end_range, granularity))

if __name__ == '__main__':
    main()
