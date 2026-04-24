"""Helpers for resolving local runtime environment files and Triton settings."""

from __future__ import annotations

from collections.abc import Mapping
import os
from pathlib import Path

from todoist.env import EnvVar

DEFAULT_TRITON_URL = "http://127.0.0.1:8003"
DEFAULT_TRITON_MODEL_NAME = "todoist_llm"
DEFAULT_TRITON_MODEL_ID = "mistralai/Ministral-3-3B-Instruct-2512"


def _sanitize_env_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip().strip("'\"")
    return text or None


def resolve_runtime_env_path(
    *,
    repo_root: Path | None = None,
    cwd: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> Path:
    env = environ or os.environ
    data_dir = _sanitize_env_text(env.get(str(EnvVar.DATA_DIR)))
    if data_dir:
        return Path(data_dir).expanduser().resolve() / ".env"

    cache_dir = _sanitize_env_text(env.get(str(EnvVar.CACHE_DIR)))
    if cache_dir:
        return Path(cache_dir).expanduser().resolve() / ".env"

    current_dir = (cwd or Path.cwd()).resolve()
    cwd_env = current_dir / ".env"
    if cwd_env.exists():
        return cwd_env

    root = (repo_root or Path(__file__).resolve().parents[1]).resolve()
    return root / ".env"


def load_runtime_env_values(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        normalized_key = key.strip()
        if not normalized_key:
            continue
        normalized_value = value.strip()
        if (
            len(normalized_value) >= 2
            and normalized_value[:1] == normalized_value[-1:]
            and normalized_value[:1] in {"'", '"'}
        ):
            normalized_value = normalized_value[1:-1]
        values[normalized_key] = normalized_value
    return values


def resolve_triton_launch_settings(
    *,
    repo_root: Path | None = None,
    cwd: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    env = environ or os.environ
    env_path = resolve_runtime_env_path(repo_root=repo_root, cwd=cwd, environ=env)
    file_values = load_runtime_env_values(env_path)
    default_url = f"http://127.0.0.1:{_sanitize_env_text(env.get('TODOIST_TRITON_HTTP_PORT')) or '8003'}"

    model_id = (
        _sanitize_env_text(env.get("TRITON_MODEL_ID"))
        or _sanitize_env_text(env.get(str(EnvVar.AGENT_TRITON_MODEL_ID)))
        or _sanitize_env_text(file_values.get(str(EnvVar.AGENT_TRITON_MODEL_ID)))
        or DEFAULT_TRITON_MODEL_ID
    )
    model_name = (
        _sanitize_env_text(env.get("TRITON_MODEL_NAME"))
        or _sanitize_env_text(env.get(str(EnvVar.AGENT_TRITON_MODEL_NAME)))
        or _sanitize_env_text(file_values.get(str(EnvVar.AGENT_TRITON_MODEL_NAME)))
        or DEFAULT_TRITON_MODEL_NAME
    )
    url = (
        _sanitize_env_text(env.get("TRITON_URL"))
        or _sanitize_env_text(env.get(str(EnvVar.AGENT_TRITON_URL)))
        or _sanitize_env_text(file_values.get(str(EnvVar.AGENT_TRITON_URL)))
        or default_url
    )

    return {
        "env_path": str(env_path),
        "model_id": model_id,
        "model_name": model_name,
        "url": url,
    }
