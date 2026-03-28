"""Tests for the Triton infer-endpoint adapter."""

import json
from typing import Any, cast
from unittest.mock import patch

import httpx
import pytest

from todoist.automations.llm_breakdown.models import TaskBreakdown
from todoist.llm.triton_llm import (
    DEFAULT_TRITON_MODEL_ID,
    DEFAULT_TRITON_MODEL_NAME,
    DEFAULT_TRITON_URL,
    TritonChatConfig,
    TritonGenerateChatModel,
)


class _FakeTokenizer:
    bos_token = "<s>"
    eos_token = "</s>"

    def apply_chat_template(self, messages, *, tokenize, add_generation_prompt, enable_thinking):
        assert tokenize is False
        assert add_generation_prompt is True
        assert enable_thinking is False
        return "PROMPT:" + " | ".join(f"{item['role']}={item['content']}" for item in messages)


class _LegacyFakeTokenizer:
    bos_token = "<s>"
    eos_token = "</s>"

    def apply_chat_template(self, messages, *, tokenize, add_generation_prompt):
        assert tokenize is False
        assert add_generation_prompt is True
        return "PROMPT:" + " | ".join(f"{item['role']}={item['content']}" for item in messages)


def test_triton_chat_posts_infer_request(monkeypatch) -> None:
    captured_payload: dict[str, object] = {}
    monkeypatch.setattr("todoist.llm.triton_llm._load_tokenizer", lambda _model_id: _FakeTokenizer())

    def _handler(request: httpx.Request) -> httpx.Response:
        captured_payload.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model_name": DEFAULT_TRITON_MODEL_NAME,
                "model_version": "1",
                "outputs": [
                    {
                        "name": "text_output",
                        "datatype": "BYTES",
                        "shape": [1, 1],
                        "data": [["completion"]],
                    }
                ],
            },
            request=request,
        )

    with patch("todoist.llm.triton_llm.logger") as mock_logger:
        model = TritonGenerateChatModel(TritonChatConfig())
        setattr(
            model,
            "_client",
            httpx.Client(
                transport=httpx.MockTransport(_handler),
                timeout=model.config.timeout_seconds,
            ),
        )

        payload = model.chat([{"role": "user", "content": "Hello"}])
    inputs = cast(list[dict[str, Any]], captured_payload["inputs"])

    assert payload == "completion"
    mock_logger.info.assert_any_call(
        "Triton chat backend ready (base_url={}, model_name={}, model_id={})",
        DEFAULT_TRITON_URL,
        DEFAULT_TRITON_MODEL_NAME,
        DEFAULT_TRITON_MODEL_ID,
    )
    mock_logger.debug.assert_any_call(
        "Triton chat request (messages={}, base_url={})",
        1,
        DEFAULT_TRITON_URL,
    )
    mock_logger.debug.assert_any_call("Triton chat rendered prompt (chars={})", len("PROMPT:user=Hello"))
    mock_logger.debug.assert_any_call(
        "Posting Triton infer request (model_name={}, prompt_chars={}, do_sample={}, temperature={}, top_p={}, max_output_tokens={})",
        DEFAULT_TRITON_MODEL_NAME,
        len("PROMPT:user=Hello"),
        True,
        0.2,
        0.95,
        256,
    )
    mock_logger.debug.assert_any_call("Received Triton infer response (text_chars={})", len("completion"))
    assert inputs[0]["name"] == "text_input"
    assert inputs[0]["datatype"] == "BYTES"
    assert inputs[0]["shape"] == [1, 1]
    assert inputs[0]["data"] == [["PROMPT:user=Hello"]]
    assert inputs[1] == {
        "name": "do_sample",
        "datatype": "BOOL",
        "shape": [1, 1],
        "data": [[True]],
    }
    assert inputs[2] == {
        "name": "max_output_tokens",
        "datatype": "INT32",
        "shape": [1, 1],
        "data": [[256]],
    }
    assert inputs[3] == {
        "name": "temperature",
        "datatype": "FP32",
        "shape": [1, 1],
        "data": [[0.2]],
    }
    assert inputs[4] == {
        "name": "top_p",
        "datatype": "FP32",
        "shape": [1, 1],
        "data": [[0.95]],
    }


def test_triton_structured_chat_parses_json(monkeypatch) -> None:
    monkeypatch.setattr("todoist.llm.triton_llm._load_tokenizer", lambda _model_id: _FakeTokenizer())
    captured_payload: dict[str, object] = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        captured_payload.update(payload)
        prompt = payload["inputs"][0]["data"][0][0]
        return httpx.Response(
            200,
            json={
                "model_name": DEFAULT_TRITON_MODEL_NAME,
                "model_version": "1",
                "outputs": [
                    {
                        "name": "text_output",
                        "datatype": "BYTES",
                        "shape": [1, 1],
                        "data": [[
                            f'{prompt} {{"children":[{{"content":"Step 1","description":null,'
                            '"priority":null,"expand":false,"children":[]}]}}'
                        ]],
                    }
                ],
            },
            request=request,
        )

    model = TritonGenerateChatModel(
        TritonChatConfig(model_id=DEFAULT_TRITON_MODEL_ID, max_output_tokens=128)
    )
    setattr(
        model,
        "_client",
        httpx.Client(
            transport=httpx.MockTransport(_handler),
            timeout=model.config.timeout_seconds,
        ),
    )

    payload = model.structured_chat([{"role": "user", "content": "Break this down"}], TaskBreakdown)

    assert payload.children[0].content == "Step 1"
    inputs = cast(list[dict[str, Any]], captured_payload["inputs"])
    assert inputs[1]["data"] == [[False]]
    assert inputs[2]["data"] == [[384]]


def test_triton_structured_chat_falls_back_to_numbered_breakdown(monkeypatch) -> None:
    monkeypatch.setattr("todoist.llm.triton_llm._load_tokenizer", lambda _model_id: _FakeTokenizer())

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model_name": DEFAULT_TRITON_MODEL_NAME,
                "model_version": "1",
                "outputs": [
                    {
                        "name": "text_output",
                        "datatype": "BYTES",
                        "shape": [1, 1],
                        "data": [[
                            "1. **Book travel**\n"
                            "2. **Reserve hotel**\n"
                            "3. **Plan agenda**\n"
                            "4. **Confirm attendees**"
                        ]],
                    }
                ],
            },
            request=request,
        )

    model = TritonGenerateChatModel(TritonChatConfig())
    setattr(
        model,
        "_client",
        httpx.Client(
            transport=httpx.MockTransport(_handler),
            timeout=model.config.timeout_seconds,
        ),
    )

    payload = model.structured_chat([{"role": "user", "content": "Break this down"}], TaskBreakdown)

    assert [child.content for child in payload.children] == [
        "Book travel",
        "Reserve hotel",
        "Plan agenda",
        "Confirm attendees",
    ]


def test_triton_structured_chat_repairs_plaintext_to_json(monkeypatch) -> None:
    monkeypatch.setattr("todoist.llm.triton_llm._load_tokenizer", lambda _model_id: _FakeTokenizer())
    calls = {"count": 0}

    def _handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            text = "PLAN THE TRIP AND BREAK IT INTO FOUR SUBTASKS"
        else:
            text = '{"children":[{"content":"Book travel"},{"content":"Reserve hotel"}]}'
        return httpx.Response(
            200,
            json={
                "model_name": DEFAULT_TRITON_MODEL_NAME,
                "model_version": "1",
                "outputs": [
                    {
                        "name": "text_output",
                        "datatype": "BYTES",
                        "shape": [1, 1],
                        "data": [[text]],
                    }
                ],
            },
            request=request,
        )

    model = TritonGenerateChatModel(TritonChatConfig())
    setattr(
        model,
        "_client",
        httpx.Client(
            transport=httpx.MockTransport(_handler),
            timeout=model.config.timeout_seconds,
        ),
    )

    payload = model.structured_chat([{"role": "user", "content": "Break this down"}], TaskBreakdown)

    assert calls["count"] == 2
    assert [child.content for child in payload.children] == ["Book travel", "Reserve hotel"]


def test_triton_post_raises_api_message_for_http_errors(monkeypatch) -> None:
    monkeypatch.setattr("todoist.llm.triton_llm._load_tokenizer", lambda _model_id: _FakeTokenizer())

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            json={"error": "model loading"},
            request=request,
        )

    with patch("todoist.llm.triton_llm.logger") as mock_logger:
        model = TritonGenerateChatModel(TritonChatConfig())
        setattr(
            model,
            "_client",
            httpx.Client(
                transport=httpx.MockTransport(_handler),
                timeout=model.config.timeout_seconds,
            ),
        )

        with pytest.raises(ValueError, match="model loading"):
            model.chat([{"role": "user", "content": "Hello"}])

    mock_logger.warning.assert_any_call(
        "Triton infer request failed (status={}, detail={})",
        503,
        "model loading",
    )


def test_triton_chat_falls_back_for_legacy_chat_template(monkeypatch) -> None:
    captured_payload: dict[str, object] = {}
    monkeypatch.setattr(
        "todoist.llm.triton_llm._load_tokenizer",
        lambda _model_id: _LegacyFakeTokenizer(),
    )

    def _handler(request: httpx.Request) -> httpx.Response:
        captured_payload.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model_name": DEFAULT_TRITON_MODEL_NAME,
                "model_version": "1",
                "outputs": [
                    {
                        "name": "text_output",
                        "datatype": "BYTES",
                        "shape": [1, 1],
                        "data": [["completion"]],
                    }
                ],
            },
            request=request,
        )

    model = TritonGenerateChatModel(TritonChatConfig())
    setattr(
        model,
        "_client",
        httpx.Client(
            transport=httpx.MockTransport(_handler),
            timeout=model.config.timeout_seconds,
        ),
    )

    payload = model.chat([{"role": "user", "content": "Hello"}])
    inputs = cast(list[dict[str, Any]], captured_payload["inputs"])

    assert payload == "completion"
    assert inputs[0]["data"] == [["PROMPT:user=Hello"]]


def test_triton_chat_strips_qwen3_thinking_block(monkeypatch) -> None:
    monkeypatch.setattr("todoist.llm.triton_llm._load_tokenizer", lambda _model_id: _FakeTokenizer())

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model_name": DEFAULT_TRITON_MODEL_NAME,
                "model_version": "1",
                "outputs": [
                    {
                        "name": "text_output",
                        "datatype": "BYTES",
                        "shape": [1, 1],
                        "data": [["<think>draft</think>\nFinal answer"]],
                    }
                ],
            },
            request=request,
        )

    model = TritonGenerateChatModel(TritonChatConfig())
    setattr(
        model,
        "_client",
        httpx.Client(
            transport=httpx.MockTransport(_handler),
            timeout=model.config.timeout_seconds,
        ),
    )

    payload = model.chat([{"role": "user", "content": "Hello"}])

    assert payload == "Final answer"
