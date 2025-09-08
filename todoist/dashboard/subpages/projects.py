import pandas as pd
import streamlit as st
from todoist.plots import (plot_event_distribution_by_type, plot_top_projects_by_events,
                           plot_event_distribution_by_root_project, plot_event_types_by_project)


@st.cache_data
def render_project_insights_page(df_activity: pd.DataFrame, beg_range, end_range, granularity: str,
                                 project_colors: dict[str, str]) -> None:
    """
    Renders the Project Insights dashboard page.
    """
    st.header("Top Projects by Number of Events")
    st.plotly_chart(plot_top_projects_by_events(df_activity, beg_range, end_range, project_colors))

    st.header("Event Distribution by Root Project")
    st.plotly_chart(plot_event_distribution_by_root_project(df_activity, beg_range, end_range, project_colors))

    st.header("Event Types by Project")
    st.plotly_chart(plot_event_types_by_project(df_activity, beg_range, end_range))

    st.header("Event Distribution by Type")
    st.plotly_chart(plot_event_distribution_by_type(df_activity, beg_range, end_range))
