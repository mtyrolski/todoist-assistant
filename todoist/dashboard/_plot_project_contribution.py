from datetime import datetime
from typing import cast

import pandas as pd
import plotly.graph_objects as go


def plot_project_contribution_timeline(
    activity: pd.DataFrame, beg: datetime, end: datetime
) -> go.Figure:
    frame = activity.loc[(activity.index >= beg) & (activity.index < end)].copy()
    frame = frame.loc[frame["event_type"] == "completed"]
    if frame.empty:
        return _empty_figure("No completed tasks in this period.")
    names = frame["parent_project_name"].fillna("Unassigned").astype(str)
    roots = frame["root_project_name"].fillna(names).astype(str)
    frame["timeline_project"] = [name if name == root else f"{root} → {name}" for root, name in zip(roots, names, strict=False)]
    frame["week"] = frame.index.to_period("W-MON").start_time
    pivot = frame.pivot_table(index="timeline_project", columns="week", aggfunc="size", fill_value=0)
    totals = cast(pd.Series, pivot.sum(axis=1)).sort_values(ascending=False).head(14)
    pivot = pivot.loc[totals.index]
    return go.Figure(
        data=go.Heatmap(
            z=pivot.to_numpy(), x=[value.strftime("%d %b") for value in pivot.columns], y=pivot.index.tolist(),
            colorscale="Blues", colorbar={"title": "Completed"}, hovertemplate="%{y}<br>Week of %{x}: %{z} completed<extra></extra>",
        ),
        layout={
            "template": "plotly_dark", "height": max(340, 58 * len(pivot.index) + 130),
            "margin": {"l": 24, "r": 24, "t": 16, "b": 36},
            "paper_bgcolor": "#111318", "plot_bgcolor": "#111318",
            "xaxis": {"title": "Week"}, "yaxis": {"title": "Parent project → subproject", "autorange": "reversed"},
        },
    )


def _empty_figure(message: str) -> go.Figure:
    figure = go.Figure()
    figure.add_annotation(text=message, x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False)
    figure.update_layout(template="plotly_dark", height=340, paper_bgcolor="#111318", plot_bgcolor="#111318")
    return figure
