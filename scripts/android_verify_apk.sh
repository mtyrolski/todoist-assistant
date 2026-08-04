#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APK_PATH="${1:-}"
EXPECTED_PACKAGE="${ANDROID_EXPECTED_PACKAGE:-dev.mtyrolski.todoistassistant}"
EXPECTED_ACTIVITY="${ANDROID_EXPECTED_ACTIVITY:-dev.mtyrolski.todoistassistant.MainActivity}"
EXPECTED_MIN_SDK="${ANDROID_EXPECTED_MIN_SDK:-26}"
EXPECTED_TARGET_SDK="${ANDROID_EXPECTED_TARGET_SDK:-33}"
EXPECTED_DEBUGGABLE="${ANDROID_EXPECT_DEBUGGABLE:-}"

if [ -z "${APK_PATH}" ]; then
  echo "Usage: $0 path/to/app.apk" >&2
  exit 2
fi

if [ ! -f "${APK_PATH}" ]; then
  echo "APK not found: ${APK_PATH}" >&2
  exit 1
fi

"${ROOT_DIR}/scripts/android_bootstrap_sdk.sh" >/dev/null

SDK_DIR="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-${ROOT_DIR}/android/.android-sdk}}"
BUILD_TOOLS_DIR="$(find "${SDK_DIR}/build-tools" -mindepth 1 -maxdepth 1 -type d | sort -V | tail -n 1)"
AAPT="${BUILD_TOOLS_DIR}/aapt"
APKSIGNER="${BUILD_TOOLS_DIR}/apksigner"

if [ ! -x "${AAPT}" ] || [ ! -x "${APKSIGNER}" ]; then
  echo "Android build tools are missing aapt or apksigner under ${BUILD_TOOLS_DIR}" >&2
  exit 1
fi

echo "Verifying APK signature: ${APK_PATH}"
"${APKSIGNER}" verify --verbose --print-certs "${APK_PATH}"

echo "Verifying APK manifest metadata"
BADGING="$("${AAPT}" dump badging "${APK_PATH}")"

require_badging_line() {
  local pattern="$1"
  local message="$2"
  if ! grep -Eq "${pattern}" <<<"${BADGING}"; then
    echo "${message}" >&2
    echo "APK badging:" >&2
    echo "${BADGING}" >&2
    exit 1
  fi
}

require_badging_line "^package: name='${EXPECTED_PACKAGE}'" \
  "Unexpected Android package name; expected ${EXPECTED_PACKAGE}"
require_badging_line "^launchable-activity: name='${EXPECTED_ACTIVITY}'" \
  "Missing launchable activity ${EXPECTED_ACTIVITY}"
require_badging_line "^sdkVersion:'${EXPECTED_MIN_SDK}'" \
  "Unexpected minSdk; expected ${EXPECTED_MIN_SDK}"
require_badging_line "^targetSdkVersion:'${EXPECTED_TARGET_SDK}'" \
  "Unexpected targetSdk; expected ${EXPECTED_TARGET_SDK}"

case "${EXPECTED_DEBUGGABLE}" in
  true)
    require_badging_line "^application-debuggable" \
      "APK is not debuggable, but ANDROID_EXPECT_DEBUGGABLE=true"
    ;;
  false)
    if grep -Eq "^application-debuggable" <<<"${BADGING}"; then
      echo "APK is debuggable, but ANDROID_EXPECT_DEBUGGABLE=false" >&2
      echo "APK badging:" >&2
      echo "${BADGING}" >&2
      exit 1
    fi
    ;;
  "")
    ;;
  *)
    echo "Unsupported ANDROID_EXPECT_DEBUGGABLE value: ${EXPECTED_DEBUGGABLE} (use true or false)" >&2
    exit 2
    ;;
esac

echo "APK verification passed"
