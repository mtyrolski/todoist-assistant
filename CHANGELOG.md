# Changelog

## v0.3 pre-release

This repository is currently on the `v0.3` pre-release line. For the latest stable build, use [todoist-assistant-v0.2.7](https://github.com/mtyrolski/todoist-assistant/releases/tag/todoist-assistant-v0.2.7).

For the full narrative release notes and the v0.3 compliance checklist, see [docs/v0.3-release-notes.md](docs/v0.3-release-notes.md).

### Added

- Guided first-run setup and cached dashboard bootstrapping.
- Dashboard cards for habit tracking and active project hierarchy.
- Optional AI chat and LLM breakdown workflows.
- More automation surfaces, including observer-driven runs and Gmail ingestion.

### Changed

- Better chart polish, including clearer project hierarchy and periodic completion views.
- Stronger Todoist API v1 compatibility and payload handling.
- Improved cache handling, rate-limit behavior, and runtime logging.

### Fixed

- Activity backfill gaps that could skip older pages.
- Schema compatibility warnings from current Todoist payloads.
- Dashboard data handling for newer project/task fields.
