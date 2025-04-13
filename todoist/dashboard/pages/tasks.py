
import pandas as pd
import streamlit as st
from todoist.plots import (plot_heatmap_of_events_by_day_and_hour,
                           plot_cumulative_events_over_time, cumsum_plot_per_project)

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

