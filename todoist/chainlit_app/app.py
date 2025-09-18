"""
Chainlit application for Todoist Assistant.
Provides interactive plot visualization with buttons and chat agent placeholder.
"""

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

import chainlit as cl
import pandas as pd
import plotly.graph_objects as go
from loguru import logger

# Add the project root to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from todoist.dashboard.utils import get_database, load_activity_data_cached
from todoist.plots import (
    current_tasks_types,
    plot_most_popular_labels,
    plot_events_over_time,
    plot_completed_tasks_periodically,
    cumsum_completed_tasks_periodically,
    plot_event_distribution_by_type,
    plot_top_projects_by_events,
    plot_event_distribution_by_root_project,
    plot_heatmap_of_events_by_day_and_hour,
    plot_event_types_by_project,
    plot_cumulative_events_over_time,
    cumsum_plot_per_project,
)

# Global variables to store data
_data_cache = {}


async def load_data():
    """Load data asynchronously and cache it."""
    if _data_cache:
        return _data_cache
    
    try:
        dbio = get_database()
        demo_mode = False  # You can modify this based on command line args if needed
        
        # Load activity data
        df_activity, active_projects = load_activity_data_cached(dbio, demo_mode)
        
        if len(df_activity) == 0:
            raise ValueError("No activity data available. Run `make init_local_env` first.")
        
        # Get additional data
        project_colors = dbio.fetch_mapping_project_name_to_color()
        label_colors = dbio.fetch_label_colors()
        
        # Set default date range (last 12 weeks)
        newest_date = df_activity.index.max().to_pydatetime()
        oldest_date = df_activity.index.min().to_pydatetime()
        default_range = (newest_date - timedelta(weeks=12), newest_date)
        
        _data_cache.update({
            'df_activity': df_activity,
            'active_projects': active_projects,
            'project_colors': project_colors,
            'label_colors': label_colors,
            'beg_range': default_range[0],
            'end_range': default_range[1],
            'granularity': 'W',  # Default to weekly
            'oldest_date': oldest_date,
            'newest_date': newest_date,
        })
        
        return _data_cache
    
    except Exception as e:
        logger.error(f"Error loading data: {e}")
        raise


@cl.on_chat_start
async def start():
    """Initialize the chat session."""
    await cl.Message(
        content="🚀 **Welcome to Todoist Assistant!**\n\n"
        "I'm your productivity analysis assistant. I can help you visualize your Todoist data with various charts and plots.\n\n"
        "**Available Features:**\n"
        "📊 **Plot Visualization** - Click the buttons below to view different charts\n"
        "💬 **Chat Agent** (Coming Soon) - Ask questions about your productivity data\n\n"
        "Let me load your data first..."
    ).send()
    
    # Load data
    try:
        await load_data()
        await cl.Message(
            content="✅ **Data loaded successfully!**\n\n"
            "Choose a visualization below to explore your productivity data:"
        ).send()
        
        # Create action buttons for different plots
        actions = [
            cl.Action(name="current_tasks", value="current_tasks", description="📋 Current Task Types"),
            cl.Action(name="popular_labels", value="popular_labels", description="🏷️ Most Popular Labels"),
            cl.Action(name="events_over_time", value="events_over_time", description="📈 Events Over Time"),
            cl.Action(name="completed_tasks", value="completed_tasks", description="✅ Completed Tasks (Periodic)"),
            cl.Action(name="cumulative_completed", value="cumulative_completed", description="📊 Cumulative Completed Tasks"),
        ]
        
        await cl.Message(
            content="**📊 Basic Visualizations:**",
            actions=actions
        ).send()
        
        # Advanced visualizations
        advanced_actions = [
            cl.Action(name="event_distribution", value="event_distribution", description="🥧 Event Distribution by Type"),
            cl.Action(name="top_projects", value="top_projects", description="🏆 Top Projects by Events"),
            cl.Action(name="project_distribution", value="project_distribution", description="📊 Event Distribution by Project"),
            cl.Action(name="event_heatmap", value="event_heatmap", description="🔥 Event Heatmap (Day/Hour)"),
        ]
        
        await cl.Message(
            content="**🔬 Advanced Analytics:**",
            actions=advanced_actions
        ).send()
        
        # More advanced plots
        expert_actions = [
            cl.Action(name="event_types_by_project", value="event_types_by_project", description="📋 Event Types by Project"),
            cl.Action(name="cumulative_events", value="cumulative_events", description="📈 Cumulative Events Over Time"),
            cl.Action(name="cumsum_per_project", value="cumsum_per_project", description="📊 Cumulative Sum per Project"),
        ]
        
        await cl.Message(
            content="**👨‍💻 Expert Analysis:**",
            actions=expert_actions
        ).send()
        
    except Exception as e:
        await cl.Message(
            content=f"❌ **Error loading data:** {str(e)}\n\n"
            "Please ensure you have run `make init_local_env` to initialize your data."
        ).send()


@cl.action_callback("current_tasks")
async def on_current_tasks(action):
    """Display current task types chart."""
    try:
        data = await load_data()
        fig = current_tasks_types(data['active_projects'])
        
        await cl.Message(
            content="📋 **Current Task Types Distribution**\n\n"
            "This chart shows the distribution of your current tasks by their due date categories."
        ).send()
        
        await cl.Plotly(figure=fig, name="current_tasks", display="inline").send()
        
    except Exception as e:
        await cl.Message(content=f"❌ Error generating chart: {str(e)}").send()


@cl.action_callback("popular_labels")
async def on_popular_labels(action):
    """Display most popular labels chart."""
    try:
        data = await load_data()
        fig = plot_most_popular_labels(data['active_projects'], data['label_colors'])
        
        await cl.Message(
            content="🏷️ **Most Popular Labels**\n\n"
            "This chart displays the most frequently used labels across your projects."
        ).send()
        
        await cl.Plotly(figure=fig, name="popular_labels", display="inline").send()
        
    except Exception as e:
        await cl.Message(content=f"❌ Error generating chart: {str(e)}").send()


@cl.action_callback("events_over_time")
async def on_events_over_time(action):
    """Display events over time chart."""
    try:
        data = await load_data()
        fig = plot_events_over_time(
            data['df_activity'],
            data['beg_range'],
            data['end_range'],
            data['granularity']
        )
        
        await cl.Message(
            content="📈 **Events Over Time**\n\n"
            "This chart shows your activity patterns over time, including different types of events."
        ).send()
        
        await cl.Plotly(figure=fig, name="events_over_time", display="inline").send()
        
    except Exception as e:
        await cl.Message(content=f"❌ Error generating chart: {str(e)}").send()


@cl.action_callback("completed_tasks")
async def on_completed_tasks(action):
    """Display completed tasks periodically chart."""
    try:
        data = await load_data()
        fig = plot_completed_tasks_periodically(
            data['df_activity'],
            data['beg_range'],
            data['end_range'],
            data['granularity'],
            data['project_colors']
        )
        
        await cl.Message(
            content="✅ **Completed Tasks (Periodic)**\n\n"
            "This chart shows the number of completed tasks over time, broken down by project."
        ).send()
        
        await cl.Plotly(figure=fig, name="completed_tasks", display="inline").send()
        
    except Exception as e:
        await cl.Message(content=f"❌ Error generating chart: {str(e)}").send()


@cl.action_callback("cumulative_completed")
async def on_cumulative_completed(action):
    """Display cumulative completed tasks chart."""
    try:
        data = await load_data()
        fig = cumsum_completed_tasks_periodically(
            data['df_activity'],
            data['beg_range'],
            data['end_range'],
            data['granularity'],
            data['project_colors']
        )
        
        await cl.Message(
            content="📊 **Cumulative Completed Tasks**\n\n"
            "This chart shows the cumulative number of completed tasks over time by project."
        ).send()
        
        await cl.Plotly(figure=fig, name="cumulative_completed", display="inline").send()
        
    except Exception as e:
        await cl.Message(content=f"❌ Error generating chart: {str(e)}").send()


@cl.action_callback("event_distribution")
async def on_event_distribution(action):
    """Display event distribution by type chart."""
    try:
        data = await load_data()
        fig = plot_event_distribution_by_type(
            data['df_activity'],
            data['beg_range'],
            data['end_range'],
            data['granularity']
        )
        
        await cl.Message(
            content="🥧 **Event Distribution by Type**\n\n"
            "This pie chart shows the distribution of different event types in your selected time range."
        ).send()
        
        await cl.Plotly(figure=fig, name="event_distribution", display="inline").send()
        
    except Exception as e:
        await cl.Message(content=f"❌ Error generating chart: {str(e)}").send()


@cl.action_callback("top_projects")
async def on_top_projects(action):
    """Display top projects by events chart."""
    try:
        data = await load_data()
        fig = plot_top_projects_by_events(
            data['df_activity'],
            data['beg_range'],
            data['end_range'],
            data['project_colors']
        )
        
        await cl.Message(
            content="🏆 **Top Projects by Events**\n\n"
            "This chart shows your most active projects based on the number of events."
        ).send()
        
        await cl.Plotly(figure=fig, name="top_projects", display="inline").send()
        
    except Exception as e:
        await cl.Message(content=f"❌ Error generating chart: {str(e)}").send()


@cl.action_callback("project_distribution")
async def on_project_distribution(action):
    """Display event distribution by root project chart."""
    try:
        data = await load_data()
        fig = plot_event_distribution_by_root_project(
            data['df_activity'],
            data['beg_range'],
            data['end_range'],
            data['project_colors']
        )
        
        await cl.Message(
            content="📊 **Event Distribution by Project**\n\n"
            "This chart shows how events are distributed across your root projects."
        ).send()
        
        await cl.Plotly(figure=fig, name="project_distribution", display="inline").send()
        
    except Exception as e:
        await cl.Message(content=f"❌ Error generating chart: {str(e)}").send()


@cl.action_callback("event_heatmap")
async def on_event_heatmap(action):
    """Display event heatmap by day and hour."""
    try:
        data = await load_data()
        fig = plot_heatmap_of_events_by_day_and_hour(
            data['df_activity'],
            data['beg_range'],
            data['end_range']
        )
        
        await cl.Message(
            content="🔥 **Event Heatmap (Day/Hour)**\n\n"
            "This heatmap shows when you're most active throughout the week and day."
        ).send()
        
        await cl.Plotly(figure=fig, name="event_heatmap", display="inline").send()
        
    except Exception as e:
        await cl.Message(content=f"❌ Error generating chart: {str(e)}").send()


@cl.action_callback("event_types_by_project")
async def on_event_types_by_project(action):
    """Display event types by project chart."""
    try:
        data = await load_data()
        fig = plot_event_types_by_project(
            data['df_activity'],
            data['beg_range'],
            data['end_range']
        )
        
        await cl.Message(
            content="📋 **Event Types by Project**\n\n"
            "This chart shows the distribution of event types across your projects."
        ).send()
        
        await cl.Plotly(figure=fig, name="event_types_by_project", display="inline").send()
        
    except Exception as e:
        await cl.Message(content=f"❌ Error generating chart: {str(e)}").send()


@cl.action_callback("cumulative_events")
async def on_cumulative_events(action):
    """Display cumulative events over time chart."""
    try:
        data = await load_data()
        fig = plot_cumulative_events_over_time(
            data['df_activity'],
            data['beg_range'],
            data['end_range'],
            data['granularity']
        )
        
        await cl.Message(
            content="📈 **Cumulative Events Over Time**\n\n"
            "This chart shows the cumulative number of events over your selected time period."
        ).send()
        
        await cl.Plotly(figure=fig, name="cumulative_events", display="inline").send()
        
    except Exception as e:
        await cl.Message(content=f"❌ Error generating chart: {str(e)}").send()


@cl.action_callback("cumsum_per_project")
async def on_cumsum_per_project(action):
    """Display cumulative sum per project chart."""
    try:
        data = await load_data()
        fig = cumsum_plot_per_project(
            data['df_activity'],
            data['beg_range'],
            data['end_range'],
            data['project_colors']
        )
        
        await cl.Message(
            content="📊 **Cumulative Sum per Project**\n\n"
            "This chart shows cumulative activity progression for each project over time."
        ).send()
        
        await cl.Plotly(figure=fig, name="cumsum_per_project", display="inline").send()
        
    except Exception as e:
        await cl.Message(content=f"❌ Error generating chart: {str(e)}").send()


@cl.on_message
async def main(message: cl.Message):
    """Handle chat messages - placeholder for future chat agent functionality."""
    user_message = message.content.lower()
    
    # Placeholder responses for future chat agent
    if any(keyword in user_message for keyword in ['help', 'what', 'how']):
        response = (
            "🤖 **Chat Agent (Coming Soon!)**\n\n"
            "I'm still learning how to analyze your productivity data through conversation! "
            "For now, please use the buttons above to explore your data visualizations.\n\n"
            "**Future capabilities will include:**\n"
            "• Natural language queries about your productivity patterns\n"
            "• Personalized insights and recommendations\n"
            "• Trend analysis and predictions\n"
            "• Custom report generation\n\n"
            "Stay tuned for these exciting features! 🚀"
        )
    elif any(keyword in user_message for keyword in ['chart', 'plot', 'graph', 'show']):
        response = (
            "📊 **Want to see a chart?**\n\n"
            "Please use the action buttons above to view different visualizations of your Todoist data. "
            "Each button will generate a specific type of chart with detailed insights about your productivity patterns."
        )
    elif any(keyword in user_message for keyword in ['data', 'activity', 'tasks']):
        try:
            data = await load_data()
            total_events = len(data['df_activity'])
            total_projects = len(data['active_projects'])
            date_range = f"{data['beg_range'].strftime('%Y-%m-%d')} to {data['end_range'].strftime('%Y-%m-%d')}"
            
            response = (
                f"📈 **Your Data Summary:**\n\n"
                f"• **Total Events:** {total_events:,}\n"
                f"• **Active Projects:** {total_projects}\n"
                f"• **Date Range:** {date_range}\n"
                f"• **Data Range:** {data['oldest_date'].strftime('%Y-%m-%d')} to {data['newest_date'].strftime('%Y-%m-%d')}\n\n"
                "Use the buttons above to explore detailed visualizations!"
            )
        except Exception as e:
            response = f"❌ **Error accessing data:** {str(e)}"
    else:
        response = (
            "👋 **Hello!** I'm your Todoist Assistant.\n\n"
            "I can help you visualize your productivity data! Use the buttons above to explore different charts and insights.\n\n"
            "💡 **Tip:** Try asking me about 'help', 'charts', or 'data' for more information!"
        )
    
    await cl.Message(content=response).send()


if __name__ == "__main__":
    # This allows running the app directly
    import chainlit as cl
    cl.run()