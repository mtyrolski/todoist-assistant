# todometry

**Local-first Todoist dashboard for activity analytics and project history.**

todometry is an independent third-party integration for exploring
Todoist activity and project history. It is not affiliated with or endorsed by
Doist. Todoist and Doist are trademarks of their respective owners.

The current application is a local dashboard and an Android app. It syncs
activity from Todoist and keeps a local cache between syncs. History is limited
by the data available and fetched for your account; forecasts are estimates.
Reopening a non-recurring task removes its completion from the original period,
while recurring occurrences remain separate.

![Weekly completion and task lifespan charts](img/dashboard.webp)

## What it does

- **Overview** shows completion trends, task lifespans, project contributions,
  priority counts and configurable attention alerts.
- **Project Timeline** shows active and archived subprojects over time. Project
  Adjustments lets you correct their local hierarchy.
- **Background refresh** updates cached dashboard data without blocking an
  existing view; recent activity and older history can also be synced manually.
- **Habit data** for tasks labelled `track_habit` is included in the dashboard
  API payload. This branch does not have a dedicated habit-tracking screen.
- **Control Panel and Live Logs** provide local settings, status and log access.

A separate observer automation, stale-task maintenance and the optional
read-only Codex executive review are not implemented on this branch. They are
not required to run the dashboard.

## Install or run from source

Windows and macOS installer and build instructions are in
[Windows and macOS builds](docs/BUILDING.md). The Python package, namespace and
terminal command are all named `todometry`. Existing local state is copied to
the new default path on upgrade; the original files are retained.

For a source checkout, use Python 3.11–3.13, [uv](https://docs.astral.sh/uv/),
Node.js 20.9+ and Make:

```bash
git clone https://github.com/mtyrolski/todoist-assistant.git
cd todoist-assistant
uv sync --locked
npm --prefix frontend ci
make dashboard
```

Open <http://127.0.0.1:3000> and enter your Todoist API token. Alternatively,
copy `.env.example` to `.env` and set `API_KEY`. Data and credentials stay in
local files; the app contacts Todoist to sync. See [architecture and local
state](docs/ARCHITECTURE.md) for paths and configuration overrides.

```bash
make sync            # fetch recent activity
make sync_history    # fetch recent and older history
make stop_dashboard  # stop the local servers
make run_demo        # explore anonymized local sample data
```

## Android

The Android app syncs directly with Todoist and stores its history on the phone.
Saved data and the built-in demo work offline. You can export project adjustments
from the desktop Control Panel and import them on the phone.

<img src="img/android.webp" width="340" alt="Android dashboard with sample data">

Build the Preview APK with JDK 17 and Android SDK 36:

```bash
make build_android_preview
adb install -r dist/android/todometry-preview.apk
```

Keep the generated Preview signing key to install later builds as updates.
Artifacts from the [Android build workflow](https://github.com/mtyrolski/todoist-assistant/actions/workflows/android.yml)
use temporary keys and are intended for testing, not upgrades. See the
[Android build instructions](docs/ANDROID.md) for signing and device tests.

## Development

Dashboard settings use OmegaConf to read and update the existing YAML
configuration. Install Playwright Chromium once, then run the canonical checks:

```bash
npm --prefix frontend exec -- playwright install chromium
make ci
```

The [architecture guide](docs/ARCHITECTURE.md) describes the current boundaries,
known web-backend debt and state compatibility requirements.
