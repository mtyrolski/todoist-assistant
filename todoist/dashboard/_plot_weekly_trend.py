from dataclasses import dataclass
from datetime import datetime
from typing import cast

import pandas as pd
import plotly.graph_objects as go

from todoist.dashboard._plot_common import apply_dashboard_axes


@dataclass(frozen=True)
class _WeeklyTrendWindowStats:
    """Computed baseline curve statistics for a lookback window."""

    lookback_weeks: int
    sample_size: int
    avg_week_total: float
    avg_curve: pd.Series
    p25_curve: pd.Series
    p75_curve: pd.Series


def _weekly_trend_empty_figure(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
        showarrow=False,
        font=dict(size=14, color="#e6e6e6"),
    )
    fig.update_layout(
        template="plotly_dark",
        title={
            "text": "Weekly Completion Trend",
            "x": 0.5,
            "xanchor": "center",
            "font": {"size": 18, "family": "Arial, sans-serif", "color": "#ffffff"},
        },
        plot_bgcolor="#111318",
        paper_bgcolor="#111318",
        margin=dict(l=56, r=32, t=84, b=56),
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


def _weekly_trend_prepare_weekly_counts(
    df: pd.DataFrame, end_date: datetime
) -> tuple[pd.DataFrame, pd.Timestamp] | None:
    if "type" not in df.columns:
        return None

    df_completed = df[df["type"] == "completed"].loc[:end_date]
    if df_completed.empty:
        return None

    completion_series = cast(
        pd.Series,
        pd.to_datetime(df_completed.index).to_series(index=df_completed.index),
    )
    completion_days = cast(pd.Series, completion_series.dt.normalize())
    daily_counts = completion_days.groupby(completion_days).size().sort_index()
    if daily_counts.empty:
        return None

    end_ts = cast(pd.Timestamp, pd.Timestamp(end_date)).normalize()
    all_days = pd.date_range(start=daily_counts.index.min(), end=end_ts, freq="D")
    daily_counts = daily_counts.reindex(all_days, fill_value=0).astype(float)

    day_index = cast(pd.Index, daily_counts.index)
    day_numbers = cast(
        pd.Series,
        pd.to_datetime(day_index).to_series(index=day_index).dt.dayofweek.astype(int),
    )
    week_starts = cast(pd.Series, day_index - pd.to_timedelta(day_numbers, unit="D"))
    day_frame = pd.DataFrame(
        {
            "count": daily_counts.values,
            "week_start": week_starts.values,
            "weekday": day_numbers.values,
        },
        index=day_index,
    )

    weekly_counts = cast(
        pd.DataFrame,
        day_frame.pivot_table(
            index="week_start",
            columns="weekday",
            values="count",
            aggfunc="sum",
            fill_value=0.0,
        ),
    )
    weekly_counts = weekly_counts.reindex(columns=range(7), fill_value=0.0).sort_index()
    current_week_start = cast(
        pd.Timestamp, end_ts - pd.Timedelta(days=int(end_ts.dayofweek))
    )
    if pd.isna(current_week_start):
        return None
    if current_week_start not in weekly_counts.index:
        weekly_counts.loc[current_week_start] = 0.0
        weekly_counts = weekly_counts.sort_index()

    return weekly_counts, current_week_start


def _weekly_trend_window_stats(
    historical_weeks: pd.DataFrame,
    lookback_weeks: int,
    *,
    require_full_window: bool = False,
) -> _WeeklyTrendWindowStats | None:
    candidate_weeks = cast(pd.DataFrame, historical_weeks.tail(lookback_weeks))
    if candidate_weeks.empty:
        return None
    if require_full_window and int(candidate_weeks.shape[0]) < lookback_weeks:
        return None

    week_totals = candidate_weeks.sum(axis=1)
    valid_weeks = cast(pd.DataFrame, candidate_weeks[week_totals > 0])
    if valid_weeks.empty:
        return None

    normalized = cast(
        pd.DataFrame,
        valid_weeks.cumsum(axis=1).div(valid_weeks.sum(axis=1), axis=0) * 100.0,
    )
    return _WeeklyTrendWindowStats(
        lookback_weeks=lookback_weeks,
        sample_size=int(valid_weeks.shape[0]),
        avg_week_total=float(valid_weeks.sum(axis=1).mean()),
        avg_curve=cast(pd.Series, normalized.mean(axis=0)),
        p25_curve=cast(pd.Series, normalized.quantile(0.25, axis=0)),
        p75_curve=cast(pd.Series, normalized.quantile(0.75, axis=0)),
    )


def _weekly_trend_current_week_curves(
    weekly_counts: pd.DataFrame,
    current_week_start: pd.Timestamp,
    *,
    end_date: datetime,
    normalize_by_total: float,
) -> tuple[pd.Series, list[int | None]]:
    end_ts = cast(pd.Timestamp, pd.Timestamp(end_date)).normalize()
    current_day_idx = int(end_ts.dayofweek)
    current_week_counts = cast(
        pd.Series, weekly_counts.loc[current_week_start].astype(float)
    )
    raw_cumulative = current_week_counts.cumsum()
    for day_idx in range(current_day_idx + 1, 7):
        raw_cumulative.loc[day_idx] = float("nan")

    denominator = max(1e-6, float(normalize_by_total))
    normalized_cumulative = raw_cumulative / denominator * 100.0
    raw_hover_values = [
        None if pd.isna(value) else int(round(float(value)))
        for value in raw_cumulative.tolist()
    ]
    return cast(pd.Series, normalized_cumulative), raw_hover_values


def _weekly_trend_add_window_traces(
    fig: go.Figure,
    *,
    weekday_labels: list[str],
    stats: _WeeklyTrendWindowStats,
    color: str,
    visible: bool | str,
    show_in_legend: bool,
) -> None:
    legend_group = f"window-{stats.lookback_weeks}"
    label = (
        f"{stats.lookback_weeks}w baseline "
        f"(n={stats.sample_size}, avg={stats.avg_week_total:.1f} tasks/w)"
    )

    fig.add_trace(
        go.Scatter(
            x=weekday_labels,
            y=stats.p25_curve.values,
            mode="lines",
            line=dict(width=0),
            legendgroup=legend_group,
            showlegend=False,
            hoverinfo="skip",
            visible=visible,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=weekday_labels,
            y=stats.p75_curve.values,
            mode="lines",
            fill="tonexty",
            fillcolor=color.replace("rgb", "rgba").replace(")", ", 0.14)"),
            line=dict(width=0),
            legendgroup=legend_group,
            showlegend=False,
            hovertemplate=(
                f"<b>{stats.lookback_weeks}w interquartile range</b><br>"
                "%{x}: %{y:.1f}%<extra></extra>"
            ),
            visible=visible,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=weekday_labels,
            y=stats.avg_curve.values,
            mode="lines+markers",
            line=dict(color=color, width=3),
            marker=dict(size=7, color=color),
            name=label,
            legendgroup=legend_group,
            showlegend=show_in_legend,
            visible=visible,
            hovertemplate=(
                f"<b>{stats.lookback_weeks}w average pace</b><br>"
                "%{x}: %{y:.1f}% cumulative<br>"
                f"Weeks used: {stats.sample_size}<br>"
                f"Avg completed/week: {stats.avg_week_total:.1f}<extra></extra>"
            ),
        )
    )


def plot_weekly_completion_trend(df: pd.DataFrame, end_date: datetime) -> go.Figure:
    prepared = _weekly_trend_prepare_weekly_counts(df, end_date)
    if prepared is None:
        message = (
            "Missing 'type' column in activity data."
            if "type" not in df.columns
            else "No completed tasks available yet."
        )
        return _weekly_trend_empty_figure(message)

    weekly_counts, current_week_start = prepared
    weekday_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    historical_weeks = cast(
        pd.DataFrame, weekly_counts[weekly_counts.index < current_week_start]
    )

    fixed_baseline = _weekly_trend_window_stats(historical_weeks, lookback_weeks=3)
    if fixed_baseline is None:
        return _weekly_trend_empty_figure(
            "Not enough finished-week data for baseline trend."
        )

    optional_stats = [
        stats
        for window in [6, 12, 24]
        if (
            stats := _weekly_trend_window_stats(
                historical_weeks,
                lookback_weeks=window,
                require_full_window=True,
            )
        )
        is not None
    ]
    current_curve, current_hover_raw = _weekly_trend_current_week_curves(
        weekly_counts,
        current_week_start,
        end_date=end_date,
        normalize_by_total=fixed_baseline.avg_week_total,
    )
    current_total = (
        max(value or 0 for value in current_hover_raw if value is not None)
        if current_hover_raw
        else 0
    )

    fig = go.Figure()
    color_map = {
        3: "rgb(108, 207, 246)",
        6: "rgb(144, 190, 109)",
        12: "rgb(249, 132, 74)",
        24: "rgb(168, 104, 255)",
    }
    _weekly_trend_add_window_traces(
        fig,
        weekday_labels=weekday_labels,
        stats=fixed_baseline,
        color=color_map[3],
        visible=True,
        show_in_legend=False,
    )
    for stats in optional_stats:
        _weekly_trend_add_window_traces(
            fig,
            weekday_labels=weekday_labels,
            stats=stats,
            color=color_map.get(stats.lookback_weeks, "rgb(190, 190, 190)"),
            visible="legendonly",
            show_in_legend=True,
        )

    fig.add_trace(
        go.Scatter(
            x=weekday_labels,
            y=current_curve.values,
            customdata=current_hover_raw,
            mode="lines+markers",
            line=dict(color="#FFB703", width=3, dash="dash"),
            marker=dict(size=8, color="#FFB703"),
            name=(
                f"Current week (raw: {current_total} tasks so far, "
                f"normalized vs 3w avg={fixed_baseline.avg_week_total:.1f})"
            ),
            showlegend=False,
            hovertemplate=(
                "<b>Current week</b><br>"
                "%{x}: %{customdata} cumulative tasks<br>"
                "%{y:.1f}% vs 3-week average volume<extra></extra>"
            ),
        )
    )

    optional_suffix = (
        "Toggle optional 6w/12w/24w baselines in legend."
        if optional_stats
        else "No optional 6w/12w/24w baselines available yet."
    )
    fig.update_layout(
        template="plotly_dark",
        title={
            "text": (
                f"Weekly Completion Trend - Fixed 3w baseline "
                f"(n={fixed_baseline.sample_size})<br>"
                f"<sup>{optional_suffix}</sup>"
            ),
            "x": 0.5,
            "xanchor": "center",
            "font": {"size": 18, "family": "Arial, sans-serif", "color": "#ffffff"},
        },
        xaxis={
            "title": {"text": "Day of week", "font": {"size": 14, "color": "#ffffff"}},
            "categoryorder": "array",
            "categoryarray": weekday_labels,
            "tickfont": {"size": 12, "color": "#e6e6e6"},
            "showline": True,
            "linewidth": 1,
            "linecolor": "rgba(255,255,255,0.24)",
        },
        yaxis={
            "title": {
                "text": "Cumulative completions (% progression)",
                "font": {"size": 14, "color": "#ffffff"},
            },
            "tickfont": {"size": 12, "color": "#e6e6e6"},
            "ticksuffix": "%",
            "showline": True,
            "linewidth": 1,
            "linecolor": "rgba(255,255,255,0.24)",
            "rangemode": "tozero",
        },
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "left",
            "x": 0.01,
            "groupclick": "togglegroup",
            "font": {"size": 11, "color": "#e6e6e6"},
            "bgcolor": "rgba(17,19,24,0.75)",
            "title": {"text": "Optional windows"},
        },
        plot_bgcolor="#111318",
        paper_bgcolor="#111318",
        margin=dict(l=56, r=32, t=106, b=56),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor="#1e1e1e", bordercolor="#444", font=dict(color="#ffffff")
        ),
    )
    return apply_dashboard_axes(fig)
