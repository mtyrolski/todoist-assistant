"""Codex CLI chat adapter."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import os
from pathlib import Path

from langgraph_codex.execution import CodexExecutor
from langgraph_codex.graph import create_codex_node
from loguru import logger

from todoist.llm.constants import DEFAULT_CODEX_MODEL


@dataclass(frozen=True)
class CodexChatConfig:
    model: str = DEFAULT_CODEX_MODEL
    sandbox: str = "read-only"
    approval: str = "never"
    reasoning_effort: str = "low"
    timeout_seconds: float = 600.0
    cwd: Path = Path.cwd()
    command: str = "codex"


class CodexCliChatModel:
    """Chat model surface backed by langgraph-codex."""

    def __init__(self, config: CodexChatConfig):
        self.config = config
        self._executor = CodexExecutor(
            codex_bin=config.command,
            model=config.model,
            sandbox=config.sandbox,
            approval_policy=config.approval,
            timeout_seconds=int(config.timeout_seconds),
            extra_args=[
                "-c",
                f"model_reasoning_effort={config.reasoning_effort!r}",
            ],
        )
        logger.info(
            "Codex chat backend ready (model={}, sandbox={}, approval={}, cwd={})",
            config.model,
            config.sandbox,
            config.approval,
            config.cwd,
        )

    def chat(self, messages: Sequence[dict[str, str]]) -> str:
        prompt = _render_messages(messages)
        return self._run_codex(prompt, operation="executive_review")

    def _run_codex(self, prompt: str, *, operation: str) -> str:
        logger.debug(
            "Running langgraph-codex request (operation={}, prompt_chars={})",
            operation,
            len(prompt),
        )
        node = create_codex_node(
            self._executor,
            prompt_builder=lambda _state: prompt,
            workspace_path=self.config.cwd,
        )
        update = node({"workspace_path": self.config.cwd})
        result = update.get("codex_result")
        if result is None:
            raise ValueError("Codex request did not return a result.")
        returncode = int(getattr(result, "returncode", 1))
        stdout = str(getattr(result, "stdout", "") or "").strip()
        stderr = str(getattr(result, "stderr", "") or "").strip()
        if returncode != 0:
            detail = stderr or stdout or f"exit code {returncode}"
            raise ValueError(f"Codex CLI request failed: {detail}")
        if not stdout:
            raise ValueError("Codex CLI did not produce output.")
        return stdout


def codex_config_from_values(
    values: Mapping[str, object],
    *,
    cwd: Path,
) -> CodexChatConfig:
    from todoist.core.env import EnvVar

    return CodexChatConfig(
        model=_text(
            os.getenv(str(EnvVar.AGENT_CODEX_MODEL))
            or values.get(str(EnvVar.AGENT_CODEX_MODEL))
        )
        or DEFAULT_CODEX_MODEL,
        sandbox=_text(
            os.getenv(str(EnvVar.AGENT_CODEX_SANDBOX))
            or values.get(str(EnvVar.AGENT_CODEX_SANDBOX))
        )
        or "read-only",
        approval=_text(
            os.getenv(str(EnvVar.AGENT_CODEX_APPROVAL))
            or values.get(str(EnvVar.AGENT_CODEX_APPROVAL))
        )
        or "never",
        reasoning_effort=_text(
            os.getenv(str(EnvVar.AGENT_CODEX_REASONING_EFFORT))
            or values.get(str(EnvVar.AGENT_CODEX_REASONING_EFFORT))
        )
        or "low",
        timeout_seconds=_float(
            os.getenv(str(EnvVar.AGENT_CODEX_TIMEOUT_SECONDS))
            or values.get(str(EnvVar.AGENT_CODEX_TIMEOUT_SECONDS)),
            default=600.0,
        ),
        cwd=cwd,
    )


def _render_messages(messages: Sequence[dict[str, str]]) -> str:
    parts: list[str] = []
    for message in messages:
        role = str(message.get("role") or "user").strip().lower()
        content = str(message.get("content") or "").strip()
        if not content:
            continue
        if role not in {"system", "user", "assistant"}:
            role = "user"
        parts.append(f"{role.upper()}:\n{content}")
    if not parts:
        raise ValueError("At least one message is required")
    return "\n\n".join(parts)


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip().strip("'\"")
    return text or None


def _float(value: object, *, default: float) -> float:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return default
