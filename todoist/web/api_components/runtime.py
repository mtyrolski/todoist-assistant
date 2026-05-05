from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import dotenv_values

from todoist.api.client import RequestSpec, TimeoutSettings, TodoistAPIClient
from todoist.api.endpoints import TodoistEndpoints
from todoist.env import EnvVar
from todoist.runtime_env import resolve_runtime_env_path


REPO_ROOT = Path(__file__).resolve().parents[3]

_API_KEY_PLACEHOLDERS = {
    "put your api here",
    "put your api key here",
    "your todoist api key",
}
_API_KEY_MIN_LENGTH = 20
_API_KEY_HEX_RE = re.compile(r"^[a-fA-F0-9]{32,64}$")
_API_KEY_FALLBACK_RE = re.compile(r"^[A-Za-z0-9_-]{20,128}$")


def resolve_data_dir() -> Path:
    override = os.getenv(str(EnvVar.DATA_DIR)) or os.getenv(str(EnvVar.CACHE_DIR))
    if override:
        return Path(override).expanduser().resolve()
    return REPO_ROOT


def resolve_config_dir() -> Path:
    override = os.getenv(str(EnvVar.CONFIG_DIR))
    if override:
        return Path(override).expanduser().resolve()
    return REPO_ROOT / "configs"


def dashboard_state_dir() -> Path:
    override = os.getenv("DASHBOARD_STATE_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return REPO_ROOT / ".cache" / "todoist-assistant" / "dashboard"


def dashboard_pid_dir() -> Path:
    override = os.getenv("DASHBOARD_PID_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return dashboard_state_dir() / "pids"


def resolve_env_path() -> Path:
    return resolve_runtime_env_path(repo_root=REPO_ROOT)


def normalize_api_key(raw: str | None) -> str:
    if not raw:
        return ""
    value = str(raw).strip().strip("'\"")
    if not value:
        return ""
    if value.strip().lower() in _API_KEY_PLACEHOLDERS:
        return ""
    return value


def looks_like_api_key(value: str) -> bool:
    if len(value) < _API_KEY_MIN_LENGTH:
        return False
    if any(char.isspace() for char in value):
        return False
    if _API_KEY_HEX_RE.fullmatch(value):
        return True
    return _API_KEY_FALLBACK_RE.fullmatch(value) is not None


def resolve_api_key() -> str:
    env_value = normalize_api_key(os.getenv("API_KEY"))
    if env_value:
        return env_value
    env_path = resolve_env_path()
    if env_path.exists():
        data = dotenv_values(env_path)
        file_value = normalize_api_key(data.get("API_KEY"))
        if file_value:
            os.environ["API_KEY"] = file_value
            return file_value
    return ""


def normalize_timezone(raw: Any) -> str:
    if raw is None:
        return ""
    return str(raw).strip().strip("'\"")


def is_valid_timezone_name(value: str) -> bool:
    if not value:
        return False
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError:
        return False
    except Exception:
        return False
    return True


def detect_system_timezone() -> str:
    local_timezone = datetime.now().astimezone().tzinfo
    if local_timezone is None:
        return "UTC"

    key = getattr(local_timezone, "key", None)
    if isinstance(key, str) and key.strip():
        return key

    timezone_name = local_timezone.tzname(None)
    if isinstance(timezone_name, str) and timezone_name.strip():
        return timezone_name

    return "UTC"


def safe_display_path(path: Path, *, root: Path | None = None) -> str:
    if root is not None:
        try:
            return str(path.relative_to(root))
        except ValueError:
            pass
    name = path.name.strip()
    return name or str(path)


def resolve_timezone_status() -> dict[str, Any]:
    env_path = resolve_env_path()
    timezone_key = str(EnvVar.TIMEZONE)
    system_timezone = detect_system_timezone()

    override = normalize_timezone(os.getenv(timezone_key))
    if not override and env_path.exists():
        data = dotenv_values(env_path)
        override = normalize_timezone(data.get(timezone_key))
        if override:
            os.environ[timezone_key] = override

    payload: dict[str, Any] = {
        "configured": False,
        "timezone": system_timezone,
        "source": "system",
        "override": None,
        "overrideValid": True,
        "system": system_timezone,
        "envPath": safe_display_path(env_path, root=REPO_ROOT),
    }
    if not override:
        return payload

    payload["override"] = override
    if is_valid_timezone_name(override):
        payload["configured"] = True
        payload["timezone"] = override
        payload["source"] = "env"
        return payload

    payload["overrideValid"] = False
    payload["invalidOverride"] = override
    return payload


def mask_api_key(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "••••"
    return f"••••{value[-4:]}"


def validate_api_token(token: str) -> tuple[bool, str | None, int | None]:
    client = TodoistAPIClient(max_attempts=1)
    spec = RequestSpec(
        endpoint=TodoistEndpoints.LIST_LABELS,
        headers={"Authorization": f"Bearer {token}"},
        timeout=TimeoutSettings(connect=5.0, read=10.0),
        max_attempts=1,
    )
    try:
        payload = client.request_json(spec, operation_name="validate_api_token")
    except Exception as exc:  # pragma: no cover - network dependent
        return False, f"{type(exc).__name__}: {exc}", None

    if not isinstance(payload, dict):
        return False, f"Unexpected payload type: {type(payload).__name__}", None
    results = payload.get("results")
    if not isinstance(results, list):
        return False, "Unexpected labels response payload", None
    return True, None, len(results)
