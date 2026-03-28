"""Triton chat adapter for the dashboard-hosted model."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable, Sequence
import json
from typing import Any, TypeVar, cast

import httpx
from loguru import logger
from pydantic import BaseModel

from .local_llm import (
    _load_tokenizer,
    _render_mistral_instruct_prompt,
    _schema_instructions,
    _try_parse_structured_output,
)


DEFAULT_TRITON_URL = "http://127.0.0.1:8003"
DEFAULT_TRITON_MODEL_NAME = "todoist_llm"
DEFAULT_TRITON_MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"
T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class TritonChatConfig:
    model_name: str = DEFAULT_TRITON_MODEL_NAME
    model_id: str = DEFAULT_TRITON_MODEL_ID
    base_url: str = DEFAULT_TRITON_URL
    temperature: float = 0.2
    top_p: float = 0.95
    max_output_tokens: int = 256
    timeout_seconds: float = 60.0


class TritonGenerateChatModel:
    """Minimal Triton infer-endpoint wrapper compatible with local chat model surface."""

    def __init__(self, config: TritonChatConfig):
        self.config = config
        self._tokenizer = _load_tokenizer(config.model_id)
        self._client = httpx.Client(timeout=config.timeout_seconds)
        logger.info(
            "Triton chat backend ready (base_url={}, model_name={}, model_id={})",
            config.base_url,
            config.model_name,
            config.model_id,
        )

    def chat(self, messages: Sequence[dict[str, str]]) -> str:
        prompt = self._render_prompt(messages)
        return self._generate_text(prompt)

    def structured_chat(self, messages: Sequence[dict[str, str]], schema: type[T]) -> T:
        schema_instruction = _schema_instructions(schema)
        prompt_messages = list(messages)
        system_parts = [
            str(message.get("content") or "").strip()
            for message in prompt_messages
            if str(message.get("role") or "").strip().lower() == "system"
            and str(message.get("content") or "").strip()
        ]
        non_system_messages = [
            message
            for message in prompt_messages
            if str(message.get("role") or "").strip().lower() != "system"
        ]
        system_parts.append(schema_instruction)
        if system_parts:
            non_system_messages = [
                {"role": "system", "content": "\n".join(system_parts).strip()},
                *non_system_messages,
            ]
        prompt = self._render_prompt(non_system_messages)
        raw = self._generate_text(
            prompt,
            do_sample=False,
            max_output_tokens=self._max_output_tokens_for_schema(schema),
        )
        parsed = _try_parse_structured_output(raw, schema)
        if parsed is not None:
            return parsed
        repaired = self._repair_structured_output(raw, schema)
        parsed = _try_parse_structured_output(repaired, schema)
        if parsed is not None:
            return parsed
        raise ValueError(f"Invalid structured output for {schema.__name__}: {raw}")

    def ready(self) -> bool:
        response = self._client.get(self._health_url())
        response.raise_for_status()
        return True

    def _render_prompt(self, messages: Sequence[dict[str, str]]) -> str:
        apply_chat_template = getattr(self._tokenizer, "apply_chat_template", None)
        if callable(apply_chat_template):
            template_fn = cast(Callable[..., object], apply_chat_template)
            payload = [
                {
                    "role": str(message.get("role") or "").strip().lower(),
                    "content": str(message.get("content") or "").strip(),
                }
                for message in messages
                if str(message.get("content") or "").strip()
            ]
            try:
                rendered = template_fn(  # pylint: disable=not-callable
                    payload,
                    tokenize=False,
                    add_generation_prompt=True,
                    enable_thinking=False,
                )
                if isinstance(rendered, str) and rendered.strip():
                    return rendered.strip()
            except (TypeError, ValueError, NotImplementedError):
                try:
                    rendered = template_fn(  # pylint: disable=not-callable
                        payload,
                        tokenize=False,
                        add_generation_prompt=True,
                    )
                    if isinstance(rendered, str) and rendered.strip():
                        return rendered.strip()
                except (TypeError, ValueError, NotImplementedError):
                    pass
        return _render_mistral_instruct_prompt(messages, self._tokenizer)

    def _generate_text(
        self,
        prompt: str,
        *,
        do_sample: bool | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        max_output_tokens: int | None = None,
    ) -> str:
        resolved_do_sample = (self.config.temperature > 0) if do_sample is None else do_sample
        resolved_temperature = self.config.temperature if temperature is None else temperature
        resolved_top_p = self.config.top_p if top_p is None else top_p
        resolved_max_output_tokens = (
            self.config.max_output_tokens if max_output_tokens is None else max_output_tokens
        )

        response = self._client.post(
            self._infer_url(),
            json={
                "inputs": [
                    {
                        "name": "text_input",
                        "datatype": "BYTES",
                        "shape": [1, 1],
                        "data": [[prompt]],
                    },
                    {
                        "name": "do_sample",
                        "datatype": "BOOL",
                        "shape": [1, 1],
                        "data": [[resolved_do_sample]],
                    },
                    {
                        "name": "max_output_tokens",
                        "datatype": "INT32",
                        "shape": [1, 1],
                        "data": [[resolved_max_output_tokens]],
                    },
                    {
                        "name": "temperature",
                        "datatype": "FP32",
                        "shape": [1, 1],
                        "data": [[resolved_temperature]],
                    },
                    {
                        "name": "top_p",
                        "datatype": "FP32",
                        "shape": [1, 1],
                        "data": [[resolved_top_p]],
                    }
                ]
            },
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = _extract_error_detail(exc.response)
            raise ValueError(
                f"Triton infer request failed ({exc.response.status_code}): {detail}"
            ) from exc

        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Triton response payload is not a JSON object")
        text_output = _normalize_generated_text(_extract_infer_text_output(payload))
        if not text_output.strip():
            raise ValueError("Triton response did not include text_output")
        return text_output.strip()

    def _max_output_tokens_for_schema(self, schema: type[BaseModel]) -> int:
        name = schema.__name__
        if name == "InstructionSelection":
            return min(self.config.max_output_tokens, 64)
        if name == "PlannerDecision":
            return min(self.config.max_output_tokens, 256)
        if name == "TaskBreakdown":
            return max(self.config.max_output_tokens, 384)
        return self.config.max_output_tokens

    def _repair_structured_output(self, raw: str, schema: type[BaseModel]) -> str:
        repair_messages = [
            {
                "role": "system",
                "content": (
                    "Convert the provided draft into strict JSON only. "
                    "Do not add commentary, markdown, or code fences."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"{_schema_instructions(schema)}\n"
                    "Rewrite this draft so it matches the schema exactly:\n"
                    f"{raw}"
                ),
            },
        ]
        repair_prompt = self._render_prompt(repair_messages)
        return self._generate_text(
            repair_prompt,
            do_sample=False,
            max_output_tokens=self._max_output_tokens_for_schema(schema),
        )

    def _infer_url(self) -> str:
        return f"{self.config.base_url.rstrip('/')}/v2/models/{self.config.model_name}/infer"

    def _health_url(self) -> str:
        return f"{self.config.base_url.rstrip('/')}/v2/health/ready"


def _extract_infer_text_output(payload: dict[str, Any]) -> str:
    outputs = payload.get("outputs")
    if not isinstance(outputs, list):
        return ""
    for output in outputs:
        if not isinstance(output, dict) or output.get("name") != "text_output":
            continue
        data = output.get("data")
        value = _unwrap_first_value(data)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _unwrap_first_value(value: Any) -> Any:
    current = value
    while isinstance(current, list) and current:
        current = current[0]
    return current


def _extract_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        text = response.text.strip()
        return text or "No error details returned"
    if not isinstance(payload, dict):
        return "No error details returned"
    error = payload.get("error")
    if isinstance(error, str) and error.strip():
        return error.strip()
    if isinstance(error, dict):
        message = str(error.get("message") or "").strip()
        if message:
            return message
    message = str(payload.get("message") or "").strip()
    return message or json.dumps(payload, ensure_ascii=False)


def _normalize_generated_text(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("<think>"):
        return stripped
    closing = stripped.find("</think>")
    if closing < 0:
        return stripped
    return stripped[closing + len("</think>") :].strip()
