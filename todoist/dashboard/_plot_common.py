from datetime import datetime
from typing import Any

import pandas as pd
import plotly.graph_objects as go

_DASHBOARD_GRID_COLOR = "rgba(255,255,255,0.03)"
_DASHBOARD_AXIS_LINE_COLOR = "rgba(255,255,255,0.18)"
_ALL_TASKS_TOTAL_COLOR = "#F4D35E"
_ALL_TASKS_TOTAL_ACCENT = "#EE964B"


def apply_dashboard_axes(fig: go.Figure) -> go.Figure:
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


def period_grouper(freq: str) -> Any:
    # Pandas supports `label` and `closed`, but type stubs frequently lag behind.
    return pd.Grouper(freq=freq, label="right", closed="right")  # type: ignore[call-arg]


def decayed_mean(values: list[float], *, decay: float = 0.75) -> float:
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


def forecast_period_total(
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

    baseline = decayed_mean(history_totals[-8:], decay=0.75) if history_totals else 0.0
    if fraction <= 0.0:
        return max(int(round(baseline)), int(actual_so_far))

    effective_fraction = max(0.25, fraction)
    pace_projection = float(actual_so_far) / effective_fraction
    weight = min(0.85, max(0.15, fraction))
    forecast = (1.0 - weight) * baseline + weight * pace_projection
    return max(int(actual_so_far), int(round(forecast)))
