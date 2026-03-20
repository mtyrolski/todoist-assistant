from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

import pandas as pd
import plotly.graph_objects as go

from todoist.dashboard._plot_common import (
    _ALL_TASKS_TOTAL_ACCENT,
    _ALL_TASKS_TOTAL_COLOR,
    apply_dashboard_axes,
    forecast_period_total,
    period_grouper,
)


def _current_period_label(
    end_date: datetime, granularity: str, index: pd.DatetimeIndex | None = None
) -> datetime | None:
    """Return the resample label that contains ``end_date``."""

    fallback: datetime | None = None
    try:
        period = cast(Any, pd.Period(end_date, freq=granularity))
        period_end = period.end_time
        if not pd.isna(period_end):
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


def _drop_projects_without_period_activity(df_periodic: pd.DataFrame) -> pd.DataFrame:
    if df_periodic.empty or not len(df_periodic.columns):
        return df_periodic

    active_columns = [
        column
        for column in df_periodic.columns
        if float(cast(pd.Series, df_periodic[column]).fillna(0).sum()) > 0
    ]
    return cast(pd.DataFrame, df_periodic.loc[:, active_columns])


@dataclass(frozen=True)
class _PeriodicForecastContext:
    current_label: datetime | None
    current_start: datetime | None
    current_end: datetime | None
    as_of: datetime
    show_forecast: bool


def _prepare_completed_periodic_frame(
    df: pd.DataFrame,
    *,
    beg_date: datetime,
    end_date: datetime,
    granularity: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    df_completed = df[df["type"] == "completed"].loc[:end_date].copy()
    df_completed.index = pd.to_datetime(df_completed.index)
    df_periodic = cast(
        pd.DataFrame,
        df_completed.groupby([period_grouper(granularity), "root_project_name"])
        .size()
        .unstack("root_project_name")
        .sort_index(),
    )
    df_periodic = cast(pd.DataFrame, df_periodic[df_periodic.index >= beg_date])
    return df_completed, _drop_projects_without_period_activity(df_periodic)


def _period_bounds_for_granularity(
    end_date: datetime, granularity: str
) -> tuple[datetime | None, datetime | None]:
    try:
        period = cast(Any, pd.Period(end_date, freq=granularity))
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
    current_label = _current_period_label(end_date, granularity, normalized_index)
    current_start: datetime | None = None
    current_end: datetime | None = None
    if current_label is not None:
        current_start, current_end = _period_bounds_for_granularity(
            end_date, granularity
        )

    as_of = min(end_date, datetime.now())
    show_forecast = bool(
        current_label and current_start and current_end and current_label > as_of
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

    df_current = df_completed[
        (df_completed.index >= context.current_start)
        & (df_completed.index <= context.as_of)
    ]
    if df_current.empty:
        return {}
    return df_current.groupby("root_project_name").size().astype(int).to_dict()


def _total_tasks_series(df_periodic: pd.DataFrame) -> pd.Series:
    if df_periodic.empty or not len(df_periodic.columns):
        return pd.Series(dtype=float)

    totals = cast(pd.Series, df_periodic.fillna(0).sum(axis=1).astype(float))
    if float(totals.fillna(0).sum()) <= 0:
        return pd.Series(dtype=float)
    return totals


def _add_total_overlay_periodic_traces(
    fig: go.Figure,
    *,
    total_series: pd.Series,
    context: _PeriodicForecastContext,
    total_actual_so_far: int,
) -> None:
    if total_series.empty:
        return

    if context.show_forecast and context.current_label is not None:
        historical = cast(
            pd.Series, total_series[total_series.index < pd.Timestamp(context.current_label)]
        )
    else:
        historical = cast(pd.Series, total_series)

    if not historical.empty:
        fig.add_trace(
            go.Scatter(
                x=historical.index,
                y=historical.astype(float).tolist(),
                name="All Projects (total)",
                legendgroup="all-projects-total",
                line_shape="spline",
                mode="lines+markers",
                line=dict(color=_ALL_TASKS_TOTAL_COLOR, width=3),
                marker=dict(size=8, symbol="diamond", color=_ALL_TASKS_TOTAL_COLOR),
                hovertemplate="<b>All projects</b><br>%{x}: %{y:.0f} tasks<extra></extra>",
            )
        )

    if (
        not context.show_forecast
        or context.current_label is None
        or context.current_start is None
        or context.current_end is None
    ):
        return

    history_values = cast(
        pd.Series, total_series[total_series.index < pd.Timestamp(context.current_label)]
    ).fillna(0).astype(float).tolist()
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

    if not historical.empty:
        fig.add_trace(
            go.Scatter(
                x=[historical.index[-1], context.current_label],
                y=[float(historical.iloc[-1]), float(forecast_total)],
                mode="lines",
                line=dict(color=_ALL_TASKS_TOTAL_COLOR, dash="dash", width=2),
                name="All Projects (forecast line)",
                legendgroup="all-projects-total",
                showlegend=False,
                hoverinfo="skip",
            )
        )

    fig.add_trace(
        go.Scatter(
            x=[context.current_label],
            y=[float(total_actual_so_far)],
            mode="markers",
            marker=dict(
                symbol="circle-open",
                size=10,
                line=dict(width=2, color=_ALL_TASKS_TOTAL_COLOR),
            ),
            name="All Projects (so far)",
            legendgroup="all-projects-total",
            showlegend=False,
            hovertemplate="<b>All projects</b><br>So far: %{y:.0f} tasks<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[context.current_label],
            y=[float(forecast_total)],
            mode="markers",
            marker=dict(
                symbol="circle",
                size=14,
                color=_ALL_TASKS_TOTAL_ACCENT,
                opacity=0.95,
            ),
            name="All Projects (forecast)",
            legendgroup="all-projects-total",
            showlegend=False,
            hovertemplate="<b>All projects</b><br>Forecast: %{y:.0f} tasks<extra></extra>",
        )
    )


def _add_total_overlay_cumulative_traces(
    fig: go.Figure,
    *,
    total_cumulative_series: pd.Series,
    context: _PeriodicForecastContext,
    total_actual_so_far: int,
) -> None:
    if total_cumulative_series.empty:
        return

    if context.show_forecast and context.current_label is not None:
        historical = cast(
            pd.Series,
            total_cumulative_series[
                total_cumulative_series.index < pd.Timestamp(context.current_label)
            ],
        )
    else:
        historical = cast(pd.Series, total_cumulative_series)

    if not historical.empty:
        fig.add_trace(
            go.Scatter(
                x=historical.index,
                y=historical.astype(float).tolist(),
                name="All Projects (total cumulative)",
                legendgroup="all-projects-total",
                line_shape="linear",
                mode="lines+markers",
                line=dict(color=_ALL_TASKS_TOTAL_COLOR, width=3),
                marker=dict(size=8, symbol="diamond", color=_ALL_TASKS_TOTAL_COLOR),
                hovertemplate="<b>All projects</b><br>%{x}: %{y:.0f} cumulative tasks<extra></extra>",
            )
        )

    if (
        not context.show_forecast
        or context.current_label is None
        or context.current_start is None
        or context.current_end is None
    ):
        return

    period_totals = total_cumulative_series.diff().fillna(total_cumulative_series).fillna(0)
    history_values = cast(
        pd.Series, period_totals[period_totals.index < pd.Timestamp(context.current_label)]
    ).astype(float).tolist()
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
    base_total = float(historical.iloc[-1]) if not historical.empty else 0.0
    actual_cumulative = float(base_total + total_actual_so_far)
    forecast_cumulative = float(base_total + forecast_total)

    if not historical.empty:
        fig.add_trace(
            go.Scatter(
                x=[historical.index[-1], context.current_label],
                y=[float(base_total), float(forecast_cumulative)],
                mode="lines",
                line=dict(color=_ALL_TASKS_TOTAL_COLOR, dash="dash", width=2),
                name="All Projects (forecast line)",
                legendgroup="all-projects-total",
                showlegend=False,
                hoverinfo="skip",
            )
        )

    fig.add_trace(
        go.Scatter(
            x=[context.current_label],
            y=[float(actual_cumulative)],
            mode="markers",
            marker=dict(
                symbol="circle-open",
                size=10,
                line=dict(width=2, color=_ALL_TASKS_TOTAL_COLOR),
            ),
            name="All Projects (so far)",
            legendgroup="all-projects-total",
            showlegend=False,
            hovertemplate="<b>All projects</b><br>So far (cumulative): %{y:.0f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[context.current_label],
            y=[float(forecast_cumulative)],
            mode="markers",
            marker=dict(
                symbol="circle",
                size=14,
                color=_ALL_TASKS_TOTAL_ACCENT,
                opacity=0.95,
            ),
            name="All Projects (forecast)",
            legendgroup="all-projects-total",
            showlegend=False,
            hovertemplate="<b>All projects</b><br>Forecast (cumulative): %{y:.0f}<extra></extra>",
        )
    )


def plot_completed_tasks_periodically(
    df: pd.DataFrame,
    beg_date: datetime,
    end_date: datetime,
    granularity: str,
    project_colors: dict[str, str],
    include_total_overlay: bool = True,
) -> go.Figure:
    df_completed, df_weekly_per_project = _prepare_completed_periodic_frame(
        df,
        beg_date=beg_date,
        end_date=end_date,
        granularity=granularity,
    )
    forecast_context = _build_periodic_forecast_context(
        end_date=end_date,
        granularity=granularity,
        period_index=df_weekly_per_project.index,
    )
    current_counts = _current_period_project_counts(
        df_completed, context=forecast_context
    )
    fig = go.Figure()

    for root_project in df_weekly_per_project.columns:
        root_project_name = str(root_project)
        project_series = cast(pd.Series, df_weekly_per_project[root_project]).fillna(0)
        color = project_colors.get(root_project_name, "#808080")

        if forecast_context.show_forecast and forecast_context.current_label is not None:
            historical = cast(
                pd.Series,
                project_series[
                    project_series.index < pd.Timestamp(forecast_context.current_label)
                ],
            )
        else:
            historical = cast(pd.Series, project_series)

        if not historical.empty:
            fig.add_trace(
                go.Scatter(
                    x=historical.index,
                    y=historical,
                    name=root_project_name,
                    legendgroup=root_project_name,
                    line_shape="linear",
                    mode="lines+markers",
                    line=dict(color=color),
                )
            )

        if (
            forecast_context.show_forecast
            and forecast_context.current_label is not None
            and forecast_context.current_start
            and forecast_context.current_end
        ):
            history_source = cast(
                pd.Series,
                project_series[
                    project_series.index < pd.Timestamp(forecast_context.current_label)
                ],
            )
            history_totals = history_source.fillna(0).astype(float).tolist()
            actual_so_far = int(current_counts.get(root_project_name, 0))
            recently_active = actual_so_far > 0 or any(v > 0 for v in history_totals[-4:])
            if not recently_active:
                continue

            forecast_total = forecast_period_total(
                actual_so_far=actual_so_far,
                history_totals=history_totals,
                period_start=forecast_context.current_start,
                period_end=forecast_context.current_end,
                as_of=forecast_context.as_of,
            )

            if not historical.empty:
                fig.add_trace(
                    go.Scatter(
                        x=[historical.index[-1], forecast_context.current_label],
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
                    x=[forecast_context.current_label],
                    y=[actual_so_far],
                    mode="markers",
                    marker=dict(
                        symbol="circle-open", size=10, line=dict(width=2, color=color)
                    ),
                    name=f"{root_project_name} (so far)",
                    legendgroup=root_project_name,
                    showlegend=False,
                    hovertemplate=f"<b>{root_project_name}</b><br>So far: %{{y}} tasks<extra></extra>",
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=[forecast_context.current_label],
                    y=[forecast_total],
                    mode="markers",
                    marker=dict(symbol="circle", size=16, color=color, opacity=0.92),
                    name=f"{root_project_name} (forecast)",
                    legendgroup=root_project_name,
                    showlegend=False,
                    hovertemplate=f"<b>{root_project_name}</b><br>Forecast: %{{y}} tasks<extra></extra>",
                )
            )

    if include_total_overlay:
        _add_total_overlay_periodic_traces(
            fig,
            total_series=_total_tasks_series(df_weekly_per_project),
            context=forecast_context,
            total_actual_so_far=sum(current_counts.values()),
        )

    fig.update_xaxes(
        title_text="Date",
        title_standoff=14,
        type="date",
        showline=True,
        showgrid=True,
    )
    fig.update_layout(
        title_text=f"{granularity} Completed Tasks Per Project",
        yaxis=dict(
            title=dict(text="Completed Tasks per Project", standoff=16),
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


def cumsum_completed_tasks_periodically(
    df: pd.DataFrame,
    beg_date: datetime,
    end_date: datetime,
    granularity: str,
    project_colors: dict[str, str],
    include_total_overlay: bool = True,
) -> go.Figure:
    df_completed, df_weekly_per_project = _prepare_completed_periodic_frame(
        df,
        beg_date=beg_date,
        end_date=end_date,
        granularity=granularity,
    )
    df_weekly_per_project = df_weekly_per_project.cumsum()
    if not df_weekly_per_project.empty and len(df_weekly_per_project.columns):
        min_date = cast(pd.Timestamp, df_weekly_per_project.index.min()) - pd.Timedelta(
            days=7 if "W" in granularity else 14
        )
        df_weekly_per_project.loc[min_date] = 0
        df_weekly_per_project = df_weekly_per_project.sort_index()

    forecast_context = _build_periodic_forecast_context(
        end_date=end_date,
        granularity=granularity,
        period_index=df_weekly_per_project.index,
    )
    current_counts = _current_period_project_counts(
        df_completed, context=forecast_context
    )
    fig = go.Figure()

    for root_project in df_weekly_per_project.columns:
        root_project_name = str(root_project)
        project_series = (
            cast(pd.Series, df_weekly_per_project[root_project]).ffill().fillna(0)
        )
        color = project_colors.get(root_project_name, "#808080")

        if forecast_context.show_forecast and forecast_context.current_label is not None:
            historical = cast(
                pd.Series,
                project_series[
                    project_series.index < pd.Timestamp(forecast_context.current_label)
                ],
            )
        else:
            historical = cast(pd.Series, project_series)

        if not historical.empty:
            fig.add_trace(
                go.Scatter(
                    x=historical.index,
                    y=historical,
                    name=root_project_name,
                    legendgroup=root_project_name,
                    line_shape="linear",
                    mode="lines+markers",
                    line=dict(color=color),
                )
            )

        if (
            forecast_context.show_forecast
            and forecast_context.current_label is not None
            and forecast_context.current_start
            and forecast_context.current_end
        ):
            base_series = cast(pd.Series, df_weekly_per_project[root_project])
            history_totals = base_series.diff().fillna(base_series).fillna(0)
            history_totals = (
                history_totals[
                    history_totals.index < pd.Timestamp(forecast_context.current_label)
                ]
                .astype(float)
                .tolist()
            )
            actual_so_far = int(current_counts.get(root_project_name, 0))
            recently_active = actual_so_far > 0 or any(v > 0 for v in history_totals[-4:])
            if not recently_active:
                continue

            forecast_total = forecast_period_total(
                actual_so_far=actual_so_far,
                history_totals=history_totals,
                period_start=forecast_context.current_start,
                period_end=forecast_context.current_end,
                as_of=forecast_context.as_of,
            )
            base = float(historical.iloc[-1]) if not historical.empty else 0.0
            actual_cumsum = int(round(base + actual_so_far))
            forecast_cumsum = int(round(base + forecast_total))

            if not historical.empty:
                fig.add_trace(
                    go.Scatter(
                        x=[historical.index[-1], forecast_context.current_label],
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
                    x=[forecast_context.current_label],
                    y=[actual_cumsum],
                    mode="markers",
                    marker=dict(
                        symbol="circle-open", size=10, line=dict(width=2, color=color)
                    ),
                    name=f"{root_project_name} (so far)",
                    legendgroup=root_project_name,
                    showlegend=False,
                    hovertemplate=f"<b>{root_project_name}</b><br>So far (cumulative): %{{y}}<extra></extra>",
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=[forecast_context.current_label],
                    y=[forecast_cumsum],
                    mode="markers",
                    marker=dict(symbol="circle", size=16, color=color, opacity=0.92),
                    name=f"{root_project_name} (forecast)",
                    legendgroup=root_project_name,
                    showlegend=False,
                    hovertemplate=f"<b>{root_project_name}</b><br>Forecast (cumulative): %{{y}}<extra></extra>",
                )
            )

    if include_total_overlay:
        _add_total_overlay_cumulative_traces(
            fig,
            total_cumulative_series=_total_tasks_series(df_weekly_per_project),
            context=forecast_context,
            total_actual_so_far=sum(current_counts.values()),
        )

    fig.update_xaxes(
        title_text="Date",
        title_standoff=14,
        type="date",
        showline=True,
        showgrid=True,
    )
    fig.update_layout(
        title_text=f"Cumulative {granularity} Completed Tasks Per Project",
        yaxis=dict(
            title=dict(text="Cumulative Tasks per Project", standoff=16),
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
