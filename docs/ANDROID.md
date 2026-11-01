# Android app

The native Android app runs on Android 8.0+ (API 26). It talks directly to Todoist over HTTPS and stores its own private JSON event cache. No Python, Next.js server, or desktop computer is required.

## Build and install

Install JDK 17 and the Android SDK, set `JAVA_HOME` and `ANDROID_HOME`, and install the SDK packages:

```bash
sdkmanager 'platforms;android-35' 'build-tools;35.0.0' 'platform-tools'
make build_android
adb install -r dist/android/todoist-assistant-debug.apk
```

`bash scripts/build_android.sh` is the equivalent CI entrypoint. It validates JVM tests and Android lint before copying the debug-signed, installable APK to `dist/android/`. The Gradle wrapper pins Gradle 8.11.1 and verifies its distribution checksum. Android Gradle Plugin is pinned to 8.9.3.

The **Android APK** workflow runs for Android changes on pull requests and pushes, and can be started manually through Actions. Download the `todoist-assistant-android-debug` artifact, unzip it, and open the APK on the phone. Android will ask you to allow installation from the app opening the file. This is a debug build for local use; Play Store signing/distribution is not configured.

## Use

1. Open Settings, enter a Todoist API token, and choose Save and sync.
2. The app loads active projects/tasks and the last twelve weeks of activity, following every cursor page.
3. Subsequent syncs overlap the latest cached event by one day and merge by event ID. Cached history grows as the app is used.
4. Scroll through priorities, weekly completions and forecasts, undo counts, project task lists and recent activity. Tap a project to expand its tasks.
5. Cached data remains visible offline; failed syncs preserve the last snapshot. Its timestamp is shown above the dashboard. Sync now refreshes explicitly; startup also attempts a refresh.

Only GET requests are made to Todoist. Tokens are encrypted with Android Keystore and excluded from backups. Disconnect and clear data deletes this app's token and snapshot. The first sync can take a while on an active account; the UI stays responsive.

## Counting contract and current scope

Both clients derive completion counts from cached events. An ordinary `uncompleted` event cancels the preceding outstanding completion of that task at its original date. Recurring occurrences survive resets. Undo actions are also displayed separately. See [completion rules](COMPLETIONS.md).

The Android app currently renders a native weekly total chart, forecast, active priority counts, local fire/P1/P2 alert toggles, active projects/tasks and recent activity. Full desktop Plotly views, lifespan analysis, hierarchy playback, project timeline and project adjustment editing remain desktop features. Android alert preferences and history are local to the device; desktop joblib caches and Python adjustment files are not imported.

Verification covers compilation, APK packaging, JVM counting/forecast tests and Android lint. A physical-device/emulator interaction test is still needed before treating this as a production mobile release.
