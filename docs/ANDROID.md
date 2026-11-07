# Android

The APK bundles the desktop's React components, stylesheet, fonts and Plotly renderer. Java handles Todoist requests, completion accounting, encrypted credentials and the local cache. A computer or Python server is not required; the dashboard and demo work offline.

Build requirements: Node.js 20.9+, JDK 17 and Android SDK 36. The app requires Android 8.0+ with an updated Android System WebView; UI tests run on Android 15, 16 and 17.

```bash
sdkmanager 'platforms;android-36' 'build-tools;35.0.0' 'platform-tools'
# Set JAVA_HOME and ANDROID_HOME
make build_android_preview
adb install -r dist/android/todometry-preview.apk
```

`make build_android_preview` installs locked dependencies, runs Java checks, and builds a signed, optimized release APK with WebView debugging disabled. Preview uses `com.todoistassistant.preview`, so it can coexist with the debug app and has separate account data. Back up `~/.local/share/todoist-assistant/signing/preview/` (or `ANDROID_PREVIEW_SIGNING_DIR`) privately: its keystore and password are needed to sign compatible updates. A fresh CI runner creates a different Preview key.

`make build_android` builds the debug APK. `make build_android_bundle` builds an optimized AAB at `dist/android/todometry-release.aab`, unsigned unless all four signing variables below are supplied. `ANDROID_VERSION_CODE` overrides the version-derived integer and must increase for each Play upload.

For a signed public bundle, set `ANDROID_SIGNING_STORE_FILE` (absolute keystore path), `ANDROID_SIGNING_STORE_PASSWORD`, `ANDROID_SIGNING_KEY_ALIAS`, and `ANDROID_SIGNING_KEY_PASSWORD` in your local environment or CI secrets. Never commit these values. CI retains the R8 mapping files alongside the artifacts.

The app targets API 36. Public Play publication still needs a confirmed permanent application ID, an upload key/Play App Signing, a public privacy policy with publisher contact details, store assets and the Play Console declarations/testing requirements. Preview is for installation and testing; nothing is uploaded automatically.

Connect a Todoist token in Control Panel, or choose Explore a demo. The app reads projects and tasks, follows cursor pages, and backfills activity in 30-day windows to the account's join date. If that date is unavailable, it loads up to twelve weeks and warns that older history may be missing. It saves checkpoints and merges later updates by event ID. A replacement token for the same account preserves history. To switch accounts, first disconnect and explicitly remove the existing local history and settings. Failed or cancelled syncs preserve saved data. Demo never overwrites account data. Tokens stay in Android Keystore-backed encrypted storage.

Android connects directly to `https://api.todoist.com` over HTTPS; it does not connect to the desktop backend. Emulators and phones need internet access, not an emulator host address or a LAN server URL. On failure, use the account's retry or refresh action; saved history remains available. Credentials are never placed in URLs.

Sync uses the [Todoist API](https://developer.todoist.com/api/v1/): `GET /api/v1/user` for account identity, then paginated `projects`, `projects/archived`, `tasks` and `activities` requests. List responses must contain `results` and `next_cursor`; activity requests use `date_from` and the exclusive `date_to`. The FastAPI dashboard routes are used by the desktop web app, not by Android. A sync continues when its screen is stopped; explicit cancellation discards obsolete responses while preserving completed checkpoints.

Android stores the encrypted current and staged tokens in app-private `auth` preferences using an Android Keystore key. The app-private `dashboard-v1.json` snapshot contains activity, tasks, project mappings and a token fingerprint; it is not separately encrypted by the app. The `rules` preferences contain alert labels and dashboard settings, while WebView storage contains view choices and search text. Treat all of these as private data. Android cloud backup and device transfer are disabled for this data; moving devices or reinstalling requires reconnecting and rebuilding local history.

Debug builds enable WebView inspection, allowing a connected debugger to inspect screen data, including a token being entered. Preview and release builds request that WebView inspection be disabled; Android userdebug images can override that setting.

A rejected saved token is not retried automatically. Enter a different token to reconnect. If a saved credential cannot be opened, entering the original token can recover a matching snapshot; otherwise the snapshot remains untouched until you explicitly disconnect and remove local data.

The desktop backend uses its own Todoist `API_KEY` environment value or local `.env` file. Its admin routes have no separate user authentication and its normal launcher binds to loopback; CORS does not authenticate local clients. Android never sends its credential to that backend. Keep the desktop API local and protect its environment file with the operating system's file permissions.

For existing desktop project adjustments, save and export them from Project Adjustments, transfer the JSON to the phone, then choose **Import project adjustments** in Control Panel. The file contains project names. Imported mappings stay with that account and survive refreshes; export and import again after changing them on the computer. Todoist may omit archived projects' parent links, so the app also retains links it observed before archiving.

Overview shows completion trends, forecasts, project contributions and charts derived from the history available on the device, including a project timeline. Projects supports search and priority filters; Activity shows recent actions. Control Panel provides alert settings and project grouping. These mobile charts use locally cached data and do not guarantee full parity with desktop analysis. Alert preferences and history remain local to each client.

To run interaction tests on a dedicated emulator:

```bash
./android/gradlew -p android connectedDebugAndroidTest
adb install -r android/app/build/outputs/apk/debug/app-debug.apk
node --test frontend/tests/device/android-ui.test.cjs
npm --prefix frontend exec -- playwright install android
adb install -r dist/android/todometry-preview.apk
node --test frontend/tests/device/android-release.test.cjs
```

These tests clear emulator app data and exercise offline rendering, actual/forecast totals, search, the keyboard, rotation and saved settings. CI also installs the optimized Preview APK and checks offline charts, navigation, rotation and disabled debugging without a WebView inspector. It uses 1440×3120/density 560 on Android 15 and 1080×2340/density 420 on Android 16/17, with font scale 130%. The Android 16 Play Store image is a production OS build and verifies that the release WebView inspector is disabled; userdebug OS images force it on. Standard Android emulation does not reproduce Samsung One UI.
