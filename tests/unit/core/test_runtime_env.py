import os
from pathlib import Path

from todoist.core.env import EnvVar
from todoist.core.runtime_env import (
    load_local_dotenv,
    resolve_llm_backend,
    resolve_runtime_env_path,
    resolve_triton_launch_settings,
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

    (data_dir / ".env").write_text(
        "\n".join(
            [
                "TODOIST_AGENT_MODEL_ID='Qwen/Qwen2.5-3B-Instruct'",
                "TODOIST_AGENT_TRITON_MODEL_NAME='todoist_llm'",
                "TODOIST_AGENT_TRITON_URL='http://127.0.0.1:8123'",
            ]
        ),
        encoding="utf-8",
    )
    (cache_dir / ".env").write_text(
        "\n".join(
            [
                "TODOIST_AGENT_MODEL_ID='from-cache'",
                "TODOIST_AGENT_TRITON_MODEL_NAME='todoist_llm'",
                "TODOIST_AGENT_TRITON_URL='http://127.0.0.1:9000'",
            ]
        ),
        encoding="utf-8",
    )

    env_path = resolve_runtime_env_path(
        repo_root=tmp_path,
        cwd=tmp_path,
        environ={
            "TODOIST_DATA_DIR": str(data_dir),
            "TODOIST_CACHE_DIR": str(cache_dir),
        },
    )
    payload = resolve_triton_launch_settings(
        repo_root=tmp_path,
        cwd=tmp_path,
        environ={
            "TODOIST_DATA_DIR": str(data_dir),
            "TODOIST_CACHE_DIR": str(cache_dir),
        },
    )

    assert env_path == data_dir / ".env"
    assert payload["model_id"] == "Qwen/Qwen2.5-3B-Instruct"
    assert payload["url"] == "http://127.0.0.1:8123"


def test_resolve_triton_launch_settings_reads_saved_env(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "TODOIST_AGENT_MODEL_ID='Qwen/Qwen2.5-3B-Instruct'",
                "TODOIST_AGENT_TRITON_MODEL_NAME='todoist_llm'",
                "TODOIST_AGENT_TRITON_URL='http://127.0.0.1:8123'",
            ]
        ),
        encoding="utf-8",
    )

    payload = resolve_triton_launch_settings(
        repo_root=tmp_path, cwd=tmp_path, environ={}
    )

    assert payload["model_id"] == "Qwen/Qwen2.5-3B-Instruct"
    assert payload["model_name"] == "todoist_llm"
    assert payload["url"] == "http://127.0.0.1:8123"


def test_resolve_triton_launch_settings_falls_back_from_unsupported_model(
    tmp_path: Path,
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "TODOIST_AGENT_MODEL_ID='not/supported'",
        encoding="utf-8",
    )

    payload = resolve_triton_launch_settings(
        repo_root=tmp_path, cwd=tmp_path, environ={}
    )

    assert payload["model_id"] == "Qwen/Qwen2.5-3B-Instruct"


def test_resolve_llm_backend_reads_agent_backend_from_env_file(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "TODOIST_AGENT_BACKEND='codex'",
        encoding="utf-8",
    )

    backend = resolve_llm_backend(repo_root=tmp_path, cwd=tmp_path, environ={})

    assert backend == "codex"


def test_resolve_llm_backend_supports_legacy_backend_env_name(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "TODOIST_LLM_BACKEND='triton'",
        encoding="utf-8",
    )

    backend = resolve_llm_backend(repo_root=tmp_path, cwd=tmp_path, environ={})

    assert backend == "triton_local"


def test_load_local_dotenv_loads_resolved_env_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv(str(EnvVar.AGENT_BACKEND), raising=False)
    (tmp_path / ".env").write_text(
        "TODOIST_AGENT_BACKEND='codex'",
        encoding="utf-8",
    )

    env_path = load_local_dotenv(repo_root=tmp_path, cwd=tmp_path)

    assert env_path == tmp_path / ".env"
    assert os.getenv(str(EnvVar.AGENT_BACKEND)) == "codex"
