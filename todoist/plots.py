from datetime import datetime, timedelta
from typing import Any, Final, cast

import pandas as pd
import plotly.graph_objects as go
from todoist.types import Project

_DASHBOARD_GRID_COLOR = "rgba(255,255,255,0.03)"
_DASHBOARD_AXIS_LINE_COLOR = "rgba(255,255,255,0.18)"


def _apply_dashboard_axes(fig: go.Figure) -> go.Figure:
    fig.update_xaxes(
        showgrid=False,
        gridcolor=_DASHBOARD_GRID_COLOR,
        zeroline=False,
        showline=True,
        linewidth=1,
        linecolor=_DASHBOARD_AXIS_LINE_COLOR,
    )
    fig.update_yaxes(
        showgrid=False,
        gridcolor=_DASHBOARD_GRID_COLOR,
        zeroline=False,
        showline=True,
        linewidth=1,
        linecolor=_DASHBOARD_AXIS_LINE_COLOR,
    )
    return fig


def _period_grouper(freq: str) -> Any:
    # Pandas supports `label` and `closed`, but type stubs frequently lag behind.
    return pd.Grouper(freq=freq, label="right", closed="right")  # type: ignore[call-arg]


def _decayed_mean(values: list[float], *, decay: float = 0.75) -> float:
    """Return an exponentially-decayed mean (most recent values weighted highest)."""

    if not values:
        return 0.0

    total = 0.0
    weight_sum = 0.0
    weight = 1.0
    for value in reversed(values):
        total += float(value) * weight
        weight_sum += weight
        weight *= float(decay)
    return total / weight_sum if weight_sum else 0.0


def _forecast_period_total(
    *,
    actual_so_far: int,
    history_totals: list[float],
    period_start: datetime,
    period_end: datetime,
    as_of: datetime,
) -> int:
    """Forecast the period total using a decayed history blended with current pace."""

    if period_end <= period_start:
        return int(actual_so_far)

    elapsed_s = max(0.0, (as_of - period_start).total_seconds())
    total_s = max(1.0, (period_end - period_start).total_seconds())
    fraction = min(0.99, max(0.0, elapsed_s / total_s))

    baseline = _decayed_mean(history_totals[-8:], decay=0.75) if history_totals else 0.0
    if fraction <= 0.0:
        return max(int(round(baseline)), int(actual_so_far))

    effective_fraction = max(0.25, fraction)
    pace_projection = float(actual_so_far) / effective_fraction
    weight = min(0.85, max(0.15, fraction))
    forecast = (1.0 - weight) * baseline + weight * pace_projection
    return max(int(actual_so_far), int(round(forecast)))


def plot_event_distribution_by_type(df: pd.DataFrame, beg_date: datetime, end_date: datetime,
                                    _granularity: str) -> go.Figure:
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


def plot_events_over_time(df: pd.DataFrame, beg_date: datetime, end_date: datetime, _granularity: str) -> go.Figure:
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
    daily_counts = cast(pd.DataFrame, pd.DataFrame(daily_counts_dict).fillna(0))

    # Ensure we have all activity types as columns (even if no data)
    for activity_type in activity_types:
        if activity_type not in daily_counts.columns:
            daily_counts[activity_type] = 0

    # Reorder columns to match our defined order
    daily_counts = cast(pd.DataFrame, daily_counts[activity_types])

    # Calculate 7-day rolling averages for each activity type
    rolling_averages = cast(pd.DataFrame, daily_counts.rolling(window=7, min_periods=1).mean())

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
            'showline': True,
            'linewidth': 1,
            'linecolor': 'rgba(255,255,255,0.24)',
            'tickfont': {'size': 12, 'color': '#e6e6e6'}
        },
        yaxis={
            'title': {'text': 'Average Number of Events per Day', 'font': {'color': '#ffffff'}},
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
    return _apply_dashboard_axes(fig)


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

    dt_series = pd.to_datetime(df_filtered.index).to_series(index=df_filtered.index)
    df_filtered['hour'] = dt_series.dt.hour.astype(int)
    df_filtered['day_of_week'] = dt_series.dt.dayofweek.astype(int)

    # Create heatmap data with proper indexing
    heatmap_data = df_filtered.groupby(['day_of_week', 'hour']).size().unstack(fill_value=0)

    # Ensure all hours (0-23) and all days (0-6) are represented
    all_hours = list(range(24))
    all_days = list(range(7))
    heatmap_data = heatmap_data.reindex(index=all_days, columns=all_hours, fill_value=0)

    # Day names for better readability
    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    nonzero_counts = heatmap_data.stack()
    nonzero_counts = nonzero_counts[nonzero_counts > 0]
    if nonzero_counts.empty:
        zmax = 1.0
    else:
        zmax = max(1.0, float(nonzero_counts.quantile(0.95)))

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
        zmin=0,
        zmax=zmax,
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
    return _apply_dashboard_axes(fig)


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


def _current_period_label(end_date: datetime, granularity: str, index: pd.DatetimeIndex | None = None) -> datetime | None:
    """Return the resample label that contains ``end_date``.

    Prefer an existing label from ``index`` to stay aligned with previously
    materialised resample bins. When no such label exists (e.g., the current
    period has no events yet), fall back to computing the theoretical period end
    using :class:`pandas.Period` so downstream plots can still surface an empty
    "current" bucket.
    """

    fallback: datetime | None = None
    try:
        period = cast(Any, pd.Period(end_date, freq=granularity))
        period_end = period.end_time
        if pd.isna(period_end):
            fallback = None
        else:
            fallback = cast(datetime, cast(Any, period_end).to_pydatetime(warn=False))
    except Exception:  # pragma: no cover - defensive fallback for unusual freqs
        fallback = None

    if index is None or index.empty:
        return fallback

    try:
        label = index[index >= pd.Timestamp(end_date)].min()
        if label is not pd.NaT and label is not None:
            return cast(datetime, cast(Any, label).to_pydatetime(warn=False))
    except (TypeError, ValueError):
        return fallback

    return fallback


def _split_completed_vs_current(series: pd.Series, current_label: datetime | None
                                 ) -> tuple[pd.Series, pd.Series | None]:
    """Split a time series into historical points and the current in-progress point."""

    if current_label is None or series.empty or current_label not in series.index:
        return series, None

    historical = series.loc[series.index < current_label]
    current = series.loc[[current_label]]
    return historical, current


def _ensure_current_point(series: pd.Series, current_label: datetime | None, *, strategy: str = 'zero') -> pd.Series:
    """Guarantee ``series`` contains ``current_label`` so dotted traces can be drawn."""

    if current_label is None:
        return series

    timestamp = pd.Timestamp(current_label)
    if timestamp in series.index:
        return series

    series = series.copy()
    if strategy == 'last' and not series.empty:
        fill_value = series.iloc[-1]
    else:
        fill_value = 0

    series.loc[timestamp] = fill_value
    return series.sort_index()


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
    df_filtered = df.loc[:end_date]
    cumulative_events = df_filtered.resample(granularity, label='right', closed='right').size().cumsum()
    cumulative_events = cumulative_events[cumulative_events.index >= beg_date]

    current_label = _current_period_label(end_date, granularity, cumulative_events.index)
    cumulative_events = _ensure_current_point(cumulative_events, current_label, strategy='last')
    completed, current = _split_completed_vs_current(cumulative_events, current_label)

    fig = go.Figure()

    if not completed.empty:
        fig.add_trace(go.Scatter(x=completed.index, y=completed.values, mode='lines', name='Events'))

    if current is not None:
        connector = pd.concat([completed.tail(1), current]) if not completed.empty else current
        fig.add_trace(go.Scatter(
            x=connector.index,
            y=connector.values,
            mode='lines+markers',
            line=dict(dash='dot'),
            name='Events (current period)',
            showlegend=False,
        ))

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
    completed_tasks: pd.DataFrame = df[df['type'] == 'completed'].groupby(
        ['root_project_name', 'root_project_id', 'date']).size().groupby('root_project_name').cumsum().reset_index()
    completed_tasks = completed_tasks.rename(columns={0: 'completed'})
    completed_tasks = cast(pd.DataFrame, completed_tasks[completed_tasks['date'] >= beg_date])
    completed_tasks = cast(pd.DataFrame, completed_tasks[completed_tasks['date'] <= end_date])
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
    df_completed = df[df['type'] == 'completed'].loc[:end_date].copy()
    df_completed.index = pd.to_datetime(df_completed.index)
    df_weekly_per_project = (
        df_completed
        .groupby([_period_grouper(granularity), 'root_project_name'])
        .size()
        .unstack('root_project_name')
        .sort_index()
    )
    df_weekly_per_project = df_weekly_per_project[df_weekly_per_project.index >= beg_date]

    current_label = _current_period_label(end_date, granularity, df_weekly_per_project.index)
    current_start: datetime | None = None
    current_end: datetime | None = None
    if current_label is not None:
        try:
            period = cast(Any, pd.Period(end_date, freq=granularity))
            start = period.start_time
            end = period.end_time
            if not pd.isna(start) and not pd.isna(end):
                current_start = cast(datetime, cast(Any, start).to_pydatetime(warn=False))
                current_end = cast(datetime, cast(Any, end).to_pydatetime(warn=False))
        except Exception:  # pragma: no cover
            current_start = None
            current_end = None

    now = datetime.now()
    as_of = min(end_date, now)
    show_forecast = bool(current_label and current_start and current_end and current_label > as_of)

    current_counts: dict[str, int] = {}
    if show_forecast and current_start and not df_completed.empty and as_of >= current_start:
        df_current = df_completed[(df_completed.index >= current_start) & (df_completed.index <= as_of)]
        current_counts = df_current.groupby("root_project_name").size().astype(int).to_dict()

    fig = go.Figure()

    for root_project_name in df_weekly_per_project.columns:
        project_series = df_weekly_per_project[root_project_name].fillna(0)
        color = project_colors.get(root_project_name, "#808080")

        if show_forecast and current_label is not None:
            historical = project_series[project_series.index < pd.Timestamp(current_label)]
        else:
            historical = project_series

        if not historical.empty:
            fig.add_trace(
                go.Scatter(
                    x=historical.index,
                    y=historical,
                    name=root_project_name,
                    legendgroup=root_project_name,
                    line_shape="spline",
                    mode="lines+markers",
                    line=dict(color=color),
                )
            )

        if show_forecast and current_label is not None and current_start and current_end:
            history_totals = (
                project_series[project_series.index < pd.Timestamp(current_label)].fillna(0).astype(float).tolist()
            )
            actual_so_far = int(current_counts.get(root_project_name, 0))

            recently_active = actual_so_far > 0 or any(v > 0 for v in history_totals[-4:])
            if not recently_active:
                continue

            forecast_total = _forecast_period_total(
                actual_so_far=actual_so_far,
                history_totals=history_totals,
                period_start=current_start,
                period_end=current_end,
                as_of=as_of,
            )

            if not historical.empty:
                fig.add_trace(
                    go.Scatter(
                        x=[historical.index[-1], current_label],
                        y=[float(historical.iloc[-1]), float(forecast_total)],
                        mode="lines",
                        line=dict(color=color, dash="dash", width=2),
                        name=f"{root_project_name} (forecast line)",
                        legendgroup=root_project_name,
                        showlegend=False,
                        hoverinfo="skip",
                    )
                )

            fig.add_trace(
                go.Scatter(
                    x=[current_label],
                    y=[actual_so_far],
                    mode="markers",
                    marker=dict(symbol="circle-open", size=10, line=dict(width=2, color=color)),
                    name=f"{root_project_name} (so far)",
                    legendgroup=root_project_name,
                    showlegend=False,
                    hovertemplate=f"<b>{root_project_name}</b><br>So far: %{{y}} tasks<extra></extra>",
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=[current_label],
                    y=[forecast_total],
                    mode="markers",
                    marker=dict(symbol="circle", size=16, color=color, opacity=0.92),
                    name=f"{root_project_name} (forecast)",
                    legendgroup=root_project_name,
                    showlegend=False,
                    hovertemplate=f"<b>{root_project_name}</b><br>Forecast: %{{y}} tasks<extra></extra>",
                )
            )

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

    return _apply_dashboard_axes(fig)


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
    df_completed = df[df['type'] == 'completed'].loc[:end_date].copy()
    df_completed.index = pd.to_datetime(df_completed.index)
    df_weekly_per_project = (
        df_completed
        .groupby([_period_grouper(granularity), 'root_project_name'])
        .size()
        .unstack('root_project_name')
        .sort_index()
    )
    df_weekly_per_project = df_weekly_per_project[df_weekly_per_project.index >= beg_date]
    df_weekly_per_project = df_weekly_per_project.cumsum()

    current_label = _current_period_label(end_date, granularity, df_weekly_per_project.index)
    current_start: datetime | None = None
    current_end: datetime | None = None
    if current_label is not None:
        try:
            period = cast(Any, pd.Period(end_date, freq=granularity))
            start = period.start_time
            end = period.end_time
            if not pd.isna(start) and not pd.isna(end):
                current_start = cast(datetime, cast(Any, start).to_pydatetime(warn=False))
                current_end = cast(datetime, cast(Any, end).to_pydatetime(warn=False))
        except Exception:  # pragma: no cover
            current_start = None
            current_end = None

    now = datetime.now()
    as_of = min(end_date, now)
    show_forecast = bool(current_label and current_start and current_end and current_label > as_of)

    current_counts: dict[str, int] = {}
    if show_forecast and current_start and not df_completed.empty and as_of >= current_start:
        df_current = df_completed[(df_completed.index >= current_start) & (df_completed.index <= as_of)]
        current_counts = df_current.groupby("root_project_name").size().astype(int).to_dict()

    # Append 0 from the left (one day before the minimum date)
    min_date = df_weekly_per_project.index.min() - timedelta(days=7 if 'W' in granularity else 14)
    df_weekly_per_project.loc[min_date] = 0
    df_weekly_per_project = df_weekly_per_project.sort_index()

    fig = go.Figure()

    for root_project_name in df_weekly_per_project.columns:
        project_series = df_weekly_per_project[root_project_name].ffill().fillna(0)
        color = project_colors.get(root_project_name, "#808080")

        if show_forecast and current_label is not None:
            historical = project_series[project_series.index < pd.Timestamp(current_label)]
        else:
            historical = project_series

        if not historical.empty:
            fig.add_trace(
                go.Scatter(
                    x=historical.index,
                    y=historical,
                    name=root_project_name,
                    legendgroup=root_project_name,
                    line_shape="spline",
                    mode="lines+markers",
                    line=dict(color=color),
                )
            )

        if show_forecast and current_label is not None and current_start and current_end:
            history_totals = (
                df_weekly_per_project[root_project_name]
                .diff()
                .fillna(df_weekly_per_project[root_project_name])
                .fillna(0)
            )
            history_totals = history_totals[history_totals.index < pd.Timestamp(current_label)].astype(float).tolist()
            actual_so_far = int(current_counts.get(root_project_name, 0))

            recently_active = actual_so_far > 0 or any(v > 0 for v in history_totals[-4:])
            if not recently_active:
                continue

            forecast_total = _forecast_period_total(
                actual_so_far=actual_so_far,
                history_totals=history_totals,
                period_start=current_start,
                period_end=current_end,
                as_of=as_of,
            )

            base = float(historical.iloc[-1]) if not historical.empty else 0.0
            actual_cumsum = int(round(base + actual_so_far))
            forecast_cumsum = int(round(base + forecast_total))

            if not historical.empty:
                fig.add_trace(
                    go.Scatter(
                        x=[historical.index[-1], current_label],
                        y=[float(base), float(forecast_cumsum)],
                        mode="lines",
                        line=dict(color=color, dash="dash", width=2),
                        name=f"{root_project_name} (forecast line)",
                        legendgroup=root_project_name,
                        showlegend=False,
                        hoverinfo="skip",
                    )
                )

            fig.add_trace(
                go.Scatter(
                    x=[current_label],
                    y=[actual_cumsum],
                    mode="markers",
                    marker=dict(symbol="circle-open", size=10, line=dict(width=2, color=color)),
                    name=f"{root_project_name} (so far)",
                    legendgroup=root_project_name,
                    showlegend=False,
                    hovertemplate=f"<b>{root_project_name}</b><br>So far (cumulative): %{{y}}<extra></extra>",
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=[current_label],
                    y=[forecast_cumsum],
                    mode="markers",
                    marker=dict(symbol="circle", size=16, color=color, opacity=0.92),
                    name=f"{root_project_name} (forecast)",
                    legendgroup=root_project_name,
                    showlegend=False,
                    hovertemplate=f"<b>{root_project_name}</b><br>Forecast (cumulative): %{{y}}<extra></extra>",
                )
            )

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

    return _apply_dashboard_axes(fig)


def plot_task_lifespans(df: pd.DataFrame) -> go.Figure:
    """Plot distribution of task completion lifespans with sensible fallbacks."""

    from loguru import logger
    import numpy as np
    from scipy import stats

    def _apply_common_layout(
        fig: go.Figure,
        *,
        title_text: str,
        x_title: str,
        tickvals: list[float] | None = None,
        ticktext: list[str] | None = None,
        x_range: list[float] | None = None,
    ) -> go.Figure:
        fig.update_layout(
            autosize=True,
            template="plotly_dark",
            title={
                "text": title_text,
                "x": 0.5,
                "xanchor": "center",
                "font": {"size": 18, "family": "Arial, sans-serif", "color": "#ffffff"},
            },
            plot_bgcolor="#111318",
            paper_bgcolor="#111318",
            margin=dict(l=80, r=60, t=100, b=86),
            font=dict(color="#ffffff", size=12, family="Arial, sans-serif"),
            legend=dict(
                x=0.98,
                y=1.06,
                xanchor="right",
                yanchor="bottom",
                bgcolor="rgba(17, 19, 24, 0.8)",
                bordercolor="rgba(255,255,255,0.3)",
                borderwidth=1,
                font=dict(size=11, color="#ffffff"),
            ),
        )

        xaxis_options: dict[str, object] = {
            "title": {"text": x_title, "font": {"size": 14, "color": "#ffffff"}},
            "type": "log",
            "showgrid": False,
            "gridcolor": _DASHBOARD_GRID_COLOR,
            "tickfont": {"size": 12, "color": "#e6e6e6"},
            "zeroline": False,
        }
        if tickvals and ticktext:
            xaxis_options["tickmode"] = "array"
            xaxis_options["tickvals"] = tickvals
            xaxis_options["ticktext"] = ticktext
        if x_range:
            xaxis_options["range"] = x_range
        fig.update_xaxes(**xaxis_options)
        fig.update_yaxes(
            title={"text": "Frequency", "font": {"size": 14, "color": "#ffffff"}},
            showgrid=False,
            gridcolor=_DASHBOARD_GRID_COLOR,
            tickfont={"size": 12, "color": "#e6e6e6"},
            rangemode="tozero",
        )
        return _apply_dashboard_axes(fig)

    def _empty_figure(message: str) -> go.Figure:
        fig = go.Figure()
        return _apply_common_layout(fig, title_text=f"Task Lifespans ({message})", x_title="Time to Completion")

    def _build_time_ticks(
        *,
        min_seconds: float,
        max_seconds: float,
        axis_unit_seconds: float,
    ) -> tuple[list[float], list[str]]:
        import math

        candidates = [
            (1, "1s"),
            (10, "10s"),
            (60, "1m"),
            (10 * 60, "10m"),
            (60 * 60, "1h"),
            (3 * 60 * 60, "3h"),
            (12 * 60 * 60, "12h"),
            (24 * 60 * 60, "1d"),
            (3 * 24 * 60 * 60, "3d"),
            (7 * 24 * 60 * 60, "1w"),
            (3 * 7 * 24 * 60 * 60, "3w"),
            (28 * 24 * 60 * 60, "4w"),
            (6 * 7 * 24 * 60 * 60, "6w"),
            (12 * 7 * 24 * 60 * 60, "12w"),
        ]
        max_ticks = 9
        lower = min_seconds / 2.0
        upper = max_seconds * 1.5
        selected = [(sec, label) for sec, label in candidates if lower <= sec <= upper]
        if not selected:
            selected = [(sec, label) for sec, label in candidates if sec <= upper]
            if selected:
                selected = selected[-max_ticks:]
        if not selected:
            target = max(min_seconds, 1e-6)
            selected = [min(candidates, key=lambda item: abs(math.log10(item[0]) - math.log10(target)))]
        if len(selected) > max_ticks:
            step = max(1, math.ceil((len(selected) - 1) / (max_ticks - 1)))
            trimmed = [selected[0]]
            trimmed.extend(selected[1:-1:step])
            trimmed.append(selected[-1])
            selected = trimmed
            if len(selected) > max_ticks:
                selected = selected[:max_ticks - 1] + [selected[-1]]
        tickvals = [sec / axis_unit_seconds for sec, _ in selected]
        ticktext = [label for _, label in selected]
        return tickvals, ticktext

    def _hex_to_rgba(hex_color: str, alpha: float) -> str:
        hex_color = hex_color.lstrip("#")
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        return f"rgba({r},{g},{b},{alpha})"

    def _slice_density(
        x_values: np.ndarray,
        densities: np.ndarray,
        *,
        low: float | None = None,
        high: float | None = None,
    ) -> tuple[np.ndarray, np.ndarray] | None:
        if low is None and high is None:
            return None
        if low is None:
            mask = x_values <= high
        elif high is None:
            mask = x_values >= low
        else:
            mask = (x_values >= low) & (x_values <= high)
        if not mask.any():
            return None
        x_segment = x_values[mask]
        y_segment = densities[mask]
        if low is not None and x_segment[0] > low:
            y_low = np.interp(low, x_values, densities)
            x_segment = np.concatenate(([low], x_segment))
            y_segment = np.concatenate(([y_low], y_segment))
        if high is not None and x_segment[-1] < high:
            y_high = np.interp(high, x_values, densities)
            x_segment = np.concatenate((x_segment, [high]))
            y_segment = np.concatenate((y_segment, [y_high]))
        if x_segment.size < 2:
            return None
        return x_segment, y_segment

    def _format_duration_compact(seconds: float) -> str:
        total = int(round(max(0.0, seconds)))
        units = [
            ("w", 7 * 24 * 60 * 60),
            ("d", 24 * 60 * 60),
            ("h", 60 * 60),
            ("m", 60),
            ("s", 1),
        ]
        parts: list[str] = []
        for suffix, unit_seconds in units:
            if total >= unit_seconds or (suffix == "s" and not parts):
                value = total // unit_seconds
                total = total % unit_seconds
                parts.append(f"{value}{suffix}")
            if len(parts) == 2:
                break
        return "".join(parts)

    def _merge_ticks(
        tickvals: list[float],
        ticktext: list[str],
        highlights: list[tuple[float, str]],
    ) -> tuple[list[float], list[str]]:
        import math

        pairs = list(zip(tickvals, ticktext))
        for value, label in highlights:
            if not np.isfinite(value) or value <= 0:
                continue
            if any(abs(math.log10(value) - math.log10(v)) < 0.03 for v in tickvals if v > 0):
                continue
            pairs.append((value, label))
        pairs.sort(key=lambda item: item[0])
        return [value for value, _ in pairs], [label for _, label in pairs]
    if "type" not in df.columns:
        logger.error("DataFrame missing required 'type' column")
        return _empty_figure("Invalid data structure")

    identifier = "task_id" if "task_id" in df.columns else "parent_item_id" if "parent_item_id" in df.columns else None
    if identifier is None:
        logger.error("DataFrame missing task identifier column ('task_id' or 'parent_item_id')")
        return _empty_figure("Invalid data structure")

    event_mask = cast(pd.Series, df["type"].isin(["added", "completed"]))
    if not event_mask.any():
        logger.info("No added/completed events available for lifespan plot")
        return _empty_figure("No Task Events")

    events = df.loc[event_mask, [identifier, "type"]].copy()
    timestamps = pd.to_datetime(df.index[event_mask])
    events["timestamp"] = timestamps

    added_times = events.loc[events["type"] == "added"].groupby(identifier)["timestamp"].min()
    completed_times = events.loc[events["type"] == "completed"].groupby(identifier)["timestamp"].max()

    common_ids = added_times.index.intersection(completed_times.index)
    if common_ids.empty:
        logger.info("No tasks have both added and completed events")
        return _empty_figure("No Tasks with Both Added and Completed Events")

    durations = (completed_times.loc[common_ids] - added_times.loc[common_ids]).dt.total_seconds().to_numpy(dtype=float)
    durations = durations[durations > 0]
    if durations.size == 0:
        logger.info("All computed durations are non-positive; nothing to plot")
        return _empty_figure("No valid durations")

    max_duration = float(durations.max())
    if max_duration < 60:
        axis_unit_seconds = 1.0
        unit_label = "sec"
        title_unit = "sec"
    elif max_duration < 3600:
        axis_unit_seconds = 60.0
        unit_label = "min"
        title_unit = "min"
    elif max_duration < 86400:
        axis_unit_seconds = 3600.0
        unit_label = "hr"
        title_unit = "hr"
    else:
        axis_unit_seconds = 86400.0
        unit_label = "days"
        title_unit = "days"
    durations_converted = durations / axis_unit_seconds
    log_durations = np.log10(durations_converted)
    total_count = int(durations_converted.size)
    percentile_low = float(np.percentile(durations_converted, 15))
    percentile_high = float(np.percentile(durations_converted, 85))
    if total_count >= 20:
        plot_min = float(np.percentile(durations_converted, 1))
        plot_max = float(np.percentile(durations_converted, 99))
    else:
        plot_min = float(durations_converted.min())
        plot_max = float(durations_converted.max())
    if not np.isfinite(plot_min) or plot_min <= 0:
        plot_min = float(durations_converted.min())
    if not np.isfinite(plot_max) or plot_max <= plot_min:
        plot_max = float(durations_converted.max())
    min_log = float(np.log10(plot_min))
    max_log = float(np.log10(plot_max))
    pad = max(0.15, 0.1 * (max_log - min_log))
    highlight_low = float(np.clip(percentile_low, plot_min, plot_max))
    highlight_high = float(np.clip(percentile_high, plot_min, plot_max))

    fig = go.Figure()

    # Optional KDE overlay when data variability allows it
    if total_count >= 2 and not np.isclose(log_durations.var(), 0.0):
        kde = stats.gaussian_kde(log_durations, bw_method="scott")
        log_bounds = np.linspace(min_log - pad, max_log + pad, 512)
        x_values = np.power(10.0, log_bounds)
        densities = kde(log_bounds)
        integral = float(np.trapezoid(densities, x_values))
        if np.isfinite(integral) and integral > 0:
            densities = densities * (total_count / integral)
            x_min = float(x_values.min())
            x_max = float(x_values.max())
            y_max = float(densities.max()) if densities.size else 0.0
            y_offset = 0.12 * y_max if y_max > 0 else 0.0
            highlight_low = float(np.clip(highlight_low, x_min, x_max))
            highlight_high = float(np.clip(highlight_high, x_min, x_max))
            highlight_specs = [
                ("Fastest 15%", None, highlight_low, "#00E5FF"),
                ("Slowest 15%", highlight_high, None, "#FF4F9A"),
            ]
            for name, low, high, color in highlight_specs:
                segment = _slice_density(x_values, densities, low=low, high=high)
                if segment is None:
                    continue
                x_segment, y_segment = segment
                fig.add_trace(
                    go.Scatter(
                        x=x_segment,
                        y=y_segment,
                        mode="lines",
                        line=dict(color=_hex_to_rgba(color, 0.55), width=6),
                        name=f"{name} outline",
                        showlegend=False,
                        hoverinfo="skip",
                    )
                )
                fig.add_trace(
                    go.Scatter(
                        x=x_segment,
                        y=y_segment,
                        mode="lines",
                        line=dict(color=color, width=3),
                        fill="tozeroy",
                        fillcolor=_hex_to_rgba(color, 0.38),
                        name=name,
                        hovertemplate=(
                            f"{name}<br>Duration: %{{x:.4g}} {unit_label}<br>"
                            "Frequency: %{y:.2f}<extra></extra>"
                        ),
                    )
                )
            boundary_specs = [
                (highlight_low, "#00E5FF"),
                (highlight_high, "#FF4F9A"),
            ]
            for x_value, color in boundary_specs:
                if not np.isfinite(x_value):
                    continue
                fig.add_shape(
                    type="line",
                    x0=x_value,
                    x1=x_value,
                    y0=0,
                    y1=1,
                    xref="x",
                    yref="paper",
                    line=dict(color=_hex_to_rgba(color, 0.85), width=2, dash="dash"),
                )
            fig.add_trace(
                go.Scatter(
                    x=x_values,
                    y=densities,
                    mode="lines",
                    line=dict(color="#1ABC9C", width=3),
                    name="Smoothed frequency",
                    hovertemplate="Duration: %{x:.4g} " + unit_label + "<br>Frequency: %{y:.2f}<extra></extra>",
                )
            )
        else:
            logger.warning("KDE normalisation failed; skipping smoothed overlay")
    else:
        fig.add_annotation(
            text="Add more completed tasks to see a smooth distribution.",
            xref="paper",
            yref="paper",
            x=0.5,
            y=0.85,
            showarrow=False,
            font=dict(color="#bbbbbb"),
        )

    fig.update_layout(barmode="overlay", bargap=0.15)

    title_text = "Task Lifespans: Time to Completion"
    x_title = ""
    tickvals, ticktext = _build_time_ticks(
        min_seconds=float(max(durations.min(), plot_min * axis_unit_seconds)),
        max_seconds=float(min(durations.max(), plot_max * axis_unit_seconds)),
        axis_unit_seconds=axis_unit_seconds,
    )
    tickvals, ticktext = _merge_ticks(
        tickvals,
        ticktext,
        [
            (highlight_low, f"15%<br>{_format_duration_compact(highlight_low * axis_unit_seconds)}"),
            (highlight_high, f"85%<br>{_format_duration_compact(highlight_high * axis_unit_seconds)}"),
        ],
    )

    return _apply_common_layout(
        fig,
        title_text=title_text,
        x_title=x_title,
        tickvals=tickvals,
        ticktext=ticktext,
        x_range=[min_log - pad, max_log + pad] if total_count >= 2 else None,
    )
