# Usage

## CLI
- Show help: `todoist-assistant --help`
- Check version: `todoist-assistant version --check`

## Dashboard
```bash
make run_dashboard
```
- Frontend: http://127.0.0.1:3000
- API: http://127.0.0.1:8000

Demo (anonymized):
```bash
make run_demo
```

## Automations
Run configured automations (short tasks only):
```bash
uv run python3 -m todoist.automations.run.automation --config-dir configs --config-name automations
```

Update local cache + automations:
```bash
make update_env
```
- Logs are stored in `./.cache/todoist-assistant/automation.log` by default, or in `<TODOIST_CACHE_DIR>/automation.log` if you override the cache location.
- Runtime logs default to `INFO`. Use `TODOIST_LOG_LEVEL=DEBUG` for verbose troubleshooting.
- Todoist retries now react to real `429` responses instead of adding a fixed local pacing delay before every request.
- `make update_env` now keeps the activity refresh incremental: it stops paging once a fetched activity page is already fully cached.

## Background observer
Continuously refresh activity and run short automations:
```bash
uv run python3 -m todoist.run_observer --config-dir configs --config-name automations
```

## Agentic chat (local, read-only)
```bash
make chat_agent
```

## Library integration (example)
```python
from todoist.database.base import Database

# Load from local .env
client = Database('.env')
activity = client.fetch_activity(max_pages=5)
print(len(activity))
```
