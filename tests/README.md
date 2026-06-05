# Tests for Todoist Assistant

The suite is organized by behavior and runtime boundary instead of keeping all
test files in one directory.

## Layout

- `api/`: FastAPI routes, API payloads, and API client behavior
- `integration/cli/`: CLI and launcher workflows
- `integration/scripts/`: repository scripts and local maintenance commands
- `unit/core/`: shared types, utilities, runtime env, stats, telemetry, versioning
- `unit/database/`: database persistence, threading, dataframe loading, transformations
- `unit/dashboard/`: dashboard payload and plot helpers
- `unit/llm/`: AI backend adapters, usage accounting, lazy backend loading
- `unit/agent/`: agent graph and safe REPL behavior
- `unit/automations/`: automation entrypoints and domain subpackages
- `macos/` and `windows/`: platform packaging checks

Shared pytest fixtures and helpers stay at the test root:
- `conftest.py`
- `factories.py`
- `web_api_helpers.py`

## Running Tests

Preferred full verification:

```bash
make test_all
```

Focused runs:

```bash
PYTHONPATH=. HYDRA_FULL_ERROR=1 uv run python3 -m pytest tests/unit/llm -v
PYTHONPATH=. HYDRA_FULL_ERROR=1 uv run python3 -m pytest tests/api -v
PYTHONPATH=. HYDRA_FULL_ERROR=1 uv run python3 -m pytest tests/unit/automations -v
```

Coverage:

```bash
make coverage
```
