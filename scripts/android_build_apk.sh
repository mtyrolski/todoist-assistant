#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
"${ROOT_DIR}/scripts/android_bootstrap_sdk.sh"

if [ -f "${ROOT_DIR}/android/.java-home" ]; then
  JAVA_HOME="$(cat "${ROOT_DIR}/android/.java-home")"
  export JAVA_HOME
  export PATH="${JAVA_HOME}/bin:${PATH}"
fi

BUILD_VARIANT="${ANDROID_BUILD_VARIANT:-Debug}"
case "${BUILD_VARIANT}" in
  Debug|debug)
    BUILD_VARIANT="Debug"
    ;;
  Release|release)
    BUILD_VARIANT="Release"
    ;;
  *)
    echo "Unsupported Android build variant: ${BUILD_VARIANT} (use Debug or Release)" >&2
    exit 2
    ;;
esac

cd "${ROOT_DIR}/android"
./gradlew ":app:assemble${BUILD_VARIANT}"
