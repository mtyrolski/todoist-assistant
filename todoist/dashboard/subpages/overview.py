import pandas as pd
import streamlit as st
from todoist.dashboard.utils import extract_metrics, get_badges
from todoist.types import Project, Task
from todoist.plots import (
    current_tasks_types, 
    plot_most_popular_labels,
    plot_events_over_time, 
    plot_heatmap_of_events_by_day_and_hour,
    plot_top_projects_by_events,
    plot_event_distribution_by_type,
    cumsum_completed_tasks_periodically
)


@st.cache_data
def render_overview_page(df_activity: pd.DataFrame, active_projects: list[Project], active_tasks: list[Task],
                        beg_range, end_range, granularity: str, label_colors: dict[str, str], 
                        project_colors: dict[str, str]) -> None:
    """
    Renders a comprehensive overview dashboard page with the most important insights.
    This page combines key metrics, visualizations, and summaries in a single view.
    """
    
    # === TOP SECTION: KEY METRICS ===
    st.header("📊 Productivity Overview")
    
    # Metrics row
    metrics: list[tuple[str, str, str, bool]] = extract_metrics(df_activity, granularity)
    cols = st.columns(len(metrics))
    for i, (metric_name, metric_value, metric_delta, do_inverse) in enumerate(metrics):
        with cols[i]:
            st.metric(
                label=metric_name,
                value=metric_value,
                delta=metric_delta,
                delta_color="inverse" if do_inverse else "normal",
                border=True
            )
    
    # Badges for quick project overview
    badges: str = get_badges(active_projects)
    st.markdown(badges)
    
    # === MAIN CONTENT: THREE COLUMN LAYOUT ===
    st.header("🎯 Activity Insights")
    st.markdown("**Current state of your productivity ecosystem**")
    
    # First row: Current state overview
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.subheader("📋 Current Task Types")
        st.plotly_chart(current_tasks_types(active_projects), use_container_width=True)
    
    with col2:
        st.subheader("🏷️ Popular Labels")
        st.plotly_chart(plot_most_popular_labels(active_projects, label_colors), use_container_width=True)
    
    with col3:
        st.subheader("📈 Event Types Distribution")
        st.plotly_chart(plot_event_distribution_by_type(df_activity, beg_range, end_range, granularity), use_container_width=True)
    
    # === SECOND ROW: TIME-BASED ANALYTICS ===
    st.header("⏰ Time & Activity Patterns")
    st.markdown("**Discover when and where you're most productive**")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🔥 Activity Heatmap")
        st.caption("When are you most productive?")
        st.plotly_chart(plot_heatmap_of_events_by_day_and_hour(df_activity, beg_range, end_range), use_container_width=True)
    
    with col2:
        st.subheader("📊 Top Active Projects")
        st.caption("Projects with most activity")
        st.plotly_chart(plot_top_projects_by_events(df_activity, beg_range, end_range, project_colors), use_container_width=True)
    
    # === THIRD ROW: TREND ANALYSIS ===
    st.header("📈 Progress Trends")
    st.markdown("**Track your productivity evolution over time**")
    
    # Full-width charts for trend analysis
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("⚡ Events Over Time")
        st.caption("Daily activity breakdown with trends")
        st.plotly_chart(plot_events_over_time(df_activity, beg_range, end_range, granularity), use_container_width=True)
    
    with col2:
        st.subheader("🎯 Cumulative Task Completion")
        st.caption("Progress tracking by project")
        st.plotly_chart(cumsum_completed_tasks_periodically(df_activity, beg_range, end_range, granularity, project_colors), use_container_width=True)
    
    # === BOTTOM SECTION: ACTIONABLE INSIGHTS ===
    st.header("💡 Quick Insights")
    st.markdown("**Key takeaways from your productivity data**")
    
    # Calculate some quick stats for insights
    total_active_tasks = len(active_tasks)
    total_projects = len(active_projects)
    recent_activity = len(df_activity.loc[beg_range:end_range])
    
    insight_col1, insight_col2, insight_col3 = st.columns(3)
    
    with insight_col1:
        st.info(f"**{total_active_tasks}** active tasks across **{total_projects}** projects")
    
    with insight_col2:
        if recent_activity > 0:
            avg_daily_activity = recent_activity / max(1, (end_range - beg_range).days)
            st.info(f"**{avg_daily_activity:.1f}** average daily events in selected period")
        else:
            st.info("No activity in selected period")
    
    with insight_col3:
        # Find most active project
        if not df_activity.empty:
            project_activity = df_activity.loc[beg_range:end_range].groupby('root_project_name').size()
            if not project_activity.empty:
                most_active_project = project_activity.idxmax()
                most_active_count = project_activity.max()
                st.success(f"**{most_active_project}** is your most active project ({most_active_count} events)")
            else:
                st.info("No project activity to analyze")
        else:
            st.info("No data available for analysis")