# Todoist Assistant Core

The core package contains the local Todoist data layer: API access, database
persistence, shared types, and activity helpers. It intentionally excludes the
dashboard, frontend, plots, and Codex review integration.

Install from a checkout:

```bash
uv pip install -e core
```

Build distributable artifacts:

```bash
uv build core
```

Use the main package when you need the local dashboard or automations.
