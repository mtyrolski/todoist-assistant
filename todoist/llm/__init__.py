"""Local LLM adapters and shared types."""

from .local_llm import DEFAULT_MODEL_ID, DType, Device, LocalChatConfig, TransformersMistral3ChatModel
from .openai_llm import (
    DEFAULT_OPENAI_MODEL,
    OpenAIChatConfig,
    OpenAIResponsesChatModel,
)
from .triton_llm import (
    DEFAULT_TRITON_MODEL_ID,
    DEFAULT_TRITON_MODEL_NAME,
    DEFAULT_TRITON_URL,
    TritonChatConfig,
    TritonGenerateChatModel,
)
from .types import MessageRole, PromptToken

__all__ = [
    "DEFAULT_OPENAI_MODEL",
    "DEFAULT_MODEL_ID",
    "DEFAULT_TRITON_MODEL_ID",
    "DEFAULT_TRITON_MODEL_NAME",
    "DEFAULT_TRITON_URL",
    "DType",
    "Device",
    "LocalChatConfig",
    "MessageRole",
    "OpenAIChatConfig",
    "OpenAIResponsesChatModel",
    "PromptToken",
    "TritonChatConfig",
    "TritonGenerateChatModel",
    "TransformersMistral3ChatModel",
]
