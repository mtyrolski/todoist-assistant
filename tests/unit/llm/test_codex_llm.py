"""Tests for the Codex CLI LLM adapter."""


from pathlib import Path
import subprocess

import pytest
from pydantic import BaseModel

from todoist.env import EnvVar
from todoist.llm.codex_llm import (
    DEFAULT_CODEX_MODEL,
    CodexChatConfig,
    CodexCliChatModel,
    codex_config_from_values,
)
from todoist.llm.codex_flags import CodexDangerousFlag, DANGEROUS_CODEX_FLAGS
from todoist.automations.llm_breakdown.models import TaskBreakdown


class _StrictPayload(BaseModel):
    value: int


def test_dangerous_codex_flags_are_enum_backed_and_immutable() -> None:
    assert DANGEROUS_CODEX_FLAGS == frozenset(CodexDangerousFlag)
    assert CodexDangerousFlag.BYPASS_APPROVALS_AND_SANDBOX in DANGEROUS_CODEX_FLAGS
    assert CodexDangerousFlag.BYPASS_HOOK_TRUST in DANGEROUS_CODEX_FLAGS
    assert str(CodexDangerousFlag.BYPASS_APPROVALS_AND_SANDBOX) == (
        "--dangerously-bypass-approvals-and-sandbox"
    )


def test_codex_chat_invokes_cli_and_reads_last_message(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    captured: dict[str, object] = {}

    def _fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        captured["cwd"] = kwargs.get("cwd")
        output_path = Path(cmd[cmd.index("--output-last-message") + 1])
        output_path.write_text("adapter-ok\n", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout="ignored", stderr="")

    monkeypatch.setattr("todoist.llm.codex_llm.subprocess.run", _fake_run)

    model = CodexCliChatModel(
        CodexChatConfig(
            model="gpt-5.5",
            sandbox="read-only",
            approval="never",
            reasoning_effort="low",
            cwd=tmp_path,
        )
    )

    assert model.chat([{"role": "user", "content": "Say adapter-ok"}]) == "adapter-ok"

    cmd = captured["cmd"]
    assert isinstance(cmd, list)
    assert cmd[:6] == ["codex", "--ask-for-approval", "never", "--model", "gpt-5.5", "-c"]
    assert 'model_reasoning_effort="low"' in cmd
    assert "exec" in cmd
    assert "--sandbox" in cmd
    assert "read-only" in cmd
    assert captured["cwd"] == tmp_path


def test_codex_structured_chat_parses_json_payload(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))

    def _fake_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        output_path = Path(cmd[cmd.index("--output-last-message") + 1])
        output_path.write_text(
            '{"children":[{"content":"Draft update","description":"",'
            '"priority":2,"expand":false,"children":[]}]}',
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("todoist.llm.codex_llm.subprocess.run", _fake_run)

    result = CodexCliChatModel(CodexChatConfig(cwd=tmp_path)).structured_chat(
        [{"role": "user", "content": "Break down status update"}],
        TaskBreakdown,
    )

    assert result.children[0].content == "Draft update"
    assert result.children[0].priority == 2


def test_codex_structured_chat_repairs_invalid_json(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    outputs = iter(
        [
            "Here are tasks: Draft update",
            '{"children":[{"content":"Draft update","description":"",'
            '"priority":1,"expand":false,"children":[]}]}',
        ]
    )
    prompts: list[str] = []

    def _fake_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        prompts.append(cmd[-1])
        output_path = Path(cmd[cmd.index("--output-last-message") + 1])
        output_path.write_text(next(outputs), encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("todoist.llm.codex_llm.subprocess.run", _fake_run)

    result = CodexCliChatModel(CodexChatConfig(cwd=tmp_path)).structured_chat(
        [{"role": "user", "content": "Break down status update"}],
        TaskBreakdown,
    )

    assert result.children[0].content == "Draft update"
    assert len(prompts) == 2
    assert "Convert this draft into strict JSON only." in prompts[1]


def test_codex_structured_chat_raises_when_repair_is_still_invalid(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    outputs = iter(["not json", '{"value": "still wrong"}'])

    def _fake_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        output_path = Path(cmd[cmd.index("--output-last-message") + 1])
        output_path.write_text(next(outputs), encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("todoist.llm.codex_llm.subprocess.run", _fake_run)

    with pytest.raises(ValueError, match="Invalid structured output for _StrictPayload"):
        CodexCliChatModel(CodexChatConfig(cwd=tmp_path)).structured_chat(
            [{"role": "user", "content": "Return a number"}],
            _StrictPayload,
        )


def test_codex_cli_failure_raises_clear_error(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))

    def _fake_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 2, stdout="", stderr="bad model")

    monkeypatch.setattr("todoist.llm.codex_llm.subprocess.run", _fake_run)

    with pytest.raises(ValueError, match="Codex CLI request failed: bad model"):
        CodexCliChatModel(CodexChatConfig(cwd=tmp_path)).chat(
            [{"role": "user", "content": "hello"}]
        )


def test_codex_empty_output_raises_clear_error(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))

    def _fake_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("todoist.llm.codex_llm.subprocess.run", _fake_run)

    with pytest.raises(ValueError, match="did not produce output"):
        CodexCliChatModel(CodexChatConfig(cwd=tmp_path)).chat(
            [{"role": "user", "content": "hello"}]
        )


def test_codex_config_prefers_environment_over_file_values(monkeypatch, tmp_path) -> None:
    values = {
        str(EnvVar.AGENT_CODEX_MODEL): "'gpt-5'",
        str(EnvVar.AGENT_CODEX_SANDBOX): "workspace-write",
        str(EnvVar.AGENT_CODEX_APPROVAL): "on-request",
        str(EnvVar.AGENT_CODEX_REASONING_EFFORT): "medium",
        str(EnvVar.AGENT_CODEX_TIMEOUT_SECONDS): "123",
    }
    monkeypatch.setenv(str(EnvVar.AGENT_CODEX_MODEL), "gpt-5.5")
    monkeypatch.setenv(str(EnvVar.AGENT_CODEX_SANDBOX), "read-only")
    monkeypatch.setenv(str(EnvVar.AGENT_CODEX_TIMEOUT_SECONDS), "45.5")

    config = codex_config_from_values(values, cwd=tmp_path)

    assert config.model == "gpt-5.5"
    assert config.sandbox == "read-only"
    assert config.approval == "on-request"
    assert config.reasoning_effort == "medium"
    assert config.timeout_seconds == 45.5
    assert config.cwd == tmp_path


def test_codex_config_falls_back_to_defaults_for_blank_or_invalid_values(monkeypatch, tmp_path) -> None:
    for env_var in (
        EnvVar.AGENT_CODEX_MODEL,
        EnvVar.AGENT_CODEX_SANDBOX,
        EnvVar.AGENT_CODEX_APPROVAL,
        EnvVar.AGENT_CODEX_REASONING_EFFORT,
        EnvVar.AGENT_CODEX_TIMEOUT_SECONDS,
    ):
        monkeypatch.delenv(str(env_var), raising=False)

    config = codex_config_from_values(
        {
            str(EnvVar.AGENT_CODEX_MODEL): "''",
            str(EnvVar.AGENT_CODEX_SANDBOX): "",
            str(EnvVar.AGENT_CODEX_APPROVAL): None,
            str(EnvVar.AGENT_CODEX_REASONING_EFFORT): "  ",
            str(EnvVar.AGENT_CODEX_TIMEOUT_SECONDS): "not-a-number",
        },
        cwd=tmp_path,
    )

    assert config.model == DEFAULT_CODEX_MODEL
    assert config.sandbox == "read-only"
    assert config.approval == "never"
    assert config.reasoning_effort == "low"
    assert config.timeout_seconds == 600.0
