from loguru import logger
import pandas as pd
import streamlit as st
from todoist.plots import (plot_heatmap_of_events_by_day_and_hour,
                           plot_cumulative_events_over_time, cumsum_plot_per_project)
from todoist.types import Task
import math

# Use Streamlit's caching decorator for processing the rescheduled tasks data
@st.cache_data(ttl=3600)  # Cache for 1 hour
def process_rescheduled_tasks(df_activity, active_tasks):
    """
    Process and return rescheduled tasks data with caching.
    """
    rescheduled_tasks = df_activity[df_activity['type'] == 'rescheduled'] \
        .groupby(['title', 'parent_project_name', 'root_project_name']) \
        .size() \
        .sort_values(ascending=False) \
        .reset_index(name='reschedule_count')

    active_non_recurring_tasks = filter(lambda task: task.is_non_recurring, active_tasks)
    act_nonrec_tasks_names = set(task.task_entry.content for task in active_non_recurring_tasks)

    # COLS: title	parent_project_name	root_project_name	reschedule_count
    filtered_tasks = rescheduled_tasks[rescheduled_tasks['title'].isin(act_nonrec_tasks_names)]
    logger.debug(f"Found {len(filtered_tasks)} rescheduled tasks")
    
    return filtered_tasks

def render_task_analysis_page(df_activity: pd.DataFrame,
                              beg_range,
                              end_range,
                              granularity: str,
                              active_tasks: list[Task]) -> None:
    """
    Renders the Task Analysis dashboard page.
    """
    st.header("Heatmap of Events by Day and Hour")
    st.plotly_chart(plot_heatmap_of_events_by_day_and_hour(df_activity, beg_range, end_range, granularity))

    st.header("Cumulative Number of Completed Tasks Over Time")
    st.plotly_chart(plot_cumulative_events_over_time(df_activity, beg_range, end_range, granularity))

    st.header("Cumulative Completed Tasks Per Project")
    st.plotly_chart(cumsum_plot_per_project(df_activity, beg_range, end_range, granularity))

    # List of tasks with the highest number of being rescheduled
    st.header("Tasks with the Highest Number of Reschedules")
    
    # Use the cached function to get rescheduled tasks
    rescheduled_tasks = process_rescheduled_tasks(df_activity, active_tasks)
    # sort by reschedule count
    rescheduled_tasks = rescheduled_tasks.sort_values(by='reschedule_count', ascending=False)
    
    with st.expander("Show Rescheduled Tasks"):
        # Add custom CSS for styling the task cards with dark theme
        st.markdown("""
        <style>
        .task-card {
            border-radius: 5px;
            padding: 8px 15px;
            margin: 5px 0;
            background-color: #2c3e50;
            color: white;
            border-left: 5px solid;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .task-title {
            font-weight: 600;
            margin-right: 10px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            max-width: 60%;
        }
        .task-project {
            color: #b2bec3;
            font-style: italic;
            margin-right: 10px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            max-width: 30%;
        }
        .reschedule-badge {
            background-color: #e74c3c;
            color: white;
            border-radius: 12px;
            padding: 3px 8px;
            font-size: 0.8em;
            min-width: 25px;
            text-align: center;
            font-weight: bold;
        }
        </style>
        """, unsafe_allow_html=True)
        
        # Initialize or get the current pagination state from session_state
        if 'page_number' not in st.session_state:
            st.session_state.page_number = 1
        
        items_per_page = 20
        total_pages = math.ceil(len(rescheduled_tasks) / items_per_page)
        
        # Calculate start and end indices for the current page
        start_idx = (st.session_state.page_number - 1) * items_per_page
        end_idx = min(start_idx + items_per_page, len(rescheduled_tasks))
        
        # Function to determine border color based on reschedule count
        def get_border_color(count):
            if count >= 10:
                return "#e74c3c"  # Red for high reschedule count
            elif count >= 5:
                return "#f39c12"  # Orange/Yellow for medium reschedule count
            else:
                return "#2ecc71"  # Green for low reschedule count
        
        # Display tasks in a compact, single-line format with dark theme
        for i in range(start_idx, end_idx):
            task = rescheduled_tasks.iloc[i]
            border_color = get_border_color(task['reschedule_count'])
            
            html = f"""
            <div class="task-card" style="border-left: 5px solid {border_color}">
                <span class="task-title">{task['title']}</span>
                <span class="task-project">{task['parent_project_name']} → {task['root_project_name']}</span>
                <span class="reschedule-badge">{task['reschedule_count']}×</span>
            </div>
            """
            st.markdown(html, unsafe_allow_html=True)
        
        # Show pagination controls if there are more pages
        if total_pages > 1:
            col1, col2, col3 = st.columns([1, 2, 1])
            
            with col1:
                if st.session_state.page_number > 1:
                    if st.button("← Previous"):
                        st.session_state.page_number -= 1
                        st.rerun()
            
            with col2:
                st.markdown(f"**Page {st.session_state.page_number} of {total_pages}**", 
                           unsafe_allow_html=True)
            
            with col3:
                # Only show "Show More" button if there are more pages to show
                if st.session_state.page_number < total_pages:
                    if st.button("Show More →"):
                        st.session_state.page_number += 1
                        st.rerun()

    # List of oldest tasks
    st.header("Oldest Tasks")