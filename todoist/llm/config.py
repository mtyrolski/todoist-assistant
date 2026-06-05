"""Backend-neutral LLM configuration types."""

from dataclasses import dataclass
from typing import Literal


DEFAULT_MODEL_ID = "Qwen/Qwen2.5-3B-Instruct"
Device = Literal["cpu", "cuda", "mps"]
DType = Literal["auto", "float16", "bfloat16", "float32"]


@dataclass(frozen=True)
class LocalChatConfig:
    model_id: str = DEFAULT_MODEL_ID
    device: Device = "cpu"
    dtype: DType = "auto"
    temperature: float = 0.2
    top_p: float = 0.95
    max_new_tokens: int = 384
    suppress_hf_warnings: bool = True
