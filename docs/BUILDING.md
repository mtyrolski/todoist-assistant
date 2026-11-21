# Building & CI

This doc captures the current build structure and the GitHub Actions workflows.

**Release blocked:** web namespace injection and the remaining product and
native upgrade validation are not complete. Publishing jobs require an explicit
`publish` input on a tag and check identity and known web debt. See the
[draft release notes](releases/v0.4.1.md).

The Homebrew formula's source archive checksum must be verified and updated
against the final release tag before distribution. CI uses a locally generated
archive for its Homebrew smoke test and does not validate the remote checksum.

The macOS app bundle is now named `todometry.app` and keeps the existing bundle
identifier. A manually installed `TodoistAssistant.app` may remain alongside
it; verify the new app and retained data before removing the old bundle.

## Build outputs
- Android: `dist/android/todometry-debug.apk`, built with `make build_android`; see [Android instructions](ANDROID.md).
- Windows: `dist/windows/`
  - `TodometrySetup.exe` (Burn bootstrapper used by end users)
  - `todometry-<version>.msi` (raw MSI for deployment and automation)
- macOS: `dist/macos/`
  - `todometry.app` (app bundle)
  - `todometry-<version>.pkg` and `todometry-<version>.dmg` from local scripts
  - `todometry-<version>-macos-<arch>.pkg` and `todometry-<version>-macos-<arch>.dmg` from CI/release runs that pass `--output-suffix macos-<arch>`

## Windows build (MSI + bootstrapper)

### Structure
- `scripts/build_windows.py` orchestrates the full Windows build.
- PyInstaller spec: `packaging/pyinstaller/todometry.spec`
- MSI authoring: `windows/installer/*.wxs`
- Burn bundle: `windows/bootstrapper/bundle.wxs`
- Bootstrapper license: `windows/bootstrapper/license.rtf`

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

The pkg and dmg scripts write versioned artifacts into `dist/macos/`; the release workflow adds the `macos-<arch>` suffix so arm64 and x86_64 assets stay separate.

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
  - Builds MSI + `TodometrySetup.exe`
  - Runs smoke tests (silent install, launch, uninstall)
  - Optionally signs artifacts when signing secrets are present

- `/.github/workflows/macos-installer.yml`
  - Matrix build for `macos-15` (arm64) and `macos-15-intel` (x86_64)
  - Builds pkg/app/dmg and runs macOS installer tests
  - Passes `--output-suffix macos-<arch>` so published pkg/dmg assets are architecture-specific
  - Publishes per-arch artifacts

- `/.github/workflows/ci.yml`
  - Runs `make ci-python` and `make ci-frontend`, including the wheel smoke test

The installer workflows also run for relevant pull requests. Publication requires
an explicit manual dispatch on a tag with `publish` enabled. Native installer
smoke tests install and uninstall system packages, so run them only on a disposable
runner. The frozen-app smoke uses synthetic legacy data in a temporary directory.

## Common failure points
- WiX schema errors: ensure bundle/installer authoring is valid for WiX v3.14.
- Node/npm flakiness: CI uses `npm ci` with cache; app build scripts retry downloads and builds.
