"""
Dashboard for Todoist Summary Plugin.
Refactored for better structure and readability.
"""

import inspect

import streamlit as st

from todoist.dashboard.utils import load_activity_data, sidebar_date_range, sidebar_granularity, get_database
from todoist.types import Project
from todoist.dashboard.subpages import render_home_page, render_project_insights_page, render_task_analysis_page, render_control_panel_page

def main() -> None:
    """
    Main function to setup the dashboard.
    """
    st.set_page_config(page_title="Todoist Dashboard", layout="wide")
    dbio = get_database()

    with st.spinner('Loading data...'):
        df_activity = load_activity_data(dbio)
        active_projects: list[Project] = dbio.fetch_projects()
    if len(df_activity) == 0:
        st.error("No activity data available. Run `make init_local_env` first and ensure that your keys refer to account with non-zero tasks count.")
        st.stop()
    beg_range, end_range = sidebar_date_range(df_activity)
    granularity = sidebar_granularity()

    # Navigation
    pages = {
        "Home": render_home_page,
        "Project Insights": render_project_insights_page,
        "Task Analysis": render_task_analysis_page,
        'Control Panel': render_control_panel_page
    }
    st.sidebar.title("Navigation")
    current_page = st.sidebar.radio("Go to", list(pages.keys()))

    st.title(f"{current_page} Dashboard")

    kwargs = {
        'df_activity': df_activity,
        'beg_range': beg_range,
        'end_range': end_range,
        'granularity': granularity,
        'active_projects': active_projects,
        'dbio': dbio
    }

    page_render_fn = pages[current_page]
    arguments = inspect.signature(page_render_fn).parameters.keys()
    page_render_fn(**{arg: kwargs[arg] for arg in arguments})


if __name__ == '__main__':
    main()
