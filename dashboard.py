"""
Dashboard for Todoist Summary Plugin.
Refactored for better structure and readability.
"""

import importlib.util
import inspect
import sys
from datetime import timedelta
from os import listdir
from os.path import exists
from pathlib import Path

import pandas as pd
import streamlit as st
from joblib import load
from loguru import logger
from omegaconf import OmegaConf
from todoist.utils import Cache, load_config
from todoist.stats import p1_tasks, p2_tasks, p3_tasks, p4_tasks
from todoist.database.base import Database
from todoist.types import (SUPPORTED_EVENT_TYPES, Event, Project, events_to_dataframe)
from todoist.plots import (current_tasks_types, plot_event_distribution_by_type, plot_events_over_time,
                           plot_most_popular_labels, plot_top_projects_by_events,
                           plot_event_distribution_by_root_project, plot_heatmap_of_events_by_day_and_hour,
                           plot_event_types_by_project, plot_cumulative_events_over_time, cumsum_plot_per_project,
                           plot_completed_tasks_periodically, cumsum_completed_tasks_periodically)
import hydra
from todoist.automations.base import Automation
import io
import contextlib
from functools import partial

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


@st.cache_data
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
    _get_total_edited_tasks = partial(_get_total_tasks_by_type, task_type='updated')
    for metric_name, metric_func, inverse in [("Events", _get_total_events, False),
                                              ("Completed Tasks", _get_total_completed_tasks, False),
                                              ("Added Tasks", _get_total_added_tasks, False),
                                              ("Edited Tasks", _get_total_edited_tasks, False)]:
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


def render_home_page(df_activity: pd.DataFrame, active_projects: list[Project], beg_range, end_range,
                     granularity: str) -> None:
    """
    Renders the Home dashboard page.
    """
    # Two-column layout for Most Popular Labels paired with Current Tasks Types
    col1, col2 = st.columns(2)
    with col1:
        st.header("Current Tasks Types")
        st.plotly_chart(current_tasks_types(active_projects))
    with col2:
        st.header("Most Popular Labels")
        st.plotly_chart(plot_most_popular_labels(active_projects))
    # Metrics
    metrics: list[tuple[str, str, str, bool]] = extract_metrics(df_activity, granularity)
    cols = st.columns(len(metrics))
    for i, (metric_name, metric_value, metric_delta, do_inverse) in enumerate(metrics):
        with cols[i]:
            st.metric(label=metric_name,
                      value=metric_value,
                      delta=metric_delta,
                      delta_color="inverse" if do_inverse else "normal",
                      border=True)

    # Badges
    badges: str = get_badges(active_projects)
    st.markdown(badges)

    st.header("Periodically Completed Tasks Per Project")
    st.plotly_chart(plot_completed_tasks_periodically(df_activity, beg_range, end_range, granularity))

    st.header("Cumulative Periodically Completed Tasks Per Project")
    st.plotly_chart(cumsum_completed_tasks_periodically(df_activity, beg_range, end_range, granularity))

    st.header("Events Over Time")
    st.plotly_chart(plot_events_over_time(df_activity, beg_range, end_range, granularity))


def render_project_insights_page(df_activity: pd.DataFrame, beg_range, end_range, granularity: str) -> None:
    """
    Renders the Project Insights dashboard page.
    """
    st.header("Top Projects by Number of Events")
    st.plotly_chart(plot_top_projects_by_events(df_activity, beg_range, end_range, granularity))

    st.header("Event Distribution by Root Project")
    st.plotly_chart(plot_event_distribution_by_root_project(df_activity, beg_range, end_range, granularity))

    st.header("Event Types by Project")
    st.plotly_chart(plot_event_types_by_project(df_activity, beg_range, end_range, granularity))

    st.header("Event Distribution by Type")
    st.plotly_chart(plot_event_distribution_by_type(df_activity, beg_range, end_range, granularity))


def render_task_analysis_page(df_activity: pd.DataFrame, beg_range, end_range, granularity: str) -> None:
    """
    Renders the Task Analysis dashboard page.
    """
    st.header("Heatmap of Events by Day and Hour")
    st.plotly_chart(plot_heatmap_of_events_by_day_and_hour(df_activity, beg_range, end_range, granularity))

    st.header("Cumulative Number of Completed Tasks Over Time")
    st.plotly_chart(plot_cumulative_events_over_time(df_activity, beg_range, end_range, granularity))

    st.header("Cumulative Completed Tasks Per Project")
    st.plotly_chart(cumsum_plot_per_project(df_activity, beg_range, end_range, granularity))


def render_control_panel_page(dbio: Database) -> None:
    config: OmegaConf = load_config('automations', '../configs')
    automations: list[Automation] = hydra.utils.instantiate(config.automations)

    st.title("Automation Control Panel")
    st.write("Manage and execute your automations below:")

    # Add some custom CSS for a better appearance
    st.markdown("""
        <style>
        .automation-box {
            border: 1px solid #ddd;
            border-radius: 5px;
            padding: 10px;
            margin-bottom: 10px;
            background-color: #fff;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
        }
        .automation-title {
            font-weight: bold;
            color: #333;
        }
        .automation-details {
            margin-top: 10px;
            margin-bottom: 10px;
        }
        .automation-output {
            background-color: #f9f9f9;
            border-radius: 5px;
            padding: 10px;
            margin-top: 10px;
        }
        </style>
        """,
                unsafe_allow_html=True)

    for automation in automations:
        cache = Cache()
        launches = cache.automation_launches.load()
        if automation.name in launches:
            launch_count = len(launches[automation.name])
            last_launch = launches[automation.name][-1].strftime("%Y-%m-%d %H:%M:%S")
        else:
            launch_count = 0
            last_launch = "Never"
        st.markdown(f"<div class='automation-details'><b>Last launch:</b> {last_launch}</div>", unsafe_allow_html=True)

        with st.expander(f"{automation.name}"):
            st.markdown(f"<span class='automation-title'>{automation.name}</span>", unsafe_allow_html=True)
            run_pressed = st.button("▶️ Run", key=automation.name)

            st.markdown(f"<div class='automation-details'><b>Launches:</b> {launch_count}</div>",
                        unsafe_allow_html=True)

            if run_pressed:
                with st.spinner("Executing automation..."):
                    stdout_capture = io.StringIO()
                    stderr_capture = io.StringIO()
                    with contextlib.redirect_stdout(stdout_capture), contextlib.redirect_stderr(stderr_capture):
                        automation.tick(dbio)
                    output = stdout_capture.getvalue()
                    error = stderr_capture.getvalue()
                    dbio.reset()
                st.success("Automation executed successfully!")

                # Display the captured output and error
                if output or error:
                    if output:
                        st.markdown("**Output:**")
                        st.text(output)
                    if error:
                        st.markdown("**Error:**")
                        st.text(error)


def main() -> None:
    """
    Main function to setup the dashboard.
    """
    st.set_page_config(page_title="Todoist Dashboard", layout="wide")
    dbio = get_database()

    with st.spinner('Loading data...'):
        df_activity = load_activity_data(dbio)
        active_projects: list[Project] = dbio.fetch_projects()

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
