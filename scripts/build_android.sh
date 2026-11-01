#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if ! command -v java >/dev/null 2>&1 && [ -z "${JAVA_HOME:-}" ]; then
    echo 'JDK 17 is required. Set JAVA_HOME before building.' >&2
    exit 1
fi
android_sdk="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-}}"
if [ -z "$android_sdk" ] && [ ! -f "$repo_root/android/local.properties" ]; then
    echo 'Set ANDROID_HOME to an Android SDK with platforms;android-35 and build-tools;35.0.0 installed.' >&2
    exit 1
fi
"$repo_root/android/gradlew" -p "$repo_root/android" --no-daemon \
    :app:testDebugUnitTest :app:lintDebug :app:assembleDebug "$@"
mkdir -p "$repo_root/dist/android"
cp "$repo_root/android/app/build/outputs/apk/debug/app-debug.apk" "$repo_root/dist/android/todoist-assistant-debug.apk"
echo "Installable APK: $repo_root/dist/android/todoist-assistant-debug.apk"
