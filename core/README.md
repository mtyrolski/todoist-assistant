# Todoist Assistant Core

This package ships the **core data layer** of Todoist Assistant: API client, database access,
types, activity helpers, and utilities. It **excludes** the web dashboard, plots, and frontend.

## Install (editable, from repo)

```bash
uv pip install -e core
```

## Build (wheel + sdist)

```bash
uv build core
```

## What’s included

- `todoist.api`, `todoist.database`, `todoist.types`, `todoist.utils`
- activity helpers (`todoist.activity`)
- automation base utilities (`todoist.automations.base`, `todoist.automations.activity`, etc.)

## What’s excluded

- Dashboard + web stack (`todoist.web`, `todoist.dashboard`)
- Plotting (`todoist.dashboard.plots`)
- LLM / agent modules (`todoist.llm`, `todoist.agent`)
- Gmail/LLM automations and other UI‑only modules

If you need the full dashboard + UI, use the main `todoist-assistant` package instead.
