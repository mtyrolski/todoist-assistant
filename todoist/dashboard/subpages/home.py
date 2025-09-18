import pandas as pd
import streamlit as st
from todoist.dashboard.utils import extract_metrics, get_badges
from todoist.types import (Project)
from todoist.plots import (current_tasks_types, plot_events_over_time, plot_most_popular_labels,
                           plot_completed_tasks_periodically, cumsum_completed_tasks_periodically,
                           plot_heatmap_of_events_by_day_and_hour, plot_top_projects_by_events,
                           plot_cumulative_events_over_time)


@st.cache_data
def render_home_page(df_activity: pd.DataFrame, active_projects: list[Project], beg_range, end_range, granularity: str,
                     label_colors: dict[str, str], project_colors: dict[str, str]) -> None:
    """
    Renders the comprehensive Home dashboard page with most important plots and insights.
    """
    
    # ===== TOP SECTION: KEY METRICS AND BADGES =====
    st.markdown("### 📊 **Productivity Overview**")
    
    # Priority badges for quick status overview
    badges: str = get_badges(active_projects)
    st.markdown(badges)
    
    # Key metrics in a single row
    metrics: list[tuple[str, str, str, bool]] = extract_metrics(df_activity, granularity)
    cols = st.columns(len(metrics))
    for i, (metric_name, metric_value, metric_delta, do_inverse) in enumerate(metrics):
        with cols[i]:
            st.metric(label=metric_name,
                      value=metric_value,
                      delta=metric_delta,
                      delta_color="inverse" if do_inverse else "normal",
                      border=True)
    
    # ===== MAIN DASHBOARD GRID =====
    st.markdown("---")
    
    # Row 1: Activity Heatmap (full width) - Most important insight
    st.markdown("### 🕒 **Activity Patterns**")
    st.plotly_chart(plot_heatmap_of_events_by_day_and_hour(df_activity, beg_range, end_range), 
                    use_container_width=True)
    
    # Row 2: Current Status (2 columns)
    st.markdown("### 📋 **Current Status**")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**🎯 Task Types Distribution**")
        st.plotly_chart(current_tasks_types(active_projects), use_container_width=True)
    with col2:
        st.markdown("**🏷️ Most Popular Labels**")
        st.plotly_chart(plot_most_popular_labels(active_projects, label_colors), use_container_width=True)
    
    # Row 3: Progress Trends (2 columns)
    st.markdown("### 📈 **Progress Trends**")
    col3, col4 = st.columns(2)
    with col3:
        st.markdown("**📊 Events Over Time**")
        st.plotly_chart(plot_events_over_time(df_activity, beg_range, end_range, granularity), 
                        use_container_width=True)
    with col4:
        st.markdown("**📂 Top Projects by Activity**")
        st.plotly_chart(plot_top_projects_by_events(df_activity, beg_range, end_range, project_colors), 
                        use_container_width=True)
    
    # Row 4: Completion Analysis (2 columns)
    st.markdown("### ✅ **Completion Analysis**")
    col5, col6 = st.columns(2)
    with col5:
        st.markdown("**📝 Completed Tasks by Period**")
        st.plotly_chart(plot_completed_tasks_periodically(df_activity, beg_range, end_range, granularity, project_colors), 
                        use_container_width=True)
    with col6:
        st.markdown("**📈 Cumulative Progress**")
        st.plotly_chart(plot_cumulative_events_over_time(df_activity, beg_range, end_range, granularity), 
                        use_container_width=True)
