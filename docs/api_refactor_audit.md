# API Refactor Audit

## Scope

Current oversized Python files:

- `todoist/web/api.py`: 4704 lines before this refactor pass.
- `tests/test_web_api.py`: 2486 lines before this refactor pass.

No other tracked Python source file is currently at or above 2000 lines.

## `todoist.web.api` Findings

`todoist/web/api.py` is doing too many jobs in one import unit:

- FastAPI application construction and CORS setup.
- Dashboard state, disk cache, refresh progress, and status endpoints.
- Dashboard home payload assembly and plot figure orchestration.
- LLM chat settings, model lifecycle, queue storage, worker execution, and chat endpoints.
- Admin API token and timezone configuration endpoints.
- Automation compatibility helpers consumed by `todoist/web/routes/admin_automations.py`.
- Observer state and runtime log discovery/read endpoints.
- Project adjustment file discovery and persistence endpoints.
- Task ingest parsing, LLM rewrite, preview, and creation endpoints.
- Status update project/report endpoints.
- LLM breakdown, multiplication, dashboard urgency, plot event, and template settings endpoints.

The largest risks are not raw line count alone. The tighter coupling comes from module globals that tests and routes monkeypatch directly:

- `_state`, `_DASHBOARD_CONFIG_PATH`, `_AUTOMATIONS_PATH`, `_ADMIN_LOCK`
- `Database`, `Cache`
- `_build_observer`, `_load_automation_inventory`, `_set_automation_enabled`
- `_gmail_automation_status`, `_read_yaml_config`, `_save_yaml_config`
- plot function aliases used by `dashboard_home`

Because of that, replacing `todoist/web/api.py` with a package directory would be higher risk. A safer first pass is to keep `todoist.web.api` as the stable compatibility module and extract pure helper code into sibling component modules imported back into `api.py`.

## Suggested Module Boundaries

Good first-pass extraction targets:

- `todoist/web/api_components/runtime.py`
  Runtime path resolution, API key handling, timezone helpers, display path helpers.

- `todoist/web/api_components/logs.py`
  Runtime log source specs, path display, log paging, log source resolution.

- `todoist/web/api_components/templates.py`
  Template path validation, YAML normalization, camel-case payload conversion, template summaries.

- `todoist/web/api_components/settings.py`
  Dashboard urgency payloads, plot event settings validation, multiplication and LLM breakdown settings payloads.

Higher-risk later extractions:

- LLM chat lifecycle and queue processing, because it has several async locks and mutable globals.
- Dashboard refresh state/progress, because it coordinates tqdm callbacks, disk cache signatures, and `_state`.
- Admin automation compatibility helpers, because both the routed admin module and tests reach through `todoist.web.api`.

## Test File Findings

`tests/test_web_api.py` has natural split points:

- Dashboard state/home/status/progress tests.
- Admin project adjustment/settings/token/timezone/log tests.
- Automation/Gmail/observer admin tests.
- Task ingest/status update tests.
- LLM chat tests.

The safest test split is mechanical: move related test blocks into new files while preserving the existing `import todoist.web.api as web_api` pattern and local stubs/factories.

## Compatibility Requirements

Refactors should preserve:

- `uvicorn todoist.web.api:app`
- `from todoist.web.api import app`
- `import todoist.web.api as web_api`
- Test monkeypatching of `web_api` globals.
- Admin router behavior in `todoist/web/routes/admin_automations.py`, which still imports `todoist.web.api` and calls protected compatibility helpers.

