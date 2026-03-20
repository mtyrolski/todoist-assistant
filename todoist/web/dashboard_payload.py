import json
from datetime import datetime, timedelta
from typing import Any, cast

from fastapi import HTTPException
from loguru import logger
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio

from todoist.habit_tracker import summarize_tracked_habits


def normalize_activity_df(df_activity) -> pd.DataFrame:
    if not isinstance(df_activity, pd.DataFrame):
        return empty_activity_df()

    normalized = df_activity.copy()
    if normalized.empty:
        if "date" in normalized.columns:
            normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce")
            return cast(pd.DataFrame, normalized.set_index("date", drop=False))
        normalized.index = pd.to_datetime(normalized.index, errors="coerce")
        return normalized

    if "date" in normalized.columns:
        date_values = pd.to_datetime(normalized["date"], errors="coerce")
        valid_date_values = int(date_values.notna().sum())
        if not isinstance(normalized.index, pd.DatetimeIndex) or valid_date_values > 0:
            normalized["date"] = date_values
            normalized = cast(
                pd.DataFrame,
                normalized[date_values.notna()].set_index("date", drop=False),
            )
    else:
        normalized.index = pd.to_datetime(normalized.index, errors="coerce")
        normalized = cast(pd.DataFrame, normalized[~pd.isna(normalized.index)])

    if not isinstance(normalized.index, pd.DatetimeIndex):
        normalized.index = pd.to_datetime(normalized.index, errors="coerce")
        normalized = cast(pd.DataFrame, normalized[~pd.isna(normalized.index)])

    normalized_df = cast(pd.DataFrame, normalized)
    return cast(pd.DataFrame, normalized_df.sort_index())


def period_bounds(df_activity, granularity: str) -> dict[str, Any]:
    df_activity = normalize_activity_df(df_activity)
    granularity_to_timedelta = {
        "W": timedelta(weeks=1),
        "ME": timedelta(weeks=4),
        "3ME": timedelta(weeks=12),
    }
    timespan = granularity_to_timedelta[granularity]

    end_range = safe_activity_anchor(df_activity)
    beg_range = end_range - timespan
    previous_beg_range = beg_range - timespan
    previous_end_range = end_range - timespan

    current_period_str = (
        f"{beg_range.strftime('%Y-%m-%d')} to {end_range.strftime('%Y-%m-%d')}"
    )
    previous_period_str = (
        f"{previous_beg_range.strftime('%Y-%m-%d')} "
        f"to {previous_end_range.strftime('%Y-%m-%d')}"
    )

    return {
        "beg": beg_range,
        "end": end_range,
        "prevBeg": previous_beg_range,
        "prevEnd": previous_end_range,
        "currentLabel": current_period_str,
        "previousLabel": previous_period_str,
    }


def extract_metrics_dict(df_activity, periods: dict[str, Any]) -> list[dict[str, Any]]:
    df_activity = normalize_activity_df(df_activity)

    def _get_total_events(beg_, end_) -> int:
        filtered_df = df_activity[
            (df_activity.index >= beg_) & (df_activity.index <= end_)
        ]
        return len(filtered_df)

    def _get_total_tasks_by_type(beg_, end_, task_type: str) -> int:
        filtered_df = df_activity[
            (df_activity.index >= beg_) & (df_activity.index <= end_)
        ]
        return int((filtered_df["type"] == task_type).sum())

    metric_specs: list[tuple[str, Any, bool]] = [
        ("Events", _get_total_events, False),
        (
            "Completed Tasks",
            lambda b, e: _get_total_tasks_by_type(b, e, "completed"),
            False,
        ),
        ("Added Tasks", lambda b, e: _get_total_tasks_by_type(b, e, "added"), False),
        (
            "Rescheduled Tasks",
            lambda b, e: _get_total_tasks_by_type(b, e, "rescheduled"),
            True,
        ),
    ]

    metrics: list[dict[str, Any]] = []
    for metric_name, metric_func, inverse in metric_specs:
        current_value = int(metric_func(periods["beg"], periods["end"]))
        previous_value = int(metric_func(periods["prevBeg"], periods["prevEnd"]))
        delta_percent = (
            round((current_value - previous_value) / previous_value * 100, 2)
            if previous_value
            else None
        )
        metrics.append(
            {
                "name": metric_name,
                "value": current_value,
                "deltaPercent": delta_percent,
                "inverseDelta": inverse,
            }
        )

    return metrics


def fig_to_dict(fig) -> dict[str, Any]:
    payload = pio.to_json(fig, validate=False, pretty=False)
    return json.loads(payload or "{}")


def parse_yyyy_mm_dd(value: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="Dates must use YYYY-MM-DD format"
        ) from exc


def safe_activity_anchor(df_activity) -> datetime:
    df_activity = normalize_activity_df(df_activity)
    if df_activity is None or df_activity.empty:
        return datetime.now()
    try:
        max_value = pd.to_datetime(df_activity.index).max()
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug(f"Failed to resolve activity anchor; defaulting to now: {exc}")
        return datetime.now()
    if max_value is None or bool(pd.isna(cast(Any, max_value))):
        return datetime.now()
    if isinstance(max_value, pd.Timestamp):
        return max_value.to_pydatetime(warn=False)
    if isinstance(max_value, datetime):
        return max_value
    try:
        return datetime.fromisoformat(str(max_value))
    except ValueError:
        return datetime.now()


def empty_activity_df() -> pd.DataFrame:
    df = pd.DataFrame(
        columns=pd.Index(
            [
                "id",
                "title",
                "type",
                "parent_project_id",
                "parent_project_name",
                "root_project_id",
                "root_project_name",
                "parent_item_id",
                "task_id",
                "date",
            ]
        )
    )
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")


def compute_plot_range(
    df_activity,
    *,
    weeks: int,
    beg: str | None,
    end: str | None,
) -> tuple[datetime, datetime]:
    df_activity = normalize_activity_df(df_activity)
    if (beg is None) ^ (end is None):
        raise HTTPException(
            status_code=400, detail="Provide both beg and end, or neither"
        )

    if beg is not None and end is not None:
        beg_dt = parse_yyyy_mm_dd(beg)
        end_dt = parse_yyyy_mm_dd(end) + timedelta(days=1)
        if end_dt <= beg_dt:
            raise HTTPException(status_code=400, detail="end must be after beg")
        if (end_dt - beg_dt) > timedelta(weeks=260):
            raise HTTPException(
                status_code=400, detail="Date range must be <= 260 weeks"
            )
        return beg_dt, end_dt

    if weeks < 1 or weeks > 260:
        raise HTTPException(status_code=400, detail="weeks must be between 1 and 260")

    end_range = safe_activity_anchor(df_activity)
    beg_range = end_range - timedelta(weeks=weeks)
    return beg_range, end_range


def last_completed_week_bounds(anchor: datetime) -> tuple[datetime, datetime, str]:
    week_start = datetime.combine(
        anchor.date() - timedelta(days=anchor.weekday()), datetime.min.time()
    )
    last_week_end = week_start
    last_week_start = last_week_end - timedelta(days=7)
    label = (
        f"{last_week_start.strftime('%Y-%m-%d')} "
        f"to {(last_week_end - timedelta(days=1)).strftime('%Y-%m-%d')}"
    )
    return last_week_start, last_week_end, label


def completed_share_leaderboard(
    df_activity,
    *,
    beg: datetime,
    end: datetime,
    column: str,
    project_colors: dict[str, str],
    limit: int = 10,
) -> dict[str, Any]:
    df_activity = normalize_activity_df(df_activity)
    df_period = cast(
        pd.DataFrame,
        df_activity[(df_activity.index >= beg) & (df_activity.index < end)],
    )
    df_completed = cast(pd.DataFrame, df_period[df_period["type"] == "completed"])
    total_completed = int(len(df_completed))

    counts = (
        cast(pd.Series, df_completed[column])
        .fillna("")
        .replace("", "(unknown)")
        .value_counts()
        .head(limit)
    )

    items: list[dict[str, Any]] = []
    for name, completed in counts.items():
        completed_i = int(completed)
        pct = (
            round((completed_i / total_completed) * 100, 2) if total_completed else 0.0
        )
        items.append(
            {
                "name": name,
                "completed": completed_i,
                "percentOfCompleted": pct,
                "color": project_colors.get(str(name), "#808080"),
            }
        )

    fig = go.Figure(
        data=[
            go.Bar(
                x=[item["percentOfCompleted"] for item in items][::-1],
                y=[item["name"] for item in items][::-1],
                orientation="h",
                marker=dict(color=[item["color"] for item in items][::-1]),
                hovertemplate="%{y}<br>%{x:.2f}% of completed tasks<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        template="plotly_dark",
        title=None,
        xaxis_title="% of completed tasks",
        yaxis_title="Project",
        height=360,
        margin=dict(l=140, r=18, t=10, b=46),
        plot_bgcolor="#111318",
        paper_bgcolor="#111318",
    )

    return {
        "items": items,
        "totalCompleted": total_completed,
        "figure": fig_to_dict(fig),
    }


def build_habit_tracker_payload(
    df_activity,
    tracked_tasks,
    *,
    anchor: datetime,
    history_weeks: int = 8,
    project_colors: dict[str, str] | None = None,
) -> dict[str, Any]:
    df_activity = normalize_activity_df(df_activity)
    summary = summarize_tracked_habits(
        df_activity,
        tracked_tasks,
        anchor=anchor,
        history_weeks=history_weeks,
    )
    if project_colors is not None:
        for item in summary["items"]:
            item["color"] = project_colors.get(
                str(item["projectName"]), str(item["color"])
            )
    history = summary["history"]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=[item["label"] for item in history],
            y=[item["completed"] for item in history],
            name="Completed",
            marker=dict(color="#61f4b3"),
        )
    )
    fig.add_trace(
        go.Bar(
            x=[item["label"] for item in history],
            y=[item["rescheduled"] for item in history],
            name="Rescheduled",
            marker=dict(color="#ffb86c"),
        )
    )
    fig.update_layout(
        template="plotly_dark",
        barmode="group",
        title=None,
        xaxis_title="Week",
        yaxis_title="Tracked habit events",
        height=360,
        margin=dict(l=56, r=18, t=18, b=70),
        plot_bgcolor="#111318",
        paper_bgcolor="#111318",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )

    return {
        **summary,
        "figure": fig_to_dict(fig),
    }


def compute_insights(
    df_activity,
    *,
    beg: datetime,
    end: datetime,
    project_colors: dict[str, str],
) -> list[dict[str, Any]]:
    df_activity = normalize_activity_df(df_activity)
    insights: list[dict[str, Any]] = []
    df_period = cast(
        pd.DataFrame,
        df_activity[(df_activity.index >= beg) & (df_activity.index < end)],
    )

    project_col = (
        "parent_project_name"
        if "parent_project_name" in df_period.columns
        else "root_project_name"
    )
    df_completed = cast(pd.DataFrame, df_period[df_period["type"] == "completed"])
    if not df_completed.empty and project_col in df_completed.columns:
        project_series = cast(pd.Series, df_completed[project_col])
        counts = (
            project_series.fillna("").replace("", "(unknown)").value_counts()
        )
        if not counts.empty:
            name = str(counts.index[0])
            completed_i = int(counts.iloc[0])
            insights.append(
                {
                    "title": "Most active project",
                    "value": name,
                    "detail": f"{completed_i} completed tasks (last week)",
                    "color": project_colors.get(name),
                }
            )

    df_rescheduled = cast(
        pd.DataFrame, df_period[df_period["type"] == "rescheduled"]
    )
    if not df_rescheduled.empty and project_col in df_rescheduled.columns:
        counts = (
            cast(pd.Series, df_rescheduled[project_col])
            .fillna("")
            .replace("", "(unknown)")
            .value_counts()
        )
        if not counts.empty:
            name = str(counts.index[0])
            rescheduled_i = int(counts.iloc[0])
            insights.append(
                {
                    "title": "Most rescheduled project",
                    "value": name,
                    "detail": f"{rescheduled_i} reschedules (last week)",
                    "color": project_colors.get(name),
                }
            )

    try:
        if not df_period.empty:
            day_names = (
                pd.Series(pd.to_datetime(df_period.index), index=df_period.index)
                .dt.day_name()
            )
            day_counts = day_names.value_counts()
            if not day_counts.empty:
                day = str(day_counts.index[0])
                cnt = int(day_counts.iloc[0])
                insights.append(
                    {
                        "title": "Busiest day",
                        "value": day,
                        "detail": f"{cnt} events (last week)",
                    }
                )
    except Exception as exc:
        logger.debug(f"Skipping busiest day insight: {exc}")

    try:
        added_i = int((df_period["type"] == "added").sum())
        completed_i = int((df_period["type"] == "completed").sum())
        ratio = round((completed_i / added_i), 2) if added_i else None
        insights.append(
            {
                "title": "Added vs completed",
                "value": f"{added_i} / {completed_i}",
                "detail": f"Completion/added ratio: {ratio}"
                if ratio is not None
                else "No added tasks (last week)",
            }
        )
    except Exception as exc:
        logger.debug(f"Skipping added vs completed insight: {exc}")

    try:
        if not df_period.empty:
            hours = (
                pd.to_datetime(df_period.index).to_series(index=df_period.index).dt.hour
            )
            hour_counts = hours.value_counts()
            if not hour_counts.empty:
                peak_hour = int(hour_counts.index.to_list()[0])
                insights.append(
                    {
                        "title": "Peak hour",
                        "value": f"{peak_hour:02d}:00",
                        "detail": "Most events (selected range)",
                    }
                )
    except Exception as exc:
        logger.debug(f"Skipping peak hour insight: {exc}")

    return insights[:4]
