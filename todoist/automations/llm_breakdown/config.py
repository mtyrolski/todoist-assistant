from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from loguru import logger

from todoist.llm import LocalChatConfig


# === LLM BREAKDOWN CONFIG ===================================================

DEFAULT_VARIANTS: dict[str, dict[str, Any]] = {
    "breakdown": {
        "instruction": "Balanced breakdown with 4-6 top-level tasks.",
        "queue_depth": 1,
    },
    "breakdown-lite": {
        "instruction": "Keep it short and light.",
        "max_depth": 2,
        "max_children": 4,
        "queue_depth": 1,
    },
    "breakdown-deep": {
        "instruction": "Provide more detail and intermediate steps.",
        "max_depth": 2,
        "max_children": 6,
        "queue_depth": 2,
    },
}

BASE_SYSTEM_PROMPT = (
    "Break down the task into actionable subtasks. "
    "Use short imperative phrases with no numbering or markdown. "
    "Do not repeat the task. "
    "Limit depth to {max_depth} levels and at most {max_children} children per task. "
    "Each child should include `content` and an `expand` boolean (true means decompose later). "
    "Return immediate children unless deeper nesting is needed. "
    "Use `task` and `ancestors`/`ancestor_context` for context only."
)


def merge_variants(variants: Mapping[str, Mapping[str, Any]] | None) -> dict[str, dict[str, Any]]:
    merged = {key: dict(value) for key, value in DEFAULT_VARIANTS.items()}
    if variants is None:
        return merged
    for key, value in variants.items():
        merged[key] = dict(value) if isinstance(value, Mapping) else {}
    return merged


def coerce_model_config(model_config: LocalChatConfig | Mapping[str, Any] | None) -> LocalChatConfig:
    if model_config is None:
        return LocalChatConfig()
    if isinstance(model_config, LocalChatConfig):
        return model_config
    if isinstance(model_config, Mapping):
        return LocalChatConfig(**dict(model_config))
    raise TypeError("model_config must be LocalChatConfig or Mapping[str, Any]")


def resolve_variant(
    label: str,
    *,
    label_prefix_lower: str,
    default_variant: str,
    variants: Mapping[str, Mapping[str, Any]],
) -> tuple[str, dict[str, Any]]:
    label_lower = label.lower()
    variant_key = label_lower[len(label_prefix_lower):].strip() if label_lower.startswith(
        label_prefix_lower) else ""
    if not variant_key:
        variant_key = default_variant
    variant_cfg = variants.get(variant_key)
    if variant_cfg is None:
        logger.warning("Unknown LLM variant '{}'; falling back to '{}'", variant_key, default_variant)
        variant_key = default_variant
        variant_cfg = variants.get(variant_key, {})
    return variant_key, dict(variant_cfg)


def build_system_prompt(*, max_depth: int, max_children: int, instruction: str | None) -> str:
    prompt = BASE_SYSTEM_PROMPT.format(max_depth=max_depth, max_children=max_children)
    if instruction:
        prompt = f"{prompt} {instruction}"
    return prompt
