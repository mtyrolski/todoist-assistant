# Changelog

## v0.3.1

Latest stable release: `v0.3.1`.

### Release prep updates
- Aligned package metadata to `0.3.1` in `pyproject.toml`, `core/pyproject.toml`, and `frontend/package.json`.
- Pointed stable release references in `README.md` and `docs/README.md` at the `todoist-assistant-v0.3.1` release tag and docs.
- Added and expanded `docs/v0.3.1-release-notes.md` as the release checklist and file-scope release summary.
- Updated the Homebrew formula in `Formula/todoist-assistant.rb` to `0.3.1`.
- Moved the runtime migration-backup removal marker to `v0.3.1` in `todoist/utils.py` so the release line and runtime messaging match.

### Notes
- `v0.3.1` is the current stable documentation and packaging target.
- Release assets should use the `todoist-assistant-v0.3.1` tag name consistently across packaging and docs.
