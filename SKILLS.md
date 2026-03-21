# SKILLS

This file is a compact onboarding guide for coding agents working in this repository.

## What This Repo Is

`todoist-assistant` is a local-first Todoist analytics and automation project with:

- a Python backend and library in `todoist/`
- a FastAPI API surface in `todoist/web/api.py`
- a Next.js dashboard in `frontend/`
- Hydra-based automation config in `configs/`
- a reusable core-only package in `core/`

The project supports offline analysis after sync, optional Gmail and LLM integrations, and desktop packaging for Windows/macOS.

## Start Here

Read these files before large changes:

- `README.md` for the product shape and primary workflows
- `AGENTS.md` for repo rules, secrets handling, and required checks
- `docs/CODE_LAYOUT.md` for the stable public module boundaries
- `docs/BUILDING.md` for packaging and CI structure
- `tests/README.md` for the test map

## Architecture Map

Use this mental model when exploring:

- `todoist/api/`: Todoist client and endpoint wrappers
- `todoist/database/`: local persistence, dataframe loading, demo data helpers
- `todoist/dashboard/`: plotting and dashboard-specific data presentation
- `todoist/web/`: FastAPI routes and dashboard payload shaping
- `todoist/automations/`: activity sync, templates, multiplicate, observer, Gmail, LLM breakdown
- `todoist/llm/`: local and OpenAI-backed chat/model helpers
- `todoist/agent/`: read-only chat and agent graph helpers
- `frontend/app/`: Next.js app router UI
- `configs/automations.yaml`: default automation wiring
- `core/`: stripped-down package excluding web/dashboard/LLM/UI layers

## Preserve These Boundaries

The repo already documents a couple of intentional facades. Keep them stable unless there is a strong reason to change the public surface:

- keep `todoist.dashboard.plots` as the public plotting entrypoint
- keep `todoist.web.api` as the main FastAPI facade
- move heavy implementation details into focused helpers such as `todoist/web/dashboard_payload.py` or `todoist/dashboard/_plot_*.py`
- keep the `core/` package free of dashboard, web, and UI-only features

If a refactor improves internals, prefer moving logic behind the existing facade instead of making callers chase renamed modules.

## Safe Working Habits

- Prefer `make` targets over ad hoc commands.
- Run general dev commands in WSL/Linux/macOS when possible; the `Makefile` assumes POSIX shell behavior.
- Use `make run_dashboard` for the local API + frontend stack.
- Use `make run_demo` when you need the anonymized/demo dashboard flow.
- Treat `make init_local_env`, `make update_env`, and `make run_observer` as stateful automation commands that may talk to external services or mutate cached local state.
- Treat `make clear_local_env` as destructive to local cache/runtime artifacts.
- Do not edit generated or local-only directories unless the task is specifically about them: `frontend/node_modules/`, `frontend/.next/`, `outputs/`, `.cache/`, `.ruff_cache/`, `.pytest_cache/`.
- Assume task creation and automation code may perform real Todoist writes unless the code path is clearly read-only; prefer tests and mocks over live runs.

## Validation Rules

Before closing work, run:

- `make typecheck`
- `make lint`
- `make test`

Also run `make coverage` when touching multiple modules or changing coverage expectations.

If you touch the Next.js app, also run:

- `npm --prefix frontend run lint`
- `npm --prefix frontend run build`

Honor the existing typing rule:

- do not silence pyright with explicit `: Any = ...` variable annotations
- narrow values or fix the type flow instead

## Test Routing

When making changes, go to the nearest matching tests first:

- web/API changes: `tests/test_web_api.py`
- database/cache changes: `tests/test_database.py`, `tests/test_database_threading.py`
- plots/dashboard metrics: `tests/test_plots.py`, `tests/test_dashboard_utils.py`
- automations: `tests/test_activity_automation.py`, `tests/test_observer.py`, `tests/test_gmail_automation.py`, `tests/test_llm_breakdown_backend.py`
- CLI and telemetry: `tests/test_cli.py`, `tests/test_telemetry.py`
- LLM/agent surfaces: `tests/test_local_llm.py`, `tests/test_openai_llm.py`, `tests/test_agent_graph.py`, `tests/test_repl_tool.py`

If you fix a bug, add or update the closest targeted test instead of relying only on full-suite coverage.

## Secrets And Local Data

Assume these are local-only even if they exist in a working tree:

- `.env`
- `credentials.json`
- `gmail_credentials.json`
- `gmail_token.json`
- token exports, private keys, cert bundles

Never commit new secret-bearing files. If a new workflow needs one, update `.gitignore` in the same change and keep `.env.example` as the only committed environment template.

## Repo-Specific Editing Tips

- The backend is type-checked Python 3.11+ with `uv`, `pyright`, and `pylint`; keep signatures and imports clean.
- `todoist/web/api.py` is large, so prefer extracting helpers rather than adding more inline route logic.
- The frontend uses Next.js App Router in `frontend/app/`; keep backend/frontend contracts explicit and verify payload changes end to end.
- If you change backend response shapes, update the matching frontend hooks, fetch helpers, and components in `frontend/app/lib/` and the affected route UI.
- Automation config is Hydra-driven; config changes usually belong in `configs/` plus the matching automation module and tests.
- Packaging changes often span `scripts/`, `packaging/`, `windows/`, `.github/workflows/`, and `docs/BUILDING.md`.
- Docs are helpful but not infallible; verify commands and entrypoints against the codebase before trusting a stale doc.

## Good Default Workflow For Agents

1. Read `AGENTS.md`, `README.md`, and the nearest module tests.
2. Find the public facade that owns the behavior.
3. Make the smallest change that preserves existing module boundaries.
4. Add or update focused tests near the affected surface.
5. Run the required checks from `AGENTS.md`.

Optimize for boring, reviewable changes over clever rewrites.
