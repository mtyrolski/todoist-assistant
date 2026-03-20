#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Required command not found: $1" >&2
    exit 1
  fi
}

if [ ! -f "${REPO_ROOT}/pyproject.toml" ]; then
  echo "Run this script from within the todoist-assistant repo." >&2
  exit 1
fi

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is required. Install it from https://brew.sh/ and re-run this script." >&2
  exit 1
fi

echo "Installing prerequisites with Homebrew..." >&2
brew install python@3.11 node uv

require_cmd uv
require_cmd npm
require_cmd make

echo "Syncing Python environment with uv..." >&2
(cd "${REPO_ROOT}" && uv sync --group dev)

if [ ! -f "${REPO_ROOT}/.env" ]; then
  cp "${REPO_ROOT}/.env.example" "${REPO_ROOT}/.env"
  echo "Created .env from template. Add your Todoist API key before initializing data." >&2
fi

needs_api=0
if grep -q "PUT YOUR API HERE" "${REPO_ROOT}/.env"; then
  needs_api=1
fi

if [ "${needs_api}" -eq 1 ]; then
  echo "Edit ${REPO_ROOT}/.env and set API_KEY, then run: make init_local_env" >&2
else
  echo "Initializing local cache (this may take a few minutes)..." >&2
  (cd "${REPO_ROOT}" && make init_local_env)
fi

echo "Next steps:" >&2
echo "  - Run the API: make run_api" >&2
echo "  - Run the dashboard: make run_dashboard" >&2
