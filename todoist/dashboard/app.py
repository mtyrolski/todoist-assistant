"""
Dashboard for Todoist Summary Plugin.
Refactored for better structure and readability.
"""

import inspect
import sys
from loguru import logger
import streamlit as st

from todoist.dashboard.utils import load_activity_data_cached, sidebar_date_range, sidebar_granularity, get_database
from todoist.types import Project, Task
from todoist.dashboard.subpages import render_home_page, render_project_insights_page, render_task_analysis_page, render_control_panel_page

from todoist.database.demo import anonymize_project_names
from todoist.database.demo import anonymize_label_names


def main() -> None:
    """
    Main function to setup the dashboard.
    """
    st.set_page_config(page_title="Todoist Dashboard", layout="wide")
    dbio = get_database()
    demo_mode: bool = len(sys.argv) > 1 and 'demo' in sys.argv

    with st.spinner('Loading data...'):
        df_activity = load_activity_data_cached(dbio)
        active_projects: list[Project] = dbio.fetch_projects()
    if len(df_activity) == 0:
        st.error(
            "No activity data available. Run `make init_local_env` first and ensure that your keys refer to account with non-zero tasks count."
        )
        st.stop()

    if demo_mode and not dbio.is_anonymized:
        logger.info("Anonymizing data...")
        project_ori2anonym = anonymize_project_names(df_activity)
        label_ori2anonym = anonymize_label_names(active_projects)
        dbio.anonymize(project_mapping=project_ori2anonym, label_mapping=label_ori2anonym)

    project_colors = dbio.fetch_mapping_project_name_to_color()
    label_colors = dbio.fetch_label_colors()
    beg_range, end_range = sidebar_date_range(df_activity)
    granularity = sidebar_granularity()
    active_tasks: list[Task] = [task for project in active_projects for task in project.tasks]
    logger.debug(f"Found {len(active_tasks)} active tasks")
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
