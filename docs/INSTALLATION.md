# Installation

This project ships a desktop app + dashboard on Windows/macOS, and a developer-oriented CLI on other platforms.

## End users

### Windows (recommended)
- Download `TodoistAssistantSetup.exe` from GitHub Releases.
- Run the setup and follow the wizard.
- For MSI command lines, logging, and data retention options, see [docs/windows_installer.md](windows_installer.md).

### macOS
- **App + dashboard:** use the DMG (`todoist-assistant-<version>-macos-<arch>.dmg`) and drag the app to `/Applications`.
- **CLI-only:** use the pkg (`todoist-assistant-<version>-macos-<arch>.pkg`) or Homebrew.
  - Homebrew (source build): `brew install --build-from-source Formula/todoist-assistant.rb`

### Linux
- There is no packaged installer. Use the source checkout (see Developer setup below).

### Docker (all platforms)
- Run the API + dashboard in containers with Docker Compose.
- See [docs/DOCKER.md](DOCKER.md) for build/run instructions.

## Developer setup (all platforms)

### Prerequisites
- Python 3.11
- `uv` (https://github.com/astral-sh/uv)
- Node.js 20+ (only required for the dashboard)
- A Todoist API token

### Quick start
```bash
git clone https://github.com/mtyrolski/todoist-assistant.git
cd todoist-assistant
cp .env.example .env
# edit .env and set API_KEY
make init_local_env
make run_dashboard
```

Open:
- Dashboard: http://127.0.0.1:3000
- API: http://127.0.0.1:8000

### Notes
- macOS packaging uses `psycopg2-binary` in the build extra; CI also installs Homebrew `postgresql` to provide `pg_config`.
- If you only want the CLI, you can skip Node and use `todoist-assistant --help` after install.
