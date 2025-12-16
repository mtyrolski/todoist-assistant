import pandas as pd
import streamlit as st
from todoist.dashboard.utils import extract_metrics, get_badges
from todoist.types import (Project)
from todoist.plots import (current_tasks_types, plot_events_over_time, plot_heatmap_of_events_by_day_and_hour, plot_most_popular_labels,
                           plot_completed_tasks_periodically, cumsum_completed_tasks_periodically,
                           plot_task_lifespans)


@st.cache_data
def render_home_page(df_activity: pd.DataFrame, active_projects: list[Project], beg_range, end_range, granularity: str,
                     label_colors: dict[str, str], project_colors: dict[str, str]) -> None:
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
        st.plotly_chart(plot_most_popular_labels(active_projects, label_colors))
    # Metrics
    metrics, current_period, previous_period = extract_metrics(df_activity, granularity)
    cols = st.columns(len(metrics))
    for i, (metric_name, metric_value, metric_delta, do_inverse) in enumerate(metrics):
        with cols[i]:
            st.metric(label=metric_name,
                      value=metric_value,
                      delta=metric_delta,
                      delta_color="inverse" if do_inverse else "normal",
                      border=True)

            # Add date range information inside the metric box area
            st.markdown(f"""
            <div style="margin-top: 5px; font-size: 9px; line-height: 1.2; padding: 4px 8px; background-color: rgba(255,255,255,0.05); border-radius: 4px;">
                <div style="color: #00d4aa; font-weight: 500; margin-bottom: 2px;">
                    ▶ {current_period}
                </div>
                <div style="color: #ff6b6b; font-weight: 500;">
                    ◀ {previous_period}
                </div>
            </div>
            """, unsafe_allow_html=True)

    # Badges
    badges: str = get_badges(active_projects)
    st.markdown(badges)

    st.header("Task Lifespans: Time to Completion")
    st.plotly_chart(plot_task_lifespans(df_activity), use_container_width=True)

    st.header("Periodically Completed Tasks Per Project")
    st.plotly_chart(plot_completed_tasks_periodically(df_activity, beg_range, end_range, granularity, project_colors))

    st.header("Cumulative Periodically Completed Tasks Per Project")
    st.plotly_chart(cumsum_completed_tasks_periodically(df_activity, beg_range, end_range, granularity, project_colors))

    st.header("Heatmap of Events by Day and Hour")
    st.plotly_chart(plot_heatmap_of_events_by_day_and_hour(df_activity, beg_range, end_range))

    st.header("Events Over Time")
    st.plotly_chart(plot_events_over_time(df_activity, beg_range, end_range, granularity))
