from datetime import datetime, timedelta
from typing import Final

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
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

def plot_most_popular_labels(projects: list[Project]) -> go.Figure:
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

    N: Final[int] = 10 # constant for now
    top_n_labels = dict(sorted(labels_counter.items(), key=lambda item: item[1], reverse=True)[:N])
    
    fig = go.Figure(data=[go.Pie(labels=list(top_n_labels.keys()), values=list(top_n_labels.values()), hole=.3)])
    fig.update_traces(hoverinfo='label+percent', textinfo='value', textfont_size=20,
                      marker=dict(line=dict(color='#000000', width=2)))
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

    fig = go.Figure(data=[go.Pie(labels=['Overdue', 'Today/Tomorrow', 'This Week', 'Later/No Date'],
                                    values=[overdue, today_tomorrow, this_week, later_nodate], hole=.3)])
    fig.update_traces(hoverinfo='label+percent', textinfo='value', textfont_size=20,
                      marker=dict(line=dict(color='#000000', width=2)))
    
    fig.update_layout(title_text='Current Tasks Types')
    return fig

def plot_top_projects_by_events(df: pd.DataFrame, beg_date: datetime, end_date: datetime,
                                granularity: str) -> go.Figure:
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
    fig.update_layout(title_text='Top Projects by Number of Events',
                      xaxis_title='Projects',
                      yaxis_title='Number of Events')
    return fig


def plot_event_distribution_by_root_project(df: pd.DataFrame, beg_date: datetime, end_date: datetime,
                                            granularity: str) -> go.Figure:
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
    fig.update_layout(barmode='stack',
                      title_text='Event Distribution by Root Project',
                      xaxis_title='Root Projects',
                      yaxis_title='Number of Events')
    return fig


def plot_heatmap_of_events_by_day_and_hour(df: pd.DataFrame, beg_date: datetime, end_date: datetime,
                                           granularity: str) -> go.Figure:
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


def plot_event_types_by_project(df: pd.DataFrame, beg_date: datetime, end_date: datetime,
                                granularity: str) -> go.Figure:
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


def plot_completed_tasks_periodically(df: pd.DataFrame, beg_date: datetime, end_date: datetime,
                                      granularity: str) -> go.Figure:
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


def cumsum_completed_tasks_periodically(df: pd.DataFrame, beg_date: datetime, end_date: datetime,
                                        granularity: str) -> go.Figure:
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
