"""Local HuggingFace chat adapter (CPU-first).

This wrapper keeps dependencies explicit and avoids mutating tokenizer internals
(no injected chat templates). We render prompts ourselves in a Mistral-Instruct
style and use `pydantic` for strict structured output parsing.
"""

# pyright: reportPrivateImportUsage=false

# === LOCAL LLM MODEL =========================================================

from collections import defaultdict
from collections.abc import Callable
import json
from pathlib import Path
from typing import Any, Protocol, Sequence, TypeVar, cast

import torch
from huggingface_hub import snapshot_download
from huggingface_hub.utils import logging as hub_logging
from huggingface_hub.utils.tqdm import disable_progress_bars
from loguru import logger
from pydantic import BaseModel
from safetensors import safe_open
from transformers import (
    AutoConfig,
    AutoModelForCausalLM,
    PreTrainedTokenizerBase,
)
from transformers.models.mistral3 import Mistral3ForConditionalGeneration
from transformers.utils import logging as hf_logging

from todoist.llm.config import DType, LocalChatConfig
from todoist.llm.prompts import _render_chat_prompt
from todoist.llm.structured import _schema_instructions, _try_parse_structured_output
from todoist.llm.tokenizer import _load_tokenizer
from todoist.llm.types import MessageRole
from todoist.llm.usage import record_llm_usage


T = TypeVar("T", bound=BaseModel)


class _GenerativeModel(Protocol):
    device: torch.device

    def to(self, device: torch.device) -> "_GenerativeModel": ...
    def eval(self) -> object: ...
    def generate(self, **kwargs: Any) -> torch.Tensor: ...


class TransformersMistral3ChatModel:
    """Minimal local chat model with strict structured output."""

    def __init__(self, config: LocalChatConfig):
        self.config = config

        if config.suppress_hf_warnings:
            hub_logging.set_verbosity_error()
            disable_progress_bars()
            hf_logging.set_verbosity_error()
            hf_logging.disable_progress_bar()

        torch_dtype = _resolve_torch_dtype(config.dtype)

        logger.info("Loading tokenizer: {}", config.model_id)
        self._tokenizer = _load_tokenizer(config.model_id)

        logger.info("Loading config: {}", config.model_id)
        hf_config = _load_config(config.model_id)
        needs_fp8_scaling = hasattr(hf_config, "quantization_config")
        _strip_quantization_config(hf_config)

        logger.info(
            "Loading model: {} (device={}, dtype={})",
            config.model_id,
            config.device,
            config.dtype,
        )
        model_kwargs: dict[str, Any] = {"config": hf_config}
        if torch_dtype is not None:
            model_kwargs["torch_dtype"] = torch_dtype

        if getattr(hf_config, "model_type", None) == "mistral3":
            model = Mistral3ForConditionalGeneration.from_pretrained(
                config.model_id, **model_kwargs
            )
        else:
            model = AutoModelForCausalLM.from_pretrained(
                config.model_id, **model_kwargs
            )
        self._model = cast(_GenerativeModel, model)
        if config.device != "cpu":
            self._model = self._model.to(torch.device(config.device))

        target_dtype = _float8_target_dtype(self._model, preferred=torch_dtype)
        _apply_fp8_weight_scales_inplace(
            self._model,
            model_id=config.model_id,
            target_dtype=target_dtype,
            force=needs_fp8_scaling,
        )
        _upcast_float8_inplace(self._model, target_dtype=target_dtype)
        self._model.eval()
        logger.info("Model ready (device={})", self._model.device)

    def chat(self, messages: Sequence[dict[str, str]]) -> str:
        logger.info(
            "LLM chat messages:\n{}",
            json.dumps(list(messages), ensure_ascii=False, indent=2),
        )
        prompt = _render_chat_prompt(messages, self._tokenizer)
        logger.debug("Rendered prompt ({} chars)", len(prompt))
        return self._generate_text(prompt, operation="chat")

    def structured_chat(self, messages: Sequence[dict[str, str]], schema: type[T]) -> T:
        schema_instruction = _schema_instructions(schema)
        system_parts: list[str] = []
        prompt_messages: list[dict[str, str]] = []
        for msg in messages:
            if (msg.get("role") or "").lower() == MessageRole.SYSTEM:
                content = (msg.get("content") or "").strip()
                if content:
                    system_parts.append(content)
            else:
                prompt_messages.append(msg)

        system_parts.append(schema_instruction)
        system_text = "\n".join(system_parts).strip()
        if system_text:
            prompt_messages = [
                {"role": MessageRole.SYSTEM, "content": system_text},
                *prompt_messages,
            ]
        logger.info(
            "LLM structured_chat schema={} messages:\n{}",
            schema.__name__,
            json.dumps(prompt_messages, ensure_ascii=False, indent=2),
        )
        prompt = _render_chat_prompt(prompt_messages, self._tokenizer)
        logger.debug("Rendered prompt ({} chars)", len(prompt))
        raw = self._generate_text(
            prompt,
            do_sample=False,
            max_new_tokens=self._max_new_tokens_for_schema(schema),
            operation="structured_chat",
        )
        logger.debug("Raw model output:\n{}", raw)
        parsed = _try_parse_structured_output(raw, schema)
        if parsed is not None:
            return parsed

        raise ValueError(f"Invalid structured output for {schema.__name__}: {raw}")

    def _max_new_tokens_for_schema(self, schema: type[BaseModel]) -> int:
        name = schema.__name__
        if name == "InstructionSelection":
            return min(self.config.max_new_tokens, 64)
        if name == "PlannerDecision":
            return min(self.config.max_new_tokens, 256)
        if name == "TaskBreakdown":
            return min(self.config.max_new_tokens, 512)
        return self.config.max_new_tokens

    def _generate_text(
        self,
        prompt: str,
        *,
        do_sample: bool | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        max_new_tokens: int | None = None,
        operation: str = "chat",
    ) -> str:
        inputs = self._tokenizer(prompt, return_tensors="pt")
        inputs.pop("token_type_ids", None)
        inputs = {k: v.to(self._model.device) for k, v in inputs.items()}
        input_len = int(inputs["input_ids"].shape[-1])

        resolved_do_sample = (
            (self.config.temperature > 0) if do_sample is None else do_sample
        )
        resolved_temperature = (
            self.config.temperature if temperature is None else temperature
        )
        resolved_top_p = self.config.top_p if top_p is None else top_p
        resolved_max_new_tokens = (
            self.config.max_new_tokens if max_new_tokens is None else max_new_tokens
        )

        generate_kwargs: dict[str, Any] = {
            **inputs,
            "do_sample": resolved_do_sample,
            "max_new_tokens": resolved_max_new_tokens,
            "pad_token_id": _resolve_pad_token_id(self._tokenizer),
        }
        if resolved_do_sample:
            generate_kwargs["temperature"] = resolved_temperature
            generate_kwargs["top_p"] = resolved_top_p

        with torch.inference_mode():
            generated = self._model.generate(**generate_kwargs)

        new_tokens = generated[0][input_len:]
        output_token_count = (
            int(getattr(new_tokens, "shape", [len(new_tokens)])[-1])
            if len(new_tokens)
            else 0
        )
        decoded_text = self._tokenizer.decode(new_tokens, skip_special_tokens=True)
        text = (
            decoded_text.strip()
            if isinstance(decoded_text, str)
            else "".join(decoded_text).strip()
        )
        record_llm_usage(
            backend="local",
            model_id=self.config.model_id,
            operation=operation,
            input_tokens=input_len,
            output_tokens=output_token_count,
        )
        return text


def _resolve_torch_dtype(dtype: DType) -> torch.dtype | None:
    if dtype == "float16":
        return torch.float16
    if dtype == "bfloat16":
        return torch.bfloat16
    if dtype == "float32":
        return torch.float32
    return None


def _resolve_pad_token_id(tokenizer: PreTrainedTokenizerBase) -> int:
    pad_token_id = tokenizer.pad_token_id
    if isinstance(pad_token_id, int):
        return pad_token_id
    eos_token_id = getattr(tokenizer, "eos_token_id", None)
    if isinstance(eos_token_id, int):
        return eos_token_id
    pad_token = getattr(tokenizer, "pad_token", None)
    if isinstance(pad_token, str) and pad_token:
        token_id = _maybe_token_id(tokenizer, pad_token)
        if isinstance(token_id, int):
            return token_id
    eos_token = getattr(tokenizer, "eos_token", None)
    if isinstance(eos_token, str) and eos_token:
        token_id = _maybe_token_id(tokenizer, eos_token)
        if isinstance(token_id, int):
            return token_id
    raise ValueError("Tokenizer is missing pad_token_id and eos_token_id")


def _maybe_token_id(tokenizer: PreTrainedTokenizerBase, token: str) -> int | None:
    convert = getattr(tokenizer, "convert_tokens_to_ids", None)
    if isinstance(convert, Callable):
        token_id = convert(token)
        if isinstance(token_id, int):
            return token_id
        if (
            isinstance(token_id, list)
            and len(token_id) == 1
            and isinstance(token_id[0], int)
        ):
            return token_id[0]
    return None


def _load_config(model_id: str):
    try:
        return AutoConfig.from_pretrained(model_id)
    except KeyError as exc:
        if "ministral3" not in str(exc):
            raise

    repo_path = Path(
        snapshot_download(repo_id=model_id, allow_patterns=["config.json"])
    )
    cfg_dict = json.loads((repo_path / "config.json").read_text(encoding="utf-8"))
    text_cfg = cfg_dict.get("text_config")
    if isinstance(text_cfg, dict) and text_cfg.get("model_type") == "ministral3":
        text_cfg["model_type"] = "mistral"

    model_type = cfg_dict.get("model_type")
    if not isinstance(model_type, str) or not model_type:
        raise ValueError("Invalid config.json: missing model_type")
    model_kwargs = {k: v for k, v in cfg_dict.items() if k != "model_type"}
    return AutoConfig.for_model(model_type, **model_kwargs)


def _strip_quantization_config(cfg: object) -> None:
    if hasattr(cfg, "quantization_config"):
        delattr(cfg, "quantization_config")


def _apply_fp8_weight_scales_inplace(
    model: Any,
    *,
    model_id: str,
    target_dtype: torch.dtype,
    force: bool,
) -> None:
    """Apply `weight_scale_inv` scalars to FP8 linear weights in-place.

    Some Mistral checkpoints ship FP8 weights plus separate scaling factors
    (`*.weight_scale_inv`). Transformers will load the weights but does not
    apply these scaling factors when initializing standard `nn.Linear`
    parameters. Without the scaling, generation becomes unusable (gibberish).
    """

    if not hasattr(model, "named_parameters"):
        return

    float8_dtypes = _float8_dtypes()

    candidate_params: list[tuple[str, torch.nn.Parameter]] = []
    for name, param in model.named_parameters():
        if not name.endswith(".weight"):
            continue
        if not force and param.dtype not in float8_dtypes:
            continue
        candidate_params.append((name, param))

    if not candidate_params:
        return

    weights_root = _resolve_weights_root(model_id)
    weight_map = _maybe_load_safetensors_index(weights_root)
    available_keys = (
        set(weight_map)
        if weight_map
        else _safetensors_keys(weights_root / "model.safetensors")
    )

    by_file: dict[Path, list[tuple[str, torch.nn.Parameter, str]]] = defaultdict(list)
    for name, param in candidate_params:
        scale_key = _find_scale_key_for_param(name, available_keys)
        if scale_key is None:
            continue
        file_path = _resolve_tensor_file(weights_root, weight_map, scale_key)
        by_file[file_path].append((name, param, scale_key))

    if not by_file:
        return

    converted = 0
    for file_path, entries in by_file.items():
        with safe_open(str(file_path), framework="pt", device="cpu") as f:
            for name, param, scale_key in entries:
                scale_inv = f.get_tensor(scale_key)
                scaled = param.data.to(dtype=target_dtype) * scale_inv.to(
                    dtype=target_dtype, device=param.device
                )
                param.data = scaled
                converted += 1

    logger.info("Applied {} FP8 weight scales (dtype={})", converted, target_dtype)


def _resolve_weights_root(model_id: str) -> Path:
    maybe_local = Path(model_id)
    if maybe_local.exists():
        return maybe_local
    return Path(
        snapshot_download(
            repo_id=model_id,
            allow_patterns=[
                "*.safetensors",
                "*.safetensors.index.json",
            ],
        )
    )


def _maybe_load_safetensors_index(weights_root: Path) -> dict[str, str] | None:
    index_path = weights_root / "model.safetensors.index.json"
    if not index_path.exists():
        return None
    raw = json.loads(index_path.read_text(encoding="utf-8"))
    weight_map = raw.get("weight_map")
    if not isinstance(weight_map, dict):
        return None
    return {str(k): str(v) for k, v in weight_map.items()}


def _resolve_tensor_file(
    weights_root: Path, weight_map: dict[str, str] | None, tensor_key: str
) -> Path:
    if weight_map is None:
        file_path = weights_root / "model.safetensors"
        if not file_path.exists():
            raise FileNotFoundError(f"Missing weights file: {file_path}")
        return file_path

    filename = weight_map.get(tensor_key)
    if not isinstance(filename, str) or not filename:
        raise KeyError(f"Missing tensor key in index: {tensor_key}")
    file_path = weights_root / filename
    if not file_path.exists():
        raise FileNotFoundError(f"Missing weights shard: {file_path}")
    return file_path


def _safetensors_keys(path: Path) -> set[str]:
    if not path.exists():
        raise FileNotFoundError(f"Missing weights file: {path}")
    with safe_open(str(path), framework="pt", device="cpu") as f:
        return set(f.keys())


def _find_scale_key_for_param(param_name: str, available_keys: set[str]) -> str | None:
    for candidate in _candidate_scale_keys(param_name):
        if candidate in available_keys:
            return candidate
    return None


def _candidate_scale_keys(param_name: str) -> list[str]:
    if not param_name.endswith(".weight"):
        return []

    bases: list[str] = [param_name]
    if param_name.startswith("model."):
        bases.append(param_name[len("model.") :])

    candidates: list[str] = []
    for base in bases:
        candidates.append(base[: -len(".weight")] + ".weight_scale_inv")
        if base.startswith("language_model.") and not base.startswith(
            "language_model.model."
        ):
            expanded = "language_model.model." + base[len("language_model.") :]
            candidates.append(expanded[: -len(".weight")] + ".weight_scale_inv")

    out: list[str] = []
    seen: set[str] = set()
    for key in candidates:
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def _upcast_float8_inplace(model: Any, *, target_dtype: torch.dtype) -> None:
    float8_dtypes = _float8_dtypes()
    if not float8_dtypes:
        return

    converted = 0
    for param in model.parameters():
        if param.dtype in float8_dtypes:
            param.data = param.data.to(dtype=target_dtype)
            converted += 1
    for buf in model.buffers():
        if buf.dtype in float8_dtypes:
            buf.data = buf.data.to(dtype=target_dtype)
            converted += 1
    if converted:
        logger.info("Upcasted {} float8 tensors to {}", converted, target_dtype)


def _float8_dtypes() -> list[torch.dtype]:
    return [
        getattr(torch, name)
        for name in (
            "float8_e4m3fn",
            "float8_e4m3fnuz",
            "float8_e5m2",
            "float8_e5m2fnuz",
        )
        if hasattr(torch, name)
    ]


def _float8_target_dtype(model: Any, *, preferred: torch.dtype | None) -> torch.dtype:
    if preferred is not None:
        return preferred

    float8_dtypes = _float8_dtypes()

    for param in model.parameters():
        if param.dtype not in float8_dtypes:
            return param.dtype
    for buf in model.buffers():
        if buf.dtype not in float8_dtypes:
            return buf.dtype
    return torch.float32
