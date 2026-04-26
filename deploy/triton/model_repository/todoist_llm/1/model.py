import json
import os
from pathlib import Path
from collections.abc import Sequence
from typing import Any

import numpy as np
import torch
from huggingface_hub import snapshot_download
from loguru import logger
import triton_python_backend_utils as pb_utils
from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer, PreTrainedTokenizerFast
from transformers.models.mistral3 import Mistral3ForConditionalGeneration


def _env(name: str, default: str) -> str:
    value = os.getenv(name, default).strip()
    return value if value else default


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name, "true" if default else "false").lower()
    return raw in {"1", "true", "yes", "on"}


def _resolve_device(name: str) -> torch.device:
    requested = _env(name, "auto").lower()
    if requested == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if requested == "cuda" and torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def _resolve_torch_dtype(dtype: str, *, device: torch.device) -> torch.dtype | None:
    normalized = dtype.strip().lower()
    if normalized == "auto":
        return torch.float16 if device.type == "cuda" else None
    if normalized == "float16":
        return torch.float16
    if normalized == "bfloat16":
        return torch.bfloat16
    if normalized == "float32":
        return torch.float32
    return None


def _load_tokenizer(model_id: str, *, trust_remote_code: bool) -> Any:
    try:
        return AutoTokenizer.from_pretrained(
            model_id,
            trust_remote_code=trust_remote_code,
            use_fast=True,
        )
    except ValueError as exc:
        if "TokenizersBackend" not in str(exc):
            raise

    logger.warning(
        "Falling back to tokenizer.json loading for model {} after AutoTokenizer failed with TokenizersBackend",
        model_id,
    )
    repo_path = Path(
        snapshot_download(
            repo_id=model_id,
            allow_patterns=[
                "tokenizer.json",
                "tokenizer_config.json",
                "special_tokens_map.json",
            ],
        )
    )
    tokenizer_json = repo_path / "tokenizer.json"
    tokenizer_config_path = repo_path / "tokenizer_config.json"

    init_kwargs: dict[str, Any] = {}
    if tokenizer_config_path.exists():
        tokenizer_cfg = json.loads(tokenizer_config_path.read_text(encoding="utf-8"))
        for key in ("bos_token", "eos_token", "unk_token", "pad_token"):
            value = tokenizer_cfg.get(key)
            if isinstance(value, str) and value:
                init_kwargs[key] = value
        additional = tokenizer_cfg.get("additional_special_tokens") or tokenizer_cfg.get(
            "extra_special_tokens"
        )
        if isinstance(additional, list):
            init_kwargs["additional_special_tokens"] = [
                item for item in additional if isinstance(item, str) and item
            ]

    return PreTrainedTokenizerFast(tokenizer_file=str(tokenizer_json), **init_kwargs)


def _load_config(model_id: str) -> Any:
    try:
        return AutoConfig.from_pretrained(model_id)
    except KeyError as exc:
        if "ministral3" not in str(exc):
            raise

    logger.warning(
        "Falling back to config.json normalization for model {} after AutoConfig failed with ministral3",
        model_id,
    )
    repo_path = Path(snapshot_download(repo_id=model_id, allow_patterns=["config.json"]))
    cfg_dict = json.loads((repo_path / "config.json").read_text(encoding="utf-8"))
    text_cfg = cfg_dict.get("text_config")
    if isinstance(text_cfg, dict) and text_cfg.get("model_type") == "ministral3":
        text_cfg["model_type"] = "mistral"

    model_type = cfg_dict.get("model_type")
    if not isinstance(model_type, str) or not model_type:
        raise ValueError("Invalid config.json: missing model_type")
    model_kwargs = {key: value for key, value in cfg_dict.items() if key != "model_type"}
    return AutoConfig.for_model(model_type, **model_kwargs)


def _strip_quantization_config(cfg: object) -> None:
    if hasattr(cfg, "quantization_config"):
        delattr(cfg, "quantization_config")


def _move_model_to_runtime(
    model: Any,
    *,
    device: torch.device,
    dtype: torch.dtype | None,
) -> Any:
    if dtype is None:
        return model.to(device)
    return model.to(device=device, dtype=dtype)


def _decode_scalar(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, np.bytes_):
        return value.decode("utf-8")
    if isinstance(value, np.ndarray):
        flattened = value.reshape(-1)
        if flattened.size:
            return _decode_scalar(flattened[0])
        return ""
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return _decode_scalar(item())
        except Exception:
            pass
    return str(value)


def _numpy_scalar(value: Any) -> Any:
    scalar = getattr(value, "item", None)
    if callable(scalar):
        try:
            return scalar()
        except Exception:
            return value
    return value


def _request_values(request: Any, name: str) -> list[Any] | None:
    tensor = pb_utils.get_input_tensor_by_name(request, name)
    if tensor is None:
        return None
    values = tensor.as_numpy()
    if values.size == 0:
        return []
    if values.ndim == 0:
        return [_numpy_scalar(values)]
    if values.ndim == 1:
        return [_numpy_scalar(item) for item in values]
    flattened = values.reshape(values.shape[0], -1)
    return [_numpy_scalar(row[0]) if row.size else None for row in flattened]


def _request_prompts(request: Any) -> list[str]:
    values = _request_values(request, "text_input")
    if values is None:
        raise ValueError("Missing required input tensor: text_input")
    if not values:
        return [""]
    return [_decode_scalar(value) for value in values]


def _row_value(values: list[Any] | None, index: int) -> Any | None:
    if values is None or not values:
        return None
    if len(values) == 1:
        return values[0]
    if index < len(values):
        return values[index]
    return None


def _coerce_bool(value: Any | None, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _coerce_int(value: Any | None, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_float(value: Any | None, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


_LOGGING_CONFIGURED = False


def _configure_logging() -> None:
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return

    log_path = os.getenv("TODOIST_TRITON_REQUEST_LOG_PATH", "").strip()
    log_level = os.getenv("TODOIST_TRITON_LOG_LEVEL", os.getenv("TODOIST_LOG_LEVEL", "INFO")).strip().upper()
    if log_path:
        path = Path(log_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        logger.add(
            path,
            level=log_level,
            rotation="500 MB",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {message}",
            enqueue=False,
            backtrace=False,
            diagnose=False,
        )

    _LOGGING_CONFIGURED = True


class TritonPythonModel:
    def initialize(self, args: dict[str, Any]) -> None:
        _configure_logging()
        self._model_config = json.loads(args["model_config"])
        self._model_id = _env(
            "TODOIST_AGENT_TRITON_MODEL_ID",
            "mistralai/Ministral-3-3B-Instruct-2512",
        )
        self._device = _resolve_device("TODOIST_TRITON_DEVICE")
        self._dtype = _env("TODOIST_TRITON_MODEL_DTYPE", "auto")
        self._max_tokens = _env_int("TODOIST_TRITON_MAX_TOKENS", 384)
        self._temperature = _env_float("TODOIST_TRITON_TEMPERATURE", 0.2)
        self._top_p = _env_float("TODOIST_TRITON_TOP_P", 0.95)
        self._trust_remote_code = _env_bool("TODOIST_TRITON_TRUST_REMOTE_CODE", False)
        self._max_batch_size = max(1, _env_int("TODOIST_TRITON_MAX_BATCH_SIZE", 8))
        self._max_batch_input_tokens = max(
            1,
            _env_int("TODOIST_TRITON_MAX_BATCH_INPUT_TOKENS", 2048),
        )
        self._torch_dtype = _resolve_torch_dtype(self._dtype, device=self._device)

        tokenizer = _load_tokenizer(
            self._model_id,
            trust_remote_code=self._trust_remote_code,
        )
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token or tokenizer.pad_token
        tokenizer.padding_side = "left"
        self._tokenizer = tokenizer

        hf_config = _load_config(self._model_id)
        _strip_quantization_config(hf_config)

        model_kwargs: dict[str, Any] = {
            "config": hf_config,
            "trust_remote_code": self._trust_remote_code,
            "low_cpu_mem_usage": True,
        }
        if self._torch_dtype is not None:
            model_kwargs["torch_dtype"] = self._torch_dtype
        if getattr(hf_config, "model_type", None) == "mistral3":
            self._model = Mistral3ForConditionalGeneration.from_pretrained(
                self._model_id,
                **model_kwargs,
            )
        else:
            self._model = AutoModelForCausalLM.from_pretrained(
                self._model_id,
                **model_kwargs,
            )
        self._model = _move_model_to_runtime(
            self._model,
            device=self._device,
            dtype=self._torch_dtype,
        )
        self._model.eval()
        self._pad_token_id = self._tokenizer.pad_token_id
        if self._pad_token_id is None and self._tokenizer.eos_token_id is not None:
            self._pad_token_id = self._tokenizer.eos_token_id
        logger.info(
            "todoist_llm initialized "
            f"(model_id={self._model_id}, device={self._device.type}, dtype={self._dtype}, "
            f"default_max_tokens={self._max_tokens}, temperature={self._temperature}, top_p={self._top_p}, "
            f"max_batch_size={self._max_batch_size}, "
            f"max_batch_input_tokens={self._max_batch_input_tokens})"
        )

    def execute(self, requests: Sequence[Any]) -> list[Any]:
        try:
            grouped_requests: dict[
                tuple[bool, int, float, float],
                list[tuple[int, int, str]],
            ] = {}
            response_rows: list[list[str]] = []
            for request_index, request in enumerate(requests):
                prompts = _request_prompts(request)
                do_sample_values = _request_values(request, "do_sample")
                max_token_values = _request_values(request, "max_output_tokens")
                temperature_values = _request_values(request, "temperature")
                top_p_values = _request_values(request, "top_p")
                response_rows.append([""] * len(prompts))
                for item_index, prompt in enumerate(prompts):
                    settings = (
                        _coerce_bool(
                            _row_value(do_sample_values, item_index),
                            self._temperature > 0,
                        ),
                        _coerce_int(
                            _row_value(max_token_values, item_index),
                            self._max_tokens,
                        ),
                        _coerce_float(
                            _row_value(temperature_values, item_index),
                            self._temperature,
                        ),
                        _coerce_float(
                            _row_value(top_p_values, item_index),
                            self._top_p,
                        ),
                    )
                    grouped_requests.setdefault(settings, []).append(
                        (request_index, item_index, prompt)
                    )
        except Exception as exc:
            logger.exception("todoist_llm failed while preparing Triton requests")
            return [
                pb_utils.InferenceResponse(error=pb_utils.TritonError(str(exc)))
                for _ in requests
            ]

        try:
            total_prompts = sum(len(rows) for rows in response_rows)
            logger.info(
                "todoist_llm received "
                f"{len(requests)} Triton request(s) carrying {total_prompts} prompt(s); "
                f"grouped into {len(grouped_requests)} execution batch(es)"
            )
            for (do_sample, max_tokens, temperature, top_p), items in grouped_requests.items():
                for batch_index, execution_items in enumerate(
                    self._split_execution_items(items),
                    start=1,
                ):
                    prompt_lengths = [len(prompt) for _, _, prompt in execution_items]
                    logger.info(
                        "todoist_llm dispatching batch "
                        f"(group_size={len(items)}, execution_batch={batch_index}, "
                        f"execution_batch_size={len(execution_items)}, do_sample={do_sample}, "
                        f"max_tokens={max_tokens}, temperature={temperature}, top_p={top_p}, "
                        f"prompt_chars={prompt_lengths})"
                    )
                    texts = self._generate_batch(
                        [prompt for _, _, prompt in execution_items],
                        do_sample=do_sample,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        top_p=top_p,
                    )
                    for (request_index, item_index, _prompt), text in zip(
                        execution_items,
                        texts,
                        strict=True,
                    ):
                        response_rows[request_index][item_index] = text
        except Exception as exc:
            logger.exception("todoist_llm failed while generating Triton responses")
            return [
                pb_utils.InferenceResponse(error=pb_utils.TritonError(str(exc)))
                for _ in requests
            ]
        responses: list[Any] = []
        for rows in response_rows:
            output = np.array([[row] for row in rows], dtype=object)
            responses.append(
                pb_utils.InferenceResponse(
                    output_tensors=[pb_utils.Tensor("text_output", output)]
                )
            )
        return responses

    def finalize(self) -> None:
        # Triton handles lifecycle; the transformers model is released with the process.
        logger.info("todoist_llm finalize called")
        return None

    def _prompt_token_lengths(self, prompts: list[str]) -> list[int]:
        if not prompts:
            return []
        encoded = self._tokenizer(
            prompts,
            add_special_tokens=True,
            padding=False,
            truncation=False,
        )
        input_ids = encoded.get("input_ids")
        if not isinstance(input_ids, list):
            return [1 for _ in prompts]
        lengths: list[int] = []
        for item in input_ids:
            if isinstance(item, list):
                lengths.append(max(1, len(item)))
            else:
                lengths.append(1)
        if len(lengths) < len(prompts):
            lengths.extend([1] * (len(prompts) - len(lengths)))
        return lengths[: len(prompts)]

    def _split_execution_items(
        self,
        items: list[tuple[int, int, str]],
    ) -> list[list[tuple[int, int, str]]]:
        if not items:
            return []
        prompts = [prompt for _, _, prompt in items]
        token_lengths = self._prompt_token_lengths(prompts)
        batches: list[list[tuple[int, int, str]]] = []
        current_items: list[tuple[int, int, str]] = []
        current_tokens = 0

        for item, token_length in zip(items, token_lengths, strict=True):
            capped_length = max(1, int(token_length))
            exceeds_size = len(current_items) >= self._max_batch_size
            exceeds_tokens = (
                bool(current_items)
                and current_tokens + capped_length > self._max_batch_input_tokens
            )
            if exceeds_size or exceeds_tokens:
                batches.append(current_items)
                current_items = []
                current_tokens = 0
            current_items.append(item)
            current_tokens += capped_length

        if current_items:
            batches.append(current_items)
        return batches

    def _generate_batch(
        self,
        prompts: list[str],
        *,
        do_sample: bool,
        max_tokens: int,
        temperature: float,
        top_p: float,
    ) -> list[str]:
        if not prompts:
            return []
        logger.debug(
            "todoist_llm generating batch (batch_size={}, do_sample={}, max_tokens={}, temperature={}, top_p={})",
            len(prompts),
            do_sample,
            max_tokens,
            temperature,
            top_p,
        )
        encodings = self._tokenizer(
            prompts,
            return_tensors="pt",
            padding=True,
        )
        encodings.pop("token_type_ids", None)
        encodings = {key: value.to(self._device) for key, value in encodings.items()}
        attention_mask = encodings.get("attention_mask")
        if attention_mask is None:
            input_lengths = [int(encodings["input_ids"].shape[-1])] * len(prompts)
        else:
            input_lengths = [int(length) for length in attention_mask.sum(dim=1).tolist()]
        generate_kwargs: dict[str, Any] = {
            **encodings,
            "do_sample": do_sample,
            "max_new_tokens": max_tokens,
            "pad_token_id": self._pad_token_id,
        }
        if do_sample:
            generate_kwargs["temperature"] = temperature
            generate_kwargs["top_p"] = top_p
        logger.info(
            "todoist_llm generating "
            f"(batch_size={len(prompts)}, input_tokens={input_lengths}, max_new_tokens={max_tokens}, "
            f"sampling={'on' if do_sample else 'off'})"
        )
        with torch.inference_mode():
            generations = self._model.generate(**generate_kwargs)

        texts: list[str] = []
        for index, generation in enumerate(generations):
            prompt_length = input_lengths[index] if index < len(input_lengths) else 0
            new_tokens = generation[prompt_length:]
            texts.append(self._tokenizer.decode(new_tokens, skip_special_tokens=True).strip())
        output_lengths = [len(text) for text in texts]
        logger.info(
            "todoist_llm completed batch "
            f"(batch_size={len(prompts)}, output_chars={output_lengths})"
        )
        return texts
