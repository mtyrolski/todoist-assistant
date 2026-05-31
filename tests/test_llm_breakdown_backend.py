"""Tests for AI breakdown backend selection."""

import pytest
from typing import cast

from todoist.automations.llm_breakdown.automation import LLMBreakdown
from todoist.database.base import Database
from todoist.env import EnvVar


def test_breakdown_uses_codex_backend_from_env(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(str(EnvVar.AGENT_BACKEND), "codex")
    monkeypatch.setenv(str(EnvVar.AGENT_CODEX_MODEL), "gpt-5.5")

    captured: dict[str, object] = {}

    class _FakeCodex:
        def __init__(self, config):
            captured["config"] = config

    monkeypatch.setattr(
        "todoist.automations.llm_breakdown.automation.CodexCliChatModel",
        _FakeCodex,
    )

    automation = LLMBreakdown()
    llm = automation.get_llm()

    assert isinstance(llm, _FakeCodex)
    config = captured["config"]
    assert getattr(config, "model") == "gpt-5.5"
    assert getattr(config, "sandbox") == "read-only"


def test_breakdown_rejects_disabled_backend(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(str(EnvVar.AGENT_BACKEND), "disabled")

    with pytest.raises(RuntimeError, match="disabled"):
        LLMBreakdown().get_llm()


def test_breakdown_tick_noops_when_backend_is_disabled(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(str(EnvVar.AGENT_BACKEND), "disabled")

    automation = LLMBreakdown(frequency_in_minutes=0)
    monkeypatch.setattr(
        automation,
        "get_llm",
        lambda: (_ for _ in ()).throw(AssertionError("disabled backend must not load an LLM")),
    )

    class _FakeDb:
        def reset(self) -> None:  # pragma: no cover - should not be called
            raise AssertionError("disabled backend must not refresh breakdown tasks")

    assert automation.should_run_without_new_activity() is False
    automation.tick(cast(Database, _FakeDb()))


def test_breakdown_reads_backend_from_cache_env_path(monkeypatch, tmp_path) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    env_path = cache_dir / ".env"
    env_path.write_text(
        "\n".join(
            [
                "TODOIST_AGENT_BACKEND='codex'",
                "TODOIST_AGENT_CODEX_MODEL='gpt-5'",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(cache_dir))
    monkeypatch.delenv(str(EnvVar.AGENT_BACKEND), raising=False)
    monkeypatch.delenv(str(EnvVar.AGENT_TRITON_URL), raising=False)
    monkeypatch.delenv(str(EnvVar.AGENT_TRITON_MODEL_NAME), raising=False)
    monkeypatch.delenv(str(EnvVar.AGENT_MODEL_ID), raising=False)
    monkeypatch.delenv(str(EnvVar.AGENT_CODEX_MODEL), raising=False)
    monkeypatch.chdir(tmp_path)

    captured: dict[str, object] = {}

    class _FakeCodex:
        def __init__(self, config):
            captured["config"] = config

    monkeypatch.setattr(
        "todoist.automations.llm_breakdown.automation.CodexCliChatModel",
        _FakeCodex,
    )

    automation = LLMBreakdown()
    llm = automation.get_llm()

    assert isinstance(llm, _FakeCodex)
    config = captured["config"]
    assert getattr(config, "model") == "gpt-5"


def test_breakdown_launch_lock_overrides_triton_env(monkeypatch, tmp_path) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    env_path = cache_dir / ".env"
    env_path.write_text(
        "\n".join(
            [
                "TODOIST_AGENT_BACKEND='triton_local'",
                "TODOIST_AGENT_MODEL_ID='Qwen/Qwen2.5-3B-Instruct'",
                "TODOIST_AGENT_CODEX_MODEL='gpt-5.5'",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(cache_dir))
    monkeypatch.setenv(str(EnvVar.AGENT_BACKEND), "triton_local")
    monkeypatch.setenv("TODOIST_DASHBOARD_LLM_BACKEND_LOCK", "codex")
    monkeypatch.chdir(tmp_path)

    captured: dict[str, object] = {}

    class _FakeCodex:
        def __init__(self, config):
            captured["config"] = config

    class _UnexpectedTriton:
        def __init__(self, config):
            raise AssertionError(f"Triton must not be constructed under a Codex launch lock: {config}")

    monkeypatch.setattr(
        "todoist.automations.llm_breakdown.automation.CodexCliChatModel",
        _FakeCodex,
    )
    monkeypatch.setattr(
        "todoist.automations.llm_breakdown.automation.TritonGenerateChatModel",
        _UnexpectedTriton,
    )

    automation = LLMBreakdown()
    llm = automation.get_llm()

    assert automation.selected_backend() == "codex"
    assert isinstance(llm, _FakeCodex)
    assert getattr(captured["config"], "model") == "gpt-5.5"


def test_breakdown_uses_triton_backend_from_env(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(str(EnvVar.AGENT_BACKEND), "triton_local")
    monkeypatch.setenv(str(EnvVar.AGENT_TRITON_URL), "http://127.0.0.1:9100")
    monkeypatch.setenv(str(EnvVar.AGENT_TRITON_MODEL_NAME), "todoist_llm")
    monkeypatch.setenv(str(EnvVar.AGENT_MODEL_ID), "Qwen/Qwen2.5-0.5B-Instruct")

    captured: dict[str, object] = {}

    class _FakeTriton:
        def __init__(self, config):
            captured["config"] = config

    monkeypatch.setattr(
        "todoist.automations.llm_breakdown.automation.TritonGenerateChatModel",
        _FakeTriton,
    )

    automation = LLMBreakdown()
    llm = automation.get_llm()

    assert isinstance(llm, _FakeTriton)
    config = captured["config"]
    assert getattr(config, "base_url") == "http://127.0.0.1:9100"
    assert getattr(config, "model_name") == "todoist_llm"
    assert getattr(config, "model_id") == "Qwen/Qwen2.5-3B-Instruct"
