from datetime import datetime, timedelta
from typing import Final, cast

import pandas as pd
import plotly.graph_objects as go
from todoist.types import Project


def plot_event_distribution_by_type(df: pd.DataFrame, beg_date: datetime, end_date: datetime,
                                    granularity: str) -> go.Figure:
    """
    Plots the distribution of event types as a pie chart within the specified date range.
    
    Parameters:
    df (pd.DataFrame): DataFrame containing event data.
    beg_date (datetime): Start date for filtering events.
    end_date (datetime): End date for filtering events.
    granularity (str): Resampling granularity for the data.
    
    Returns:
    go.Figure: Plotly figure object representing the event distribution by type.
    """
    df_filtered = df.loc[beg_date:end_date]
    event_counts = df_filtered['type'].value_counts()
    fig = go.Figure(data=[go.Pie(labels=event_counts.index, values=event_counts.values, hole=.3)])
    fig.update_layout(title_text='Event Distribution by Type')
    return fig


def plot_events_over_time(df: pd.DataFrame, beg_date: datetime, end_date: datetime, granularity: str) -> go.Figure:
    """
    Plots the number of events over time as a stacked area chart with daily data points
    and 7-day rolling averages, segmented by activity type.
    
    Parameters:
    df (pd.DataFrame): DataFrame containing event data.
    beg_date (datetime): Start date for filtering events.
    end_date (datetime): End date for filtering events.
    granularity (str): Resampling granularity (ignored - uses daily granularity with 7-day rolling average).
    
    Returns:
    go.Figure: Plotly figure object representing the events over time by activity type.
    """
    # Filter data by date range
    df_filtered = df.loc[beg_date:end_date].copy()
    
    # Define activity types and colors with high contrast
    activity_types = ['added', 'completed', 'updated', 'deleted', 'rescheduled']
    activity_colors = {
        'added': '#2E8B57',      # Sea Green - for creation
        'completed': '#4169E1',   # Royal Blue - for accomplishment  
        'updated': '#FF8C00',     # Dark Orange - for modification
        'deleted': '#DC143C',     # Crimson - for removal
        'rescheduled': '#9370DB'  # Medium Purple - for rescheduling
    }
    
    # Resample to daily granularity and count events by type
    # Create daily counts for each activity type, avoiding the deprecation warning
    daily_counts_dict = {}
    activity_types = ['added', 'completed', 'updated', 'deleted', 'rescheduled']
    
    for activity_type in activity_types:
        type_data = df_filtered[df_filtered['type'] == activity_type]
        if len(type_data) > 0:
            daily_counts_dict[activity_type] = type_data.resample('D').size()
        else:
            # Create empty series for this activity type
            date_range = pd.date_range(start=beg_date.date(), end=end_date.date(), freq='D')
            daily_counts_dict[activity_type] = pd.Series(0, index=date_range)
    
    # Combine into a single DataFrame
    daily_counts = pd.DataFrame(daily_counts_dict).fillna(0)
    
    # Ensure we have all activity types as columns (even if no data)
    for activity_type in activity_types:
        if activity_type not in daily_counts.columns:
            daily_counts[activity_type] = 0
    
    # Reorder columns to match our defined order
    daily_counts = daily_counts[activity_types]
    
    # Calculate 7-day rolling averages for each activity type
    rolling_averages = daily_counts.rolling(window=7, min_periods=1).mean()
    
    # Helper to convert HEX to RGBA with alpha (for nicer area fills on dark bg)
    def hex_to_rgba(hex_color: str, alpha: float) -> str:
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        return f'rgba({r},{g},{b},{alpha})'

    # Create the figure (dark-friendly template)
    fig = go.Figure()
    
    # Add traces for each activity type (stacked area chart)
    for i, activity_type in enumerate(activity_types):
        if activity_type in rolling_averages.columns:
            fig.add_trace(go.Scatter(
                x=rolling_averages.index,
                y=rolling_averages[activity_type],
                mode='lines',
                name=activity_type.capitalize(),
                fill='tonexty' if i > 0 else 'tozeroy',
                line=dict(
                    color=activity_colors.get(activity_type, '#808080'),
                    width=2
                ),
                # Use semi-transparent fill while keeping solid line for readability on dark bg
                fillcolor=hex_to_rgba(activity_colors.get(activity_type, '#9e9e9e'), 0.28),
                hovertemplate=(
                    f'<b>{activity_type.capitalize()}</b><br>' +
                    'Date: %{x}<br>' +
                    'Average: %{y:.1f} events/day<br>' +
                    '<extra></extra>'
                )
            ))
    
    # Update layout with improved styling
    fig.update_layout(
        template='plotly_dark',
        title={
            'text': 'Events Over Time (7-Day Rolling Average by Activity Type)',
            'x': 0.5,
            'xanchor': 'center',
            'font': {'size': 18, 'family': 'Arial, sans-serif', 'color': '#ffffff'}
        },
        xaxis={
            'title': {'text': 'Date', 'font': {'color': '#ffffff'}},
            'showgrid': True,
            'gridwidth': 1,
            'gridcolor': 'rgba(255,255,255,0.08)',
            'showline': True,
            'linewidth': 1,
            'linecolor': 'rgba(255,255,255,0.24)',
            'tickfont': {'size': 12, 'color': '#e6e6e6'}
        },
        yaxis={
            'title': {'text': 'Average Number of Events per Day', 'font': {'color': '#ffffff'}},
            'showgrid': True,
            'gridwidth': 1,
            'gridcolor': 'rgba(255,255,255,0.08)',
            'showline': True,
            'linewidth': 1,
            'linecolor': 'rgba(255,255,255,0.24)',
            'tickfont': {'size': 12, 'color': '#e6e6e6'}
        },
        plot_bgcolor='#111318',
        paper_bgcolor='#111318',
        legend={
            'orientation': 'h',
            'yanchor': 'bottom',
            'y': 1.02,
            'xanchor': 'right',
            'x': 1,
            'font': {'size': 12, 'color': '#e6e6e6'}
        },
        margin=dict(l=50, r=50, t=80, b=50),
        hovermode='x unified',
        hoverlabel=dict(bgcolor='#1e1e1e', bordercolor='#444', font=dict(color='#ffffff'))
    )
    
    return fig


def plot_most_popular_labels(projects: list[Project], label_colors: dict[str, str]) -> go.Figure:
    """
    Plots the most popular labels as pie chart.
    
    Parameters:
    projects (list[Project]): List of projects.
    
    Returns:
    go.Figure: Plotly figure object representing the most popular labels.
    """

    labels_counter = {}
    for project in projects:
        for task in project.tasks:
            for label in task.task_entry.labels:
                labels_counter[label] = labels_counter.get(label, 0) + 1

    N: Final[int] = 10    # constant for now
    top_n_labels = dict(sorted(labels_counter.items(), key=lambda item: item[1], reverse=True)[:N])

    fig = go.Figure(data=[go.Pie(labels=list(top_n_labels.keys()), values=list(top_n_labels.values()), hole=.3)])
    fig.update_traces(hoverinfo='label+percent',
                      textinfo='value',
                      textfont_size=20,
                      marker=dict(colors=[label_colors.get(label, '#808080') for label in top_n_labels.keys()],
                                  line=dict(color='#000000', width=2)))
    fig.update_layout(title_text='Most Popular Labels')
    return fig


def current_tasks_types(projects: list[Project]) -> go.Figure:
    # count overude, today+tomorrow, this week, later+nodate tasks
    # make  pie plot as above
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)
    week_end = today + timedelta(days=7)
    overdue = 0
    today_tomorrow = 0
    this_week = 0
    later_nodate = 0
    for project in projects:
        for task in project.tasks:
            if task.task_entry.due_datetime is None:
                later_nodate += 1
                continue
            task_due_date = task.task_entry.due_datetime.date()

            if task_due_date < today:
                overdue += 1
            elif task_due_date >= today and task_due_date <= tomorrow:
                today_tomorrow += 1
            elif task_due_date <= week_end:
                this_week += 1
            else:
                later_nodate += 1

    fig = go.Figure(data=[
        go.Pie(labels=['Overdue', 'Today/Tomorrow', 'This Week', 'Later/No Date'],
               values=[overdue, today_tomorrow, this_week, later_nodate],
               hole=.3)
    ])
    fig.update_traces(hoverinfo='label+percent',
                      textinfo='value',
                      textfont_size=20,
                      marker=dict(line=dict(color='#000000', width=2)))

    fig.update_layout(title_text='Current Tasks Types')
    return fig


def plot_top_projects_by_events(df: pd.DataFrame, beg_date: datetime, end_date: datetime,
                                project_colors: dict[str, str]) -> go.Figure:
    """
    Plots the top projects by the number of events as a bar chart within the specified date range.
    
    Parameters:
    df (pd.DataFrame): DataFrame containing event data.
    beg_date (datetime): Start date for filtering events.
    end_date (datetime): End date for filtering events.
    granularity (str): Resampling granularity for the data.
    
    Returns:
    go.Figure: Plotly figure object representing the top projects by number of events.
    """
    df_filtered = df.loc[beg_date:end_date]
    project_counts = df_filtered['root_project_name'].value_counts().head(10)

    fig = go.Figure(data=[
        go.Bar(x=project_counts.index,
               y=project_counts.values,
               marker_color=[project_colors.get(project, '#808080') for project in project_counts.index])
    ])
    fig.update_layout(title_text='Top Projects by Number of Events',
                      xaxis_title='Projects',
                      yaxis_title='Number of Events')
    return fig


def plot_event_distribution_by_root_project(df: pd.DataFrame, beg_date: datetime, end_date: datetime,
                                            project_colors: dict[str, str]) -> go.Figure:
    """
    Plots the distribution of event types by root project as a stacked bar chart within the specified date range.
    
    Parameters:
    df (pd.DataFrame): DataFrame containing event data.
    beg_date (datetime): Start date for filtering events.
    end_date (datetime): End date for filtering events.
    granularity (str): Resampling granularity for the data.
    
    Returns:
    go.Figure: Plotly figure object representing the event distribution by root project.
    """
    df_filtered = df.loc[beg_date:end_date]
    event_counts = df_filtered.groupby('root_project_name')['type'].value_counts().unstack().fillna(0)
    fig = go.Figure()

    for col in event_counts.columns:
        fig.add_trace(
            go.Bar(name=col,
                   x=event_counts.index,
                   y=event_counts[col],
                   marker_color=[project_colors.get(project, '#808080') for project in event_counts.index],
                   showlegend=False))
    fig.update_layout(barmode='stack',
                      title_text='Event Distribution by Root Project',
                      xaxis_title='Root Projects',
                      yaxis_title='Number of Events')
    return fig


def plot_heatmap_of_events_by_day_and_hour(df: pd.DataFrame, beg_date: datetime, end_date: datetime) -> go.Figure:
    """
    Plots a heatmap of events by day of the week and hour of the day within the specified date range.
    Enhanced version with dark mode support and improved informativeness.
    
    Parameters:
    df (pd.DataFrame): DataFrame containing event data.
    beg_date (datetime): Start date for filtering events.
    end_date (datetime): End date for filtering events.
    
    Returns:
    go.Figure: Plotly figure object representing the heatmap of events by day and hour.
    """
    df_filtered = df.loc[beg_date:end_date].copy()
    
    # Handle empty data gracefully
    if df_filtered.empty:
        fig = go.Figure()
        fig.update_layout(
            template='plotly_dark',
            title={
                'text': 'Heatmap of Events by Day and Hour (No Data)',
                'x': 0.5,
                'xanchor': 'center',
                'font': {'size': 18, 'family': 'Arial, sans-serif', 'color': '#ffffff'}
            },
            paper_bgcolor='#111318',
            plot_bgcolor='#111318'
        )
        return fig
    
    # Ensure we operate on a DateTimeIndex for static typing correctness
    dt_index = cast(pd.DatetimeIndex, pd.to_datetime(df_filtered.index))
    df_filtered['hour'] = dt_index.hour
    df_filtered['day_of_week'] = dt_index.dayofweek
    
    # Create heatmap data with proper indexing
    heatmap_data = df_filtered.groupby(['day_of_week', 'hour']).size().unstack(fill_value=0)
    
    # Ensure all hours (0-23) and all days (0-6) are represented
    all_hours = list(range(24))
    all_days = list(range(7))
    heatmap_data = heatmap_data.reindex(index=all_days, columns=all_hours, fill_value=0)
    
    # Day names for better readability
    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    
    # Create custom hover text with more information
    total_events = heatmap_data.sum().sum()
    hover_text = []
    
    for day_idx in range(7):
        hover_row = []
        for hour in range(24):
            count = heatmap_data.iloc[day_idx, hour]
            percentage = (count / total_events * 100) if total_events > 0 else 0
            
            # Format hour display (e.g., "9 AM", "2 PM", "0 (midnight)")
            if hour == 0:
                hour_str = "12 AM (midnight)"
            elif hour == 12:
                hour_str = "12 PM (noon)"
            elif hour < 12:
                hour_str = f"{hour} AM"
            else:
                hour_str = f"{hour - 12} PM"
            
            hover_text_cell = (
                f"<b>{day_names[day_idx]}</b><br>"
                f"Time: {hour_str}<br>"
                f"Events: {int(count)}<br>"
                f"Percentage: {percentage:.1f}%<br>"
                f"<extra></extra>"
            )
            hover_row.append(hover_text_cell)
        hover_text.append(hover_row)
    
    # Create the heatmap using plotly graph objects for better control
    fig = go.Figure(data=go.Heatmap(
        z=heatmap_data.values,
        x=all_hours,
        y=day_names,
        colorscale=[
            [0.0, '#0d1b2a'],      # Dark blue for low activity
            [0.1, '#1b263b'],      # Slightly lighter blue
            [0.2, '#2d4f7c'],      # Medium blue
            [0.3, '#415a77'],      # Blue-gray
            [0.4, '#778da9'],      # Light blue-gray
            [0.5, '#a8dadc'],      # Light blue
            [0.6, '#f1faee'],      # Very light blue/white
            [0.7, '#ffeaa7'],      # Light yellow
            [0.8, '#fdcb6e'],      # Orange-yellow
            [0.9, '#e17055'],      # Orange-red
            [1.0, '#d63031']       # Red for high activity
        ],
        hovertemplate='%{customdata}<extra></extra>',
        customdata=hover_text,
        showscale=True,
        colorbar=dict(
            title=dict(
                text="Events Count",
                font=dict(size=14, color='#ffffff')
            ),
            tickfont=dict(size=12, color='#e6e6e6'),
            bgcolor='#111318',
            bordercolor='rgba(255,255,255,0.24)',
            borderwidth=1
        )
    ))
    
    # Update layout with dark theme and enhanced styling
    fig.update_layout(
        template='plotly_dark',
        title={
            'text': 'Activity Heatmap: Events by Day and Hour',
            'x': 0.5,
            'xanchor': 'center',
            'font': {'size': 18, 'family': 'Arial, sans-serif', 'color': '#ffffff'}
        },
        xaxis={
            'title': {
                'text': 'Hour of Day',
                'font': {'size': 14, 'color': '#ffffff'}
            },
            'tickmode': 'array',
            'tickvals': list(range(0, 24, 2)),  # Show every 2 hours for readability
            'ticktext': [f'{h}:00' for h in range(0, 24, 2)],
            'tickfont': {'size': 11, 'color': '#e6e6e6'},
            'showgrid': True,
            'gridwidth': 1,
            'gridcolor': 'rgba(255,255,255,0.08)',
            'showline': True,
            'linewidth': 1,
            'linecolor': 'rgba(255,255,255,0.24)'
        },
        yaxis={
            'title': {
                'text': 'Day of Week',
                'font': {'size': 14, 'color': '#ffffff'}
            },
            'tickfont': {'size': 11, 'color': '#e6e6e6'},
            'showgrid': True,
            'gridwidth': 1,
            'gridcolor': 'rgba(255,255,255,0.08)',
            'showline': True,
            'linewidth': 1,
            'linecolor': 'rgba(255,255,255,0.24)'
        },
        plot_bgcolor='#111318',
        paper_bgcolor='#111318',
        margin=dict(l=80, r=100, t=80, b=60),
        font=dict(color='#ffffff'),
        hoverlabel=dict(
            bgcolor='#1e1e1e',
            bordercolor='#444',
            font=dict(color='#ffffff', size=12)
        )
    )
    
    # Add subtle annotations for peak activity times if there's data
    if total_events > 0:
        # Find peak hour and day
        max_pos = heatmap_data.stack().idxmax()
        peak_day, peak_hour = max_pos
        peak_count = heatmap_data.iloc[peak_day, peak_hour]
        
        if peak_count > 0:
            fig.add_annotation(
                x=peak_hour,
                y=day_names[peak_day],
                text=f"Peak: {int(peak_count)}",
                showarrow=True,
                arrowhead=2,
                arrowsize=1,
                arrowwidth=2,
                arrowcolor="#ffffff",
                font=dict(color="#ffffff", size=10),
                bgcolor="rgba(0,0,0,0.7)",
                bordercolor="#ffffff",
                borderwidth=1
            )
    
    return fig


def plot_event_types_by_project(df: pd.DataFrame, beg_date: datetime, end_date: datetime) -> go.Figure:
    """
    Plots the distribution of event types by project as a grouped bar chart within the specified date range.
    
    Parameters:
    df (pd.DataFrame): DataFrame containing event data.
    beg_date (datetime): Start date for filtering events.
    end_date (datetime): End date for filtering events.
    granularity (str): Resampling granularity for the data.
    
    Returns:
    go.Figure: Plotly figure object representing the event types by project.
    """
    df_filtered = df.loc[beg_date:end_date]
    event_counts = df_filtered.groupby(['root_project_name', 'type']).size().unstack().fillna(0).head(10)
    fig = go.Figure()
    for col in event_counts.columns:
        fig.add_trace(go.Bar(name=col, x=event_counts.index, y=event_counts[col]))
    fig.update_layout(barmode='group',
                      title_text='Event Types by Project',
                      xaxis_title='Projects',
                      yaxis_title='Number of Events')
    return fig


def plot_cumulative_events_over_time(df: pd.DataFrame, beg_date: datetime, end_date: datetime,
                                     granularity: str) -> go.Figure:
    """
    Plots the cumulative number of events over time as a line chart within the specified date range.
    
    Parameters:
    df (pd.DataFrame): DataFrame containing event data.
    beg_date (datetime): Start date for filtering events.
    end_date (datetime): End date for filtering events.
    granularity (str): Resampling granularity for the data.
    
    Returns:
    go.Figure: Plotly figure object representing the cumulative events over time.
    """
    df_filtered = df.loc[beg_date:end_date]
    cumulative_events = df_filtered.resample(granularity).size().cumsum()
    fig = go.Figure(data=[go.Scatter(x=cumulative_events.index, y=cumulative_events.values, mode='lines')])
    fig.update_layout(title_text='Cumulative Events Over Time',
                      xaxis_title='Date',
                      yaxis_title='Cumulative Number of Events')
    return fig


def cumsum_plot_per_project(df: pd.DataFrame, beg_date: datetime, end_date: datetime,
                            project_colors: dict[str, str]) -> go.Figure:
    """
    Plots the cumulative number of completed tasks per project over time as a line chart within the specified date range.
    
    Parameters:
    df (pd.DataFrame): DataFrame containing event data.
    beg_date (datetime): Start date for filtering events.
    end_date (datetime): End date for filtering events.
    granularity (str): Resampling granularity for the data.
    
    Returns:
    go.Figure: Plotly figure object representing the cumulative number of completed tasks per project over time.
    """
    completed_tasks = df[df['type'] == 'completed'].groupby(
        ['root_project_name', 'root_project_id', 'date']).size().groupby('root_project_name').cumsum().reset_index()
    completed_tasks = completed_tasks.rename(columns={0: 'completed'})
    completed_tasks = completed_tasks[completed_tasks['date'] >= beg_date]
    completed_tasks = completed_tasks[completed_tasks['date'] <= end_date]
    fig = go.Figure()

    for root_project_name in completed_tasks['root_project_name'].unique():
        data = completed_tasks[completed_tasks['root_project_name'] == root_project_name]
        fig.add_trace(
            go.Scatter(
                x=data['date'],
                y=data['completed'],
                line=dict(width=3, color=project_colors.get(root_project_name, '#808080')),
                name=root_project_name,
                line_shape='spline',
            ))

    # Update x-axis
    fig.update_xaxes(
        title_text='Date',
        type='date',
        showline=True,
        showgrid=True,
    )

    # Update y-axis
    fig.update_yaxes(title_text='Number of Completed Tasks')
    return fig


def plot_completed_tasks_periodically(df: pd.DataFrame, beg_date: datetime, end_date: datetime, granularity: str,
                                      project_colors: dict[str, str]) -> go.Figure:
    """
    Plots the number of completed tasks per project over time as a line chart with markers within the specified date range.

    Parameters:
    df (pd.DataFrame): DataFrame containing event data.
    beg_date (datetime): Start date for filtering events.
    end_date (datetime): End date for filtering events.
    granularity (str): Resampling granularity for the data.

    Returns:
    go.Figure: Plotly figure object representing the number of completed tasks per project over time.
    """
    df_weekly_per_project = df[df['type'] == 'completed'].groupby(['root_project_name'
                                                                  ]).resample(granularity).size().unstack(level=0)
    df_weekly_per_project = df_weekly_per_project[df_weekly_per_project.index >= beg_date]
    df_weekly_per_project = df_weekly_per_project[df_weekly_per_project.index <= end_date]

    fig = go.Figure()

    for root_project_name in df_weekly_per_project.columns:
        fig.add_trace(
            go.Scatter(
                x=df_weekly_per_project.index,
                y=df_weekly_per_project[root_project_name],
                name=root_project_name,
                line_shape='spline',
                mode='lines+markers',
                line=dict(color=project_colors.get(root_project_name, '#808080')),
            ))

    # Update x-axis
    fig.update_xaxes(
        title_text='Date',
        type='date',
        showline=True,
        showgrid=True,
    )

    # Update y-axis
    fig.update_yaxes(title_text='Number of Completed Tasks')

    fig.update_layout(title_text=f'{granularity} Completed Tasks Per Project',
                      yaxis=dict(autorange=True, fixedrange=False))

    return fig


def cumsum_completed_tasks_periodically(df: pd.DataFrame, beg_date: datetime, end_date: datetime, granularity: str,
                                        project_colors: dict[str, str]) -> go.Figure:
    """
    Plots the cumulative number of completed tasks per project over time as a line chart with markers within the specified date range.

    Parameters:
    df (pd.DataFrame): DataFrame containing event data.
    beg_date (datetime): Start date for filtering events.
    end_date (datetime): End date for filtering events.
    granularity (str): Resampling granularity for the data.

    Returns:
    go.Figure: Plotly figure object representing the cumulative number of completed tasks per project over time.
    """
    df_weekly_per_project = df[df['type'] == 'completed'].groupby(['root_project_name'
                                                                  ]).resample(granularity).size().unstack(level=0)
    df_weekly_per_project = df_weekly_per_project[df_weekly_per_project.index >= beg_date]
    df_weekly_per_project = df_weekly_per_project[df_weekly_per_project.index <= end_date]
    df_weekly_per_project = df_weekly_per_project.cumsum()

    # Append 0 from the left (one day before the minimum date)
    min_date = df_weekly_per_project.index.min() - timedelta(days=7 if 'W' in granularity else 14)
    df_weekly_per_project.loc[min_date] = 0

    # Append the maximum value of each project from the right (one day after the maximum date)
    max_date = df_weekly_per_project.index.max() + timedelta(days=1)
    for root_project_name in df_weekly_per_project.columns:
        df_weekly_per_project.loc[max_date, root_project_name] = df_weekly_per_project[root_project_name].max()

    # Sort the index
    df_weekly_per_project = df_weekly_per_project.sort_index()

    # Interpolate to ensure all dots are connected
    df_weekly_per_project = df_weekly_per_project.interpolate(method='linear', axis=0)

    fig = go.Figure()

    for root_project_name in df_weekly_per_project.columns:
        fig.add_trace(
            go.Scatter(
                x=df_weekly_per_project.index,
                y=df_weekly_per_project[root_project_name],
                name=root_project_name,
                line_shape='spline',
                mode='lines+markers',
                line=dict(color=project_colors.get(root_project_name, '#808080')),
            ))

    # Update x-axis
    fig.update_xaxes(
        title_text='Date',
        type='date',
        showline=True,
        showgrid=True,
    )

    # Update y-axis
    fig.update_yaxes(title_text='Number of Completed Tasks')

    fig.update_layout(title_text=f'Cumulative {granularity} Completed Tasks Per Project',
                      yaxis=dict(autorange=True, fixedrange=False))

    return fig
