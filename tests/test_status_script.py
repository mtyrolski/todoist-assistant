"""Tests for the status command output."""

from scripts import status


def test_discover_triton_models_reads_repository(monkeypatch, tmp_path) -> None:
    repo_root = tmp_path / "deploy" / "triton" / "model_repository"
    model_dir = repo_root / "todoist_llm"
    model_dir.mkdir(parents=True)
    (model_dir / "config.pbtxt").write_text(
        '\n'.join(
            [
                'name: "todoist_llm"',
                'backend: "python"',
                'platform: "python"',
            ]
        ),
        encoding="utf-8",
    )
    (model_dir / "1").mkdir()
    (model_dir / "2").mkdir()
    (model_dir / "1" / "model.py").write_text(
        '\n'.join(
            [
                "def initialize() -> None:",
                '    model_id = _env("TODOIST_AGENT_MODEL_ID", "Qwen/Qwen2.5-0.5B-Instruct")',
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(status, "_triton_model_repository_path", lambda: repo_root)

    models = status.discover_triton_models()

    assert models == [
        {
            "name": "todoist_llm",
            "backend": "python",
            "platform": "python",
            "directory": "todoist_llm",
            "versions": ["1", "2"],
            "model_id": "Qwen/Qwen2.5-0.5B-Instruct",
        }
    ]


def test_main_renders_colored_status_sections(monkeypatch, tmp_path, capsys) -> None:
    repo_root = tmp_path / "deploy" / "triton" / "model_repository"
    model_dir = repo_root / "todoist_llm"
    model_dir.mkdir(parents=True)
    (model_dir / "config.pbtxt").write_text(
        '\n'.join(
            [
                'name: "todoist_llm"',
                'backend: "python"',
            ]
        ),
        encoding="utf-8",
    )
    (model_dir / "1").mkdir()
    (model_dir / "1" / "model.py").write_text(
        '\n'.join(
            [
                "def initialize() -> None:",
                '    model_id = _env("TODOIST_AGENT_MODEL_ID", "Qwen/Qwen2.5-0.5B-Instruct")',
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(status, "_triton_model_repository_path", lambda: repo_root)
    monkeypatch.setattr(status, "_supports_color", lambda: False)
    monkeypatch.setattr(
        status,
        "discover_served_triton_models",
        lambda base_url: [
            {
                "name": "todoist_llm",
                "version": "1",
                "state": "READY",
                "reason": None,
            }
        ]
        if base_url == "http://127.0.0.1:8003"
        else [],
    )

    def _fake_fetch_json(url: str):
        if url.endswith("/api/health"):
            return status.EndpointResult(ok=True, status_code=200, payload={"version": "1.2.3"})
        if url.endswith("/api/dashboard/llm_chat"):
            return status.EndpointResult(
                ok=True,
                status_code=200,
                payload={
                    "enabled": True,
                    "backend": {
                        "label": "Triton local",
                        "selected": "triton_local",
                        "envPath": ".env",
                        "triton": {
                            "baseUrl": "http://127.0.0.1:8003",
                            "modelId": "Qwen/Qwen2.5-3B-Instruct",
                        },
                    },
                    "model": {
                        "label": "Qwen/Qwen2.5-3B-Instruct",
                        "selected": "Qwen/Qwen2.5-3B-Instruct",
                    },
                    "device": {"label": "CPU", "selected": "cpu"},
                    "queue": {"queued": 1, "running": 0, "done": 2, "failed": 0},
                },
            )
        if url.endswith("/api/dashboard/status"):
            return status.EndpointResult(
                ok=True,
                status_code=200,
                payload={
                    "services": [
                        {"name": "Todoist token", "status": "ok", "detail": "API_KEY set"},
                        {"name": "Triton", "status": "ok", "detail": "ready"},
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
    assert "Triton Inventory" in output
    assert "Configured model" in output
    assert "todoist_llm" in output
    assert "Qwen/Qwen2.5-3B-Instruct" in output
    assert "http://127.0.0.1:8003" in output
    assert "state=READY" in output
    assert "model=Qwen/Qwen2.5-0.5B-Instruct" not in output
