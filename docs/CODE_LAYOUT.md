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

### `todoist.core`

Shared, non-UI primitives: environment names, constants, data types, runtime environment resolution, telemetry, utilities, and version helpers.

New code should import these modules directly from `todoist.core`; the package root is kept for entry points, not implementation modules.

### `todoist.features`

Domain-level feature helpers that are shared across automations and the dashboard:

- `activity`
- `habit_tracker`
- `stale_tasks`
- `stats`
- `status_update`
- `task_tree_import`

New code should import these modules directly from `todoist.features`.

### `todoist.dashboard`

Dashboard-facing utilities and subpages used by the web experience.

### `todoist.web`

FastAPI application and API surface used by the dashboard and local integrations.

### `todoist.llm`

Optional LLM integration and summary helpers.

The package is split so backend-neutral configuration, constants, model catalog,
and structured-output parsing can be imported without loading a backend. Backend
modules are loaded lazily from the selected environment value:
- `config.py`, `constants.py`, `model_catalog.py`, `structured.py`: safe shared surface
- `backends/raw.py`: explicit no-AI backend marker used by launch/runtime selection
- `backends/codex.py`: Codex CLI adapter
- `backends/triton.py`: Triton inference adapter
- `backends/transformers.py`: direct Transformers adapter used by the CLI agent
- `factory.py`: facade for constructing only the selected backend

### `todoist.agent`

Local agent and chat helpers built on top of cached Todoist data.

## Frontend and web split

- `frontend/` is the user interface
- `todoist.web` is the local backend API
- `make dashboard` starts both together for local development or usage
- `make dashboard_codex` and `make dashboard_triton` opt into AI backends

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

- `make setup`: first sync and setup
- `make update_env`: refresh cache and run short automations
- `make dashboard`: start API + frontend without AI
- `make run_observer`: run background refresh loop
- `make chat_agent`: start local read-only chat flow

## Test layout

The pytest suite is intentionally nested by behavior:

- `tests/api/`: FastAPI and API-client behavior
- `tests/integration/`: CLI and script workflow checks
- `tests/unit/core/`: shared types, utilities, runtime environment, statistics
- `tests/unit/database/`: persistence and dataframe loading
- `tests/unit/dashboard/`: dashboard payload and Plotly helpers
- `tests/unit/llm/`: optional AI backend adapters and lazy-loading contracts
- `tests/unit/agent/`: local agent graph and REPL tool
- `tests/unit/automations/`: automation entry points plus subdomains
- `tests/macos/` and `tests/windows/`: platform packaging checks

## Where to look first

- If you want to use the app: [INSTALLATION.md](INSTALLATION.md) and [USAGE.md](USAGE.md)
- If you want to extend the backend: start in `todoist/`
- If you want to work on the UI: start in `frontend/`
- If you want packaging or release workflows: [BUILDING.md](BUILDING.md)
