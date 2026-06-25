from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd
import plotly.graph_objects as go

from todoist.core.env import EnvVar

from todoist.dashboard._plot_common import (
    _ALL_TASKS_TOTAL_COLOR,
    apply_dashboard_axes,
    forecast_period_total,
    period_grouper,
)


def _current_period_label(
    end_date: datetime, granularity: str, index: pd.DatetimeIndex | None = None
) -> datetime | None:
    """Return the resample label that contains ``end_date``."""

    fallback = _period_label_for_granularity(end_date, granularity)

    if index is None or index.empty:
        return fallback

    try:
        label = index[index >= pd.Timestamp(end_date)].min()
        if label is not pd.NaT and label is not None:
            return cast(datetime, cast(Any, label).to_pydatetime(warn=False))
    except (TypeError, ValueError):
        return fallback
    return fallback


def _periodic_timezone() -> ZoneInfo | Any:
    configured = os.getenv(str(EnvVar.TIMEZONE), "").strip().strip("'\"")
    candidates = [configured]
    timezone_file = Path("/etc/timezone")
    if timezone_file.exists():
        try:
            candidates.append(timezone_file.read_text(encoding="utf-8").strip())
        except OSError:
            pass
    try:
        localtime = Path("/etc/localtime").resolve()
        marker = "zoneinfo/"
        if marker in str(localtime):
            candidates.append(str(localtime).split(marker, 1)[1])
    except OSError:
        pass

    for candidate in candidates:
        if not candidate:
            continue
        try:
            return ZoneInfo(candidate)
        except ZoneInfoNotFoundError:
            continue
    return datetime.now().astimezone().tzinfo


def _local_periodic_index(index: pd.Index) -> pd.DatetimeIndex:
    utc_index = pd.to_datetime(index, errors="coerce", utc=True)
    return cast(
        pd.DatetimeIndex, utc_index.tz_convert(_periodic_timezone()).tz_localize(None)
    )


def _drop_projects_without_period_activity(df_periodic: pd.DataFrame) -> pd.DataFrame:
    if df_periodic.empty or df_periodic.columns.empty:
        return df_periodic

    active_columns = [
        column
        for column in df_periodic.columns
        if float(cast(pd.Series, df_periodic[column]).fillna(0).sum()) > 0
    ]
    return cast(pd.DataFrame, df_periodic.loc[:, active_columns])


def _columns_with_completed_activity(
    df_completed: pd.DataFrame,
    *,
    beg_date: datetime,
    end_date: datetime,
    always_visible_projects: set[str] | None = None,
) -> list[str]:
    if df_completed.empty:
        return []

    always_visible_projects = always_visible_projects or set()
    df_visible = df_completed[
        (df_completed.index >= beg_date) & (df_completed.index <= end_date)
    ]
    visible_names: set[str] = set()
    if not df_visible.empty:
        project_names = cast(pd.Series, df_visible["root_project_name"])
        visible_names.update(
            str(name) for name in project_names.dropna().astype(str).unique()
        )

    if always_visible_projects:
        all_project_names = cast(pd.Series, df_completed["root_project_name"])
        visible_names.update(
            str(name)
            for name in all_project_names.dropna().astype(str).unique()
            if str(name) in always_visible_projects
        )

    return sorted(visible_names)


def _period_freq_for_granularity(granularity: str) -> str:
    """Convert resampling aliases into Period-compatible frequencies."""

    if granularity == "ME":
        return "M"
    if granularity == "3ME":
        return "Q-DEC"
    return granularity


def _period_label_for_granularity(
    end_date: datetime, granularity: str
) -> datetime | None:
    try:
        period = cast(
            Any, pd.Period(end_date, freq=_period_freq_for_granularity(granularity))
        )
        period_end = period.end_time
        if pd.isna(period_end):
            return None
        period_end_ts = cast(pd.Timestamp, pd.Timestamp(period_end))
        return cast(datetime, period_end_ts.normalize().to_pydatetime(warn=False))
    except Exception:  # pragma: no cover - defensive fallback for unusual freqs
        return None


@dataclass(frozen=True)
class _PeriodicForecastContext:
    current_label: datetime | None
    current_start: datetime | None
    current_end: datetime | None
    as_of: datetime
    show_forecast: bool


@dataclass(frozen=True)
class _PeriodicPlotConfig:
    cumulative: bool
    total_name: str
    title_prefix: str
    yaxis_title: str
    line_shape: str
    hover_total_suffix: str


_PERIODIC_CONFIG = _PeriodicPlotConfig(
    cumulative=False,
    total_name="All Projects (total)",
    title_prefix="",
    yaxis_title="Completed Tasks per Project",
    line_shape="spline",
    hover_total_suffix=" tasks",
)
_CUMULATIVE_CONFIG = _PeriodicPlotConfig(
    cumulative=True,
    total_name="All Projects (total cumulative)",
    title_prefix="Cumulative ",
    yaxis_title="Cumulative Tasks per Project",
    line_shape="linear",
    hover_total_suffix=" cumulative tasks",
)


def _prepare_completed_periodic_frame(
    df: pd.DataFrame,
    *,
    beg_date: datetime,
    end_date: datetime,
    granularity: str,
    visibility_beg_date: datetime | None = None,
    visibility_end_date: datetime | None = None,
    always_visible_projects: set[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    df_completed = cast(pd.DataFrame, df[df["type"] == "completed"].copy())
    df_completed.index = _local_periodic_index(df_completed.index)
    df_completed = cast(pd.DataFrame, df_completed[df_completed.index <= end_date])
    visibility_beg = visibility_beg_date or beg_date
    visibility_end = visibility_end_date or end_date
    active_columns = _columns_with_completed_activity(
        df_completed,
        beg_date=visibility_beg,
        end_date=visibility_end,
        always_visible_projects=always_visible_projects,
    )
    df_periodic = cast(
        pd.DataFrame,
        df_completed.groupby([period_grouper(granularity), "root_project_name"])
        .size()
        .unstack("root_project_name")
        .sort_index(),
    )
    df_periodic = cast(pd.DataFrame, df_periodic[df_periodic.index >= beg_date])
    df_periodic = cast(
        pd.DataFrame,
        df_periodic.loc[
            :, [column for column in active_columns if column in df_periodic.columns]
        ],
    )
    return df_completed, _drop_projects_without_period_activity(df_periodic)


def _period_bounds_for_granularity(
    end_date: datetime, granularity: str
) -> tuple[datetime | None, datetime | None]:
    try:
        period = cast(
            Any, pd.Period(end_date, freq=_period_freq_for_granularity(granularity))
        )
        start = period.start_time
        end = period.end_time
        if pd.isna(start) or pd.isna(end):
            return None, None
        return (
            cast(datetime, cast(Any, start).to_pydatetime(warn=False)),
            cast(datetime, cast(Any, end).to_pydatetime(warn=False)),
        )
    except Exception:  # pragma: no cover - defensive fallback for unusual freqs
        return None, None


def _build_periodic_forecast_context(
    *,
    end_date: datetime,
    granularity: str,
    period_index: pd.Index,
) -> _PeriodicForecastContext:
    normalized_index = cast(pd.DatetimeIndex, pd.DatetimeIndex(period_index))
    as_of = min(end_date, datetime.now())
    current_label = _current_period_label(as_of, granularity, normalized_index)
    current_start: datetime | None = None
    current_end: datetime | None = None
    if current_label is not None:
        current_start, current_end = _period_bounds_for_granularity(as_of, granularity)

    has_current_period_activity = bool(
        current_start is not None
        and not normalized_index.empty
        and cast(pd.Timestamp, normalized_index.max()) >= pd.Timestamp(current_start)
    )
    show_forecast = bool(
        current_label
        and current_start
        and current_end
        and current_label > as_of
        and has_current_period_activity
    )
    return _PeriodicForecastContext(
        current_label=current_label,
        current_start=current_start,
        current_end=current_end,
        as_of=as_of,
        show_forecast=show_forecast,
    )


def _current_period_project_counts(
    df_completed: pd.DataFrame, *, context: _PeriodicForecastContext
) -> dict[str, int]:
    if (
        not context.show_forecast
        or context.current_start is None
        or df_completed.empty
        or context.as_of < context.current_start
    ):
        return {}

    df_current = cast(
        pd.DataFrame,
        df_completed[
            (df_completed.index >= context.current_start)
            & (df_completed.index <= context.as_of)
        ],
    )
    if df_current.empty:
        return {}
    return df_current.groupby("root_project_name").size().astype(int).to_dict()


def _total_tasks_series(df_periodic: pd.DataFrame) -> pd.Series:
    if df_periodic.empty or df_periodic.columns.empty:
        return pd.Series(dtype=float)

    totals = cast(pd.Series, df_periodic.fillna(0).sum(axis=1).astype(float))
    if float(totals.fillna(0).sum()) <= 0:
        return pd.Series(dtype=float)
    return totals


def _activity_span(series: pd.Series) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    active = cast(pd.Series, series.fillna(0).astype(float) > 0)
    if not bool(active.any()):
        return None
    active_index = cast(pd.Index, series.index[active])
    return cast(pd.Timestamp, active_index.min()), cast(
        pd.Timestamp, active_index.max()
    )


def _trim_to_activity_span(series: pd.Series, activity_series: pd.Series) -> pd.Series:
    span = _activity_span(activity_series)
    if span is None:
        return pd.Series(dtype=float)
    start, end = span
    return cast(
        pd.Series,
        series[(series.index >= start) & (series.index <= end)],
    )


def _positive_activity_periods(series: pd.Series) -> pd.Series:
    active = cast(pd.Series, series.fillna(0).astype(float) > 0)
    return cast(pd.Series, series[active])


def _series_at_positive_activity_periods(
    series: pd.Series,
    activity_series: pd.Series,
) -> pd.Series:
    active_periods = _positive_activity_periods(activity_series)
    if active_periods.empty:
        return pd.Series(dtype=float)
    return cast(pd.Series, series.loc[active_periods.index])


def _forecast_marker_trace(
    *,
    x: datetime,
    y: float | int,
    color: str,
    name: str,
    legendgroup: str,
    hovertemplate: str,
    forecast: bool,
    marker_size: int | None = None,
    marker_opacity: float | None = None,
) -> go.Scatter:
    return go.Scatter(
        x=[x],
        y=[y],
        mode="markers",
        marker=(
            dict(
                symbol="circle",
                size=marker_size or 16,
                color=color,
                opacity=marker_opacity or 0.92,
            )
            if forecast
            else dict(symbol="circle-open", size=10, line=dict(width=2, color=color))
        ),
        name=name,
        legendgroup=legendgroup,
        showlegend=False,
        hovertemplate=hovertemplate,
    )


def _add_total_overlay_traces(
    fig: go.Figure,
    *,
    total_series: pd.Series,
    context: _PeriodicForecastContext,
    total_actual_so_far: int,
    config: _PeriodicPlotConfig,
) -> None:
    if total_series.empty:
        return

    if context.show_forecast and context.current_label is not None:
        historical = cast(
            pd.Series,
            total_series[total_series.index < pd.Timestamp(context.current_label)],
        )
    else:
        historical = cast(pd.Series, total_series)

    if not historical.empty:
        fig.add_trace(
            go.Scatter(
                x=historical.index,
                y=historical.astype(float).tolist(),
                name=config.total_name,
                legendgroup="all-projects-total",
                line_shape=config.line_shape,
                mode="lines+markers",
                line=dict(color=_ALL_TASKS_TOTAL_COLOR, width=3),
                marker=dict(size=8, symbol="diamond", color=_ALL_TASKS_TOTAL_COLOR),
                hovertemplate=f"<b>All projects</b><br>%{{x}}: %{{y:.0f}}{config.hover_total_suffix}<extra></extra>",
            )
        )

    if (
        not context.show_forecast
        or context.current_label is None
        or context.current_start is None
        or context.current_end is None
    ):
        return

    history_source = cast(
        pd.Series,
        total_series[total_series.index < pd.Timestamp(context.current_label)],
    )
    history_values = history_source.fillna(0).astype(float).tolist()
    if config.cumulative:
        period_totals = total_series.diff().fillna(total_series).fillna(0)
        history_values = (
            cast(
                pd.Series,
                period_totals[
                    period_totals.index < pd.Timestamp(context.current_label)
                ],
            )
            .astype(float)
            .tolist()
        )
    recently_active = total_actual_so_far > 0 or any(v > 0 for v in history_values[-4:])
    if not recently_active:
        return

    forecast_total = forecast_period_total(
        actual_so_far=int(total_actual_so_far),
        history_totals=history_values,
        period_start=context.current_start,
        period_end=context.current_end,
        as_of=context.as_of,
    )
    base_total = (
        float(historical.iloc[-1])
        if config.cumulative and not historical.empty
        else 0.0
    )
    actual_value = float(base_total + total_actual_so_far)
    forecast_value = float(base_total + forecast_total)
    if not config.cumulative:
        actual_value = float(total_actual_so_far)
        forecast_value = float(forecast_total)

    if not historical.empty:
        fig.add_trace(
            go.Scatter(
                x=[historical.index[-1], context.current_label],
                y=[float(historical.iloc[-1]), forecast_value],
                mode="lines",
                line=dict(color=_ALL_TASKS_TOTAL_COLOR, dash="dash", width=2),
                name="All Projects (forecast line)",
                legendgroup="all-projects-total",
                showlegend=False,
                hoverinfo="skip",
            )
        )

    total_suffix = " (cumulative)" if config.cumulative else ""
    task_suffix = "" if config.cumulative else " tasks"
    for label, value, forecast in (
        ("So far", actual_value, False),
        ("Forecast", forecast_value, True),
    ):
        marker_trace = _forecast_marker_trace(
            x=context.current_label,
            y=value,
            color=_ALL_TASKS_TOTAL_COLOR,
            name=f"All Projects ({'forecast' if forecast else 'so far'})",
            legendgroup="all-projects-total",
            hovertemplate=(
                f"<b>All projects</b><br>{label}{total_suffix}: "
                f"%{{y:.0f}}{task_suffix}<extra></extra>"
            ),
            forecast=forecast,
            marker_size=14,
            marker_opacity=0.82,
        )
        fig.add_trace(marker_trace)


def _project_series_for_mode(
    *,
    root_project: str,
    counts: pd.Series,
    values: pd.Series,
    archived_project_names: set[str],
    config: _PeriodicPlotConfig,
) -> pd.Series:
    is_archived_project = root_project in archived_project_names
    if is_archived_project:
        if config.cumulative:
            return _series_at_positive_activity_periods(values, counts)
        return _positive_activity_periods(counts)
    return _trim_to_activity_span(values.fillna(0), counts)


def _historical_part(
    series: pd.Series,
    *,
    context: _PeriodicForecastContext,
    is_archived_project: bool,
) -> pd.Series:
    if (
        is_archived_project
        or not context.show_forecast
        or context.current_label is None
    ):
        return cast(pd.Series, series)
    return cast(pd.Series, series[series.index < pd.Timestamp(context.current_label)])


def _history_totals_for_project(
    *,
    values: pd.Series,
    series: pd.Series,
    context: _PeriodicForecastContext,
    config: _PeriodicPlotConfig,
) -> list[float]:
    if context.current_label is None:
        return []
    source = (
        values.diff().fillna(values).fillna(0)
        if config.cumulative
        else series.fillna(0)
    )
    return (
        cast(pd.Series, source[source.index < pd.Timestamp(context.current_label)])
        .astype(float)
        .tolist()
    )


def _add_project_forecast_traces(
    fig: go.Figure,
    *,
    project_name: str,
    color: str,
    historical: pd.Series,
    values: pd.Series,
    project_series: pd.Series,
    actual_so_far: int,
    context: _PeriodicForecastContext,
    config: _PeriodicPlotConfig,
) -> None:
    if (
        not context.show_forecast
        or context.current_label is None
        or not context.current_start
        or not context.current_end
    ):
        return

    history_totals = _history_totals_for_project(
        values=values,
        series=project_series,
        context=context,
        config=config,
    )
    if actual_so_far <= 0 and not any(v > 0 for v in history_totals[-4:]):
        return

    forecast_total = forecast_period_total(
        actual_so_far=actual_so_far,
        history_totals=history_totals,
        period_start=context.current_start,
        period_end=context.current_end,
        as_of=context.as_of,
    )
    base = (
        float(historical.iloc[-1])
        if config.cumulative and not historical.empty
        else 0.0
    )
    actual_value = (
        int(round(base + actual_so_far)) if config.cumulative else actual_so_far
    )
    forecast_value = (
        int(round(base + forecast_total)) if config.cumulative else forecast_total
    )

    if not historical.empty:
        fig.add_trace(
            go.Scatter(
                x=[historical.index[-1], context.current_label],
                y=[float(historical.iloc[-1]), float(forecast_value)],
                mode="lines",
                line=dict(color=color, dash="dash", width=2),
                name=f"{project_name} (forecast line)",
                legendgroup=project_name,
                showlegend=False,
                hoverinfo="skip",
            )
        )

    label_suffix = " (cumulative)" if config.cumulative else ""
    task_suffix = "" if config.cumulative else " tasks"
    for label, value, forecast in (
        ("So far", actual_value, False),
        ("Forecast", forecast_value, True),
    ):
        fig.add_trace(
            _forecast_marker_trace(
                x=context.current_label,
                y=value,
                color=color,
                name=f"{project_name} ({'forecast' if forecast else 'so far'})",
                legendgroup=project_name,
                hovertemplate=(
                    f"<b>{project_name}</b><br>{label}{label_suffix}: "
                    f"%{{y}}{task_suffix}<extra></extra>"
                ),
                forecast=forecast,
            )
        )


def _completed_tasks_periodically_figure(
    df: pd.DataFrame,
    beg_date: datetime,
    end_date: datetime,
    granularity: str,
    project_colors: dict[str, str],
    include_total_overlay: bool = True,
    visibility_beg_date: datetime | None = None,
    visibility_end_date: datetime | None = None,
    always_visible_projects: set[str] | None = None,
    config: _PeriodicPlotConfig = _PERIODIC_CONFIG,
) -> go.Figure:
    df_completed, df_weekly_per_project = _prepare_completed_periodic_frame(
        df,
        beg_date=beg_date,
        end_date=end_date,
        granularity=granularity,
        visibility_beg_date=visibility_beg_date,
        visibility_end_date=visibility_end_date,
        always_visible_projects=always_visible_projects,
    )
    df_periodic_counts = cast(pd.DataFrame, df_weekly_per_project.copy())
    df_values = df_weekly_per_project
    if config.cumulative:
        df_values = cast(pd.DataFrame, df_values.cumsum().ffill().fillna(0))
    if config.cumulative and not df_values.empty and len(df_values.columns):
        min_date = cast(pd.Timestamp, df_values.index.min()) - pd.Timedelta(
            days=7 if "W" in granularity else 14
        )
        df_values.loc[min_date] = 0
        df_values = df_values.sort_index()

    forecast_context = _build_periodic_forecast_context(
        end_date=end_date,
        granularity=granularity,
        period_index=df_values.index,
    )
    current_counts = _current_period_project_counts(
        df_completed, context=forecast_context
    )
    fig = go.Figure()
    archived_project_names = always_visible_projects or set()

    for root_project in df_values.columns:
        root_project_name = str(root_project)
        project_counts = cast(pd.Series, df_periodic_counts[root_project])
        is_archived_project = root_project_name in archived_project_names
        project_values = cast(pd.Series, df_values[root_project]).ffill().fillna(0)
        project_series = _project_series_for_mode(
            root_project=root_project_name,
            counts=project_counts,
            values=project_values,
            archived_project_names=archived_project_names,
            config=config,
        )
        if project_series.empty:
            continue
        color = project_colors.get(root_project_name, "#808080")
        historical = _historical_part(
            project_series,
            context=forecast_context,
            is_archived_project=is_archived_project,
        )

        if not historical.empty:
            fig.add_trace(
                go.Scatter(
                    x=historical.index,
                    y=historical,
                    name=root_project_name,
                    legendgroup=root_project_name,
                    line_shape=config.line_shape,
                    mode="lines+markers",
                    line=dict(color=color),
                )
            )

        if not is_archived_project:
            _add_project_forecast_traces(
                fig,
                project_name=root_project_name,
                color=color,
                historical=historical,
                values=project_values,
                project_series=project_series,
                actual_so_far=int(current_counts.get(root_project_name, 0)),
                context=forecast_context,
                config=config,
            )

    if include_total_overlay:
        _add_total_overlay_traces(
            fig,
            total_series=_total_tasks_series(df_values),
            context=forecast_context,
            total_actual_so_far=sum(current_counts.values()),
            config=config,
        )

    fig.update_xaxes(
        title_text="Date",
        title_standoff=14,
        type="date",
        showline=True,
        showgrid=True,
    )
    fig.update_layout(
        title_text=f"{config.title_prefix}{granularity} Completed Tasks Per Project",
        yaxis=dict(
            title=dict(text=config.yaxis_title, standoff=16),
            autorange=True,
            fixedrange=False,
            rangemode="tozero",
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.03,
            xanchor="left",
            x=0.0,
            tracegroupgap=12,
            bgcolor="rgba(17,19,24,0.72)",
            font=dict(size=11, color="#e6e6e6"),
        ),
        margin=dict(l=56, r=86, t=84, b=60),
    )
    return apply_dashboard_axes(fig)


def plot_completed_tasks_periodically(
    df: pd.DataFrame,
    beg_date: datetime,
    end_date: datetime,
    granularity: str,
    project_colors: dict[str, str],
    include_total_overlay: bool = True,
    visibility_beg_date: datetime | None = None,
    visibility_end_date: datetime | None = None,
    always_visible_projects: set[str] | None = None,
) -> go.Figure:
    return _completed_tasks_periodically_figure(
        df,
        beg_date,
        end_date,
        granularity,
        project_colors,
        include_total_overlay,
        visibility_beg_date,
        visibility_end_date,
        always_visible_projects,
        config=_PERIODIC_CONFIG,
    )


def cumsum_completed_tasks_periodically(
    df: pd.DataFrame,
    beg_date: datetime,
    end_date: datetime,
    granularity: str,
    project_colors: dict[str, str],
    include_total_overlay: bool = True,
    visibility_beg_date: datetime | None = None,
    visibility_end_date: datetime | None = None,
    always_visible_projects: set[str] | None = None,
) -> go.Figure:
    return _completed_tasks_periodically_figure(
        df,
        beg_date,
        end_date,
        granularity,
        project_colors,
        include_total_overlay,
        visibility_beg_date,
        visibility_end_date,
        always_visible_projects,
        config=_CUMULATIVE_CONFIG,
    )
