#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ANDROID_DIR="${ROOT_DIR}/android"
SDK_DIR="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-${ANDROID_DIR}/.android-sdk}}"
JDK_DIR="${ANDROID_DIR}/.jdk"
TOOLS_DIR="${SDK_DIR}/cmdline-tools/latest"
TOOLS_ZIP="${ANDROID_DIR}/.gradle/android-commandlinetools.zip"
TOOLS_URL="https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip"
JDK_TAR="${ANDROID_DIR}/.gradle/jdk17.tar.gz"
JDK_URL="https://api.adoptium.net/v3/binary/latest/17/ga/linux/x64/jdk/hotspot/normal/eclipse?project=jdk"

mkdir -p "${ANDROID_DIR}/.gradle" "${SDK_DIR}/cmdline-tools" "${JDK_DIR}"

java_major_version() {
  local java_bin="${1}"
  if [ ! -x "${java_bin}" ]; then
    echo 0
    return
  fi
  "${java_bin}" -version 2>&1 | awk -F[\".] '/version/ {print $2; exit}'
}

JAVA_BIN="${JAVA_HOME:-}/bin/java"
if [ "$(java_major_version "${JAVA_BIN}")" -lt 17 ]; then
  JAVA_BIN="$(command -v java || true)"
fi

if [ "$(java_major_version "${JAVA_BIN}")" -lt 17 ]; then
  if ! find "${JDK_DIR}" -maxdepth 3 -type f -path "*/bin/java" | grep -q .; then
    if [ ! -f "${JDK_TAR}" ]; then
      curl -fL "${JDK_URL}" -o "${JDK_TAR}"
    fi
    rm -rf "${JDK_DIR:?}"/*
    tar -xzf "${JDK_TAR}" -C "${JDK_DIR}"
  fi
  JAVA_HOME="$(find "${JDK_DIR}" -maxdepth 3 -type f -path "*/bin/java" -print -quit | sed 's#/bin/java##')"
  if [ -z "${JAVA_HOME}" ]; then
    echo "Failed to locate bootstrapped JDK 17 under ${JDK_DIR}" >&2
    exit 1
  fi
  export JAVA_HOME
  export PATH="${JAVA_HOME}/bin:${PATH}"
fi

if [ ! -x "${TOOLS_DIR}/bin/sdkmanager" ]; then
  if [ ! -f "${TOOLS_ZIP}" ]; then
    curl -fL "${TOOLS_URL}" -o "${TOOLS_ZIP}"
  fi
  rm -rf "${SDK_DIR}/cmdline-tools/latest" "${SDK_DIR}/cmdline-tools/cmdline-tools"
  unzip -q "${TOOLS_ZIP}" -d "${SDK_DIR}/cmdline-tools"
  mv "${SDK_DIR}/cmdline-tools/cmdline-tools" "${TOOLS_DIR}"
fi

set +o pipefail
yes | "${TOOLS_DIR}/bin/sdkmanager" --sdk_root="${SDK_DIR}" --licenses >/dev/null
set -o pipefail
"${TOOLS_DIR}/bin/sdkmanager" --sdk_root="${SDK_DIR}" \
  "platform-tools" \
  "platforms;android-33" \
  "build-tools;33.0.2"

cat > "${ANDROID_DIR}/local.properties" <<EOF
sdk.dir=${SDK_DIR}
EOF

echo "Android SDK ready at ${SDK_DIR}"
if [ -n "${JAVA_HOME:-}" ]; then
  echo "${JAVA_HOME}" > "${ANDROID_DIR}/.java-home"
fi
