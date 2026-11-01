# Android app

The native Android app runs on Android 8.0+ (API 26). It talks directly to Todoist over HTTPS and stores its own private JSON event cache. No Python, Next.js server, or desktop computer is required.

## Build and install

Install JDK 17 and the Android SDK, set `JAVA_HOME` and `ANDROID_HOME`, and install the SDK packages:

```bash
sdkmanager 'platforms;android-35' 'build-tools;35.0.0' 'platform-tools'
make build_android
adb install -r dist/android/todoist-assistant-debug.apk
```

`bash scripts/build_android.sh` is the equivalent CI entrypoint. It validates Java formatting, JVM tests and Android lint before copying the debug-signed, installable APK to `dist/android/`. The Gradle wrapper pins Gradle 8.11.1 and verifies its distribution checksum. Android Gradle Plugin is pinned to 8.9.3.

The **Android APK** workflow runs for Android changes on pull requests and pushes, and can be started manually through Actions. Download the `todoist-assistant-android-debug` artifact, unzip it, and open the APK on the phone. Android will ask you to allow installation from the app opening the file. This is a debug build for local use; Play Store signing/distribution is not configured.

## Use

1. Open Settings, enter a Todoist API token, and choose Save and sync.
2. The app loads active projects/tasks and the last twelve weeks of activity, following every cursor page.
3. Subsequent syncs overlap the latest cached event by one day and merge by event ID. Cached history grows as the app is used.
4. Use Overview for weekly counts, forecasts and project contributions. Tap a week on the chart to inspect it. Projects provides task/project/label search and priority filters; Activity searches the latest 200 events.
5. Settings includes local fire, priority, due-date and deadline rules with minimum match thresholds. Blank selections stay blank.
6. Explore demo works without credentials and never overwrites your saved account data.
7. Cached data remains visible offline; failed syncs preserve the last snapshot. Its timestamp is shown above the dashboard. Sync now refreshes explicitly; startup also attempts a refresh.

Archived project names are refreshed daily and retained for historical labels. If the account cannot access the activity endpoint, active tasks/projects still work; the UI explicitly marks history as unavailable instead of displaying invented zeros. Network failures preserve the last snapshot.

Only GET requests are made to Todoist. Tokens are encrypted with Android Keystore and excluded from backups. Disconnect and clear data deletes this app's token and snapshot. The first sync can take a while on an active account; progress includes page/record counts, and Cancel sync preserves saved data. Synchronization and parsing run outside the UI thread and survive screen rotation.

Changing an API token for the same Todoist account preserves history; changing accounts never merges their private events. Credentials are verified against the account profile before merging. Snapshots are atomically committed and bound to the encrypted connection. A failed credential write rolls back the pending snapshot.

## Counting contract and current scope

Both clients derive completion counts from cached events. An ordinary `uncompleted` event cancels the preceding outstanding completion of that task at its original date. Recurring occurrences survive resets. Undo actions are also displayed separately. See [completion rules](COMPLETIONS.md).

The Android app renders a native weekly total chart, project contribution breakdowns, forecasts, active priority counts, local attention rules, searchable/filterable active projects/tasks and recent activity. A retained ViewModel owns network/IO work, and a RecyclerView creates only visible rows. Full desktop Plotly views, lifespan analysis, hierarchy playback, project timeline and project adjustment editing remain desktop features. Android alert preferences and history are local to the device; desktop joblib caches and Python adjustment files are not imported.

Verification includes API 35 emulator interaction tests for onboarding, offline demo, rotation, searching/filtering, rule persistence, token validation, Keystore encryption, credential isolation, atomic rollback and sync cancellation. The workflow runs interaction tests on API 26 and API 35. A physical phone has not been tested.

Run JVM checks and packaging with `make build_android`. Format Java with `./android/gradlew -p android spotlessApply`. With an emulator running, run `./android/gradlew -p android connectedDebugAndroidTest`. Interaction tests reset test-account data; use a dedicated emulator, not a phone containing your saved account.
