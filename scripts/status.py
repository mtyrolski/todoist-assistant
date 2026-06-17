#!/usr/bin/env python3

"""Pretty-print local app and service status for the dashboard stack."""

import json
import os
import sys
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API_BASE_URL = "http://127.0.0.1:8000"
FRONTEND_URL = "http://127.0.0.1:3000"


@dataclass
class EndpointResult:
    ok: bool
    status_code: int | None
    payload: dict[str, Any] | None
    error: str | None = None


class _Ansi:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    GRAY = "\033[90m"


def _supports_color() -> bool:
    return sys.stdout.isatty() and not os.getenv("NO_COLOR")


def _paint(text: str, color: str, *, bold: bool = False, dim: bool = False) -> str:
    if not _supports_color():
        return text
    prefix = ""
    if bold:
        prefix += _Ansi.BOLD
    if dim:
        prefix += _Ansi.DIM
    prefix += color
    return f"{prefix}{text}{_Ansi.RESET}"


def _status_badge(status: str) -> str:
    normalized = status.strip().lower()
    label = {
        "ok": "OK",
        "warn": "WARN",
        "neutral": "INFO",
        "down": "DOWN",
    }.get(normalized, normalized.upper() or "INFO")
    color = {
        "ok": _Ansi.GREEN,
        "warn": _Ansi.YELLOW,
        "neutral": _Ansi.CYAN,
        "down": _Ansi.RED,
    }.get(normalized, _Ansi.GRAY)
    return _paint(f"[{label}]", color, bold=True)


def _section(title: str) -> None:
    print(_paint(title, _Ansi.CYAN, bold=True))


def _print_line(label: str, status: str, detail: str, *, indent: str = "") -> None:
    label_text = _paint(label, _Ansi.WHITE, bold=True)
    badge = _status_badge(status)
    print(f"{indent}{badge} {label_text:<18} {detail}")


def _fetch_json(url: str) -> EndpointResult:
    request = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=2.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return EndpointResult(ok=True, status_code=response.status, payload=payload)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        return EndpointResult(
            ok=False,
            status_code=exc.code,
            payload=None,
            error=detail or f"HTTP {exc.code}",
        )
    except URLError as exc:
        return EndpointResult(
            ok=False, status_code=None, payload=None, error=str(exc.reason)
        )


def _fetch_http_code(url: str) -> tuple[bool, int | None, str | None]:
    request = Request(url, method="HEAD")
    try:
        with urlopen(request, timeout=2.0) as response:
            return True, response.status, None
    except HTTPError as exc:
        return True, exc.code, None
    except URLError as exc:
        return False, None, str(exc.reason)


def _print_services(payload: dict[str, Any]) -> None:
    services = payload.get("services")
    if not isinstance(services, list) or not services:
        _print_line("Dashboard", "warn", "no service entries returned")
        return

    for service in services:
        if not isinstance(service, dict):
            continue
        name = str(service.get("name") or "Unknown")
        status = str(service.get("status") or "neutral")
        detail = str(service.get("detail") or "no detail")
        _print_line(name, status, detail)


def _print_llm_snapshot(payload: dict[str, Any]) -> None:
    _section("LLM Runtime")
    backend_raw = payload.get("backend")
    model_raw = payload.get("model")
    device_raw = payload.get("device")
    env_path_raw = payload.get("envPath")
    queue_raw = payload.get("queue")
    backend = backend_raw if isinstance(backend_raw, dict) else {}
    model = model_raw if isinstance(model_raw, dict) else {}
    device = device_raw if isinstance(device_raw, dict) else {}
    env_path = str(
        env_path_raw
        or backend.get("envPath")
        or model.get("envPath")
        or device.get("envPath")
        or ""
    ).strip()
    queue = queue_raw if isinstance(queue_raw, dict) else {}

    backend_label = str(backend.get("label") or backend.get("selected") or "unknown")
    backend_selected = str(backend.get("selected") or backend_label).strip().lower()
    backend_status = (
        "ok" if payload.get("enabled") or backend_selected == "codex" else "warn"
    )
    _print_line("Backend", backend_status, backend_label)

    model_active = str(model.get("active") or model.get("selected") or "unknown")
    model_selected = str(model.get("label") or model.get("selected") or model_active)
    model_detail = model_selected
    if model_active != model_selected:
        model_detail = f"{model_selected} (active: {model_active})"
    _print_line("Selected model", "neutral", model_detail)
    if env_path:
        _print_line("Settings source", "neutral", env_path)

    device_label = str(device.get("label") or device.get("selected") or "unknown")
    _print_line("Device", "neutral", device_label)

    queue_detail = (
        f"{int(queue.get('queued') or 0)} queued, "
        f"{int(queue.get('running') or 0)} running, "
        f"{int(queue.get('done') or 0)} done, "
        f"{int(queue.get('failed') or 0)} failed"
    )
    _print_line("Queue", "neutral", queue_detail)


def main() -> int:
    _section("Dashboard Status")

    health = _fetch_json(f"{API_BASE_URL}/api/health")
    if health.ok and health.payload:
        version = health.payload.get("version") or "unknown"
        _print_line("API", "ok", f"online at {API_BASE_URL} (v{version})")
    else:
        error = health.error or "unavailable"
        _print_line("API", "down", f"offline at {API_BASE_URL} ({error})")

    frontend_ok, frontend_status, frontend_error = _fetch_http_code(FRONTEND_URL)
    if frontend_ok:
        _print_line(
            "Frontend", "ok", f"reachable at {FRONTEND_URL} (HTTP {frontend_status})"
        )
    else:
        _print_line("Frontend", "down", f"offline at {FRONTEND_URL} ({frontend_error})")

    llm_snapshot = _fetch_json(f"{API_BASE_URL}/api/dashboard/llm_chat")
    if llm_snapshot.ok and llm_snapshot.payload:
        print()
        _print_llm_snapshot(llm_snapshot.payload)
    else:
        print()
        _section("LLM Runtime")
        error = llm_snapshot.error or "unavailable"
        _print_line("LLM", "down", f"status endpoint unavailable ({error})")

    print()
    _section("Services")
    dashboard_status = _fetch_json(f"{API_BASE_URL}/api/dashboard/status")
    if not dashboard_status.ok or not dashboard_status.payload:
        error = dashboard_status.error or "unavailable"
        _print_line("Dashboard", "down", f"status endpoint unavailable ({error})")
        return 0

    _print_services(dashboard_status.payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
