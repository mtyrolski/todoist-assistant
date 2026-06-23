"""Tests for AI breakdown backend selection."""

from typing import Any, cast

import pytest

from todoist.automations.llm_breakdown.automation import LLMBreakdown
from todoist.database.base import Database
from todoist.core.env import EnvVar


def test_breakdown_uses_codex_backend_from_env(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(str(EnvVar.AGENT_BACKEND), "codex")
    monkeypatch.setenv(str(EnvVar.AGENT_CODEX_MODEL), "gpt-5.5")

    captured: dict[str, Any] = {}

    class _FakeCodex:
        pass

    def _fake_codex_builder(values, *, cwd):
        captured["values"] = values
        captured["cwd"] = cwd
        return _FakeCodex()

    monkeypatch.setattr(
        "todoist.automations.llm_breakdown.automation.build_codex_chat_model",
        _fake_codex_builder,
    )

    automation = LLMBreakdown()
    llm = automation.get_llm()

    assert isinstance(llm, _FakeCodex)
    assert captured["values"] == {}


def test_breakdown_accepts_model_config_from_hydra_settings() -> None:
    automation = LLMBreakdown(model_config={"max_new_tokens": 384})

    assert automation.model_config == {"max_new_tokens": 384}


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
        lambda: (_ for _ in ()).throw(
            AssertionError("disabled backend must not load an LLM")
        ),
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
    monkeypatch.delenv(str(EnvVar.AGENT_CODEX_MODEL), raising=False)
    monkeypatch.chdir(tmp_path)

    captured: dict[str, Any] = {}

    class _FakeCodex:
        pass

    def _fake_codex_builder(values, *, cwd):
        captured["values"] = values
        captured["cwd"] = cwd
        return _FakeCodex()

    monkeypatch.setattr(
        "todoist.automations.llm_breakdown.automation.build_codex_chat_model",
        _fake_codex_builder,
    )

    automation = LLMBreakdown()
    llm = automation.get_llm()

    assert isinstance(llm, _FakeCodex)
    assert captured["values"][str(EnvVar.AGENT_CODEX_MODEL)] == "gpt-5"
