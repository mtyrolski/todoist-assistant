"""Optional LLM adapters and backend-neutral shared types.

Backend classes are exposed lazily so importing :mod:`todoist.llm` does not load
Codex, Triton, Torch, or Transformers unless a caller asks for that backend.
"""

from typing import TYPE_CHECKING, Any

from .config import DEFAULT_MODEL_ID, DType, Device, LocalChatConfig
from .constants import (
    DEFAULT_CODEX_MODEL,
    DEFAULT_TRITON_MODEL_NAME,
    DEFAULT_TRITON_URL,
)
from .factory import ChatModel, build_codex_chat_model, build_triton_chat_model
from .types import MessageRole, PromptToken

if TYPE_CHECKING:
    from todoist.llm.backends.codex import CodexChatConfig, CodexCliChatModel
    from todoist.llm.backends.transformers import TransformersMistral3ChatModel
    from todoist.llm.backends.triton import TritonChatConfig, TritonGenerateChatModel

_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "CodexChatConfig": ("todoist.llm.backends.codex", "CodexChatConfig"),
    "CodexCliChatModel": ("todoist.llm.backends.codex", "CodexCliChatModel"),
    "TritonChatConfig": ("todoist.llm.backends.triton", "TritonChatConfig"),
    "TritonGenerateChatModel": (
        "todoist.llm.backends.triton",
        "TritonGenerateChatModel",
    ),
    "TransformersMistral3ChatModel": (
        "todoist.llm.backends.transformers",
        "TransformersMistral3ChatModel",
    ),
}


def __getattr__(name: str) -> Any:
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = target
    from importlib import import_module

    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value


__all__ = [
    "ChatModel",
    "CodexChatConfig",
    "CodexCliChatModel",
    "DEFAULT_CODEX_MODEL",
    "DEFAULT_MODEL_ID",
    "DEFAULT_TRITON_MODEL_NAME",
    "DEFAULT_TRITON_URL",
    "DType",
    "Device",
    "LocalChatConfig",
    "MessageRole",
    "PromptToken",
    "TritonChatConfig",
    "TritonGenerateChatModel",
    "TransformersMistral3ChatModel",
    "build_codex_chat_model",
    "build_triton_chat_model",
]
