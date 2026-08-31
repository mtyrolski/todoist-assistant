"""Tests for the Codex CLI LLM adapter."""

from langgraph_codex.execution import ExecutionResult
import pytest

from todoist.core.env import EnvVar
from todoist.llm.backends.codex import (
    DEFAULT_CODEX_MODEL,
    CodexChatConfig,
    CodexCliChatModel,
    codex_config_from_values,
)
def _fake_codex_executor(monkeypatch, outputs, captured: dict[str, object]) -> None:
    output_iter = iter(outputs)

    class _FakeExecutor:
        def __init__(self, **kwargs: object) -> None:
            captured["executor_config"] = kwargs

        def execute(self, request):
            if "requests" not in captured:
                captured["requests"] = []
            requests = captured["requests"]
            assert isinstance(requests, list)
            requests.append(request)
            output = next(output_iter)
            if isinstance(output, ExecutionResult):
                return output
            return ExecutionResult(stdout=str(output), stderr="", returncode=0)

    monkeypatch.setattr("todoist.llm.backends.codex.CodexExecutor", _FakeExecutor)


def test_codex_chat_invokes_cli_and_reads_last_message(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    captured: dict[str, object] = {}
    _fake_codex_executor(monkeypatch, ["adapter-ok\n"], captured)

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

    executor_config = captured["executor_config"]
    assert isinstance(executor_config, dict)
    assert executor_config["codex_bin"] == "codex"
    assert executor_config["model"] == "gpt-5.5"
    assert executor_config["sandbox"] == "read-only"
    assert executor_config["approval_policy"] == "never"
    assert executor_config["extra_args"] == [
        "-c",
        "model_reasoning_effort='low'",
    ]
    requests = captured["requests"]
    assert isinstance(requests, list)
    assert requests[0].workspace_path == tmp_path
    assert "Say adapter-ok" in requests[0].prompt


def test_codex_cli_failure_raises_clear_error(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    captured: dict[str, object] = {}
    _fake_codex_executor(
        monkeypatch,
        [ExecutionResult(stdout="", stderr="bad model", returncode=2)],
        captured,
    )

    with pytest.raises(ValueError, match="Codex CLI request failed: bad model"):
        CodexCliChatModel(CodexChatConfig(cwd=tmp_path)).chat(
            [{"role": "user", "content": "hello"}]
        )


def test_codex_empty_output_raises_clear_error(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    captured: dict[str, object] = {}
    _fake_codex_executor(
        monkeypatch,
        [ExecutionResult(stdout="", stderr="", returncode=0)],
        captured,
    )

    with pytest.raises(ValueError, match="did not produce output"):
        CodexCliChatModel(CodexChatConfig(cwd=tmp_path)).chat(
            [{"role": "user", "content": "hello"}]
        )


def test_codex_config_prefers_environment_over_file_values(
    monkeypatch, tmp_path
) -> None:
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


def test_codex_config_falls_back_to_defaults_for_blank_or_invalid_values(
    monkeypatch, tmp_path
) -> None:
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
