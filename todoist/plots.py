from datetime import datetime

import pandas as pd
import plotly.graph_objects as go


def cumsum_plot(df: pd.DataFrame, beg_date: datetime, end_date: datetime) -> go.Figure:
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


def cumsum_plot_per_project(df: pd.DataFrame, beg_date: datetime, end_date: datetime) -> go.Figure:
    completed_tasks = df[df['type'] == 'completed'].groupby(
        ['root_project_name', 'root_project_id', 'date']).size().groupby('root_project_name').cumsum().reset_index()
    # completed_tasks = df[df['type'] == 'completed'].groupby('date').size().cumsum()
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


def plot_completed_tasks_biweekly(df: pd.DataFrame, beg_date: datetime, end_date: datetime) -> go.Figure:
    df_weekly_per_project = df[df['type'] == 'completed'].groupby(['root_project_name'
                                                                  ]).resample('2W').size().unstack(level=0)
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

    fig.update_layout(title_text='Weekly Completed Tasks Per Project', yaxis=dict(autorange=True, fixedrange=False))

    return fig

def cumsum_completed_tasks_biweekly(df: pd.DataFrame, beg_date: datetime, end_date: datetime) -> go.Figure:
    df_weekly_per_project = df[df['type'] == 'completed'].groupby(['root_project_name'
                                                                  ]).resample('W').size().unstack(level=0)
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

    fig.update_layout(title_text='Cumulative Weekly Completed Tasks Per Project', yaxis=dict(autorange=True, fixedrange=False))

    return fig