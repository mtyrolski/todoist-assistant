# Code Layout

This project keeps public import paths stable, while the heavier implementation details live in narrower support modules.

## Dashboard plots

`todoist.dashboard.plots` stays the public entrypoint for plotting helpers.

The implementation now lives in focused modules:

- `todoist/dashboard/_plot_common.py`
  Shared styling constants plus small forecasting helpers.
- `todoist/dashboard/_plot_activity.py`
  Event timeline and heatmap charts.
- `todoist/dashboard/_plot_weekly_trend.py`
  Weekly completion trend calculations and figure assembly.
- `todoist/dashboard/_plot_periodic.py`
  Periodic and cumulative completion charts.
- `todoist/dashboard/_plot_lifespans.py`
  Task lifespan distribution plotting.

This keeps callers stable while making each chart family easier to review and test in isolation.

## Web dashboard API

`todoist.web.api` remains the FastAPI facade used by the app and tests.

Dashboard payload shaping helpers now live in:

- `todoist/web/dashboard_payload.py`

That module owns:

- date-range parsing
- activity anchor resolution
- metric extraction
- leaderboard payload building
- insight generation
- Plotly figure serialization

The route surface stays in `todoist.web.api`, which avoids churn for existing imports and monkeypatch-heavy tests.
