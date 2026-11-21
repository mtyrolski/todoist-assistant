# Architecture

This document describes the current v0.4.1 development branch and its intended
boundaries. It does not imply that every planned release migration is complete.

## Data and history

`todometry/api/` accesses Todoist; `todometry/database/` fetches projects and
activity. `todometry/features/activity.py` and `todometry/features/data_sync.py`
merge and checkpoint activity, while `todometry/sync.py` exposes recent and history
sync. `todometry/core/utils.py` stores the activity cache, dashboard snapshot and
archived-activity scan state locally, with atomic writes and locking.

`todometry/database/dataframe.py` transforms activity and applies local project
adjustments; `todometry/web/services/project_adjustments.py` resolves manual and
inferred mappings. The project timeline is a semantic payload built by
`todometry/dashboard/_plot_project_lifecycle.py` and rendered by the frontend.
Other retained dashboard charts still use Plotly.

## Runtime and presentation

`todometry/launcher.py`, `scripts/dashboard_stack.sh` and `todometry/sync.py` run
the installed or source workflows. Desktop demo mode is an anonymized local
dashboard. The web entrypoint is `todometry/web/api.py`, with routes in
`todometry/web/routes/` and runtime helpers in `todometry/web/api_components/`.
The intended boundary is a thin FastAPI composition root with explicit shared
state and imports. **Current debt:** dashboard and settings routes and dashboard
runtime still synchronize the API namespace dynamically. The architecture check
prevents that debt from growing; it does not claim the rewrite is finished.

`frontend/app/` owns browser navigation, controls, settings and rendering;
`android/` is the separately packaged mobile app. Dashboard state and progress
are held by the web runtime, which can refresh stale cached data in the
background. There is no separate observer automation in this branch. Likewise,
optional Codex executive review is not currently implemented; any future
retained review must be read-only and must not mutate Todoist.

## Local state and compatibility

For a source checkout, the default cache is `.cache/todometry` under
the working directory; `TODOIST_CACHE_DIR` overrides it. The runtime resolves
`.env` using `TODOIST_DATA_DIR`, `TODOIST_CACHE_DIR`, the working directory and
repository fallback in that order. Dashboard settings use
`TODOIST_CONFIG_DIR/dashboard.yaml`, or the applicable data/repository config
path. Project adjustment files live in `personal/`, with
`TODOIST_PERSONAL_DIR` available as an override.

The installed launcher sets data, config, cache and log directories. Its
platform defaults are in `todometry/launcher.py`. When the former
`todoist-assistant` default directory exists, retained files are copied into
the new default directory once. Existing destination files win conflicts.
Conflicts are logged, source files remain untouched, and an interrupted copy
resumes on the next run.
Explicit path overrides are never migrated. A small `todoist.core.types` shim
allows old joblib activity and dashboard snapshots to be read; newly saved
objects use `todometry`. Keep compatibility only for real upgrades or documented
external consumers, not internal facades.

## Distribution and exclusions

Windows and macOS installers and the Android app are supported build targets;
see `docs/BUILDING.md` and `docs/ANDROID.md`. Docker distribution is not
supported. This product is not a conversational AI assistant, a general-purpose
integration hub or a Gmail client. Task Multiplication and task-tree/template
import are not supported features.

`make ci` runs the canonical Python and frontend checks. The architecture
check reports production file/line counts and direct runtime dependency count
without enforcing size quotas. It blocks new known namespace injection and
broader Ruff F821 exemptions while tracking the explicitly baselined debt.
