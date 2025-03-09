from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from loguru import logger

def plot_event_distribution_by_type(df: pd.DataFrame, beg_date: datetime, end_date: datetime, granularity: str) -> go.Figure:
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
    Plots the number of events over time as a line chart within the specified date range.
    
    Parameters:
    df (pd.DataFrame): DataFrame containing event data.
    beg_date (datetime): Start date for filtering events.
    end_date (datetime): End date for filtering events.
    granularity (str): Resampling granularity for the data.
    
    Returns:
    go.Figure: Plotly figure object representing the events over time.
    """
    df_filtered = df.loc[beg_date:end_date]
    events_over_time = df_filtered.resample(granularity).size()
    fig = go.Figure(data=[go.Scatter(x=events_over_time.index, y=events_over_time.values, mode='lines')])
    fig.update_layout(title_text='Events Over Time', xaxis_title='Date', yaxis_title='Number of Events')
    return fig

def plot_top_projects_by_events(df: pd.DataFrame, beg_date: datetime, end_date: datetime, granularity: str) -> go.Figure:
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
    fig = go.Figure(data=[go.Bar(x=project_counts.index, y=project_counts.values)])
    fig.update_layout(title_text='Top Projects by Number of Events', xaxis_title='Projects', yaxis_title='Number of Events')
    return fig

def plot_event_distribution_by_root_project(df: pd.DataFrame, beg_date: datetime, end_date: datetime, granularity: str) -> go.Figure:
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
        fig.add_trace(go.Bar(name=col, x=event_counts.index, y=event_counts[col]))
    fig.update_layout(barmode='stack', title_text='Event Distribution by Root Project', xaxis_title='Root Projects', yaxis_title='Number of Events')
    return fig

def plot_heatmap_of_events_by_day_and_hour(df: pd.DataFrame, beg_date: datetime, end_date: datetime, granularity: str) -> go.Figure:
    """
    Plots a heatmap of events by day of the week and hour of the day within the specified date range.
    
    Parameters:
    df (pd.DataFrame): DataFrame containing event data.
    beg_date (datetime): Start date for filtering events.
    end_date (datetime): End date for filtering events.
    granularity (str): Resampling granularity for the data.
    
    Returns:
    go.Figure: Plotly figure object representing the heatmap of events by day and hour.
    """
    df_filtered = df.loc[beg_date:end_date].copy()
    df_filtered['hour'] = df_filtered.index.hour
    df_filtered['day_of_week'] = df_filtered.index.dayofweek
    heatmap_data = df_filtered.groupby(['day_of_week', 'hour']).size().unstack().fillna(0)
    fig = px.imshow(heatmap_data, labels=dict(x="Hour of Day", y="Day of Week", color="Number of Events"))
    fig.update_layout(title_text='Heatmap of Events by Day and Hour')
    return fig

def plot_event_types_by_project(df: pd.DataFrame, beg_date: datetime, end_date: datetime, granularity: str) -> go.Figure:
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
    fig.update_layout(barmode='group', title_text='Event Types by Project', xaxis_title='Projects', yaxis_title='Number of Events')
    return fig

def plot_cumulative_events_over_time(df: pd.DataFrame, beg_date: datetime, end_date: datetime, granularity: str) -> go.Figure:
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
    fig.update_layout(title_text='Cumulative Events Over Time', xaxis_title='Date', yaxis_title='Cumulative Number of Events')
    return fig

def plot_events_per_project_over_time(df: pd.DataFrame, beg_date: datetime, end_date: datetime, granularity: str) -> go.Figure:
    """
    Plots the number of events per project over time as a line chart within the specified date range.
    
    Parameters:
    df (pd.DataFrame): DataFrame containing event data.
    beg_date (datetime): Start date for filtering events.
    end_date (datetime): End date for filtering events.
    granularity (str): Resampling granularity for the data.
    
    Returns:
    go.Figure: Plotly figure object representing the events per project over time.
    """
    df_filtered = df.loc[beg_date:end_date]
    events_per_project = df_filtered.groupby(['root_project_name', df_filtered.index.to_period(granularity)]).size().unstack().fillna(0).T
    fig = go.Figure()
    for project in events_per_project.columns:
        fig.add_trace(go.Scatter(x=events_per_project.index.to_timestamp(), y=events_per_project[project], mode='lines', name=project))
    fig.update_layout(title_text='Events Per Project Over Time', xaxis_title='Date', yaxis_title='Number of Events')
    return fig

def plot_event_duration_analysis(df: pd.DataFrame, beg_date: datetime, end_date: datetime) -> go.Figure | None:
    """
    Plots the duration analysis of events as a histogram within the specified date range.
    
    Parameters:
    df (pd.DataFrame): DataFrame containing event data.
    beg_date (datetime): Start date for filtering events.
    end_date (datetime): End date for filtering events.
    
    Returns:
    go.Figure | None: Plotly figure object representing the event duration analysis or None if required columns are missing.
    """
    df_filtered = df.loc[beg_date:end_date]
    if 'updated' in df_filtered['type'].unique():
        updated_events = df_filtered[df_filtered['type'] == 'updated']
        added_events = df_filtered[df_filtered['type'] == 'added']
        if 'date_updated' not in updated_events.columns or 'date_added' not in added_events.columns:
            logger.error("Required columns for duration analysis are missing.")
            return None
        durations = pd.merge(updated_events, added_events, on='id', suffixes=('_updated', '_added'))
        durations['duration'] = (durations['date_updated'] - durations['date_added']).dt.total_seconds() / 3600
        fig = go.Figure(data=[go.Histogram(x=durations['duration'])])
        fig.update_layout(title_text='Event Duration Analysis', xaxis_title='Duration (hours)', yaxis_title='Number of Events')
        return fig
    else:
        logger.error("No update events found for duration analysis.")
        return None

def plot_percentage_change(df: pd.DataFrame, beg_date: datetime, end_date: datetime, granularity: str, plot_func, *args) -> go.Figure:
    """
    Plots the percentage change of events compared to the previous period and adds the percentage change annotation to the plot.
    
    Parameters:
    df (pd.DataFrame): DataFrame containing event data.
    beg_date (datetime): Start date for filtering events.
    end_date (datetime): End date for filtering events.
    granularity (str): Resampling granularity for the data.
    plot_func (function): The plot function to which the percentage change annotation will be added.
    *args: Additional arguments to pass to the plot function.
    
    Returns:
    go.Figure: Plotly figure object representing the percentage change of events.
    """
    curr_period = df.loc[beg_date:end_date]
    prev_period = df.loc[(beg_date - (end_date - beg_date)) : beg_date]
    
    curr_count = curr_period.resample(granularity).size().sum()
    prev_count = prev_period.resample(granularity).size().sum()
    
    percentage_change = ((curr_count - prev_count) / prev_count) * 100 if prev_count != 0 else float('inf')
    
    fig = plot_func(df, beg_date, end_date, granularity, *args)
    
    fig.update_layout(
        annotations=[
            go.layout.Annotation(
                text=f"Change: {percentage_change:.2f}%",
                xref="paper", yref="paper",
                x=1, y=1, showarrow=False,
                font=dict(size=14, color="red" if percentage_change < 0 else "green")
            )
        ]
    )
    
    return fig

def cumsum_plot(df: pd.DataFrame, beg_date: datetime, end_date: datetime, granularity: str) -> go.Figure:
    """
    Plots the cumulative number of completed tasks over time as a line chart within the specified date range.
    
    Parameters:
    df (pd.DataFrame): DataFrame containing event data.
    beg_date (datetime): Start date for filtering events.
    end_date (datetime): End date for filtering events.
    granularity (str): Resampling granularity for the data.
    
    Returns:
    go.Figure: Plotly figure object representing the cumulative number of completed tasks over time.
    """
    completed_tasks = df[df['type'] == 'completed'].groupby('date').size().cumsum()

    completed_tasks = completed_tasks[completed_tasks.index >= beg_date]
    completed_tasks = completed_tasks[completed_tasks.index <= end_date]

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=completed_tasks.index,
            y=completed_tasks.values,
            line=dict(color='blue', width=4),
            name='Completed Tasks',
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
    fig.update_yaxes(title_text='Number of Completed Tasks', showline=True, showgrid=True)

    # Update title and show plot
    fig.update_layout(title_text='Cumulative Number of Completed Tasks Over Time',
                      yaxis=dict(autorange=True, fixedrange=False))

    return fig


def cumsum_plot_per_project(df: pd.DataFrame, beg_date: datetime, end_date: datetime, granularity: str) -> go.Figure:
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
                line=dict(width=3),
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


def plot_completed_tasks_biweekly(df: pd.DataFrame, beg_date: datetime, end_date: datetime, granularity: str) -> go.Figure:
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
    df_weekly_per_project = df[df['type'] == 'completed'].groupby(['root_project_name']).resample(granularity).size().unstack(level=0)
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
        # dots
                mode='lines+markers',
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

    fig.update_layout(title_text=f'{granularity} Completed Tasks Per Project', yaxis=dict(autorange=True, fixedrange=False))

    return fig

def cumsum_completed_tasks_biweekly(df: pd.DataFrame, beg_date: datetime, end_date: datetime, granularity: str) -> go.Figure:
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
    df_weekly_per_project = df[df['type'] == 'completed'].groupby(['root_project_name']).resample(granularity).size().unstack(level=0)
    df_weekly_per_project = df_weekly_per_project[df_weekly_per_project.index >= beg_date]
    df_weekly_per_project = df_weekly_per_project[df_weekly_per_project.index <= end_date]
    df_weekly_per_project = df_weekly_per_project.cumsum()

    fig = go.Figure()

    for root_project_name in df_weekly_per_project.columns:
        fig.add_trace(
            go.Scatter(
                x=df_weekly_per_project.index,
                y=df_weekly_per_project[root_project_name],
                name=root_project_name,
                line_shape='spline',
        # dots
                mode='lines+markers',
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

    fig.update_layout(title_text=f'Cumulative {granularity} Completed Tasks Per Project', yaxis=dict(autorange=True, fixedrange=False))

    return fig
