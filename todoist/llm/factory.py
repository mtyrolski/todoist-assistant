"""Lazy LLM backend construction."""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol, TypeVar

from pydantic import BaseModel

from .constants import DEFAULT_MODEL_ID, DEFAULT_TRITON_MODEL_NAME, DEFAULT_TRITON_URL

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


def build_triton_chat_model(
    *,
    base_url: str | None,
    model_name: str | None,
    model_id: str | None,
    temperature: float = 0.2,
    top_p: float = 0.95,
    max_output_tokens: int = 384,
) -> ChatModel:
    from .backends.triton import TritonChatConfig, TritonGenerateChatModel

    return mark_backend(
        TritonGenerateChatModel(
            TritonChatConfig(
                base_url=base_url or DEFAULT_TRITON_URL,
                model_name=model_name or DEFAULT_TRITON_MODEL_NAME,
                model_id=model_id or DEFAULT_MODEL_ID,
                temperature=temperature,
                top_p=top_p,
                max_output_tokens=max_output_tokens,
            )
        ),
        "triton_local",
    )
