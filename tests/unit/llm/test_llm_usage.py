"""Tests for persistent LLM usage accounting."""

from todoist.core.env import EnvVar
from todoist.llm.usage import load_llm_usage_summary, record_llm_usage


def test_record_llm_usage_aggregates_totals_and_selected_model(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))

    record_llm_usage(
        backend="codex",
        model_id="mistralai/Ministral-3-3B-Instruct-2512",
        operation="chat",
        input_tokens=12,
        output_tokens=5,
    )
    record_llm_usage(
        backend="codex",
        model_id="mistralai/Ministral-3-3B-Instruct-2512",
        operation="structured_chat",
        input_tokens=20,
        output_tokens=9,
    )
    record_llm_usage(
        backend="triton_local",
        model_id="Qwen/Qwen2.5-3B-Instruct",
        operation="repair",
        input_tokens=7,
        output_tokens=3,
    )

    usage = load_llm_usage_summary(
        selected_backend="codex",
        selected_model_id="mistralai/Ministral-3-3B-Instruct-2512",
    )

    assert usage["totals"]["inferenceCount"] == 3
    assert usage["totals"]["inputTokens"] == 39
    assert usage["totals"]["outputTokens"] == 17
    assert usage["totals"]["repairCount"] == 1
    assert usage["current"]["inferenceCount"] == 2
    assert usage["current"]["chatCount"] == 1
    assert usage["current"]["structuredCount"] == 1
    assert usage["current"]["inputTokens"] == 32
    assert usage["current"]["outputTokens"] == 14
    assert usage["lastRequest"]["backend"] == "triton_local"
    assert usage["lastRequest"]["modelId"] == "Qwen/Qwen2.5-3B-Instruct"
    assert usage["lastRequest"]["operation"] == "repair"
