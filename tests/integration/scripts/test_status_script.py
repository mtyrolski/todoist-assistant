"""Tests for the status command output."""

from scripts import status


def test_main_renders_colored_status_sections(monkeypatch, capsys) -> None:
    monkeypatch.setattr(status, "_supports_color", lambda: False)

    def _fake_fetch_json(url: str):
        if url.endswith("/api/health"):
            return status.EndpointResult(
                ok=True, status_code=200, payload={"version": "1.2.3"}
            )
        if url.endswith("/api/dashboard/llm_chat"):
            return status.EndpointResult(
                ok=True,
                status_code=200,
                payload={
                    "enabled": True,
                    "backend": {
                        "label": "Codex",
                        "selected": "codex",
                        "envPath": ".env",
                        "codex": {"model": "gpt-5.5"},
                    },
                    "model": {
                        "label": "gpt-5.5",
                        "selected": "gpt-5.5",
                    },
                    "device": {"label": "CPU", "selected": "cpu"},
                    "usage": {
                        "totals": {
                            "inputTokens": 120,
                            "outputTokens": 30,
                            "totalTokens": 150,
                        }
                    },
                    "assistant": {
                        "tools": ["cache_summary()", "run_script()"],
                        "scripts": [{"name": "weekly"}],
                        "telemetry": {
                            "enabled": True,
                            "endpointConfigured": True,
                        },
                    },
                },
            )
        if url.endswith("/api/dashboard/status"):
            return status.EndpointResult(
                ok=True,
                status_code=200,
                payload={
                    "services": [
                        {
                            "name": "Todoist token",
                            "status": "ok",
                            "detail": "API_KEY set",
                        },
                        {"name": "LLM backend", "status": "ok", "detail": "Codex"},
                    ]
                },
            )
        raise AssertionError(url)

    monkeypatch.setattr(status, "_fetch_json", _fake_fetch_json)
    monkeypatch.setattr(status, "_fetch_http_code", lambda url: (True, 200, None))

    exit_code = status.main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Dashboard Status" in output
    assert "LLM Runtime" in output
    assert "Settings source" in output
    assert "Selected model" in output
    assert "gpt-5.5" in output
    assert "150 total (120 input, 30 output)" in output
    assert "Tools" in output and "2" in output
    assert "Scripts" in output and "1" in output
    assert "Telemetry" in output and "enabled, endpoint configured" in output
    assert "Queue" not in output
    assert "Triton Inventory" not in output
    assert "todoist_llm" not in output
