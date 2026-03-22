from collections.abc import Mapping
from pathlib import Path
import os
from typing import Any, cast

from omegaconf import DictConfig, OmegaConf

from todoist.env import EnvVar

DEFAULT_OBSERVER_SETTINGS: dict[str, Any] = {
    "enabled": True,
    "refresh_interval_minutes": 0.5,
}


def resolve_dashboard_config_path() -> Path:
    override = os.getenv(str(EnvVar.CONFIG_DIR))
    if override:
        return Path(override).expanduser().resolve() / "dashboard.yaml"
    return Path(__file__).resolve().parents[1] / "configs" / "dashboard.yaml"


def load_dashboard_config(path: Path | None = None) -> DictConfig:
    config_path = path or resolve_dashboard_config_path()
    if not config_path.exists():
        return OmegaConf.create({})
    loaded = OmegaConf.load(config_path)
    if isinstance(loaded, DictConfig):
        return loaded
    return cast(DictConfig, OmegaConf.create(loaded if isinstance(loaded, Mapping) else {}))


def _config_path_label(path: Path) -> str:
    repo_root = Path(__file__).resolve().parents[1]
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def observer_settings_payload(config: DictConfig, *, path: Path | None = None) -> dict[str, Any]:
    raw = config.get("observer") if hasattr(config, "get") else None
    data = OmegaConf.to_container(raw, resolve=False) if raw is not None else {}
    if not isinstance(data, dict):
        data = {}
    effective_path = path or resolve_dashboard_config_path()
    try:
        refresh_minutes = float(
            data.get(
                "refresh_interval_minutes",
                DEFAULT_OBSERVER_SETTINGS["refresh_interval_minutes"],
            )
        )
    except (TypeError, ValueError):
        refresh_minutes = float(DEFAULT_OBSERVER_SETTINGS["refresh_interval_minutes"])
    return {
        "enabled": bool(data.get("enabled", DEFAULT_OBSERVER_SETTINGS["enabled"])),
        "refreshIntervalMinutes": refresh_minutes,
        "configPath": _config_path_label(effective_path),
    }


def update_observer_settings(
    config: DictConfig,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    current = config.get("observer") if hasattr(config, "get") else None
    if isinstance(current, DictConfig):
        observer_cfg = cast(dict[str, Any], OmegaConf.to_container(current, resolve=False) or {})
    elif isinstance(current, Mapping):
        observer_cfg = dict(current)
    else:
        observer_cfg = {}

    if "enabled" in payload:
        observer_cfg["enabled"] = bool(payload["enabled"])
    if "refreshIntervalMinutes" in payload:
        try:
            refresh_minutes = float(payload["refreshIntervalMinutes"])
        except (TypeError, ValueError) as exc:
            raise ValueError("refreshIntervalMinutes must be numeric") from exc
        if refresh_minutes <= 0:
            raise ValueError("refreshIntervalMinutes must be greater than zero")
        observer_cfg["refresh_interval_minutes"] = refresh_minutes

    config["observer"] = observer_cfg
    return observer_settings_payload(config)
