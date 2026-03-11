"""Tests for the OpenAI Responses API adapter."""

import pytest

import httpx

from todoist.automations.llm_breakdown.models import TaskBreakdown
from todoist.llm.openai_llm import (
    DEFAULT_OPENAI_MODEL,
    OpenAIChatConfig,
    OpenAIResponsesChatModel,
    _build_text_format,
)


def test_gpt5_payload_omits_sampling_controls() -> None:
    model = OpenAIResponsesChatModel(OpenAIChatConfig(api_key="sk-test"))

    payload = model._create_payload([{"role": "user", "content": "Hello"}])

    assert payload["model"] == DEFAULT_OPENAI_MODEL
    assert "temperature" not in payload
    assert "top_p" not in payload


def test_non_gpt5_payload_keeps_sampling_controls() -> None:
    model = OpenAIResponsesChatModel(
        OpenAIChatConfig(api_key="sk-test", model="gpt-4.1-mini")
    )

    payload = model._create_payload([{"role": "user", "content": "Hello"}])

    assert payload["temperature"] == pytest.approx(0.2)
    assert payload["top_p"] == pytest.approx(0.95)


def test_post_raises_api_message_for_http_errors() -> None:
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": {
                    "message": "Unsupported parameter: 'temperature' is not supported with this model."
                }
            },
            request=request,
        )

    model = OpenAIResponsesChatModel(OpenAIChatConfig(api_key="sk-test"))
    model._client = httpx.Client(
        transport=httpx.MockTransport(_handler),
        timeout=model.config.timeout_seconds,
        headers={"Authorization": "Bearer sk-test", "Content-Type": "application/json"},
    )

    with pytest.raises(ValueError, match="Unsupported parameter"):
        model._post({"model": DEFAULT_OPENAI_MODEL, "input": []})


def test_build_text_format_uses_openai_strict_object_schema() -> None:
    text_format = _build_text_format(TaskBreakdown)

    assert text_format["type"] == "json_schema"
    assert text_format["strict"] is True

    schema = text_format["schema"]
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["children"]

    breakdown_node = schema["$defs"]["BreakdownNode"]
    assert breakdown_node["additionalProperties"] is False
    assert breakdown_node["required"] == [
        "content",
        "description",
        "priority",
        "expand",
        "children",
    ]
    assert "default" not in breakdown_node["properties"]["content"]
    assert "title" not in breakdown_node
