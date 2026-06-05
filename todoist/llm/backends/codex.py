"""Codex CLI chat adapter."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import tempfile
from typing import TypeVar

from loguru import logger
from pydantic import BaseModel

from todoist.llm.constants import DEFAULT_CODEX_MODEL
from todoist.llm.structured import _schema_instructions, _try_parse_structured_output
from todoist.llm.types import MessageRole
from todoist.llm.usage import record_llm_usage


T = TypeVar("T", bound=BaseModel)


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
    """Chat model surface backed by `codex exec`."""

    def __init__(self, config: CodexChatConfig):
        self.config = config
        logger.info(
            "Codex chat backend ready (model={}, sandbox={}, approval={}, cwd={})",
            config.model,
            config.sandbox,
            config.approval,
            config.cwd,
        )

    def chat(self, messages: Sequence[dict[str, str]]) -> str:
        prompt = _render_messages(messages)
        return self._run_codex(prompt, operation="chat")

    def structured_chat(self, messages: Sequence[dict[str, str]], schema: type[T]) -> T:
        prompt = "\n\n".join(
            [
                _render_messages(messages),
                _schema_instructions(schema),
                "Return only the final JSON payload. Do not include markdown fences.",
            ]
        )
        raw = self._run_codex(prompt, operation="structured_chat")
        parsed = _try_parse_structured_output(raw, schema)
        if parsed is not None:
            return parsed

        repaired = self._run_codex(
            "\n\n".join(
                [
                    "Convert this draft into strict JSON only.",
                    _schema_instructions(schema),
                    raw,
                ]
            ),
            operation="repair",
        )
        parsed = _try_parse_structured_output(repaired, schema)
        if parsed is not None:
            return parsed
        raise ValueError(f"Invalid structured output for {schema.__name__}: {raw}")

    def _run_codex(self, prompt: str, *, operation: str) -> str:
        with tempfile.TemporaryDirectory(prefix="todoist-codex-") as tmp_dir:
            output_path = Path(tmp_dir) / "last-message.md"
            cmd = [
                self.config.command,
                "--ask-for-approval",
                self.config.approval,
                "--model",
                self.config.model,
                "-c",
                f'model_reasoning_effort="{self.config.reasoning_effort}"',
                "exec",
                "--sandbox",
                self.config.sandbox,
                "--output-last-message",
                str(output_path),
                prompt,
            ]
            logger.debug(
                "Running Codex CLI request (operation={}, prompt_chars={})",
                operation,
                len(prompt),
            )
            result = subprocess.run(
                cmd,
                cwd=self.config.cwd,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.config.timeout_seconds,
                check=False,
            )
            if result.returncode != 0:
                detail = (
                    result.stderr or result.stdout
                ).strip() or f"exit code {result.returncode}"
                raise ValueError(f"Codex CLI request failed: {detail}")
            text = (
                output_path.read_text(encoding="utf-8").strip()
                if output_path.exists()
                else result.stdout.strip()
            )
            if not text:
                raise ValueError("Codex CLI did not produce output.")
            record_llm_usage(
                backend="codex",
                model_id=self.config.model,
                operation=operation,
                input_tokens=_estimate_token_count(prompt),
                output_tokens=_estimate_token_count(text),
            )
            return text


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
        role = str(message.get("role") or MessageRole.USER.value).strip().lower()
        content = str(message.get("content") or "").strip()
        if not content:
            continue
        if role not in {
            MessageRole.SYSTEM.value,
            MessageRole.USER.value,
            MessageRole.ASSISTANT.value,
        }:
            role = MessageRole.USER.value
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


def _estimate_token_count(text: str) -> int:
    stripped = str(text or "").strip()
    if not stripped:
        return 0
    return max(1, len(stripped.split()))
