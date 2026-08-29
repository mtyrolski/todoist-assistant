from pathlib import Path
from typing import cast

from fastapi import HTTPException
from omegaconf import DictConfig, OmegaConf


def read_yaml_config(path: Path, *, required: bool = True) -> DictConfig:
    if not path.exists():
        if required:
            raise HTTPException(status_code=404, detail=f"Missing config file: {path.name}")
        return OmegaConf.create({})
    try:
        loaded = OmegaConf.load(path)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=f"Failed to read {path.name}: {exc}") from exc
    return OmegaConf.create({}) if loaded is None else cast(DictConfig, loaded)


def save_yaml_config(path: Path, config: DictConfig) -> None:
    try:
        OmegaConf.save(config, path, resolve=False)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=f"Failed to write {path.name}: {exc}") from exc
