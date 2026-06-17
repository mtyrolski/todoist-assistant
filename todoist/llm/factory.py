"""Lazy LLM backend construction."""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol, TypeVar

from pydantic import BaseModel

_StructuredT = TypeVar("_StructuredT", bound=BaseModel)
_ModelT = TypeVar("_ModelT", bound="ChatModel")


class ChatModel(Protocol):
    def chat(self, messages: Sequence[dict[str, str]]) -> str: ...

    def structured_chat(
        self, messages: Sequence[dict[str, str]], schema: type[_StructuredT]
    ) -> _StructuredT: ...


def mark_backend(model: _ModelT, backend: str) -> _ModelT:
    try:
        setattr(model, "_todoist_llm_backend", backend)
    except (AttributeError, TypeError):
        pass
    return model


def model_backend(model: object) -> str | None:
    value = getattr(model, "_todoist_llm_backend", None)
    return str(value) if isinstance(value, str) and value else None


def build_codex_chat_model(values: Mapping[str, object], *, cwd: Path) -> ChatModel:
    from .backends.codex import CodexCliChatModel, codex_config_from_values

    return mark_backend(
        CodexCliChatModel(codex_config_from_values(values, cwd=cwd)), "codex"
    )
