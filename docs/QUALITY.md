# Verification and remaining limits

Verified locally on 2026-11-01. The changes cover completion accounting, chart forecasts, editable attention rules, stale desktop views and the native Android app.

## Behavior fixed

- Original completion and undo actions remain in cache/activity history. One shared completion projection removes ordinary undone completions from their original periods and retains recurring occurrences. Python and Android run the same eight fixture scenarios.
- Calendar periods use local time; stored timestamps normalize to UTC. Forecasts include empty periods, cannot fall below actuals and sum project estimates. Archived projects contribute actuals without extrapolation. Current actual/forecast markers share project colors.
- Invalid settings patches cannot silently convert strings or fractions into booleans/integers. Empty selections remain empty, concurrent partial writes preserve each other, and failed saves retain the draft. Overdue tasks remain eligible when expanding a due-date window.
- Cached desktop dashboards refresh in the background after a minute. Open pages poll for finished updates. Failed refreshes retain loaded data and show a warning, including partial activity-sync failures. Sync uses the configured credential-file path.
- Android sync runs outside the UI thread and survives rotation. It handles cursor pages, retries, cancellation, account changes, archived metadata and missing activity access. Snapshot writes are atomic and bound to encrypted credentials; failed credential writes roll back the pending snapshot. Offline demo never replaces account data.

## Checks

| Area | Result |
| --- | --- |
| Python suite | 406 passed, 4 platform-specific installer tests skipped on Linux |
| Python static checks | Ruff undefined/unused checks and focused Pyright checks passed |
| Frontend | TypeScript, 11 form tests and production build passed |
| Chromium interaction tests | 6 passed: invalid/empty settings, failed loads/saves, touch selections, retained data after failure and completed background refresh |
| Android JVM tests | 28 passed, including shared completion scenarios, forecasts, sync pagination/account isolation and projection/rule cases |
| Android API 35 emulator | 11 passed: onboarding/demo, search/filter, rotation, settings, token validation, Keystore, credential isolation, corruption/rollback and cancellation |
| Android packaging | Java formatting, lint and APK assembly passed |
| Dependencies/version checks | npm audit: zero reported vulnerabilities; uv lock and application/Plotly version checks passed |

CI runs the Python suite, Ruff and version checks, plus frontend TypeScript, form/browser tests and the production build. Android CI runs formatting, JVM tests, lint and APK assembly, with a device job targeting API 26 and API 35. Test output and failure reports are uploaded as workflow artifacts.

## Scope and limits

The Android artifact is a debug-signed local-use APK. Release signing and Play Store distribution are not configured. API 35 was exercised locally; API 26 is configured in CI. No physical phone was tested.

Android has native weekly counts/charts, forecasts, project contributions, tasks, recent activity and local attention rules. Full Plotly analyses and project adjustment editing remain desktop features. Each client keeps its own cache. Missing activity access/history is shown explicitly; aggregate Productivity counters never fill those gaps. Forecasts are estimates based on recorded history.

One upstream Starlette/AnyIO deprecation warning remains in Python tests. The FastAPI global-injection compatibility layer is still active and remains a candidate for a separate refactor. See [the audit](CODE_AUDIT.md).
