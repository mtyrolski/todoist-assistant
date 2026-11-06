# Tests

Tests are arranged by runtime boundary:

- `api/` — FastAPI routes and payloads
- `integration/` — launcher and repository scripts
- `unit/` — core, database, dashboard, and data sync
- `macos/` and `windows/` — packaging checks

Run the full suite:

```bash
make ci
```

Useful focused runs:

```bash
PYTHONPATH=. uv run pytest tests/unit/dashboard -v
PYTHONPATH=. uv run pytest tests/unit/features -v
PYTHONPATH=. uv run pytest tests/api -v
```

Use `make coverage` for the coverage report.
