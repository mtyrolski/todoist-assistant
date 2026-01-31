#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="${REPO_ROOT}/dist/macos"
APP_PATH="${DIST_DIR}/TodoistAssistant.app"
OUTPUT_SUFFIX=""

usage() {
  echo "Usage: $0 [--force] [--output-suffix SUFFIX]" >&2
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

FORCE=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --force)
      FORCE=1
      shift
      ;;
    --output-suffix)
      OUTPUT_SUFFIX="$2"
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
require_cmd hdiutil
require_cmd uv

if [ ! -d "${APP_PATH}" ]; then
  echo "App bundle not found at ${APP_PATH}. Build it first with scripts/build_macos_app.sh." >&2
  exit 1
fi

version="$(uv run python3 -m scripts.get_version)"
if [ -z "${version}" ] || [ "${version}" = "0.0.0" ]; then
  echo "Failed to resolve project version." >&2
  exit 1
fi

mkdir -p "${DIST_DIR}"
suffix=""
if [ -n "${OUTPUT_SUFFIX}" ]; then
  suffix="-${OUTPUT_SUFFIX}"
fi
output_dmg="${DIST_DIR}/todoist-assistant-${version}${suffix}.dmg"

if [ -f "${output_dmg}" ] && [ "${FORCE}" -ne 1 ]; then
  echo "DMG already exists at ${output_dmg}. Use --force to overwrite." >&2
  exit 1
fi

hdiutil create -volname "TodoistAssistant" -srcfolder "${APP_PATH}" -ov -format UDZO "${output_dmg}"
echo "Built macOS DMG: ${output_dmg}"
