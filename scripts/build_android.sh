#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
mode="${1:-debug}"
case "$mode" in
    debug|preview|bundle) [ "$#" -eq 0 ] || shift ;;
    *) echo 'Usage: build_android.sh [debug|preview|bundle] [Gradle options]' >&2; exit 1 ;;
esac
if ! command -v java >/dev/null 2>&1 && [ -z "${JAVA_HOME:-}" ]; then
    echo 'JDK 17 is required. Set JAVA_HOME before building.' >&2
    exit 1
fi
android_sdk="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-}}"
if [ -z "$android_sdk" ] && { [ "$mode" = preview ] || [ ! -f "$repo_root/android/local.properties" ]; }; then
    echo 'Set ANDROID_HOME to an Android SDK with platforms;android-36 and build-tools;35.0.0 installed.' >&2
    exit 1
fi
if [ "$mode" = preview ]; then
    signing_dir="${ANDROID_PREVIEW_SIGNING_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/todoist-assistant/signing/preview}"
    mkdir -p "$signing_dir"
    signing_dir="$(cd -- "$signing_dir" && pwd)"
    chmod 700 "$signing_dir"
    if [ ! -f "$signing_dir/preview.keystore" ]; then
        if [ -e "$signing_dir/password" ]; then
            echo 'Preview keystore is missing but its password file exists. Restore the keystore or choose another signing directory.' >&2
            exit 1
        fi
        (
            umask 077
            node -e "process.stdout.write(require('node:crypto').randomBytes(32).toString('hex'))" > "$signing_dir/password"
            "${JAVA_HOME:+$JAVA_HOME/bin/}keytool" -genkeypair -noprompt -storetype PKCS12 \
                -keystore "$signing_dir/preview.keystore" -alias preview \
                -storepass:file "$signing_dir/password" -keypass:file "$signing_dir/password" \
                -keyalg RSA -keysize 3072 -validity 10000 -dname 'CN=Telemetry for Todoist Preview'
        )
    fi
    export ANDROID_SIGNING_STORE_FILE="$signing_dir/preview.keystore"
    export ANDROID_SIGNING_STORE_PASSWORD="$(cat "$signing_dir/password")"
    export ANDROID_SIGNING_KEY_ALIAS=preview
    export ANDROID_SIGNING_KEY_PASSWORD="$ANDROID_SIGNING_STORE_PASSWORD"
fi
npm --prefix "$repo_root/frontend" ci --no-audit --no-fund
checks=(:app:spotlessJavaCheck :app:testDebugUnitTest)
case "$mode" in
    debug) checks+=(:app:lintDebug :app:assembleDebug); artifact='apk/debug/app-debug.apk'; output='todoist-assistant-debug.apk' ;;
    preview) checks+=(-Ppreview=true :app:lintRelease :app:assembleRelease); artifact='apk/release/app-release.apk'; output='todoist-assistant-preview.apk' ;;
    bundle) checks+=(:app:lintRelease :app:bundleRelease); artifact='bundle/release/app-release.aab'; output='todoist-assistant-release.aab' ;;
esac
"$repo_root/android/gradlew" -p "$repo_root/android" --no-daemon "${checks[@]}" "$@"
mkdir -p "$repo_root/dist/android"
cp "$repo_root/android/app/build/outputs/$artifact" "$repo_root/dist/android/$output"
if [ "$mode" != debug ]; then
    cp "$repo_root/android/app/build/outputs/mapping/release/mapping.txt" "$repo_root/dist/android/$mode-mapping.txt"
fi
if [ "$mode" = preview ]; then
    "$android_sdk/build-tools/35.0.0/apksigner" verify "$repo_root/dist/android/$output"
    echo "Keep a private backup of $signing_dir to sign future Preview updates."
fi
echo "Built: $repo_root/dist/android/$output"
