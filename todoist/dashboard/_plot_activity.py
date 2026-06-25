from datetime import datetime
from typing import cast

import pandas as pd
import plotly.graph_objects as go

from todoist.dashboard._plot_common import apply_dashboard_axes

_BACKGROUND_COLOR = "#111318"
_TEXT_COLOR = "#ffffff"
_MUTED_TEXT_COLOR = "#e6e6e6"
_AXIS_LINE_COLOR = "rgba(255,255,255,0.24)"
_HOVER_LABEL = dict(
    bgcolor="#1e1e1e", bordercolor="#444", font=dict(color=_TEXT_COLOR)
)
_TITLE_FONT = dict(size=18, family="Arial, sans-serif", color=_TEXT_COLOR)
_DAY_NAMES = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]
_ACTIVITY_COLORS = {
    "added": "#2E8B57",
    "completed": "#4169E1",
    "updated": "#FF8C00",
    "deleted": "#DC143C",
    "rescheduled": "#9370DB",
}
_ACTIVITY_TYPES = list(_ACTIVITY_COLORS)


def _title(text: str) -> dict[str, object]:
    return {
        "text": text,
        "x": 0.5,
        "xanchor": "center",
        "font": _TITLE_FONT,
    }


def _axis(title: str, *, font_size: int = 12) -> dict[str, object]:
    return {
        "title": {"text": title, "font": {"size": 14, "color": _TEXT_COLOR}},
        "showline": True,
        "linewidth": 1,
        "linecolor": _AXIS_LINE_COLOR,
        "tickfont": {"size": font_size, "color": _MUTED_TEXT_COLOR},
    }


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    hex_color = hex_color.lstrip("#")
    red = int(hex_color[0:2], 16)
    green = int(hex_color[2:4], 16)
    blue = int(hex_color[4:6], 16)
    return f"rgba({red},{green},{blue},{alpha})"


def plot_events_over_time(
    df: pd.DataFrame, beg_date: datetime, end_date: datetime, _granularity: str
) -> go.Figure:
    """
    Plot event volume as a stacked rolling-average area chart by activity type.
    """

    df_filtered = df.loc[beg_date:end_date].copy()
    date_range = pd.date_range(start=beg_date.date(), end=end_date.date(), freq="D")
    daily_counts = (
        df_filtered.groupby([pd.Grouper(freq="D"), "type"])
        .size()
        .unstack(fill_value=0)
        .reindex(index=date_range, columns=_ACTIVITY_TYPES, fill_value=0)
    )
    rolling_averages = cast(
        pd.DataFrame, daily_counts.rolling(window=7, min_periods=1).mean()
    )

    fig = go.Figure()
    for index, activity_type in enumerate(_ACTIVITY_TYPES):
        if activity_type not in rolling_averages.columns:
            continue
        fig.add_trace(
            go.Scatter(
                x=rolling_averages.index,
                y=rolling_averages[activity_type],
                mode="lines",
                name=activity_type.capitalize(),
                fill="tonexty" if index > 0 else "tozeroy",
                line=dict(
                    color=_ACTIVITY_COLORS.get(activity_type, "#808080"),
                    width=2,
                ),
                fillcolor=_hex_to_rgba(
                    _ACTIVITY_COLORS.get(activity_type, "#9e9e9e"), 0.28
                ),
                hovertemplate=(
                    f"<b>{activity_type.capitalize()}</b><br>"
                    + "Date: %{x}<br>"
                    + "Average: %{y:.1f} events/day<br>"
                    + "<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        template="plotly_dark",
        title=_title("Events Over Time (7-Day Rolling Average by Activity Type)"),
        xaxis=_axis("Date"),
        yaxis=_axis("Average Number of Events per Day"),
        plot_bgcolor=_BACKGROUND_COLOR,
        paper_bgcolor=_BACKGROUND_COLOR,
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
            "font": {"size": 12, "color": _MUTED_TEXT_COLOR},
        },
        margin=dict(l=50, r=50, t=80, b=50),
        hovermode="x unified",
        hoverlabel=_HOVER_LABEL,
    )
    return apply_dashboard_axes(fig)


def plot_heatmap_of_events_by_day_and_hour(
    df: pd.DataFrame, beg_date: datetime, end_date: datetime
) -> go.Figure:
    """Plot weekly/hourly activity density within the selected date range."""

    df_filtered = df.loc[beg_date:end_date].copy()
    if df_filtered.empty:
        fig = go.Figure()
        fig.update_layout(
            template="plotly_dark",
            title=_title("Heatmap of Events by Day and Hour (No Data)"),
            paper_bgcolor=_BACKGROUND_COLOR,
            plot_bgcolor=_BACKGROUND_COLOR,
        )
        return fig

    dt_series = pd.to_datetime(df_filtered.index).to_series(index=df_filtered.index)
    df_filtered["hour"] = dt_series.dt.hour.astype(int)
    df_filtered["day_of_week"] = dt_series.dt.dayofweek.astype(int)

    heatmap_data = (
        df_filtered.groupby(["day_of_week", "hour"]).size().unstack(fill_value=0)
    )
    all_hours = list(range(24))
    all_days = list(range(7))
    heatmap_data = heatmap_data.reindex(index=all_days, columns=all_hours, fill_value=0)

    nonzero_counts = heatmap_data.stack()
    nonzero_counts = nonzero_counts[nonzero_counts > 0]
    zmax = (
        1.0 if nonzero_counts.empty else max(1.0, float(nonzero_counts.quantile(0.95)))
    )

    total_events = heatmap_data.sum().sum()
    hover_text = []
    for day_idx in range(7):
        hover_row = []
        for hour in range(24):
            count = heatmap_data.iloc[day_idx, hour]
            percentage = (count / total_events * 100) if total_events > 0 else 0
            if hour == 0:
                hour_str = "12 AM (midnight)"
            elif hour == 12:
                hour_str = "12 PM (noon)"
            elif hour < 12:
                hour_str = f"{hour} AM"
            else:
                hour_str = f"{hour - 12} PM"
            hover_row.append(
                (
                    f"<b>{_DAY_NAMES[day_idx]}</b><br>"
                    f"Time: {hour_str}<br>"
                    f"Events: {int(count)}<br>"
                    f"Percentage: {percentage:.1f}%<br>"
                    f"<extra></extra>"
                )
            )
        hover_text.append(hover_row)

    fig = go.Figure(
        data=go.Heatmap(
            z=heatmap_data.values,
            x=all_hours,
            y=_DAY_NAMES,
            zmin=0,
            zmax=zmax,
            colorscale=[
                [0.0, "#0d1b2a"],
                [0.1, "#1b263b"],
                [0.2, "#2d4f7c"],
                [0.3, "#415a77"],
                [0.4, "#778da9"],
                [0.5, "#a8dadc"],
                [0.6, "#f1faee"],
                [0.7, "#ffeaa7"],
                [0.8, "#fdcb6e"],
                [0.9, "#e17055"],
                [1.0, "#d63031"],
            ],
            hovertemplate="%{customdata}<extra></extra>",
            customdata=hover_text,
            showscale=True,
            colorbar=dict(
                title=dict(text="Events Count", font=dict(size=14, color=_TEXT_COLOR)),
                tickfont=dict(size=12, color=_MUTED_TEXT_COLOR),
                bgcolor=_BACKGROUND_COLOR,
                bordercolor=_AXIS_LINE_COLOR,
                borderwidth=1,
            ),
        )
    )
    fig.update_layout(
        template="plotly_dark",
        title=_title("Activity Heatmap: Events by Day and Hour"),
        xaxis={
            **_axis("Hour of Day", font_size=11),
            "tickmode": "array",
            "tickvals": list(range(0, 24, 2)),
            "ticktext": [f"{hour}:00" for hour in range(0, 24, 2)],
        },
        yaxis=_axis("Day of Week", font_size=11),
        plot_bgcolor=_BACKGROUND_COLOR,
        paper_bgcolor=_BACKGROUND_COLOR,
        margin=dict(l=80, r=100, t=80, b=60),
        font=dict(color=_TEXT_COLOR),
        hoverlabel={**_HOVER_LABEL, "font": dict(color=_TEXT_COLOR, size=12)},
    )

    if total_events > 0:
        peak_day, peak_hour = heatmap_data.stack().idxmax()
        peak_count = heatmap_data.iloc[peak_day, peak_hour]
        if peak_count > 0:
            fig.add_annotation(
                x=peak_hour,
                y=_DAY_NAMES[peak_day],
                text=f"Peak: {int(peak_count)}",
                showarrow=True,
                arrowhead=2,
                arrowsize=1,
                arrowwidth=2,
                arrowcolor="#ffffff",
                font=dict(color="#ffffff", size=10),
                bgcolor="rgba(0,0,0,0.7)",
                bordercolor="#ffffff",
                borderwidth=1,
            )
    return apply_dashboard_axes(fig)
