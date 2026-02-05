# Windows installer build (MSI)

This repository ships a Windows packaging pipeline that bundles the Python backend with PyInstaller and the Next.js dashboard with a standalone Node runtime, then builds an MSI via WiX.

## End user install (Windows 10/11)

1. Download `TodoistAssistantSetup.exe` from GitHub Releases (recommended).
   - If you only have the MSI, download `todoist-assistant-<version>.msi` instead.
2. Double-click the installer. If SmartScreen appears, click "More info" -> "Run anyway".
3. Choose an install directory (default: `C:\Program Files\TodoistAssistant`) and finish the wizard.
   - You can toggle the desktop shortcut and anonymous telemetry (off by default).
4. Launch Todoist Assistant from the Start Menu or Desktop shortcut.
5. On first run you will see a guided setup overlay:
   - Step 1: paste your Todoist API token (validated immediately).
   - Step 2: optional project hierarchy adjustments (map archived projects to parents).
6. You can change the token later in Control Panel -> Settings, and adjust mappings in Control Panel -> Project Adjustments.

Manual token setup (optional):
`C:\ProgramData\TodoistAssistant\.env` is created on first run. If you prefer, you can edit it directly.
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

## Settings and data locations

- Install dir: `C:\Program Files\TodoistAssistant`
- Writable data/config: `C:\ProgramData\TodoistAssistant`
  - `config\` (YAML config + templates + agent instructions)
  - `.env` (created on first launch)
  - `logs\` (runtime logs and installer logs)

## Installer logs (verbose)

If the installer fails, check the logs in:

- `C:\ProgramData\TodoistAssistant\logs\installer\setup.log`
- `C:\ProgramData\TodoistAssistant\logs\installer\msi.log`
- `C:\ProgramData\TodoistAssistant\logs\installer\vc_redist.log`

These logs are intentionally verbose to help troubleshoot installation issues.

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
- Installer ACLs use WiX `WIX_ACCOUNT_USERS` to resolve the localized Built-in Users group; avoid hardcoding `BUILTIN\\Users` in WiX sources to keep non-English Windows installs working.

## macOS build notes

- The macOS packaging workflow installs PostgreSQL via Homebrew so `pg_config` is available, and then sets the macOS-specific extra (`uv sync --locked --group build --extra macos`) to pin `psycopg2-binary`. If you build locally, run `brew install postgresql` before `uv sync --extra macos` so that `pg_config --version` succeeds and the environment matches CI.
- The macOS smoke test installs the pkg, launches `todoist-assistant --no-browser` on ephemeral API/front-end ports, waits for `http://127.0.0.1:3000` to respond, and only then uninstalls, ensuring the dashboard really hosts on localhost.

## Code signing

The Windows MSI is unsigned by default, which is why SmartScreen/UAC show “Unknown publisher”. When you sign the PyInstaller executable and MSI with a trusted code signing certificate, those warnings go away and end users only need to download the single `todoist-assistant-<version>.msi` asset (the cabinet is embedded with the installer via `windows/installer/product.wxs`, so there is no separate `cab1.cab` file to carry alongside the MSI).

### Local builds

Before running `uv run python -m scripts.build_windows`, populate the following environment variables:

```powershell
$env:WINDOWS_SIGNING_CERTIFICATE = "C:\path\to\certificate.pfx"
$env:WINDOWS_SIGNING_CERTIFICATE_PASSWORD = "pfx-password"
uv run python -m scripts.build_windows
```

`WINDOWS_SIGNING_TIMESTAMP_URL` can override the default timestamp server (`http://timestamp.digicert.com`), and `WINDOWS_SIGNTOOL_PATH` points to a custom `signtool.exe` when it is not on `PATH`. Providing the PFX and password causes the build script to sign `todoist-assistant.exe` before WiX stages it and to sign the final MSI after `light.exe` finishes.

### GitHub Actions

Store the base64-encoded PFX in a secret like `WINDOWS_SIGNING_CERTIFICATE` and keep the password in `WINDOWS_SIGNING_CERTIFICATE_PASSWORD`. The Windows installer workflow can decode the certificate into the workspace, export those environment variables, and then the `uv run python -m scripts.build_windows` step automatically signs both artifacts during the build. Once the release MSI carries that signature, Windows no longer treats it as an unknown publisher.
