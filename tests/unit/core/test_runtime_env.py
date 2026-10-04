import os
from pathlib import Path

from todoist.core.runtime_env import (
    load_local_dotenv,
    resolve_runtime_env_path,
)


def test_resolve_runtime_env_path_prefers_cache_dir(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    env_path = resolve_runtime_env_path(
        repo_root=tmp_path,
        cwd=tmp_path,
        environ={"TODOIST_CACHE_DIR": str(cache_dir)},
    )

    assert env_path == cache_dir / ".env"


def test_resolve_runtime_env_path_defaults_to_cwd_without_repo_root(
    tmp_path: Path,
) -> None:
    env_path = resolve_runtime_env_path(cwd=tmp_path, environ={})

    assert env_path == tmp_path / ".env"


def test_resolve_runtime_env_path_prefers_data_dir_over_cache_dir(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    cache_dir = tmp_path / "cache"
    data_dir.mkdir()
    cache_dir.mkdir()

    env_path = resolve_runtime_env_path(
        repo_root=tmp_path,
        cwd=tmp_path,
        environ={
            "TODOIST_DATA_DIR": str(data_dir),
            "TODOIST_CACHE_DIR": str(cache_dir),
        },
    )

    assert env_path == data_dir / ".env"
def test_load_local_dotenv_loads_resolved_env_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("API_KEY", raising=False)
    (tmp_path / ".env").write_text("API_KEY='test-token'", encoding="utf-8")

    env_path = load_local_dotenv(repo_root=tmp_path, cwd=tmp_path)

    assert env_path == tmp_path / ".env"
    assert os.getenv("API_KEY") == "test-token"
