# Android app

The Android app is a native client for the existing Todoist Assistant local API. It lets a user save credentials, load the dashboard Plotly payload, view plots in Android WebViews, run automations such as `@ai-breakdown`, and schedule background automation runs through Android `JobScheduler`.

## Runtime model

Run the Python API on a machine reachable from Android:

```bash
make run_api
```

Use these API URLs in the Android app:

- Android emulator: `http://10.0.2.2:8000`
- Physical Android device: `http://<your-computer-lan-ip>:8000`

The app sends the pasted Todoist API token to `/api/admin/api_token`; the backend writes it to the existing runtime `.env`. The Android text field is cleared after saving and only the masked backend status is shown afterward.

## Build

The build script installs a repo-local JDK 17 and Android SDK if they are not already available:

```bash
make android_apk
```

The debug APK is produced at:

```text
android/app/build/outputs/apk/debug/app-debug.apk
```

For real-device sideload testing, build the staging APK instead. It uses release-like settings, is non-debuggable, and is signed automatically for manual installation:

```bash
make android_staging_apk
```

The staging APK is produced at:

```text
android/app/build/outputs/apk/staging/app-staging.apk
```

Verify the debug APK before sharing it:

```bash
make android_verify_debug_apk
```

Verify the staging APK before sharing it:

```bash
make android_verify_staging_apk
```

With a device or emulator connected through `adb`, run an installation and launch smoke test:

```bash
make android_install_smoke_staging
```

## CI artifacts

GitHub Actions builds, verifies, installs, and launches the staging APK on an emulator. The artifact named `todoist-assistant-android-sideload-apk` contains:

```text
app-staging.apk
```

Use that artifact for branch and pull request testing. It is signed with Android's debug signing key, so it can be installed manually on a phone after allowing installs from the source app. Uninstall any previous Todoist Assistant APK before installing an artifact from a different workflow run or machine, because Android rejects updates signed by a different key.

Do not use `app-release-unsigned.apk` for manual installation. Android rejects unsigned APKs and often shows only a generic "App not installed" dialog.

When release signing secrets are configured, CI also builds and verifies the artifact named `todoist-assistant-android-signed-release-apk`, which contains:

```text
app-release.apk
```

Tagged Android release builds require signing secrets. If the secrets are missing, the workflow fails instead of publishing an unusable unsigned release APK.

## Release signing

The release variant is installable only when it is signed. Generate a release keystore once and keep using the same keystore for updates:

```bash
keytool -genkeypair -v \
  -keystore todoist-assistant-release.jks \
  -alias todoist-assistant \
  -keyalg RSA \
  -keysize 2048 \
  -validity 10000
```

Encode the keystore for GitHub Actions:

```bash
base64 -w0 todoist-assistant-release.jks
```

On macOS, use:

```bash
base64 < todoist-assistant-release.jks | tr -d '\n'
```

Set these GitHub repository secrets:

```text
ANDROID_SIGNING_KEYSTORE_BASE64
ANDROID_SIGNING_STORE_PASSWORD
ANDROID_SIGNING_KEY_ALIAS
ANDROID_SIGNING_KEY_PASSWORD
```

For a local signed release build, set the Gradle signing environment variables and build:

```bash
export ANDROID_KEYSTORE_PATH=/path/to/todoist-assistant-release.jks
export ANDROID_KEYSTORE_PASSWORD='...'
export ANDROID_KEY_ALIAS=todoist-assistant
export ANDROID_KEY_PASSWORD='...'
make android_release_apk
```

The signed release APK is produced at:

```text
android/app/build/outputs/apk/release/app-release.apk
```

Verify it before distribution:

```bash
make android_verify_release_apk
```

If those signing variables are not set, Gradle may still produce:

```text
android/app/build/outputs/apk/release/app-release-unsigned.apk
```

That file is not installable and should not be distributed.

## Installation troubleshooting

If Android shows a generic installation failure, install with `adb` to get the real failure code:

```bash
adb install -r path/to/app.apk
```

Common causes:

- `INSTALL_PARSE_FAILED_NO_CERTIFICATES`: the APK is unsigned. Use `app-staging.apk` or a signed `app-release.apk`.
- `INSTALL_FAILED_UPDATE_INCOMPATIBLE`: a previous APK with the same package name was signed by a different key. Uninstall the existing app first, then install again.
- `INSTALL_FAILED_OLDER_SDK`: the device is older than Android 8.0. The app requires `minSdkVersion 26`.
- `INSTALL_FAILED_INVALID_APK`: the downloaded APK or artifact zip was not extracted correctly. Install the `.apk` file inside the artifact, not the artifact `.zip`.

On Samsung devices, also check that the app you install from, such as Files, My Files, Telegram, or a browser, is allowed to install unknown apps. If Samsung Auto Blocker or a similar security setting is enabled, temporarily disable that protection or install through `adb` while testing.

For the full install-and-launch smoke check:

```bash
adb devices -l
./scripts/android_install_smoke.sh path/to/app.apk
```

## App capabilities

- Save Todoist API token and timezone through the existing admin API.
- Check API health and masked token status.
- Fetch `/api/dashboard/home` and render returned Plotly figures.
- List configured automations from `/api/admin/automations`.
- Run a selected automation by name, for example `@ai-breakdown`.
- Run all automations by entering `ALL`.
- Force one observer tick with `/api/admin/observer/run?force=true`.
- Schedule repeated background automation starts every 15 minutes or more.

## Notes

Android limits periodic background jobs to a minimum interval of 15 minutes. The scheduled job starts an async backend automation job; actual execution still happens in the Python API process so existing automation behavior, logs, and caches are preserved.
