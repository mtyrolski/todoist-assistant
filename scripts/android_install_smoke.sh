#!/usr/bin/env bash
set -euo pipefail

APK_PATH="${1:-}"
PACKAGE_NAME="${ANDROID_PACKAGE_NAME:-dev.mtyrolski.todoistassistant}"
MAIN_ACTIVITY="${ANDROID_MAIN_ACTIVITY:-dev.mtyrolski.todoistassistant.MainActivity}"

if [ -z "${APK_PATH}" ]; then
  echo "Usage: $0 path/to/app.apk" >&2
  exit 2
fi

if [ ! -f "${APK_PATH}" ]; then
  echo "APK not found: ${APK_PATH}" >&2
  exit 1
fi

if ! command -v adb >/dev/null 2>&1; then
  echo "adb is required for Android install smoke tests" >&2
  exit 1
fi

dump_diagnostics() {
  echo "== adb devices =="
  adb devices -l || true
  echo "== package path =="
  adb shell pm path "${PACKAGE_NAME}" || true
  echo "== recent logcat =="
  adb logcat -d -t 200 || true
}

wait_for_boot() {
  adb wait-for-device
  for _ in $(seq 1 120); do
    if [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ]; then
      return 0
    fi
    sleep 1
  done
  echo "Android device did not finish booting" >&2
  dump_diagnostics
  exit 1
}

trap 'status=$?; if [ "${status}" -ne 0 ]; then dump_diagnostics; fi; exit "${status}"' EXIT

wait_for_boot
adb shell input keyevent 82 >/dev/null 2>&1 || true

adb uninstall "${PACKAGE_NAME}" >/dev/null 2>&1 || true
adb install -r "${APK_PATH}"
adb shell pm path "${PACKAGE_NAME}" >/dev/null

adb shell am force-stop "${PACKAGE_NAME}" >/dev/null 2>&1 || true
adb shell am start -W -n "${PACKAGE_NAME}/${MAIN_ACTIVITY}" | tee /tmp/android-start-output.txt

if ! grep -Eq "Status: ok|Complete" /tmp/android-start-output.txt; then
  echo "Activity launch did not report success" >&2
  exit 1
fi

sleep 3
if ! adb shell pidof "${PACKAGE_NAME}" >/dev/null; then
  echo "Application process is not running after launch" >&2
  exit 1
fi

trap - EXIT
echo "Android install smoke passed"
