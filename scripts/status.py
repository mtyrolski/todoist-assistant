#!/usr/bin/env python3
# pylint: disable=cyclic-import

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
