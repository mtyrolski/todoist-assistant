from datetime import timedelta

import pandas as pd
import streamlit as st
from todoist.database.dataframe import load_activity_data
from todoist.stats import p1_tasks, p2_tasks, p3_tasks, p4_tasks
from todoist.database.base import Database
from todoist.types import (Project)
from functools import partial


@st.cache_data
def load_activity_data_cached(_dbio: Database) -> pd.DataFrame:
    """
    Loads and processes the activity data from joblib file and database mappings.
    """
    df = load_activity_data(_dbio)
    return df


@st.cache_resource
def get_database() -> Database:
    """
    Returns a Database instance and pulls the latest data.
    """
    dbio = Database('.env', 4)
    dbio.pull()
    return dbio


def sidebar_date_range(df_activity: pd.DataFrame) -> tuple:
    """
    Creates the date range slider in the sidebar.
    """
    oldest_date = df_activity.index.min().to_pydatetime()
    newest_date = df_activity.index.max().to_pydatetime()
    default_range = (newest_date - timedelta(weeks=12), newest_date)

    return st.sidebar.slider(label='Date range',
                             min_value=oldest_date,
                             max_value=newest_date,
                             step=timedelta(weeks=2),
                             value=default_range)


def sidebar_granularity() -> str:
    """
    Creates a granularity selection in the sidebar.
    """
    return st.sidebar.selectbox("Select granularity",
                                options=["W", "ME", "3ME"],
                                format_func=lambda x: {
                                    "W": "Week",
                                    "ME": "Month",
                                    "3ME": "Three Months"
                                }[x])


def extract_metrics(df_activity: pd.DataFrame, granularity: str) -> list[tuple[str, str, str]]:
    # Define time span based on granularity
    granularity_to_timedelta = {"W": timedelta(weeks=1), "ME": timedelta(weeks=4), "3ME": timedelta(weeks=12)}
    if granularity not in granularity_to_timedelta:
        raise ValueError(f"Unsupported granularity: {granularity}")

    timespan = granularity_to_timedelta[granularity]
    # Set current range as the last 'timespan' period in the data
    end_range = df_activity.index.max().to_pydatetime()
    beg_range = end_range - timespan

    # Previous period is the same length immediately preceding beg_range
    previous_beg_range = beg_range - timespan
    previous_end_range = end_range - timespan

    metrics: list[tuple[str, str, str]] = []

    def _get_total_events(df_, beg_, end_):
        filtered_df = df_[(df_.index >= beg_) & (df_.index <= end_)]
        return len(filtered_df)

    def _get_total_tasks_by_type(df_, beg_, end_, task_type):
        filtered_df = df_[(df_.index >= beg_) & (df_.index <= end_)]
        return len(filtered_df[filtered_df['type'] == task_type])

    _get_total_completed_tasks = partial(_get_total_tasks_by_type, task_type='completed')
    _get_total_added_tasks = partial(_get_total_tasks_by_type, task_type='added')
    _get_total_rescheduled_tasks = partial(_get_total_tasks_by_type, task_type='rescheduled')
    for metric_name, metric_func, inverse in [("Events", _get_total_events, False),
                                              ("Completed Tasks", _get_total_completed_tasks, False),
                                              ("Added Tasks", _get_total_added_tasks, False),
                                              ("Rescheduled Tasks", _get_total_rescheduled_tasks, True)]:
        current_value = metric_func(df_activity, beg_range, end_range)
        previous_value = metric_func(df_activity, previous_beg_range, previous_end_range)
        # Avoid division by zero when previous_value is 0
        if previous_value:
            delta_percent = round((current_value - previous_value) / previous_value * 100, 2)
        else:
            delta_percent = float('inf')
        metrics.append((metric_name, str(current_value), f"{delta_percent}%", inverse))

    return metrics


def get_badges(active_projects: list[Project]) -> str:
    """
    Returns a string with the badges of the active projects.
    
    Example of four badges: 
    ":violet-badge[:material/star: 10] :orange-badge[⚠️ 5] :blue-badge[🔵 8] :gray-badge[🔧 2]"
    
    This function returns the following badges:
    P1, P2, P3, P4
    """
    p1_task_count = sum(map(p1_tasks, active_projects))
    p2_task_count = sum(map(p2_tasks, active_projects))
    p3_task_count = sum(map(p3_tasks, active_projects))
    p4_task_count = sum(map(p4_tasks, active_projects))

    badge = (f":red-badge[P1 tasks {p1_task_count}🔥] "
             f":orange-badge[P2 tasks {p2_task_count} ⚠️] "
             f":blue-badge[P3 tasks {p3_task_count} 🔵] "
             f":gray-badge[P4 tasks {p4_task_count} 🔧]")
    return badge
