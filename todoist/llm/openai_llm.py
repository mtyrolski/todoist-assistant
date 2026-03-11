"""OpenAI Responses API chat adapter."""


from dataclasses import dataclass
from collections.abc import Sequence
import json
from typing import Any, TypeVar

import httpx
from loguru import logger
from pydantic import BaseModel

from .types import MessageRole


DEFAULT_OPENAI_MODEL = "gpt-5-mini"
T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class OpenAIChatConfig:
    api_key: str
    model: str = DEFAULT_OPENAI_MODEL
    key_name: str | None = None
    temperature: float = 0.2
    top_p: float = 0.95
    max_output_tokens: int = 256
    timeout_seconds: float = 60.0
    base_url: str = "https://api.openai.com/v1/responses"


class OpenAIResponsesChatModel:
    """Minimal Responses API wrapper compatible with the local chat model surface."""

    def __init__(self, config: OpenAIChatConfig):
        self.config = config
        self._client = httpx.Client(
            timeout=config.timeout_seconds,
            headers={
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
            },
        )
        logger.info(
            "OpenAI chat backend ready (model={}, key_name={})",
            config.model,
            config.key_name or "unnamed",
        )

    def chat(self, messages: Sequence[dict[str, str]]) -> str:
        payload = self._create_payload(messages)
        response = self._post(payload)
        return _extract_response_text(response)

    def structured_chat(self, messages: Sequence[dict[str, str]], schema: type[T]) -> T:
        payload = self._create_payload(
            messages,
            text_format=_build_text_format(schema),
        )
        response = self._post(payload)
        text = _extract_response_text(response)
        parsed = json.loads(text)
        return schema.model_validate(parsed)

    def _create_payload(
        self,
        messages: Sequence[dict[str, str]],
        *,
        text_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        instructions = _join_system_messages(messages)
        input_messages = _build_input_messages(messages)
        payload: dict[str, Any] = {
            "model": self.config.model,
            "input": input_messages,
            "max_output_tokens": self.config.max_output_tokens,
            "store": False,
            "text": {"format": text_format or {"type": "text"}},
        }
        if _supports_sampling_controls(self.config.model):
            payload["temperature"] = self.config.temperature
            payload["top_p"] = self.config.top_p
        if instructions:
            payload["instructions"] = instructions
        return payload

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._client.post(self.config.base_url, json=payload)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = _extract_error_detail(exc.response)
            raise ValueError(
                f"OpenAI Responses API request failed ({exc.response.status_code}): {detail}"
            ) from exc
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("OpenAI response payload is not a JSON object")
        return data


def _join_system_messages(messages: Sequence[dict[str, str]]) -> str | None:
    parts = [
        str(message.get("content") or "").strip()
        for message in messages
        if str(message.get("role") or "").strip().lower() == MessageRole.SYSTEM.value
        and str(message.get("content") or "").strip()
    ]
    return "\n".join(parts) if parts else None


def _build_input_messages(messages: Sequence[dict[str, str]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for message in messages:
        role = str(message.get("role") or "").strip().lower()
        content = str(message.get("content") or "").strip()
        if not content or role == MessageRole.SYSTEM.value:
            continue
        if role not in {MessageRole.USER.value, MessageRole.ASSISTANT.value}:
            role = MessageRole.USER.value
        items.append(
            {
                "role": role,
                "content": [{"type": "input_text", "text": content}],
            }
        )
    return items


def _extract_response_text(payload: dict[str, Any]) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    for item in payload.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            if content.get("type") == "output_text":
                text = str(content.get("text") or "").strip()
                if text:
                    return text
            if content.get("type") == "refusal":
                refusal = str(content.get("refusal") or "").strip()
                if refusal:
                    raise ValueError(refusal)

    error = payload.get("error")
    if isinstance(error, dict):
        message = str(error.get("message") or "").strip()
        if message:
            raise ValueError(message)
    raise ValueError("OpenAI response did not include output text")


def _supports_sampling_controls(model: str) -> bool:
    normalized = model.strip().lower()
    return not normalized.startswith("gpt-5")


def _build_text_format(schema: type[BaseModel]) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "name": schema.__name__,
        "strict": True,
        "schema": _normalize_structured_output_schema(schema.model_json_schema()),
    }


def _normalize_structured_output_schema(node: object) -> object:
    if isinstance(node, dict):
        normalized = {
            str(key): _normalize_structured_output_schema(value)
            for key, value in node.items()
            if key not in {"default", "title"}
        }
        if normalized.get("type") == "object":
            properties = normalized.get("properties")
            if isinstance(properties, dict):
                normalized["required"] = list(properties.keys())
            else:
                normalized["required"] = []
            normalized["additionalProperties"] = False
        return normalized
    if isinstance(node, list):
        return [_normalize_structured_output_schema(item) for item in node]
    return node


def _extract_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        text = response.text.strip()
        return text or "No error details returned"
    if not isinstance(payload, dict):
        return "No error details returned"
    error = payload.get("error")
    if isinstance(error, dict):
        message = str(error.get("message") or "").strip()
        if message:
            return message
    message = str(payload.get("message") or "").strip()
    return message or "No error details returned"
