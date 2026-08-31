"""Tests for the status command output."""

from scripts import status


def test_main_renders_colored_status_sections(monkeypatch, capsys) -> None:
    monkeypatch.setattr(status, "_supports_color", lambda: False)

    def _fake_fetch_json(url: str):
        if url.endswith("/api/health"):
            return status.EndpointResult(
                ok=True, status_code=200, payload={"version": "1.2.3"}
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
    assert "Services" in output
    assert "Todoist token" in output
