"""Tests for the OpenAI Responses API adapter."""

import json

import pytest

import httpx

from todoist.env import EnvVar
from todoist.automations.llm_breakdown.models import TaskBreakdown
from todoist.llm.usage import load_llm_usage_summary
from todoist.llm.openai_llm import (
    DEFAULT_OPENAI_MODEL,
    OpenAIChatConfig,
    OpenAIResponsesChatModel,
    _build_text_format,
)


def test_gpt5_payload_omits_sampling_controls(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    captured_payload: dict[str, object] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured_payload.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={"output_text": "ok", "usage": {"input_tokens": 11, "output_tokens": 7}},
            request=request,
        )

    model = OpenAIResponsesChatModel(OpenAIChatConfig(api_key="sk-test"))
    setattr(
        model,
        "_client",
        httpx.Client(
            transport=httpx.MockTransport(_handler),
            timeout=model.config.timeout_seconds,
            headers={"Authorization": "Bearer sk-test", "Content-Type": "application/json"},
        ),
    )

    payload = model.chat([{"role": "user", "content": "Hello"}])

    assert payload == "ok"
    assert captured_payload["model"] == DEFAULT_OPENAI_MODEL
    assert "temperature" not in captured_payload
    assert "top_p" not in captured_payload
    usage = load_llm_usage_summary(selected_backend="openai", selected_model_id=DEFAULT_OPENAI_MODEL)
    assert usage["totals"]["inferenceCount"] == 1
    assert usage["totals"]["inputTokens"] == 11
    assert usage["totals"]["outputTokens"] == 7


def test_non_gpt5_payload_keeps_sampling_controls() -> None:
    captured_payload: dict[str, object] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured_payload.update(json.loads(request.content))
        return httpx.Response(200, json={"output_text": "ok"}, request=request)

    model = OpenAIResponsesChatModel(
        OpenAIChatConfig(api_key="sk-test", model="gpt-4.1-mini")
    )
    setattr(
        model,
        "_client",
        httpx.Client(
            transport=httpx.MockTransport(_handler),
            timeout=model.config.timeout_seconds,
            headers={"Authorization": "Bearer sk-test", "Content-Type": "application/json"},
        ),
    )

    payload = model.chat([{"role": "user", "content": "Hello"}])

    assert payload == "ok"
    assert captured_payload["temperature"] == pytest.approx(0.2)
    assert captured_payload["top_p"] == pytest.approx(0.95)


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
    setattr(
        model,
        "_client",
        httpx.Client(
            transport=httpx.MockTransport(_handler),
            timeout=model.config.timeout_seconds,
            headers={"Authorization": "Bearer sk-test", "Content-Type": "application/json"},
        ),
    )

    with pytest.raises(ValueError, match="Unsupported parameter"):
        model.chat([{"role": "user", "content": "Hello"}])


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
