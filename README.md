# Todoist Assistant

Todoist Assistant is a local dashboard for Todoist activity and project history. It stores fetched activity on disk and uses that cache to build charts, priorities, project hierarchy views, and the project timeline.

![Dashboard overview](img/fig1.png)

## Quick start

Requirements: Python 3.11, [uv](https://docs.astral.sh/uv/), Node.js 20+, and a Todoist API token.

```bash
git clone https://github.com/mtyrolski/todoist-assistant.git
cd todoist-assistant
cp .env.example .env
# Set API_KEY in .env
make setup
make dashboard
```

Open <http://127.0.0.1:3000>. The dashboard refreshes cached activity when needed. You can also fetch activity explicitly:

```bash
make sync          # incremental activity sync
make sync_history  # incremental sync plus older history backfill
make stop_dashboard
```

Activity updates use a one-day overlap, fetch all pages in the range, and merge under a file lock. History windows are checkpointed on disk. Project adjustments are a full-width page under Operations; they preserve archived project mappings locally.

## Development

```bash
uv sync --locked
make test
npm --prefix frontend ci
npm --prefix frontend run lint
npm --prefix frontend run build
```

The Python data and sync code is separate from the web API and frontend. Plots remain in the dashboard modules. The planned Android app is a standalone native client with its own local data store; the current Python and Next.js desktop dashboard is not an Android APK. See [Android direction](docs/ANDROID.md).

## Packaging

Windows and macOS packaging remains available through manually triggered workflows; see [Windows installer notes](docs/windows_installer.md).
