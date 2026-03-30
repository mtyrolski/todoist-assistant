# Status Update Automation Plan

This plan turns the new manual Status Update Studio into a fuller automation surface that can be saved, rerun, and scheduled without losing the evidence trail from completed tasks and task comments.

## Goal

Let a user pick a time range plus one or more projects, gather the matching Todoist activity, expand that into an accomplishment report grounded in completed tasks and comments, and generate a sync-ready update for daily, weekly, or custom check-ins.

The shipped studio already covers the first manual pass:

- project selection
- daily, weekly, and custom ranges
- deterministic report generation from completed tasks plus comments
- markdown output and evidence review

The next phase should make that flow operational as a reusable automation, not just a one-off report builder.

## Target User Flow

1. Open Status Update Studio or an Automation preset.
2. Choose one or more projects and a time range or preset.
3. Preview the gathered activity with grouped accomplishments and source evidence.
4. Adjust title, framing, and output style.
5. Save the selection as a reusable preset or run it once.
6. Optionally schedule the preset for a daily, weekly, or ad-hoc sync cadence.
7. Review generated output history and rerun with one click.

## Scope Breakdown

### Phase 1: Harden the report pipeline

- Cache activity slices and task comment fetches for repeated generation runs.
- Preserve both deterministic stats and source evidence in the API payload.
- Normalize response contracts so manual and scheduled runs share the same shape.
- Add guardrails for large project selections and long date ranges.

### Phase 2: Add reusable presets

- Persist saved status-update presets in config.
- Support project scope, range mode, sync label, and output options per preset.
- Add preset duplication, rename, delete, and last-run metadata.
- Expose presets in both the dashboard and the automation settings surface.

### Phase 3: Add automation execution

- Register a dedicated automation that can run saved presets.
- Support manual trigger first, then scheduled trigger windows.
- Store run history, generated markdown, and warnings for later review.
- Prepare delivery hooks for copy/export now and future posting targets later.

### Phase 4: Improve summarization quality

- Introduce richer sectioning such as accomplishments, follow-ups, risks, and notes.
- Add task clustering so repeated completions do not read like raw logs.
- Keep the default path deterministic; any LLM-assisted polish should be optional.

## Architecture Direction

### Backend domain layer

Add a status-update service layer centered on `todoist/status_update.py` that owns:

- project scope expansion
- activity filtering
- task comment hydration
- deterministic section building
- cached report artifacts

This layer should remain usable from both the web API and an automation runner.

### API layer

Keep `todoist/web/api.py` thin:

- list selectable projects
- generate a one-off report
- create, update, delete, and list presets
- trigger preset runs
- fetch run history and generated artifacts

### Automation layer

Add a dedicated automation module under `todoist/automations/` that:

- loads saved presets
- decides which presets should run
- invokes the shared status-update report builder
- stores run metadata
- exposes warnings instead of silently swallowing data gaps

### Frontend layer

The dashboard should support two adjacent modes:

- `Status Update Studio` for one-off manual generation
- `Status Update Automations` for saved presets, schedules, and history

Both should reuse the same evidence and markdown review components.

## Parallel Agent Plan

### Agent 1: Activity and evidence backend

Own:

- `todoist/status_update.py`
- `todoist/database/db_tasks.py`
- `todoist/api/endpoints.py`
- `tests/test_status_update.py`

Deliver:

- cached activity and comment hydration
- richer structured report sections
- stable domain model usable by API and automation runner
- edge-case tests for missing comments, large ranges, and repeated task completions

Commit bucket:

- `Expand status update report generation and evidence loading`

### Agent 2: API and preset contracts

Own:

- `todoist/web/api.py`
- `tests/test_web_api.py`

Deliver:

- preset CRUD endpoints
- one-off and preset-trigger report generation endpoints
- run-history endpoints
- response contract tests that lock the frontend shape

Commit bucket:

- `Add status update preset and run-history API endpoints`

### Agent 3: Studio UX and preset management

Own:

- `frontend/app/components/StatusUpdateStudio.tsx`
- `frontend/app/status-updates/page.tsx`
- `frontend/app/components/AppShell.tsx`
- `frontend/app/globals.css`

Deliver:

- cleaner range picking and multi-project selection
- saved preset creation and management
- run-history drawer with evidence drill-down
- stronger empty, loading, and warning states

Commit bucket:

- `Extend status update studio with presets and run history`

### Agent 4: Automation runtime

Own:

- `todoist/automations/status_updates/automation.py`
- `todoist/automations/__init__.py`
- `configs/automations.yaml`
- automation-specific tests

Deliver:

- automation registration
- schedule config and enablement rules
- execution wrapper around the shared report builder
- persisted run artifacts for dashboard inspection

Commit bucket:

- `Add scheduled status update automation`

### Agent 5: Documentation and release verification

Own:

- `docs/USAGE.md`
- `docs/README.md`
- release notes if needed

Deliver:

- user-facing workflow docs
- operator notes for automation setup
- validation checklist for scheduled runs and output review

Commit bucket:

- `Document status update automation workflow`

## Integration Sequence

1. Land backend report hardening before preset CRUD.
2. Land preset CRUD before the automation runner.
3. Land frontend preset management once the API contract is stable.
4. Land scheduled execution after manual preset runs are already working.
5. Finish with docs and a cross-surface validation pass.

## Validation Matrix

Required after each integration pass:

- `make typecheck`
- `make lint`
- `make test`

Required before merging the full automation phase:

- `make coverage`
- `npm --prefix frontend run build`
- manual dashboard smoke test for one-off generation, preset save, preset rerun, and schedule toggle

## Risks To Control

- Comment fetching can become slow for large project scopes; cache and batch carefully.
- Generated summaries can become noisy if repeated completions are not clustered.
- Preset scheduling must respect local timezone and configured dashboard timezone.
- Delivery integrations should not be coupled to the core report builder.
- Manual and scheduled runs must return the same structured artifact shape.

## Suggested Future Commit Series

1. `Expand status update report generation and evidence loading`
2. `Add status update preset and run-history API endpoints`
3. `Extend status update studio with presets and run history`
4. `Add scheduled status update automation`
5. `Document status update automation workflow`
