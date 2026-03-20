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
PREFER_SYSTEM_NODE=0
SIGN_ID=""
ENTITLEMENTS=""

usage() {
  echo "Usage: $0 [--no-dashboard] [--node-version VERSION] [--prefer-system-node] [--sign \"Developer ID Application: ...\"] [--entitlements path]" >&2
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Required command not found: $1" >&2
    exit 1
  fi
}

retry() {
  local attempts="$1"
  local delay="$2"
  shift 2
  local n=1
  until "$@"; do
    if [ "${n}" -ge "${attempts}" ]; then
      echo "Command failed after ${attempts} attempts: $*" >&2
      return 1
    fi
    echo "Command failed (attempt ${n}/${attempts}); retrying in ${delay}s..." >&2
    sleep "${delay}"
    n=$((n + 1))
    delay=$((delay * 2))
  done
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

host_arch() {
  local arch
  arch="$(uname -m)"
  if [ "${arch}" = "arm64" ]; then
    echo "arm64"
  elif [ "${arch}" = "x86_64" ]; then
    echo "x86_64"
  else
    echo "${arch}"
  fi
}

node_arch_matches() {
  local expected_arch="$1"
  local node_arch
  node_arch="$(node -p 'process.arch' 2>/dev/null || true)"
  if [ "${node_arch}" = "arm64" ]; then
    node_arch="arm64"
  elif [ "${node_arch}" = "x64" ]; then
    node_arch="x86_64"
  fi
  [ "${node_arch}" = "${expected_arch}" ]
}

node_version_matches() {
  local expected_version="$1"
  local node_version
  node_version="$(node -p 'process.versions.node' 2>/dev/null || true)"
  [ "${node_version}" = "${expected_version}" ]
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
  require_cmd shasum

  shasums_url="https://nodejs.org/dist/v${version}/SHASUMS256.txt"
  expected_sha="$(retry 3 2 curl -fsSL "${shasums_url}" | awk "/${tarball}\$/ {print \$1}")"
  if [ -z "${expected_sha}" ]; then
    echo "Failed to resolve checksum for ${tarball}" >&2
    exit 1
  fi

  verify_tarball() {
    echo "${expected_sha}  ${tar_path}" | shasum -a 256 -c - >/dev/null
  }

  fetch_tarball() {
    echo "Downloading Node.js ${version}..." >&2
    retry 3 2 curl -fsSL "${url}" -o "${tar_path}"
    verify_tarball
  }

  if [ -f "${tar_path}" ] && verify_tarball; then
    echo "Using cached Node.js tarball at ${tar_path}" >&2
  else
    rm -f "${tar_path}"
    fetch_tarball
  fi

  rm -rf "${extract_dir}"
  tar -xzf "${tar_path}" -C "${DIST_DIR}"

  rm -rf "${dest_dir}"
  mkdir -p "${dest_dir}"
  cp -R "${extract_dir}/." "${dest_dir}/"
}

stage_node_runtime() {
  local dest_dir="$1"
  local version="$2"
  local expected_arch
  expected_arch="$(host_arch)"
  local node_path
  node_path="$(command -v node 2>/dev/null || true)"
  if [ "${PREFER_SYSTEM_NODE}" -eq 1 ] && [ -n "${node_path}" ]; then
    if node_arch_matches "${expected_arch}" && node_version_matches "${version}"; then
      echo "Bundling Node runtime from ${node_path}" >&2
      rm -rf "${dest_dir}"
      mkdir -p "${dest_dir}"
      cp -L "${node_path}" "${dest_dir}/node"
      return
    fi
    echo "System node does not match requested ${version} (${expected_arch}); downloading Node runtime." >&2
  fi

  download_node "${dest_dir}" "${version}"
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
    --prefer-system-node)
      PREFER_SYSTEM_NODE=1
      shift
      ;;
    --sign)
      SIGN_ID="$2"
      shift 2
      ;;
    --entitlements)
      ENTITLEMENTS="$2"
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

if [ -z "${SIGN_ID}" ] && [ -n "${MACOS_APP_SIGN_IDENTITY:-}" ]; then
  SIGN_ID="${MACOS_APP_SIGN_IDENTITY}"
fi
if [ -z "${ENTITLEMENTS}" ] && [ -n "${MACOS_APP_SIGN_ENTITLEMENTS:-}" ]; then
  ENTITLEMENTS="${MACOS_APP_SIGN_ENTITLEMENTS}"
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
  if [ ! -f "${FRONTEND_DIR}/package-lock.json" ]; then
    echo "package-lock.json missing in frontend; npm ci requires a lockfile." >&2
    exit 1
  fi
  require_cmd npm
  export NEXT_TELEMETRY_DISABLED=1
  (cd "${FRONTEND_DIR}" && retry 3 2 npm ci --no-audit --no-fund)
  (cd "${FRONTEND_DIR}" && retry 2 2 npm run build)
fi

rm -rf "${APP_PATH}" "${DIST_DIR}/build"
export TODOIST_VERSION="${version}"
pushd "${REPO_ROOT}" >/dev/null
uv run python3 -m PyInstaller "${SPEC_FILE}" --distpath "${DIST_DIR}" --workpath "${DIST_DIR}/build" --clean
popd >/dev/null

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

  nested_dir="${stage_dir}/frontend/$(basename "${FRONTEND_DIR}")"
  if [ ! -f "${stage_dir}/frontend/server.js" ] && [ -f "${nested_dir}/server.js" ]; then
    cp -R "${nested_dir}/." "${stage_dir}/frontend/"
    rm -rf "${nested_dir}"
  fi

  if [ ! -f "${stage_dir}/frontend/server.js" ]; then
    echo "Next.js standalone server.js missing in staged frontend." >&2
    exit 1
  fi

  stage_node_runtime "${stage_dir}/node" "${NODE_VERSION}"

  resources_dir="${APP_PATH}/Contents/Resources"
  rm -rf "${resources_dir}/frontend" "${resources_dir}/node"
  mkdir -p "${resources_dir}"
  cp -R "${stage_dir}/frontend" "${resources_dir}/frontend"
  cp -R "${stage_dir}/node" "${resources_dir}/node"

  node_exe="${resources_dir}/node/node"
  if [ ! -f "${node_exe}" ] && [ ! -f "${resources_dir}/node/bin/node" ]; then
    echo "Bundled Node runtime missing from app resources." >&2
    exit 1
  fi
fi

echo "Built macOS app: ${APP_PATH}"

if [ -n "${SIGN_ID}" ]; then
  require_cmd codesign
  sign_args=(--force --timestamp --options runtime --sign "${SIGN_ID}")
  if [ -n "${ENTITLEMENTS}" ]; then
    sign_args+=(--entitlements "${ENTITLEMENTS}")
  fi
  codesign "${sign_args[@]}" "${APP_PATH}"
  codesign --verify --deep --strict "${APP_PATH}"
  echo "Signed macOS app: ${APP_PATH}"
fi
