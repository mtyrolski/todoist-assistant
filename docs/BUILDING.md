# Building & CI

This doc captures the current build structure and the GitHub Actions workflows.

## Build outputs
- Windows: `dist/windows/`
  - `todoist-assistant-<version>.msi`
  - `TodoistAssistantSetup.exe` (Burn bootstrapper)
- macOS: `dist/macos/`
  - `todoist-assistant-<version>-macos-<arch>.pkg`
  - `todoist-assistant-<version>-macos-<arch>.dmg`
  - `TodoistAssistant.app`

## Windows build (MSI + bootstrapper)

### Structure
- `scripts/build_windows.py` orchestrates the full Windows build.
- PyInstaller spec: `packaging/pyinstaller/todoist_assistant.spec`
- MSI authoring: `windows/installer/*.wxs`
- Burn bundle: `windows/bootstrapper/bundle.wxs`
- Bootstrapper assets: `windows/bootstrapper/todoist-assistant.ico`, `license.rtf`

### Commands
```powershell
# From a Windows shell
make build_windows_installer
# or
uv run python3 -m scripts.build_windows
```

Optional flags:
- `--no-dashboard` (skip Next.js dashboard packaging)
- `--node-version 20.11.1` (pin Node runtime bundled into the app)

### Requirements
- Windows 10/11 or Windows Server runner
- WiX Toolset v3.14 (candle/light)
- Node 20+ (if including dashboard)
- Python 3.11 + uv

### Code signing (optional)
Set these before running the build:
- `WINDOWS_SIGNING_CERTIFICATE` (base64-encoded PFX)
- `WINDOWS_SIGNING_CERTIFICATE_PASSWORD`
- Optional: `WINDOWS_SIGNING_TIMESTAMP_URL`

Manual signing:
- `scripts/windows/sign_windows_artifacts.ps1`

## macOS build (pkg + app + dmg)

### Structure
- App bundle: `scripts/build_macos_app.sh`
- CLI pkg: `scripts/build_macos_pkg.sh`
- DMG: `scripts/build_macos_dmg.sh`
- Packaging scripts: `packaging/macos/scripts/`

### Commands
```bash
make build_macos_pkg
make build_macos_app
make build_macos_dmg
```

### Requirements
- macOS runner
- Xcode command line tools (for `pkgbuild`, `productbuild`, `hdiutil`)
- Node 20+ (for the app dashboard)
- Python 3.11 + uv

### Code signing (optional)
- App signing: `MACOS_APP_SIGN_IDENTITY`
- Installer signing: `MACOS_INSTALLER_SIGN_IDENTITY`

## CI workflows

- `/.github/workflows/windows-installer.yml`
  - Builds MSI + `TodoistAssistantSetup.exe`
  - Runs smoke tests (silent install, launch, uninstall)
  - Optionally signs artifacts when signing secrets are present

- `/.github/workflows/macos-installer.yml`
  - Matrix build for `macos-14` (arm64) and `macos-13` (x86_64)
  - Builds pkg/app/dmg and runs macOS installer tests
  - Publishes per-arch artifacts

- `/.github/workflows/ci.yml`
  - General lint/test pipeline

## Common failure points
- WiX schema errors: ensure bundle/installer authoring is valid for WiX v3.14.
- `pg_config` on macOS: CI installs Homebrew `postgresql` and validates `pg_config --version`.
- Node/npm flakiness: CI uses `npm ci` with cache; app build scripts retry downloads and builds.
