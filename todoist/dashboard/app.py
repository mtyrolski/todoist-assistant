"""
Dashboard for Todoist Summary Plugin.
Refactored for better structure and readability.
"""

import inspect
import sys
import streamlit as st

from todoist.dashboard.utils import load_activity_data_cached, sidebar_date_range, sidebar_granularity, get_database
from todoist.types import Task
from todoist.dashboard.subpages import render_home_page, render_project_insights_page, render_task_analysis_page, render_control_panel_page
from todoist.automations.activity import Activity

def main() -> None:
    """
    Main function to setup the dashboard.
    """
    st.set_page_config(page_title="Todoist Dashboard", layout="wide")
    dbio = get_database()
    demo_mode: bool = len(sys.argv) > 1 and 'demo' in sys.argv
    Activity(name='last_2_week.on_launch', nweeks=2, frequency_in_minutes=2).tick(dbio)

    with st.spinner('Loading data...'):
        (df_activity, active_projects) = load_activity_data_cached(dbio, demo_mode)
    if len(df_activity) == 0:
        st.error(
            "No activity data available. Run `make init_local_env` first and ensure that your keys refer to account with non-zero tasks count."
        )
        st.stop()

    project_colors = dbio.fetch_mapping_project_name_to_color()
    label_colors = dbio.fetch_label_colors()
    beg_range, end_range = sidebar_date_range(df_activity)
    granularity = sidebar_granularity()
    active_tasks: list[Task] = [task for project in active_projects for task in project.tasks]
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
        'active_tasks': active_tasks,
        'dbio': dbio,
        'project_colors': project_colors,
        'label_colors': label_colors,
    }

    page_render_fn = pages[current_page]
    arguments = inspect.signature(page_render_fn).parameters.keys()
    page_render_fn(**{arg: kwargs[arg] for arg in arguments})


if __name__ == '__main__':
    main()
