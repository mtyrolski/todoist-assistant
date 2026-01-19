# Windows installer build (MSI)

This repository ships a Windows packaging pipeline that bundles the Python backend with PyInstaller and the Next.js dashboard with a standalone Node runtime, then builds an MSI via WiX.

## End user install (Windows 10/11)

1. Download `todoist-assistant-<version>.msi` from GitHub Releases.
2. Double-click the MSI to launch the installer. If SmartScreen appears, click "More info" -> "Run anyway".
3. Choose an install directory (default: `C:\Program Files\TodoistAssistant`) and complete the wizard.
4. On the final screen you can opt in to anonymous telemetry (off by default).
5. Launch Todoist Assistant from the Start Menu or Desktop shortcut.
6. Set your API key by editing `C:\ProgramData\TodoistAssistant\.env`.
   - Or use the dashboard: Control Panel → Settings → paste the token and Save.

If the `.env` file does not exist yet, run the app once to generate it from
`C:\ProgramData\TodoistAssistant\config\.env.template`, then edit the `.env` file.
`C:\ProgramData` is hidden by default; paste it into File Explorer's address bar.

### Silent install / uninstall

```powershell
# Interactive install
msiexec /i todoist-assistant-<version>.msi

# Silent install (no UI)
msiexec /i todoist-assistant-<version>.msi /qn /norestart

# Install log
msiexec /i todoist-assistant-<version>.msi /l*v install.log

# Skip desktop shortcut
msiexec /i todoist-assistant-<version>.msi INSTALLDESKTOPSHORTCUT=0

# Silent uninstall
msiexec /x todoist-assistant-<version>.msi /qn /norestart
```

### Launch flags

```powershell
"C:\Program Files\TodoistAssistant\todoist-assistant.exe" --no-frontend
"C:\Program Files\TodoistAssistant\todoist-assistant.exe" --api-port 8001 --frontend-port 3001
```

## Prerequisites

- Windows 10/11 build machine
- Python 3.11+ and `uv`
- Node.js 20+ (build-time only)
- WiX Toolset v3.11+ (`candle.exe`, `light.exe`, `heat.exe` on PATH)

Install Python deps (including PyInstaller):

```powershell
uv sync --group build
```

## Build

From the repo root:

```powershell
uv run python3 -m scripts.build_windows
```

Skip dashboard packaging:

```powershell
uv run python3 -m scripts.build_windows --no-dashboard
```

Output:

```
dist\windows\todoist-assistant-<version>.msi
```

## Runtime layout

- Install dir: `C:\Program Files\TodoistAssistant`
- Writable data/config: `C:\ProgramData\TodoistAssistant`
  - `config\` (YAML config + templates + agent instructions)
  - `.env` (created from `config\.env.template` on first launch)
End users do not need Python installed; the MSI bundles the runtime via PyInstaller.

The launcher sets:

- `TODOIST_CONFIG_DIR`
- `TODOIST_CACHE_DIR`
- `TODOIST_AGENT_CACHE_PATH`
- `TODOIST_AGENT_INSTRUCTIONS_DIR`

## Notes

- The build script bundles a Node.js runtime when the dashboard is included; pass `--no-dashboard` to skip frontend packaging.
- The Start Menu/Desktop shortcut launches the API + Next.js dashboard and opens `http://127.0.0.1:3000`.
- To skip the Desktop shortcut, install with `msiexec /i todoist-assistant-<version>.msi INSTALLDESKTOPSHORTCUT=0`.
- Uninstall removes the installed files and the ProgramData folder used by the app.
