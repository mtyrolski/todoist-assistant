"""Triton chat adapter for the dashboard-hosted model."""

from dataclasses import dataclass
from collections.abc import Sequence
import json
from typing import Any, TypeVar

import httpx
from loguru import logger
from pydantic import BaseModel

from todoist.llm.constants import (
    DEFAULT_MODEL_ID,
    DEFAULT_TRITON_MODEL_NAME,
    DEFAULT_TRITON_URL,
)
from todoist.llm.prompts import _render_chat_prompt
from todoist.llm.structured import _schema_instructions, _try_parse_structured_output
from todoist.llm.tokenizer import _load_tokenizer
from todoist.llm.usage import record_llm_usage


T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class TritonChatConfig:
    model_name: str = DEFAULT_TRITON_MODEL_NAME
    model_id: str = DEFAULT_MODEL_ID
    base_url: str = DEFAULT_TRITON_URL
    temperature: float = 0.2
    top_p: float = 0.95
    max_output_tokens: int = 384
    timeout_seconds: float = 240.0


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
        logger.debug(
            "Triton chat request (messages={}, base_url={})",
            len(messages),
            self.config.base_url,
        )
        prompt = self._render_prompt(messages)
        logger.debug("Triton chat rendered prompt (chars={})", len(prompt))
        return self._generate_text(prompt, operation="chat")

    def structured_chat(self, messages: Sequence[dict[str, str]], schema: type[T]) -> T:
        logger.debug(
            "Triton structured_chat request (schema={}, messages={})",
            schema.__name__,
            len(messages),
        )
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
        logger.debug(
            "Triton structured_chat rendered prompt (schema={}, chars={})",
            schema.__name__,
            len(prompt),
        )
        raw = self._generate_text(
            prompt,
            do_sample=False,
            max_output_tokens=self._max_output_tokens_for_schema(schema),
            operation="structured_chat",
        )
        parsed = _try_parse_structured_output(raw, schema)
        if parsed is not None and not _is_empty_structured_result(parsed):
            logger.debug(
                "Triton structured_chat parsed schema={} without repair",
                schema.__name__,
            )
            return parsed
        if parsed is not None:
            logger.warning(
                "Triton structured_chat repairing empty output for schema={}",
                schema.__name__,
            )
        else:
            logger.warning(
                "Triton structured_chat repairing malformed output for schema={}",
                schema.__name__,
            )
        repaired = self._repair_structured_output(raw, schema)
        parsed = _try_parse_structured_output(repaired, schema)
        if parsed is not None and not _is_empty_structured_result(parsed):
            logger.debug(
                "Triton structured_chat repair succeeded for schema={}", schema.__name__
            )
            return parsed
        logger.error("Triton structured_chat failed for schema={}", schema.__name__)
        raise ValueError(f"Invalid structured output for {schema.__name__}: {raw}")

    def ready(self) -> bool:
        logger.debug("Checking Triton readiness at {}", self._health_url())
        response = self._client.get(self._health_url())
        response.raise_for_status()
        logger.debug("Triton readiness check succeeded at {}", self._health_url())
        return True

    def _render_prompt(self, messages: Sequence[dict[str, str]]) -> str:
        return _render_chat_prompt(messages, self._tokenizer)

    def _generate_text(
        self,
        prompt: str,
        *,
        do_sample: bool | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        max_output_tokens: int | None = None,
        operation: str = "chat",
    ) -> str:
        resolved_do_sample = (
            (self.config.temperature > 0) if do_sample is None else do_sample
        )
        resolved_temperature = (
            self.config.temperature if temperature is None else temperature
        )
        resolved_top_p = self.config.top_p if top_p is None else top_p
        resolved_max_output_tokens = (
            self.config.max_output_tokens
            if max_output_tokens is None
            else max_output_tokens
        )

        logger.debug(
            "Posting Triton infer request (model_name={}, prompt_chars={}, do_sample={}, temperature={}, top_p={}, max_output_tokens={})",
            self.config.model_name,
            len(prompt),
            resolved_do_sample,
            resolved_temperature,
            resolved_top_p,
            resolved_max_output_tokens,
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
                    },
                ]
            },
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = _extract_error_detail(exc.response)
            logger.warning(
                "Triton infer request failed (status={}, detail={})",
                exc.response.status_code,
                detail,
            )
            raise ValueError(
                f"Triton infer request failed ({exc.response.status_code}): {detail}"
            ) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            logger.exception("Triton response payload is not valid JSON")
            raise ValueError("Triton response payload is not valid JSON") from exc
        if not isinstance(payload, dict):
            logger.error("Triton response payload is not a JSON object")
            raise ValueError("Triton response payload is not a JSON object")
        text_output = _normalize_generated_text(_extract_infer_text_output(payload))
        if not text_output.strip():
            logger.error("Triton response did not include text_output")
            raise ValueError("Triton response did not include text_output")
        record_llm_usage(
            backend="triton_local",
            model_id=self.config.model_id,
            operation=operation,
            input_tokens=_estimate_token_count(self._tokenizer, prompt),
            output_tokens=_estimate_token_count(self._tokenizer, text_output),
        )
        logger.debug("Received Triton infer response (text_chars={})", len(text_output))
        return text_output.strip()

    def _max_output_tokens_for_schema(self, schema: type[BaseModel]) -> int:
        name = schema.__name__
        if name == "InstructionSelection":
            return min(self.config.max_output_tokens, 64)
        if name == "PlannerDecision":
            return min(self.config.max_output_tokens, 256)
        if name == "TaskBreakdown":
            return min(self.config.max_output_tokens, 512)
        return self.config.max_output_tokens

    def _repair_structured_output(self, raw: str, schema: type[BaseModel]) -> str:
        repair_messages = [
            {
                "role": "system",
                "content": (
                    "Convert the provided draft into strict JSON only. "
                    "Do not add commentary, markdown, or code fences."
                    "\nFor TaskBreakdown, children must contain at least one concrete actionable task."
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
            operation="repair",
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


def _is_empty_structured_result(value: BaseModel) -> bool:
    if value.__class__.__name__ != "TaskBreakdown":
        return False
    children = getattr(value, "children", None)
    return isinstance(children, list) and len(children) == 0


def _estimate_token_count(tokenizer: Any, text: str) -> int:
    encode = getattr(tokenizer, "encode", None)
    if callable(encode):
        try:
            encoded = encode(text, add_special_tokens=False)
        except TypeError:
            encoded = encode(text)
        if isinstance(encoded, list):
            return len(encoded)

    call = getattr(tokenizer, "__call__", None)
    if callable(call):
        try:
            encoded = call(text, return_tensors="pt")
        except TypeError:
            encoded = None
        if isinstance(encoded, dict):
            input_ids = encoded.get("input_ids")
            shape = getattr(input_ids, "shape", None)
            if shape is not None:
                return int(shape[-1])

    stripped = str(text or "").strip()
    if not stripped:
        return 0
    return len(stripped.split())
