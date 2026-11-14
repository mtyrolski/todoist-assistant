# Engineering contract

This file guides engineering agents working in this repository.
Read relevant code, tests and current Git status before editing.
Follow the user's explicit instructions when they conflict with this file.

## Scope and design

- Prefer modifying or deleting existing code to adding modules.
- Add an abstraction for one consumer only when its benefit is demonstrated.
- Do not introduce speculative provider, plugin or backend frameworks.
- An internal compatibility facade requires a documented external consumer.
- Remove unused code rather than retaining it for hypothetical future callers.
- A feature removal includes implementation, routes, UI, tests, config and docs.
- Also remove its dead dependencies, cache entries, commands and build paths.
- Keep changes focused on the requested behaviour.
- Do not add product features during a cleanup.

## Boundaries

- The intended web API is a thin FastAPI composition root.
- Routes should use explicit imports and small, clear state or service objects.
- Do not add runtime namespace injection or copy API globals into other modules.
- Existing injection is technical debt, not a pattern to extend.
- Avoid circular imports and forwarding modules that conceal dependencies.
- Do not use catch-all type stubs or broad type or lint suppressions.
- Fix real typing and import issues rather than masking them.
- Every runtime dependency must have a concrete production consumer.
- Keep test, lint and build tools out of runtime dependencies.
- Prefer one canonical command per supported operation.
- Keep the architecture checks and their temporary debt baseline honest.

## Product and state

- Preserve local activity history, project mappings, settings and cache data.
- Protect the v0.4.0 to v0.4.1 upgrade path and explicit path overrides.
- Do not silently overwrite, delete or reset existing user state.
- Keep the dashboard, project timeline and supported operations working.
- Background refresh must preserve usable cached data on failure.
- Desktop demo mode and the Android app are currently supported surfaces.
- Any future retained Codex executive review must be read-only.
- Executive review and a separate observer are absent on this branch.
- Do not describe absent functionality as implemented.
- Windows and macOS installers are supported release targets.
- Docker is not a supported distribution target.
- Avoid restoring removed assistant, integration or task-template features.

## Verification

- Search tracked code, tests, scripts, configuration and docs before deletion.
- Distinguish production consumers from tests of dead implementation.
- Test behaviour and migration outcomes, not obsolete implementation shape.
- Add focused tests for consequential changes and failure paths.
- Run the checks appropriate to the changes and fix regressions.
- Use `make ci` for the canonical Python and frontend verification suite.
- Browser checks require Playwright Chromium; follow the README setup.
- Run `python -m scripts.check_architecture` for size and architecture checks.
- LOC, file count and dependency totals are review signals, not quotas.
- Do not increase a legacy architecture baseline to make a check pass.
- When packaging changes, validate metadata and affected native build paths.
- Report platform or environment checks that could not be run.
- Keep documentation aligned with current functionality and command names.
- Treat local secrets, user data and untracked files as user-owned.
