import pandas as pd
import streamlit as st
from todoist.dashboard.utils import extract_metrics, get_badges
from todoist.types import (Project)
from todoist.plots import (current_tasks_types, plot_events_over_time, plot_most_popular_labels,
                           plot_completed_tasks_periodically, cumsum_completed_tasks_periodically)


@st.cache_data
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
