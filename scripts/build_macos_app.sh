#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="${REPO_ROOT}/dist/macos"
FRONTEND_DIR="${REPO_ROOT}/frontend"
SPEC_FILE="${REPO_ROOT}/packaging/macos/pyinstaller.spec"
APP_NAME="TodoistAssistant.app"
APP_PATH="${DIST_DIR}/${APP_NAME}"
ICON_PNG="${REPO_ROOT}/img/logo.png"
ICON_ICNS="${REPO_ROOT}/packaging/macos/TodoistAssistant.icns"
NODE_VERSION="20.11.1"
INCLUDE_DASHBOARD=1

usage() {
  echo "Usage: $0 [--no-dashboard] [--node-version VERSION]" >&2
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

ensure_icon() {
  if [ -f "${ICON_ICNS}" ]; then
    return
  fi
  if [ ! -f "${ICON_PNG}" ]; then
    echo "Icon source not found at ${ICON_PNG}. Using default app icon." >&2
    return
  fi
  if ! command -v sips >/dev/null 2>&1 || ! command -v iconutil >/dev/null 2>&1; then
    echo "sips/iconutil not available; skipping icon generation." >&2
    return
  fi
  tmp_dir="$(mktemp -d)"
  iconset="${tmp_dir}/TodoistAssistant.iconset"
  mkdir -p "${iconset}"
  for size in 16 32 128 256 512; do
    sips -z "${size}" "${size}" "${ICON_PNG}" --out "${iconset}/icon_${size}x${size}.png" >/dev/null
    double=$((size * 2))
    sips -z "${double}" "${double}" "${ICON_PNG}" --out "${iconset}/icon_${size}x${size}@2x.png" >/dev/null
  done
  iconutil -c icns "${iconset}" -o "${ICON_ICNS}"
  rm -rf "${tmp_dir}"
}

download_node() {
  local dest_dir="$1"
  local version="$2"
  local arch
  arch="$(uname -m)"
  if [ "${arch}" = "arm64" ]; then
    arch="darwin-arm64"
  elif [ "${arch}" = "x86_64" ]; then
    arch="darwin-x64"
  else
    echo "Unsupported macOS architecture: ${arch}" >&2
    exit 1
  fi

  local tarball="node-v${version}-${arch}.tar.gz"
  local url="https://nodejs.org/dist/v${version}/${tarball}"
  local tar_path="${DIST_DIR}/${tarball}"
  local extract_dir="${DIST_DIR}/node-v${version}-${arch}"

  require_cmd curl
  require_cmd tar

  if [ ! -f "${tar_path}" ]; then
    echo "Downloading Node.js ${version}..." >&2
    curl -fsSL "${url}" -o "${tar_path}"
  fi

  rm -rf "${extract_dir}"
  tar -xzf "${tar_path}" -C "${DIST_DIR}"

  rm -rf "${dest_dir}"
  mkdir -p "${dest_dir}"
  cp -R "${extract_dir}/." "${dest_dir}/"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --no-dashboard)
      INCLUDE_DASHBOARD=0
      shift
      ;;
    --node-version)
      NODE_VERSION="$2"
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

if [ ! -f "${SPEC_FILE}" ]; then
  echo "PyInstaller spec not found at ${SPEC_FILE}" >&2
  exit 1
fi

version="$(uv run python3 -m scripts.get_version)"
if [ -z "${version}" ] || [ "${version}" = "0.0.0" ]; then
  echo "Failed to resolve project version." >&2
  exit 1
fi

ensure_icon || true

mkdir -p "${DIST_DIR}"

if [ "${INCLUDE_DASHBOARD}" -eq 1 ]; then
  if [ ! -d "${FRONTEND_DIR}" ]; then
    echo "Dashboard directory not found at ${FRONTEND_DIR}" >&2
    exit 1
  fi
  require_cmd npm
  export NEXT_TELEMETRY_DISABLED=1
  (cd "${FRONTEND_DIR}" && npm ci)
  (cd "${FRONTEND_DIR}" && npm run build)
fi

rm -rf "${APP_PATH}" "${DIST_DIR}/build"
export TODOIST_VERSION="${version}"
uv run python3 -m PyInstaller "${SPEC_FILE}" --distpath "${DIST_DIR}" --workpath "${DIST_DIR}/build" --clean

if [ "${INCLUDE_DASHBOARD}" -eq 1 ]; then
  stage_dir="${DIST_DIR}/app_stage"
  rm -rf "${stage_dir}"
  mkdir -p "${stage_dir}"

  standalone_dir="${FRONTEND_DIR}/.next/standalone"
  static_dir="${FRONTEND_DIR}/.next/static"
  public_dir="${FRONTEND_DIR}/public"

  if [ ! -d "${standalone_dir}" ]; then
    echo "Next.js standalone output missing. Ensure next.config.js sets output=standalone." >&2
    exit 1
  fi

  cp -R "${standalone_dir}" "${stage_dir}/frontend"
  if [ -d "${static_dir}" ]; then
    mkdir -p "${stage_dir}/frontend/.next"
    cp -R "${static_dir}" "${stage_dir}/frontend/.next/static"
  fi
  if [ -d "${public_dir}" ]; then
    cp -R "${public_dir}" "${stage_dir}/frontend/public"
  fi

  if [ ! -f "${stage_dir}/frontend/server.js" ]; then
    echo "Next.js standalone server.js missing in staged frontend." >&2
    exit 1
  fi

  download_node "${stage_dir}/node" "${NODE_VERSION}"

  resources_dir="${APP_PATH}/Contents/Resources"
  rm -rf "${resources_dir}/frontend" "${resources_dir}/node"
  mkdir -p "${resources_dir}"
  cp -R "${stage_dir}/frontend" "${resources_dir}/frontend"
  cp -R "${stage_dir}/node" "${resources_dir}/node"
fi

echo "Built macOS app: ${APP_PATH}"
