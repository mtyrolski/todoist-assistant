"""Tokenizer loading helpers for backends that render local prompts."""

import json
from pathlib import Path
from typing import Any

from huggingface_hub import snapshot_download
from transformers import AutoTokenizer, PreTrainedTokenizerBase, PreTrainedTokenizerFast


def _load_tokenizer(model_id: str) -> PreTrainedTokenizerBase:
    try:
        return AutoTokenizer.from_pretrained(model_id, use_fast=True)
    except ValueError as exc:
        if "TokenizersBackend" not in str(exc):
            raise

    repo_path = Path(
        snapshot_download(
            repo_id=model_id,
            allow_patterns=[
                "tokenizer.json",
                "tokenizer_config.json",
                "special_tokens_map.json",
            ],
        ))
    tokenizer_json = repo_path / "tokenizer.json"
    tokenizer_config_path = repo_path / "tokenizer_config.json"

    init_kwargs: dict[str, Any] = {}
    if tokenizer_config_path.exists():
        tokenizer_cfg = json.loads(tokenizer_config_path.read_text(encoding="utf-8"))
        for key in ("bos_token", "eos_token", "unk_token", "pad_token"):
            value = tokenizer_cfg.get(key)
            if isinstance(value, str) and value:
                init_kwargs[key] = value
        additional = tokenizer_cfg.get("additional_special_tokens") or tokenizer_cfg.get("extra_special_tokens")
        if isinstance(additional, list):
            init_kwargs["additional_special_tokens"] = [x for x in additional if isinstance(x, str) and x]

    return PreTrainedTokenizerFast(tokenizer_file=str(tokenizer_json), **init_kwargs)
