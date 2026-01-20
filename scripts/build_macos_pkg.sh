#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="${REPO_ROOT}/dist/macos"
BUILD_DIR="${DIST_DIR}/pkgbuild"
PKG_ROOT="${BUILD_DIR}/root"
SCRIPTS_DIR="${REPO_ROOT}/packaging/macos/scripts"
PYINSTALLER_DIST="${BUILD_DIR}/pyinstaller"
APP_ROOT="${PKG_ROOT}/usr/local/todoist-assistant"
BIN_DIR="${PKG_ROOT}/usr/local/bin"
ETC_DIR="${PKG_ROOT}/usr/local/etc/todoist-assistant"

usage() {
  echo "Usage: $0 [--sign \"Developer ID Installer: ...\"]" >&2
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Required command not found: $1" >&2
    exit 1
  fi
}

ensure_macos() {
  if [ "$(uname -s)" != "Darwin" ]; then
    echo "This script must be run on macOS." >&2
    exit 1
  fi
}

SIGN_ID=""

while [ "$#" -gt 0 ]; do
  case "$1" in
    --sign)
      SIGN_ID="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

ensure_macos
require_cmd uv
require_cmd pkgbuild
require_cmd productbuild

version="$(uv run python3 -m scripts.get_version)"
if [ -z "${version}" ] || [ "${version}" = "0.0.0" ]; then
  echo "Failed to resolve project version." >&2
  exit 1
fi

if [ ! -d "${SCRIPTS_DIR}" ]; then
  echo "Installer scripts directory not found at ${SCRIPTS_DIR}" >&2
  exit 1
fi

rm -rf "${BUILD_DIR}"
mkdir -p "${APP_ROOT}" "${BIN_DIR}" "${ETC_DIR}"

echo "Building PyInstaller CLI bundle..." >&2
pushd "${REPO_ROOT}" >/dev/null
uv run python3 -m PyInstaller \
  --clean \
  --name todoist-assistant \
  --onedir todoist/cli.py \
  --distpath "${PYINSTALLER_DIST}" \
  --workpath "${BUILD_DIR}/pyinstaller-build"
popd >/dev/null

if [ ! -d "${PYINSTALLER_DIST}/todoist-assistant" ]; then
  echo "PyInstaller output not found at ${PYINSTALLER_DIST}/todoist-assistant" >&2
  exit 1
fi

cp -R "${PYINSTALLER_DIST}/todoist-assistant/." "${APP_ROOT}/"

cat > "${BIN_DIR}/todoist-assistant" <<'EOF'
#!/bin/sh
exec /usr/local/todoist-assistant/todoist-assistant "$@"
EOF
chmod +x "${BIN_DIR}/todoist-assistant"

if [ -d "${REPO_ROOT}/configs" ]; then
  cp -R "${REPO_ROOT}/configs/." "${ETC_DIR}/"
fi

if [ -f "${REPO_ROOT}/.env.example" ]; then
  cp "${REPO_ROOT}/.env.example" "${ETC_DIR}/.env.template"
fi

if [ -f "${REPO_ROOT}/README.md" ]; then
  cp "${REPO_ROOT}/README.md" "${APP_ROOT}/README.md"
fi

component_pkg="${BUILD_DIR}/todoist-assistant-component.pkg"
pkgbuild \
  --root "${PKG_ROOT}" \
  --identifier "com.todoist.assistant" \
  --version "${version}" \
  --scripts "${SCRIPTS_DIR}" \
  "${component_pkg}"

output_pkg="${DIST_DIR}/todoist-assistant-${version}.pkg"
if [ -n "${SIGN_ID}" ]; then
  productbuild --sign "${SIGN_ID}" --package "${component_pkg}" "${output_pkg}"
else
  productbuild --package "${component_pkg}" "${output_pkg}"
fi

echo "Built macOS pkg: ${output_pkg}"
echo "Optional signing: pass --sign \"Developer ID Installer: Your Name\""
