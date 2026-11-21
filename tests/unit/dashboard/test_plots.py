"""Activity plots for selected dates."""

from datetime import datetime

import pandas as pd

from todometry.dashboard._plot_activity import plot_events_over_time


def test_daily_activity_excludes_events_outside_selected_day():
    dates = pd.to_datetime(
        ["2025-01-14 23:59", "2025-01-15 00:00", "2025-01-15 23:59", "2025-01-16 00:00"]
    )
    activity = pd.DataFrame({"type": ["completed"] * len(dates)}, index=dates)
    plot = plot_events_over_time(
        activity, datetime(2025, 1, 15), datetime(2025, 1, 16), "W", daily=True
    )
    completed = next(trace for trace in plot.data if trace.name == "Completion actions")
    assert list(completed.x) == [datetime(2025, 1, 15)]
    assert list(completed.y) == [2]
    assert completed.mode == "lines+markers"
