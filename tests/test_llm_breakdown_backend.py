"""Tests for LLM breakdown backend selection."""

from todoist.automations.llm_breakdown.automation import LLMBreakdown
from todoist.env import EnvVar


def test_breakdown_uses_openai_backend_from_env(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(str(EnvVar.AGENT_BACKEND), "openai")
    monkeypatch.setenv("OPEN_AI_SECRET_KEY", "sk-test")
    monkeypatch.setenv("OPEN_AI_KEY_NAME", "primary-key")
    monkeypatch.setenv("OPEN_AI_MODEL", "gpt-5-mini")

    captured: dict[str, object] = {}

    class _FakeOpenAI:
        def __init__(self, config):
            captured["config"] = config

    monkeypatch.setattr(
        "todoist.automations.llm_breakdown.automation.OpenAIResponsesChatModel",
        _FakeOpenAI,
    )

    automation = LLMBreakdown()
    llm = automation.get_llm()

    assert isinstance(llm, _FakeOpenAI)
    config = captured["config"]
    assert getattr(config, "api_key") == "sk-test"
    assert getattr(config, "key_name") == "primary-key"
    assert getattr(config, "model") == "gpt-5-mini"


def test_breakdown_uses_selected_device_for_transformers(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(str(EnvVar.AGENT_BACKEND), "transformers_local")
    monkeypatch.setenv(str(EnvVar.AGENT_DEVICE), "cuda")

    captured: dict[str, object] = {}

    class _FakeTransformers:
        def __init__(self, config):
            captured["config"] = config

    monkeypatch.setattr(
        "todoist.automations.llm_breakdown.automation.TransformersMistral3ChatModel",
        _FakeTransformers,
    )

    automation = LLMBreakdown()
    llm = automation.get_llm()

    assert isinstance(llm, _FakeTransformers)
    config = captured["config"]
    assert getattr(config, "device") == "cuda"


def test_breakdown_reads_backend_from_cache_env_path(monkeypatch, tmp_path) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    env_path = cache_dir / ".env"
    env_path.write_text(
        "\n".join(
            [
                "TODOIST_AGENT_BACKEND='openai'",
                "OPEN_AI_SECRET_KEY='sk-test'",
                "OPEN_AI_KEY_NAME='cache-key'",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(cache_dir))
    monkeypatch.chdir(tmp_path)

    captured: dict[str, object] = {}

    class _FakeOpenAI:
        def __init__(self, config):
            captured["config"] = config

    monkeypatch.setattr(
        "todoist.automations.llm_breakdown.automation.OpenAIResponsesChatModel",
        _FakeOpenAI,
    )

    automation = LLMBreakdown()
    llm = automation.get_llm()

    assert isinstance(llm, _FakeOpenAI)
    config = captured["config"]
    assert getattr(config, "key_name") == "cache-key"
