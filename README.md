<div align="center">
  <table>
    <tr>
      <td align="center" width="340">
        <table border="1" cellpadding="8">
          <tr>
            <td align="center">
              <img src="img/logo.png" alt="Todoist Assistant Logo" width="320" />
            </td>
          </tr>
        </table>
      </td>
      <td align="left">
        <h1>Todoist Assistant</h1>
        <p>Local-first analytics, automation, and a dashboard for Todoist data, plus optional AI summaries and read-only chat over cached activity. Sync once, analyze and automate repeatedly.</p>
        <p><strong>Quick links</strong><br/>
          <a href="docs/README.md">Docs index</a><br/>
          <a href="docs/v0.3-release-notes.md">v0.3 release notes</a><br/>
          <a href="CHANGELOG.md">Changelog</a><br/>
          <a href="docs/INSTALLATION.md">Installation</a><br/>
          <a href="docs/USAGE.md">Usage</a><br/>
          <a href="docs/BUILDING.md">Build and CI</a><br/>
          <a href="docs/DOCKER.md">Docker workflow</a><br/>
          <a href="docs/windows_installer.md">Windows installer</a><br/>
          <a href="docs/gmail_setup.md">Gmail setup</a>
        </p>
      </td>
    </tr>
  </table>
</div>

<p><strong>Latest release</strong><br/>
  The latest stable release is
  <a href="https://github.com/mtyrolski/todoist-assistant/releases/tag/todoist-assistant-v0.3.0">todoist-assistant-v0.3.0</a>.<br/>
  For release details, notes, and checklist, see
  <a href="docs/v0.3-release-notes.md">v0.3 release notes</a>.
</p>

<p><strong>Download the latest stable release</strong><br/>
  Go to <a href="https://github.com/mtyrolski/todoist-assistant/releases/tag/todoist-assistant-v0.3.0">GitHub Releases</a> and open the latest stable tag, then download the file you need:<br/>
  - Windows installer: <code>TodoistAssistantSetup.exe</code> or the <code>.msi</code>.<br/>
  - macOS app: <code>.dmg</code> (full app) or <code>.pkg</code> (CLI-only).<br/>
  - Linux: source distribution (see docs for setup).
</p>

<p><strong>Surface status</strong><br/>
  The dashboard and control panel are the stable paths. LLM-Agent Chat is beta. Habit Tracker Lab is experimental and intentionally separate from the main dashboard flow.
</p>

### Triton-backed local LLM
- Set `TODOIST_AGENT_BACKEND=triton_local` to route the LLM breakdown/chat stack through the local Triton server.
- Start the stack with `make run_dashboard_cpu` for CPU or `make run_dashboard_gpu` for GPU. `make triton_shell` opens a shell inside the running Triton container.
- Defaults: HTTP `http://127.0.0.1:8003`, model name `todoist_llm`, model id `Qwen/Qwen2.5-0.5B-Instruct`.
- Logs: container output is tailed to `.cache/todoist-assistant/dashboard/triton.log`, and per-request inference logs go to `.cache/todoist-assistant/dashboard/triton-inference.log`.
- The backend model lives in [`deploy/triton/model_repository/todoist_llm/1/model.py`](deploy/triton/model_repository/todoist_llm/1/model.py), with the GPU override in [`compose.triton.gpu.yaml`](compose.triton.gpu.yaml).

## Highlights
- Fast, local dashboard from your cached Todoist data (reproducible analytics, works offline after sync).
- Guided first-run setup with token validation and project hierarchy cleanup.
- Automations you can enable: task multiplication, local-only LLM breakdown, and an observer loop.
- Read-only chat over cached activity for summaries and insights (no writes to Todoist).

## Python library (what you can do)
The Python package is meant for **local-first data access** and **automation**:
- Read and cache Todoist activity via the API client and database layer.
- Run analytics helpers (stats, activity utilities).
- Build automations and observer loops on top of cached data.
- (Optional) Use AI helpers and agent tools for summaries and chat.

Basic import:
```python
import todoist
```

### Structure (where things live)
- `todoist` - public package (core modules + helpers).
- `todoist.api` - Todoist API client.
- `todoist.database` - local data store and persistence helpers.
- `todoist.automations` - automation workflows (observer, gmail, templates).
- `todoist.llm` - AI/LLM helpers.
- `todoist.agent` - agent tools and chat helpers.
- `todoist.web` - FastAPI app + web API surface.
- `todoist.dashboard` - plots + dashboard utilities.

### Core package notes (from `core/README.md`)
- Install editable core-only package:
  - `uv pip install -e core`
- Build wheel + sdist:
  - `uv build core`
- Included: `todoist.api`, `todoist.database`, `todoist.types`, `todoist.utils`, activity helpers, automation bases.
- Excluded: dashboard + web stack, plotting, LLM/agent modules, UI-only automations.

See `core/README.md` for full details.

## Screenshots
![Dashboard overview](img/fig1.png)
![Activity trends](img/fig2.png)
![Plots](img/fig3.png)

## Quick start (dev)
```bash
cp .env.example .env
# set API_KEY in .env
make init_local_env
make run_dashboard
```
Open:
- Frontend: http://127.0.0.1:3000
- API: http://127.0.0.1:8000

## Checks
```bash
make typecheck
make lint
make test
make coverage
make check
```

- `make typecheck` now rejects explicit `: Any =` variable annotations used as checker escape hatches.
- Keep secrets local: commit `.env.example`, never `.env`, OAuth tokens, private keys, or local credential exports.
- Full coverage snapshots live in [`tests/COVERAGE_REPORT.md`](tests/COVERAGE_REPORT.md).

## Cache and logs
- Runtime cache files now live in `./.cache/todoist-assistant/` by default.
- You can override cache location with `TODOIST_CACHE_DIR`.
- Automation logs are written to `<cache-dir>/automation.log`.
- Runtime logging defaults to `INFO`. Set `TODOIST_LOG_LEVEL=DEBUG` when you want the verbose trace again.
- Todoist request retries now wait only after an actual `429` response, using Todoist's `Retry-After` value when available and a small RPM-based fallback otherwise.
- On startup, legacy runtime files found in old locations are migrated to the cache dir and backed up in `.cache-migration-backup/`.
- Migration backups are temporary and will be removed once the `v0.3` line is finalized.

![Automation controls](img/fig4.png)


## Quick start (Docker)
```bash
docker compose up --build
```
Open:
- Dashboard: http://127.0.0.1:3000
- API: http://127.0.0.1:8000

## Installation (end users)
- **Windows:** use `TodoistAssistantSetup.exe` from Releases (recommended). MSI details in [docs/windows_installer.md](docs/windows_installer.md).
- **macOS:** DMG for the full app; pkg/Homebrew for CLI-only. See [docs/INSTALLATION.md](docs/INSTALLATION.md).
- **Linux:** source setup only. See [docs/INSTALLATION.md](docs/INSTALLATION.md).

## First run (what it looks like)
- The app opens with a guided setup overlay.
- Step 1: paste your Todoist API token. It validates immediately and shows a connection sanity check (masked token + label count).
- Step 2: optional project adjustments (map archived projects to active roots). This can be edited later in Control Panel → Project Adjustments.
- You can always change the token later in Control Panel → Settings.
- After setup, the first data sync starts and a progress overlay appears while charts are generated (can take a few minutes on large accounts).

## Contributing
Issues and PRs are welcome. See [docs/BUILDING.md](docs/BUILDING.md) for build structure and CI workflows.

## License
MIT. See [LICENSE](LICENSE).
