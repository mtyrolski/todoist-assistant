"""Tests for persistent LLM usage accounting."""

from todoist.core.env import EnvVar
from todoist.core.utils import Cache
from todoist.llm.usage import load_llm_usage_summary, record_llm_usage


def test_record_llm_usage_aggregates_totals_and_last_request(
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
        backend="codex",
        model_id="gpt-5",
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
    assert usage["current"]["backend"] == "codex"
    assert usage["current"]["modelId"] == "mistralai/Ministral-3-3B-Instruct-2512"
    assert usage["current"]["inferenceCount"] == 3
    assert usage["current"]["inputTokens"] == 39
    assert usage["current"]["outputTokens"] == 17
    assert usage["lastRequest"]["backend"] == "codex"
    assert usage["lastRequest"]["modelId"] == "gpt-5"
    assert usage["lastRequest"]["operation"] == "repair"

    saved = Cache().llm_usage_stats.load()
    assert "backends" not in saved
    assert saved["totals"]["inference_count"] == 3
    assert saved["last_request"]["model_id"] == "gpt-5"
