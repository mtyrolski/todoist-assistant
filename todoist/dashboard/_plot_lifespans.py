from typing import Any, cast

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from loguru import logger

from todoist.dashboard._plot_common import (
    _DASHBOARD_GRID_COLOR,
    apply_dashboard_axes,
)

_RECENCY_WEIGHT_HALFLIFE_DAYS = 180.0
_MIN_RECENCY_WEIGHT = 0.2
_TIME_TICKS = (
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
)
_DURATION_UNITS = (
    ("w", 7 * 24 * 60 * 60),
    ("d", 24 * 60 * 60),
    ("h", 60 * 60),
    ("m", 60),
    ("s", 1),
)
_AXIS_UNITS = ((60, 1.0, "sec"), (3600, 60.0, "min"), (86400, 3600.0, "hr"))
_HIGHLIGHT_SPECS = (
    ("Fastest 15%", "#00E5FF"),
    ("Slowest 15%", "#FF4F9A"),
)


def plot_task_lifespans(df: pd.DataFrame) -> go.Figure:
    """Plot distribution of task completion lifespans with sensible fallbacks."""

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

        xaxis_options: dict[str, Any] = {
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
        return apply_dashboard_axes(fig)

    def _empty_figure(message: str) -> go.Figure:
        fig = go.Figure()
        return _apply_common_layout(
            fig, title_text=f"Task Lifespans ({message})", x_title="Time to Completion"
        )

    def _build_time_ticks(
        *,
        min_seconds: float,
        max_seconds: float,
        axis_unit_seconds: float,
    ) -> tuple[list[float], list[str]]:
        import math

        max_ticks = 9
        lower = min_seconds / 2.0
        upper = max_seconds * 1.5
        selected = [(sec, label) for sec, label in _TIME_TICKS if lower <= sec <= upper]
        if not selected:
            selected = [(sec, label) for sec, label in _TIME_TICKS if sec <= upper]
            if selected:
                selected = selected[-max_ticks:]
        if not selected:
            target = max(min_seconds, 1e-6)
            selected = [
                min(
                    _TIME_TICKS,
                    key=lambda item: abs(math.log10(item[0]) - math.log10(target)),
                )
            ]
        if len(selected) > max_ticks:
            step = max(1, math.ceil((len(selected) - 1) / (max_ticks - 1)))
            trimmed = [selected[0]]
            trimmed.extend(selected[1:-1:step])
            trimmed.append(selected[-1])
            selected = trimmed
            if len(selected) > max_ticks:
                selected = selected[: max_ticks - 1] + [selected[-1]]
        tickvals = [sec / axis_unit_seconds for sec, _ in selected]
        ticktext = [label for _, label in selected]
        return tickvals, ticktext

    def _hex_to_rgba(hex_color: str, alpha: float) -> str:
        hex_color = hex_color.lstrip("#")
        red = int(hex_color[0:2], 16)
        green = int(hex_color[2:4], 16)
        blue = int(hex_color[4:6], 16)
        return f"rgba({red},{green},{blue},{alpha})"

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

    def _smooth_log_density(
        log_samples: np.ndarray,
        log_bounds: np.ndarray,
        sample_weights: np.ndarray,
    ) -> np.ndarray:
        weight_sum = float(sample_weights.sum())
        weighted_mean = float(np.average(log_samples, weights=sample_weights))
        sample_std = float(
            np.sqrt(
                np.average(
                    np.square(log_samples - weighted_mean),
                    weights=sample_weights,
                )
            )
        )
        effective_count = float(np.square(weight_sum) / np.square(sample_weights).sum())
        bandwidth = sample_std * effective_count ** (-1 / 5)
        if not np.isfinite(bandwidth) or bandwidth <= 0:
            bandwidth = max(float(np.ptp(log_bounds)) / 64, 0.05)

        scaled_offsets = log_bounds[:, np.newaxis] - log_samples[np.newaxis, :]
        scaled_offsets = scaled_offsets / bandwidth
        kernel_values = np.exp(-0.5 * np.square(scaled_offsets))
        weighted_kernels = kernel_values * sample_weights[np.newaxis, :]
        return weighted_kernels.sum(axis=1) / (
            weight_sum * bandwidth * np.sqrt(2 * np.pi)
        )

    def _completion_recency_weights(completed_at: pd.Series) -> np.ndarray:
        latest_completion = completed_at.max()
        ages_days = (
            (latest_completion - completed_at).dt.total_seconds() / (24 * 60 * 60)
        ).to_numpy(dtype=float)
        raw_weights = np.power(0.5, ages_days / _RECENCY_WEIGHT_HALFLIFE_DAYS)
        raw_weights = np.clip(raw_weights, _MIN_RECENCY_WEIGHT, 1.0)
        weight_sum = float(raw_weights.sum())
        if not np.isfinite(weight_sum) or weight_sum <= 0:
            return np.ones_like(raw_weights, dtype=float)
        return raw_weights * (raw_weights.size / weight_sum)

    def _weighted_percentile(
        values: np.ndarray,
        weights: np.ndarray,
        percentile: float,
    ) -> float:
        if values.size == 0:
            return float("nan")
        order = np.argsort(values)
        ordered_values = values[order]
        ordered_weights = weights[order]
        cumulative_weights = np.cumsum(ordered_weights)
        cutoff = (percentile / 100.0) * float(ordered_weights.sum())
        return float(
            ordered_values[
                int(np.searchsorted(cumulative_weights, cutoff, side="left"))
            ]
        )

    def _format_duration_compact(seconds: float) -> str:
        total = int(round(max(0.0, seconds)))
        parts: list[str] = []
        for suffix, unit_seconds in _DURATION_UNITS:
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
            if any(
                abs(math.log10(value) - math.log10(existing)) < 0.03
                for existing in tickvals
                if existing > 0
            ):
                continue
            pairs.append((value, label))
        pairs.sort(key=lambda item: item[0])
        return [value for value, _ in pairs], [label for _, label in pairs]

    if "type" not in df.columns:
        logger.error("DataFrame missing required 'type' column")
        return _empty_figure("Invalid data structure")

    identifier = (
        "task_id"
        if "task_id" in df.columns
        else "parent_item_id"
        if "parent_item_id" in df.columns
        else None
    )
    if identifier is None:
        logger.error(
            "DataFrame missing task identifier column ('task_id' or 'parent_item_id')"
        )
        return _empty_figure("Invalid data structure")

    event_mask = cast(pd.Series, df["type"].isin(["added", "completed"]))
    if not event_mask.any():
        logger.info("No added/completed events available for lifespan plot")
        return _empty_figure("No Task Events")

    events = df.loc[event_mask, [identifier, "type"]].copy()
    events["timestamp"] = pd.to_datetime(df.index[event_mask])
    added_times = (
        events.loc[events["type"] == "added"].groupby(identifier)["timestamp"].min()
    )
    completed_times = (
        events.loc[events["type"] == "completed"].groupby(identifier)["timestamp"].max()
    )

    common_ids = added_times.index.intersection(completed_times.index)
    if common_ids.empty:
        logger.info("No tasks have both added and completed events")
        return _empty_figure("No Tasks with Both Added and Completed Events")

    lifespan_frame = pd.DataFrame(
        {
            "added_at": added_times.loc[common_ids],
            "completed_at": completed_times.loc[common_ids],
        }
    )
    lifespan_frame["duration_seconds"] = (
        lifespan_frame["completed_at"] - lifespan_frame["added_at"]
    ).dt.total_seconds()
    lifespan_frame = cast(
        pd.DataFrame, lifespan_frame[lifespan_frame["duration_seconds"] > 0].copy()
    )
    durations = cast(pd.Series, lifespan_frame["duration_seconds"]).to_numpy(
        dtype=float
    )
    if durations.size == 0:
        logger.info("All computed durations are non-positive; nothing to plot")
        return _empty_figure("No valid durations")
    recency_weights = _completion_recency_weights(
        cast(pd.Series, lifespan_frame["completed_at"])
    )

    max_duration = float(durations.max())
    axis_unit_seconds, unit_label = next(
        (
            (unit_seconds, label)
            for limit_seconds, unit_seconds, label in _AXIS_UNITS
            if max_duration < limit_seconds
        ),
        (86400.0, "days"),
    )
    durations_converted = durations / axis_unit_seconds
    log_durations = np.log10(durations_converted)
    total_count = int(durations_converted.size)
    percentile_low = _weighted_percentile(durations_converted, recency_weights, 15)
    percentile_high = _weighted_percentile(durations_converted, recency_weights, 85)
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
    if total_count >= 2 and not np.isclose(log_durations.var(), 0.0):
        log_bounds = np.linspace(min_log - pad, max_log + pad, 512)
        x_values = np.power(10.0, log_bounds)
        densities = _smooth_log_density(
            log_durations,
            log_bounds,
            recency_weights,
        )
        integral = float(np.trapezoid(densities, x_values))
        if np.isfinite(integral) and integral > 0:
            densities = densities * (float(recency_weights.sum()) / integral)
            x_min = float(x_values.min())
            x_max = float(x_values.max())
            highlight_low = float(np.clip(highlight_low, x_min, x_max))
            highlight_high = float(np.clip(highlight_high, x_min, x_max))
            for (name, color), low, high in zip(
                _HIGHLIGHT_SPECS,
                (None, highlight_high),
                (highlight_low, None),
                strict=True,
            ):
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
            for x_value, (_, color) in zip(
                (highlight_low, highlight_high), _HIGHLIGHT_SPECS, strict=True
            ):
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
                    name="Recency-weighted frequency",
                    hovertemplate="Duration: %{x:.4g} "
                    + unit_label
                    + "<br>Frequency: %{y:.2f}<extra></extra>",
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
    tickvals, ticktext = _build_time_ticks(
        min_seconds=float(max(durations.min(), plot_min * axis_unit_seconds)),
        max_seconds=float(min(durations.max(), plot_max * axis_unit_seconds)),
        axis_unit_seconds=axis_unit_seconds,
    )
    tickvals, ticktext = _merge_ticks(
        tickvals,
        ticktext,
        [
            (
                highlight_low,
                f"15%<br>{_format_duration_compact(highlight_low * axis_unit_seconds)}",
            ),
            (
                highlight_high,
                f"85%<br>{_format_duration_compact(highlight_high * axis_unit_seconds)}",
            ),
        ],
    )
    return _apply_common_layout(
        fig,
        title_text="Task Lifespans: Time to Completion",
        x_title="",
        tickvals=tickvals,
        ticktext=ticktext,
        x_range=[min_log - pad, max_log + pad] if total_count >= 2 else None,
    )
