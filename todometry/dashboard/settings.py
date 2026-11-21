from collections.abc import Mapping
from pathlib import Path
import os
from typing import cast

from omegaconf import DictConfig, OmegaConf

from todometry.core.env import EnvVar


def resolve_dashboard_config_path() -> Path:
    override = os.getenv(str(EnvVar.CONFIG_DIR))
    if override:
        return Path(override).expanduser().resolve() / "dashboard.yaml"
    data_dir = os.getenv(str(EnvVar.DATA_DIR))
    if data_dir:
        return Path(data_dir).expanduser().resolve() / "configs" / "dashboard.yaml"
    return Path(__file__).resolve().parents[2] / "configs" / "dashboard.yaml"


def load_dashboard_config(path: Path | None = None) -> DictConfig:
    config_path = path or resolve_dashboard_config_path()
    if not config_path.exists():
        return OmegaConf.create({})
    loaded = OmegaConf.load(config_path)
    if isinstance(loaded, DictConfig):
        return loaded
    return cast(
        DictConfig, OmegaConf.create(loaded if isinstance(loaded, Mapping) else {})
    )
