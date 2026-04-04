# Code Layout

This document explains where the main parts of Todoist Assistant live and what each area is responsible for.

## Top-level directories

- `todoist/`: main Python package
- `frontend/`: Next.js dashboard frontend
- `configs/`: Hydra configuration for automations and dashboard behavior
- `docs/`: user-facing and developer-facing documentation
- `tests/`: pytest suite and coverage notes
- `core/`: core-only package variant
- `scripts/`: packaging, build, and local workflow helpers
- `windows/`: WiX installer and bootstrapper assets
- `deploy/`: deployment assets, including Triton model packaging

## Python package layout

### `todoist.api`

Todoist API client code and request-facing helpers.

Use this when you need to fetch or send Todoist data through the API.

### `todoist.database`

Local persistence, cache access, and database-oriented helpers.

Use this when you need to read cached activity, tasks, or local state.

### `todoist.automations`

Automation entry points and automation-specific modules.

Important subpackages include:
- `activity`
- `gmail_tasks`
- `habit_tracker`
- `init_env`
- `llm_breakdown`
- `multiplicate`
- `observer`
- `run`
- `stale_tasks`
- `template`
- `update_env`

### `todoist.dashboard`

Dashboard-facing utilities and subpages used by the web experience.

### `todoist.web`

FastAPI application and API surface used by the dashboard and local integrations.

### `todoist.llm`

Optional LLM integration and summary helpers.

### `todoist.agent`

Local agent and chat helpers built on top of cached Todoist data.

## Frontend and web split

- `frontend/` is the user interface
- `todoist.web` is the local backend API
- `make run_dashboard` starts both together for local development or usage

## Core package

The `core/` package is the stripped-down distribution for the data layer.

Included:
- API client
- Database layer
- Types
- Utility helpers

Excluded:
- Dashboard and frontend surfaces
- Plotting
- LLM and agent modules
- UI-specific automation features

See [../core/README.md](../core/README.md) for packaging details.

## Configuration and runtime behavior

- `configs/automations.yaml` controls which automations run and how they are configured
- `configs/dashboard.yaml` controls dashboard behavior
- `.env` stores local environment variables such as `API_KEY`
- Runtime cache and logs default to `.cache/todoist-assistant/`

## Common entry points

- `make init_local_env`: first sync and setup
- `make update_env`: refresh cache and run short automations
- `make run_dashboard`: start API + frontend
- `make run_observer`: run background refresh loop
- `make chat_agent`: start local read-only chat flow

## Where to look first

- If you want to use the app: [INSTALLATION.md](INSTALLATION.md) and [USAGE.md](USAGE.md)
- If you want to extend the backend: start in `todoist/`
- If you want to work on the UI: start in `frontend/`
- If you want packaging or release workflows: [BUILDING.md](BUILDING.md)
