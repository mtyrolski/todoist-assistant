"""Backend-neutral LLM constants."""

from .config import DEFAULT_MODEL_ID


DEFAULT_CODEX_MODEL = "gpt-5.5"
DEFAULT_TRITON_URL = "http://127.0.0.1:8003"
DEFAULT_TRITON_MODEL_NAME = "todoist_llm"

__all__ = [
    "DEFAULT_CODEX_MODEL",
    "DEFAULT_MODEL_ID",
    "DEFAULT_TRITON_MODEL_NAME",
    "DEFAULT_TRITON_URL",
]
