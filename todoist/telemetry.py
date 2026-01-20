import json
import os
from pathlib import Path
import sys
from typing import Any
from urllib.request import Request, urlopen

from todoist.version import get_version

CONFIG_FILENAME = "telemetry.json"
SENTINEL_FILENAME = ".telemetry_sent"


def default_data_dir() -> Path:
    override = os.getenv("TODOIST_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        base = os.getenv("PROGRAMDATA") or os.getenv("LOCALAPPDATA") or str(Path.home())
        return Path(base) / "TodoistAssistant"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "TodoistAssistant"
    return Path.home() / ".local" / "share" / "todoist-assistant"


def resolve_config_dir() -> Path:
    override = os.getenv("TODOIST_CONFIG_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return default_data_dir() / "config"


def _config_path(config_dir: Path) -> Path:
    return config_dir / CONFIG_FILENAME


def _sentinel_path(data_dir: Path) -> Path:
    return data_dir / SENTINEL_FILENAME


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _read_windows_registry_opt_in() -> bool | None:
    if os.name != "nt":
        return None
    try:
        import winreg
    except ImportError:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"Software\TodoistAssistant") as key:
            value, _ = winreg.QueryValueEx(key, "telemetry_opt_in")
            return bool(int(value))
    except OSError:
        return None


def bootstrap_config(config_dir: Path) -> bool:
    config_path = _config_path(config_dir)
    existing = _read_json(config_path)
    if existing and isinstance(existing.get("enabled"), bool):
        return bool(existing["enabled"])

    opt_in = _read_windows_registry_opt_in()
    if opt_in is None:
        opt_in = False

    _write_json(config_path, {"enabled": bool(opt_in)})
    return bool(opt_in)


def set_enabled(config_dir: Path, enabled: bool) -> None:
    _write_json(_config_path(config_dir), {"enabled": bool(enabled)})


def is_enabled(config_dir: Path) -> bool:
    config = _read_json(_config_path(config_dir)) or {}
    return bool(config.get("enabled", False))


def _endpoint() -> str | None:
    return os.getenv("TODOIST_TELEMETRY_ENDPOINT")


def _debug_enabled() -> bool:
    value = os.getenv("TODOIST_TELEMETRY_DEBUG", "")
    return value.strip().lower() in {"1", "true", "yes"}


def _log_debug(message: str) -> None:
    if _debug_enabled():
        print(f"[telemetry] {message}", file=sys.stderr)


def send_event(event: str, *, config_dir: Path, _data_dir: Path) -> bool:
    if not is_enabled(config_dir):
        _log_debug("Telemetry disabled; skipping event.")
        return False
    endpoint = _endpoint()
    if not endpoint:
        _log_debug("TODOIST_TELEMETRY_ENDPOINT not set; skipping event.")
        return False

    payload = {
        "event": event,
        "version": get_version(),
        "os": sys.platform,
    }
    body = json.dumps(payload).encode("utf-8")
    request = Request(endpoint, data=body, headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=5):
            return True
    except Exception as exc:
        _log_debug(f"Telemetry request failed: {exc}")
        return False


def maybe_send_install_success(config_dir: Path, data_dir: Path) -> None:
    sentinel = _sentinel_path(data_dir)
    if sentinel.exists():
        return
    if send_event("install_success", config_dir=config_dir, _data_dir=data_dir):
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_text("sent\n", encoding="utf-8")


def maybe_send_install_failure(config_dir: Path, data_dir: Path) -> None:
    send_event("install_failure", config_dir=config_dir, _data_dir=data_dir)
