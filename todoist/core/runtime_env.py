"""Helpers for resolving local runtime environment files."""

from collections.abc import Mapping
import os
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

from todoist.core.env import EnvVar

LEGACY_AGENT_BACKEND_ENV = "TODOIST_LLM_BACKEND"


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
    env = os.environ if environ is None else environ
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

    if repo_root is not None:
        return repo_root.resolve() / ".env"
    return current_dir / ".env"


def load_runtime_env_values(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    return {
        key: value
        for key, value in dotenv_values(path).items()
        if isinstance(key, str) and isinstance(value, str)
    }


def load_local_dotenv(
    *,
    path: Path | None = None,
    repo_root: Path | None = None,
    cwd: Path | None = None,
    override: bool = True,
    environ: Mapping[str, str] | None = None,
) -> Path:
    env_path = path or resolve_runtime_env_path(
        repo_root=repo_root,
        cwd=cwd,
        environ=environ,
    )
    if env_path.exists():
        load_dotenv(env_path, override=override)
    return env_path


def normalize_llm_backend(value: object) -> str:
    backend = (_sanitize_env_text(value) or "disabled").lower()
    if backend in {"triton", "triton_local"}:
        return "codex"
    if backend in {"raw", "none"}:
        return "disabled"
    return backend


def resolve_llm_backend(
    *,
    repo_root: Path | None = None,
    cwd: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> str:
    env = os.environ if environ is None else environ
    env_path = resolve_runtime_env_path(repo_root=repo_root, cwd=cwd, environ=env)
    file_values = load_runtime_env_values(env_path)
    return normalize_llm_backend(
        env.get(str(EnvVar.AGENT_BACKEND))
        or env.get(LEGACY_AGENT_BACKEND_ENV)
        or file_values.get(str(EnvVar.AGENT_BACKEND))
        or file_values.get(LEGACY_AGENT_BACKEND_ENV)
    )
