#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
"${ROOT_DIR}/scripts/android_bootstrap_sdk.sh"

if [ -f "${ROOT_DIR}/android/.java-home" ]; then
  JAVA_HOME="$(cat "${ROOT_DIR}/android/.java-home")"
  export JAVA_HOME
  export PATH="${JAVA_HOME}/bin:${PATH}"
fi

cd "${ROOT_DIR}/android"
./gradlew :app:assembleDebug
