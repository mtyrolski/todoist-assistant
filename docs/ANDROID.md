# Android

The APK bundles the desktop's React components, stylesheet, fonts and Plotly renderer. Java handles Todoist requests, completion accounting, encrypted credentials and the local cache. A computer or Python server is not required; the dashboard and demo work offline.

Build requirements: Node.js 20.9+, JDK 17 and Android SDK 35. The app requires Android 8.0+ with an updated Android System WebView; UI tests run on Android 15 and 17.

```bash
sdkmanager 'platforms;android-35' 'build-tools;35.0.0' 'platform-tools'
# Set JAVA_HOME and ANDROID_HOME
make build_android
adb install -r dist/android/todoist-assistant-debug.apk
```

`scripts/build_android.sh` installs the locked frontend dependencies, exports the web assets, runs Java formatting/tests/lint and builds the debug-signed APK. Gradle also rebuilds web assets when their sources change. Android APK artifacts are available from the GitHub Actions workflow. Release signing and Play Store publication are not configured.

Connect a Todoist token in Control Panel, or choose Explore a demo. The app reads projects/tasks and twelve weeks of activity initially, follows cursor pages, then merges incremental updates by event ID. Account changes keep histories separate. Failed or cancelled syncs preserve saved data. Demo never overwrites account data. Tokens stay in Android Keystore-backed encrypted storage.

Overview shows weekly actuals/forecasts, project contributions and cumulative completions. Projects supports search and priority filters; Activity shows recent actions. Control Panel reuses desktop alert settings. Full desktop lifespan analysis, hierarchy editing and project timelines are not included. Alert preferences and history remain local to each client.

To run interaction tests on a dedicated emulator:

```bash
./android/gradlew -p android connectedDebugAndroidTest
adb install -r android/app/build/outputs/apk/debug/app-debug.apk
node --test frontend/tests/device/android-ui.test.cjs
```

These tests clear emulator app data and exercise offline rendering, actual/forecast totals, search, the keyboard, rotation and saved settings. CI uses 1440×3120/density 560 on Android 15 and 1080×2340/density 420 on Android 17, both with font scale 130%. Standard Android emulation does not reproduce Samsung One UI.
