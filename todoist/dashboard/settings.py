from collections.abc import Mapping
from pathlib import Path
import os
from typing import cast

from omegaconf import DictConfig, OmegaConf

from todoist.core.env import EnvVar

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
    return cast(
        DictConfig, OmegaConf.create(loaded if isinstance(loaded, Mapping) else {})
    )


def _config_path_label(path: Path) -> str:
    repo_root = Path(__file__).resolve().parents[1]
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)
