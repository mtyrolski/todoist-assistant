# Standalone Android direction

The intended Android product is one installable app that fetches Todoist data, keeps it on the device, and renders the dashboard and plots. It must not require a separately running Python API, Next.js server, or desktop computer.

This repository currently builds a desktop web dashboard. The Android implementation is future work; no APK is produced by this change.

The current cleanup keeps the data boundary small: `todoist/features/data_sync.py` owns incremental, locked activity cache updates, while the plot modules remain separate from API routes. An Android implementation will need an on-device equivalent for Todoist requests, durable cache and sync, and Plotly rendering in its own view layer. The cached data format is Python joblib and is not an Android storage contract. A native app should use a portable on-device store and define a versioned migration path before importing desktop caches.

Project adjustments are user data and should be stored locally on the device. The desktop version currently stores them in `personal/` Python files; that format is likewise not the Android storage contract.
