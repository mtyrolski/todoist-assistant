"""Tests for FastAPI runtime and status endpoints."""

import os
from pathlib import Path

from fastapi.testclient import TestClient

import todoist
import todoist.web.api_components.runtime as runtime_component
import todoist.web.api as web_api

# pylint: disable=protected-access


def test_runtime_logs_only_return_explicit_allowlist(monkeypatch, tmp_path) -> None:
    cache_dir = tmp_path / "cache"
    dashboard_dir = cache_dir / "dashboard"
    dashboard_dir.mkdir(parents=True)
    (dashboard_dir / "api.log").write_text("api line\n", encoding="utf-8")
    (dashboard_dir / "frontend.log").write_text("frontend line\n", encoding="utf-8")
    (dashboard_dir / "rogue.log").write_text("rogue line\n", encoding="utf-8")

    monkeypatch.setenv(str(web_api.EnvVar.CACHE_DIR), str(cache_dir))
    monkeypatch.setattr(web_api, "_DATA_DIR", tmp_path / "data")

    client = TestClient(web_api.app)
    res = client.get("/api/runtime/logs")
    assert res.status_code == 200
    payload = res.json()

    ids = [item["id"] for item in payload["sources"]]
    assert ids == [
        "api",
        "frontend",
        "observer",
        "triton",
        "triton_inference",
        "automation",
    ]
    assert "rogue" not in ids
    assert all(item["inspectOnly"] is True for item in payload["sources"])

def test_runtime_log_read_accepts_allowlisted_source_only(monkeypatch, tmp_path) -> None:
    cache_dir = tmp_path / "cache"
    dashboard_dir = cache_dir / "dashboard"
    dashboard_dir.mkdir(parents=True)
    (dashboard_dir / "observer.log").write_text("line-1\nline-2\nline-3\n", encoding="utf-8")

    monkeypatch.setenv(str(web_api.EnvVar.CACHE_DIR), str(cache_dir))
    monkeypatch.setattr(web_api, "_DATA_DIR", tmp_path / "data")

    client = TestClient(web_api.app)

    ok = client.get("/api/runtime/logs/read?source=observer&tail_lines=2&page=1")
    assert ok.status_code == 200
    payload = ok.json()
    assert payload["source"] == "observer"
    assert payload["inspectOnly"] is True
    assert payload["content"] == "line-2\nline-3\n"

    missing = client.get("/api/runtime/logs/read?source=rogue")
    assert missing.status_code == 404

def test_admin_logs_lists_explicit_runtime_sources(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(str(web_api.EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.chdir(tmp_path)

    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir(parents=True)
    (dashboard_dir / "api.log").write_text("api ready\n", encoding="utf-8")
    (tmp_path / "automation.log").write_text("automation ready\n", encoding="utf-8")
    (tmp_path / "dashboard" / "unexpected.log").write_text("should not be listed\n", encoding="utf-8")

    client = TestClient(web_api.app)
    res = client.get("/api/admin/logs")
    assert res.status_code == 200
    payload = res.json()

    assert [item["source"] for item in payload["logs"]] == [
        "api",
        "frontend",
        "observer",
        "triton",
        "triton_inference",
        "automation",
    ]
    assert payload["logs"][0]["available"] is True
    assert payload["logs"][0]["path"] == "dashboard/api.log"
    assert payload["logs"][-1]["available"] is True
    assert payload["logs"][-1]["path"] == "automation.log"
    assert all(item["path"] != "dashboard/unexpected.log" for item in payload["logs"])

def test_admin_read_log_uses_named_runtime_source(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(str(web_api.EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.chdir(tmp_path)

    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir(parents=True)
    (dashboard_dir / "observer.log").write_text("line-a\nline-b\n", encoding="utf-8")

    client = TestClient(web_api.app)
    res = client.get("/api/admin/logs/read", params={"source": "observer", "tail_lines": 20, "page": 1})
    assert res.status_code == 200
    payload = res.json()

    assert payload["source"] == "observer"
    assert payload["label"] == "Observer"
    assert payload["path"] == "dashboard/observer.log"
    assert "line-a" in payload["content"]
    assert payload["totalLines"] == 2

    missing = client.get("/api/admin/logs/read", params={"source": "frontend"})
    assert missing.status_code == 404
    assert "not available yet" in missing.json()["detail"]

def test_runtime_logs_lists_curated_sources(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(str(web_api.EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(web_api, "_DATA_DIR", tmp_path)

    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir(parents=True)
    (dashboard_dir / "api.log").write_text("api line\n", encoding="utf-8")
    (tmp_path / "automation.log").write_text("automation line\n", encoding="utf-8")

    client = TestClient(web_api.app)
    res = client.get("/api/runtime/logs")
    assert res.status_code == 200
    payload = res.json()
    assert payload["inspectOnly"] is True

    by_id = {item["id"]: item for item in payload["sources"]}
    assert by_id["api"]["available"] is True
    assert by_id["api"]["inspectOnly"] is True
    assert by_id["frontend"]["available"] is False
    assert by_id["automation"]["available"] is True

def test_runtime_read_log_reads_curated_source(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv(str(web_api.EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(web_api, "_DATA_DIR", tmp_path)

    dashboard_dir = tmp_path / "dashboard"
    dashboard_dir.mkdir(parents=True)
    (dashboard_dir / "triton.log").write_text("line 1\nline 2\nline 3\n", encoding="utf-8")

    client = TestClient(web_api.app)
    res = client.get("/api/runtime/logs/read", params={"source": "triton", "tail_lines": 2, "page": 1})
    assert res.status_code == 200
    payload = res.json()
    assert payload["id"] == "triton"
    assert payload["inspectOnly"] is True
    assert payload["content"] == "line 2\nline 3\n"
    assert payload["totalLines"] == 3

def test_admin_timezone_status_uses_system_timezone_when_not_configured(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv(str(web_api.EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(str(web_api.EnvVar.TIMEZONE), raising=False)
    monkeypatch.setattr(web_api, "_detect_system_timezone", lambda: "UTC")
    monkeypatch.setattr(runtime_component, "detect_system_timezone", lambda: "UTC")

    client = TestClient(web_api.app)
    res = client.get("/api/admin/timezone")
    assert res.status_code == 200
    payload = res.json()
    assert payload["configured"] is False
    assert payload["timezone"] == "UTC"
    assert payload["source"] == "system"
    assert payload["override"] is None
    assert payload["envPath"] == ".env"
    assert payload["overrideValid"] is True

def test_admin_timezone_set_and_clear(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(str(web_api.EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(web_api, "_detect_system_timezone", lambda: "UTC")
    monkeypatch.setattr(runtime_component, "detect_system_timezone", lambda: "UTC")

    client = TestClient(web_api.app)

    set_response = client.post(
        "/api/admin/timezone",
        json={"timezone": "Europe/Warsaw"},
    )
    assert set_response.status_code == 200
    set_payload = set_response.json()
    assert set_payload["configured"] is True
    assert set_payload["timezone"] == "Europe/Warsaw"
    assert set_payload["source"] == "env"
    assert set_payload["override"] == "Europe/Warsaw"
    assert set_payload["overrideValid"] is True
    assert set_payload["envPath"] == ".env"
    assert web_api.os.getenv(str(web_api.EnvVar.TIMEZONE)) == "Europe/Warsaw"

    env_path = tmp_path / ".env"
    assert env_path.exists()
    env_text = env_path.read_text(encoding="utf-8")
    assert "TODOIST_TIMEZONE" in env_text
    assert "Europe/Warsaw" in env_text

    clear_response = client.delete("/api/admin/timezone")
    assert clear_response.status_code == 200
    clear_payload = clear_response.json()
    assert clear_payload["configured"] is False
    assert clear_payload["timezone"] == "UTC"
    assert clear_payload["source"] == "system"
    assert clear_payload["override"] is None
    assert clear_payload["envPath"] == ".env"
    assert web_api.os.getenv(str(web_api.EnvVar.TIMEZONE)) is None

    env_text_after_clear = env_path.read_text(encoding="utf-8")
    assert "TODOIST_TIMEZONE" not in env_text_after_clear

def test_admin_timezone_rejects_invalid_timezone(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(str(web_api.EnvVar.CACHE_DIR), str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(web_api, "_detect_system_timezone", lambda: "UTC")
    monkeypatch.setattr(runtime_component, "detect_system_timezone", lambda: "UTC")

    client = TestClient(web_api.app)
    response = client.post(
        "/api/admin/timezone",
        json={"timezone": "Invalid/Timezone"},
    )
    assert response.status_code == 400
    payload = response.json()
    assert "Invalid timezone" in payload["detail"]

def test_admin_api_token_status_uses_safe_env_label(monkeypatch, tmp_path) -> None:
    env_path = tmp_path / ".env"
    monkeypatch.setattr(web_api, "_resolve_env_path", lambda: env_path)
    monkeypatch.setenv("API_KEY", "test_api_key_12345")

    client = TestClient(web_api.app)
    res = client.get("/api/admin/api_token")

    assert res.status_code == 200
    payload = res.json()
    assert payload["configured"] is True
    assert payload["masked"] == "••••2345"
    assert payload["envPath"] == ".env"

def test_admin_api_token_save_clear_and_status_cycle(monkeypatch, tmp_path) -> None:
    env_path = tmp_path / ".env"
    token = "a" * 32
    monkeypatch.setattr(web_api, "_resolve_env_path", lambda: env_path)
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.setattr(web_api, "_validate_api_token", lambda _token: (True, None, 3))

    client = TestClient(web_api.app)

    save = client.post("/api/admin/api_token", json={"token": token, "validate": True})
    assert save.status_code == 200
    assert save.json()["configured"] is True
    assert save.json()["validated"] is True
    assert save.json()["labelsCount"] == 3
    assert os.environ["API_KEY"] == token
    assert f"API_KEY='{token}'" in env_path.read_text(encoding="utf-8")

    status = client.get("/api/admin/api_token")
    assert status.status_code == 200
    assert status.json()["configured"] is True
    assert status.json()["masked"] == "••••aaaa"

    clear = client.delete("/api/admin/api_token")
    assert clear.status_code == 200
    assert clear.json()["configured"] is False
    assert "API_KEY" not in os.environ

    status_after_clear = client.get("/api/admin/api_token")
    assert status_after_clear.status_code == 200
    assert status_after_clear.json()["configured"] is False
    assert status_after_clear.json()["masked"] == ""
    assert "API_KEY" not in env_path.read_text(encoding="utf-8")

def test_openapi_includes_app_version() -> None:
    client = TestClient(web_api.app)
    res = client.get("/openapi.json")
    assert res.status_code == 200
    payload = res.json()
    assert payload["info"]["version"] == web_api.app.version == todoist.__version__

def test_dashboard_progress_inactive_state() -> None:
    """Test progress endpoint returns correct structure when inactive."""
    # Reset progress state to inactive
    web_api._progress_state.active = False
    web_api._progress_state.stage = None
    web_api._progress_state.step = 0
    web_api._progress_state.total_steps = 0
    web_api._progress_state.started_at = None
    web_api._progress_state.updated_at = "2025-01-01T00:00:00"
    web_api._progress_state.detail = None
    web_api._progress_state.error = None

    client = TestClient(web_api.app)
    res = client.get("/api/dashboard/progress")
    assert res.status_code == 200
    payload = res.json()

    # Verify structure
    assert "active" in payload
    assert "stage" in payload
    assert "step" in payload
    assert "totalSteps" in payload
    assert "startedAt" in payload
    assert "updatedAt" in payload
    assert "detail" in payload
    assert "error" in payload

    # Verify inactive state
    assert payload["active"] is False
    assert payload["stage"] is None
    assert payload["step"] == 0
    assert payload["totalSteps"] == 0
    assert payload["startedAt"] is None
    assert payload["error"] is None

def test_dashboard_progress_active_state() -> None:
    """Test progress endpoint returns correct structure when active."""
    # Set progress state to active
    web_api._progress_state.active = True
    web_api._progress_state.stage = "Loading data"
    web_api._progress_state.step = 2
    web_api._progress_state.total_steps = 5
    web_api._progress_state.started_at = "2025-01-01T10:00:00"
    web_api._progress_state.updated_at = "2025-01-01T10:00:30"
    web_api._progress_state.detail = "Fetching projects"
    web_api._progress_state.error = None

    client = TestClient(web_api.app)
    res = client.get("/api/dashboard/progress")
    assert res.status_code == 200
    payload = res.json()

    # Verify active state with all fields populated
    assert payload["active"] is True
    assert payload["stage"] == "Loading data"
    assert payload["step"] == 2
    assert payload["totalSteps"] == 5
    assert payload["startedAt"] == "2025-01-01T10:00:00"
    assert payload["updatedAt"] == "2025-01-01T10:00:30"
    assert payload["detail"] == "Fetching projects"
    assert payload["error"] is None

def test_dashboard_progress_with_error() -> None:
    """Test progress endpoint returns error state correctly."""
    # Set progress state with error
    web_api._progress_state.active = False
    web_api._progress_state.stage = None
    web_api._progress_state.step = 0
    web_api._progress_state.total_steps = 0
    web_api._progress_state.started_at = None
    web_api._progress_state.updated_at = "2025-01-01T10:05:00"
    web_api._progress_state.detail = None
    web_api._progress_state.error = "Failed to connect to API"

    client = TestClient(web_api.app)
    res = client.get("/api/dashboard/progress")
    assert res.status_code == 200
    payload = res.json()

    # Verify error is captured
    assert payload["active"] is False
    assert payload["error"] == "Failed to connect to API"
    assert payload["updatedAt"] == "2025-01-01T10:05:00"

def test_dashboard_progress_without_error() -> None:
    """Test progress endpoint handles state without error correctly."""
    # Set progress state without error
    web_api._progress_state.active = True
    web_api._progress_state.stage = "Processing"
    web_api._progress_state.step = 1
    web_api._progress_state.total_steps = 3
    web_api._progress_state.started_at = "2025-01-01T12:00:00"
    web_api._progress_state.updated_at = "2025-01-01T12:00:15"
    web_api._progress_state.detail = None
    web_api._progress_state.error = None

    client = TestClient(web_api.app)
    res = client.get("/api/dashboard/progress")
    assert res.status_code == 200
    payload = res.json()

    # Verify no error
    assert payload["active"] is True
    assert payload["error"] is None
    assert payload["stage"] == "Processing"

def test_dashboard_progress_ignores_adaptive_activity_page_counts() -> None:
    web_api._progress_state.active = False
    web_api._progress_state.stage = None
    web_api._progress_state.step = 0
    web_api._progress_state.total_steps = 0
    web_api._progress_state.started_at = None
    web_api._progress_state.updated_at = None
    web_api._progress_state.detail = None
    web_api._progress_state.sub_current = None
    web_api._progress_state.sub_total = None
    web_api._progress_state.error = None

    callback = web_api._build_tqdm_progress_callback()
    callback("Fetching activity history", 1, 2, "page")

    client = TestClient(web_api.app)
    payload = client.get("/api/dashboard/progress").json()
    assert payload["active"] is False
    assert payload["subCurrent"] is None
    assert payload["subTotal"] is None

    callback("Fetching activity history", 1, 3, "window")

    payload = client.get("/api/dashboard/progress").json()
    assert payload["active"] is True
    assert payload["detail"] == "Fetching activity history: 1/3 window"
    assert payload["subCurrent"] == 1
    assert payload["subTotal"] == 3

def test_dashboard_progress_uses_verbose_tqdm_detail() -> None:
    web_api._progress_state.active = False
    web_api._progress_state.stage = None
    web_api._progress_state.step = 0
    web_api._progress_state.total_steps = 0
    web_api._progress_state.started_at = None
    web_api._progress_state.updated_at = None
    web_api._progress_state.detail = None
    web_api._progress_state.sub_current = None
    web_api._progress_state.sub_total = None
    web_api._progress_state.error = None

    callback = web_api._build_tqdm_progress_callback()
    callback(
        "Fetching activity history",
        1,
        3,
        "window",
        "Fetching activity history: window 1 scanning 2026-03-05 to 2026-05-14 UTC; workers=1",
    )

    client = TestClient(web_api.app)
    payload = client.get("/api/dashboard/progress").json()
    assert payload["detail"] == (
        "Fetching activity history: window 1 scanning 2026-03-05 to 2026-05-14 UTC; workers=1"
    )
    assert payload["subCurrent"] == 1
    assert payload["subTotal"] == 3

def test_dashboard_status_includes_triton_service(monkeypatch) -> None:
    monkeypatch.setattr(web_api, "_triton_ready", lambda _settings: True)

    client = TestClient(web_api.app)
    res = client.get("/api/dashboard/status")

    assert res.status_code == 200
    payload = res.json()
    assert any(svc.get("name") == "Triton" for svc in payload["services"])
