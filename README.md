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
        <p>Local-first analytics, automation, and dashboards for Todoist with optional AI summaries and read-only chat.</p>
        <ul>
          <li>Cache Todoist data locally and explore it in a dashboard</li>
          <li>Run automations like sync, task multiplication, and Gmail task import</li>
          <li>Use optional local AI summaries and read-only chat over cached activity</li>
        </ul>
        <p><strong>Quick links</strong><br/>
          <a href="docs/README.md">Docs index</a><br/>
          <a href="docs/INSTALLATION.md">Installation</a><br/>
          <a href="docs/USAGE.md">Usage</a><br/>
          <a href="docs/DOCKER.md">Docker</a><br/>
          <a href="docs/BUILDING.md">Build and CI</a><br/>
          <a href="docs/CODE_LAYOUT.md">Code layout</a><br/>
          <a href="https://github.com/mtyrolski/todoist-assistant/releases">Releases</a>
        </p>
      </td>
    </tr>
  </table>
</div>

Todoist Assistant is a local-first Todoist toolkit. It syncs your Todoist data into a local cache, gives you a dashboard to explore it, and lets you run automations on top of that data.

The main product is the dashboard and automation workflow. Optional AI features can summarize your local activity and power a read-only chat view, but the core value of the project is local analytics and automation. After the first sync, most day-to-day usage runs against your local cached data.
![Dashboard overview](img/fig1.png)
![Activity trends](img/fig2.png)
## What this project is

- A local dashboard for Todoist activity, trends, and task analysis
- A Python package and API for working with cached Todoist data
- A set of automations such as environment updates, task multiplication, and Gmail task import
- An optional local AI layer for summaries and chat over your cached history

## Who it is for

- Todoist users who want a local dashboard instead of only Todoist's built-in views
- People who want to automate recurring Todoist workflows
- Developers who want a Python codebase they can extend

## Latest stable release

`v0.3.3`

Release assets live on GitHub Releases:
- Windows: `TodoistAssistantSetup.exe` or the `.msi`
- macOS: `.dmg` for the app, `.pkg` for CLI-only installs
- Linux: source checkout or Docker

Releases: <https://github.com/mtyrolski/todoist-assistant/releases>

## Quick start

### End users

#### Windows

1. Download `TodoistAssistantSetup.exe` from GitHub Releases.
2. Run the installer.
3. Paste your Todoist API token during first-run setup.
4. Open the dashboard and let the first sync complete.

More Windows details: [docs/windows_installer.md](docs/windows_installer.md)

#### macOS

- App + dashboard: install the `.dmg` release asset
- CLI-only: install the `.pkg` release asset or use Homebrew

Full instructions: [docs/INSTALLATION.md](docs/INSTALLATION.md)

#### Linux

- Run from source
- Or use Docker Compose

Setup details: [docs/INSTALLATION.md](docs/INSTALLATION.md)

### Docker

```bash
docker compose up --build
```

Open:
- Dashboard: http://127.0.0.1:3000
- API: http://127.0.0.1:8000

Container workflow: [docs/DOCKER.md](docs/DOCKER.md)

### Developers

Prerequisites:
- Python 3.11
- `uv`
- Node.js 20+
- A Todoist API token

```bash
git clone https://github.com/mtyrolski/todoist-assistant.git
cd todoist-assistant
cp .env.example .env
# set API_KEY in .env
make init_local_env
make run_dashboard
```

Open:
- Dashboard: http://127.0.0.1:3000
- API: http://127.0.0.1:8000

## Everyday usage

### Main commands

```bash
make run_dashboard     # start the local dashboard stack (in most cases only this one needed)
make update_env        # refresh local cache and run short automations
make run_observer      # keep syncing in the background
make run_demo          # run the dashboard with demo/anonymized data
make chat_agent        # start the local read-only chat flow
```

Command details: [docs/USAGE.md](docs/USAGE.md)

### What the first run looks like

1. Paste your Todoist API token.
2. Confirm or adjust project mapping for archived or moved projects.
3. Let the first sync build the local cache.
4. Use the dashboard, automations, or chat against local data.

## Main features

### Dashboard

- Runs locally against cached Todoist data
- Shows trends, counts, priorities, and activity summaries
- Works well for repeated analysis after the initial sync

## Screenshots


![Plots](img/fig3.png)
![Automation controls](img/fig4.png)

### Automations

- `init_env` and `update_env` keep local data current
- Multiplication automation expands tasks based on labels
- Gmail automation can turn emails into Todoist tasks
- Observer mode keeps refresh and short automations running continuously

Automation setup lives in [`configs/automations.yaml`](configs/automations.yaml).

### Optional AI features

- Local summaries over cached Todoist history
- Read-only dashboard chat
- AI task breakdown for labeled Todoist tasks

AI is opt-in. Set `TODOIST_AGENT_BACKEND` in `.env` to choose the backend:

- `disabled`: default; no AI backend module is loaded
- `codex`: uses the local Codex CLI backend for read-only chat and task breakdown
- `triton_local`: uses the local Triton inference endpoint and the configured catalog model

Currently supported models are the catalog entries in `todoist/llm/model_catalog.py`. The project does not currently support arbitrary OpenAI-compatible HTTP endpoints, Anthropic-compatible HTTP endpoints, uncatalogued local model ids from the dashboard, or write-capable AI agents.

Usage details: [docs/USAGE.md](docs/USAGE.md)

## Project structure

- [`todoist/`](todoist) contains the main Python package
- [`frontend/`](frontend) contains the Next.js dashboard
- [`configs/`](configs) contains automation and dashboard configuration
- [`docs/`](docs) contains longer-form documentation
- [`tests/`](tests) contains API, integration, platform, and nested unit test segments
- [`core/`](core) contains the core-only package variant

Code layout details: [docs/CODE_LAYOUT.md](docs/CODE_LAYOUT.md)

## Documentation

- [docs/README.md](docs/README.md): docs index
- [docs/INSTALLATION.md](docs/INSTALLATION.md): installation by platform
- [docs/USAGE.md](docs/USAGE.md): commands, dashboard, and automations
- [docs/DOCKER.md](docs/DOCKER.md): container workflow
- [docs/BUILDING.md](docs/BUILDING.md): packaging and CI
- [docs/gmail_setup.md](docs/gmail_setup.md): Gmail automation setup
- [core/README.md](core/README.md): core-only package
- [tests/README.md](tests/README.md): test layout and coverage notes

## Checks

Run this before closing code changes:

```bash
make test_all
make coverage
```

## Contributing

Issues and pull requests are welcome. Read [AGENTS.md](AGENTS.md) and [SKILLS.md](SKILLS.md) for repository rules and workflow expectations.

## License

MIT. See [LICENSE](LICENSE).
