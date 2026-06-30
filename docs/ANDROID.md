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
