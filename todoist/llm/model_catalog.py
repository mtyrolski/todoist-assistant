"""Supported Codex model options."""

from typing import TypedDict

from .constants import DEFAULT_CODEX_MODEL


class ModelOption(TypedDict):
    id: str
    label: str


CODEX_MODEL_OPTIONS: tuple[ModelOption, ...] = (
    {"id": DEFAULT_CODEX_MODEL, "label": "GPT-5.5"},
    {"id": "gpt-5", "label": "GPT-5"},
)
