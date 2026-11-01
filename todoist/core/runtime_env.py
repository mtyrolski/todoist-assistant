"""Helpers for resolving local runtime environment files."""

from collections.abc import Mapping
import os
from pathlib import Path


from todoist.core.env import EnvVar


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
