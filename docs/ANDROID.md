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

Both clients count cached events. An ordinary undo cancels the preceding completion at its original date. Recurring occurrences survive resets, and undo actions remain in activity history.

The Android app renders a native weekly total chart, project contribution breakdowns, forecasts, active priority counts, local attention rules, searchable/filterable active projects/tasks and recent activity. A retained ViewModel owns network/IO work, and a RecyclerView creates only visible rows. Full desktop Plotly views, lifespan analysis, hierarchy playback, project timeline and project adjustment editing remain desktop features. Android alert preferences and history are local to the device; desktop joblib caches and Python adjustment files are not imported.

The workflow tests API 26, 35 and 37.0 at 1440×3120, density 560 and font scale 130%, including search, rotation, keyboard layout, settings, encrypted storage and sync cancellation. This covers a Galaxy S25 Ultra screen configuration on standard Android; it does not emulate Samsung One UI. No physical Samsung was connected during development.

Run JVM checks and packaging with `make build_android`. Format Java with `./android/gradlew -p android spotlessApply`. With an emulator running, run `./android/gradlew -p android connectedDebugAndroidTest`. Interaction tests reset test-account data; use a dedicated emulator, not a phone containing your saved account.
