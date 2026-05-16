"""Shared model option catalog for local and Triton LLM backends."""

from collections.abc import Iterable
from pathlib import Path
from typing import Literal, TypedDict

from .local_llm import DEFAULT_MODEL_ID


class ModelOption(TypedDict):
    id: str
    label: str


LOCAL_MODEL_OPTIONS: tuple[ModelOption, ...] = (
    {"id": DEFAULT_MODEL_ID, "label": "Qwen 2.5 3B Instruct"},
)

OPENAI_MODEL_OPTIONS: tuple[ModelOption, ...] = (
    {"id": "gpt-5-nano", "label": "GPT-5 nano"},
    {"id": "gpt-5-mini", "label": "GPT-5 mini"},
    {"id": "gpt-5", "label": "GPT-5"},
    {"id": "gpt-4.1-mini", "label": "GPT-4.1 mini"},
    {"id": "gpt-4.1", "label": "GPT-4.1"},
)

TRITON_MODEL_OPTIONS: tuple[ModelOption, ...] = (
    {"id": DEFAULT_MODEL_ID, "label": "Qwen 2.5 3B Instruct"},
)


ModelBackend = Literal["local", "triton", "all"]


def model_options_for_backend(backend: ModelBackend) -> tuple[ModelOption, ...]:
    if backend == "local":
        return LOCAL_MODEL_OPTIONS
    if backend == "triton":
        return TRITON_MODEL_OPTIONS
    return (*LOCAL_MODEL_OPTIONS, *TRITON_MODEL_OPTIONS)


def coerce_model_id_for_backend(model_id: str | None, backend: ModelBackend) -> str:
    option_ids = {
        option["id"]
        for option in model_options_for_backend(backend)
    }
    if model_id in option_ids:
        return str(model_id)
    return DEFAULT_MODEL_ID


def is_downloadable_huggingface_model_id(model_id: str) -> bool:
    if "/" not in model_id:
        return False
    return not Path(model_id).expanduser().exists()


def downloadable_model_ids(backends: Iterable[ModelBackend]) -> list[str]:
    seen: set[str] = set()
    ids: list[str] = []
    for backend in backends:
        for option in model_options_for_backend(backend):
            model_id = option["id"]
            if model_id in seen or not is_downloadable_huggingface_model_id(model_id):
                continue
            seen.add(model_id)
            ids.append(model_id)
    return ids
