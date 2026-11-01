from pathlib import Path
import os
from tempfile import NamedTemporaryFile
from typing import cast

from fastapi import HTTPException
from omegaconf import DictConfig, OmegaConf


def read_yaml_config(path: Path, *, required: bool = True) -> DictConfig:
    if not path.exists():
        if required:
            raise HTTPException(
                status_code=404, detail=f"Missing config file: {path.name}"
            )
        return OmegaConf.create({})
    try:
        loaded = OmegaConf.load(path)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=500, detail=f"Failed to read {path.name}: {exc}"
        ) from exc
    return OmegaConf.create({}) if loaded is None else cast(DictConfig, loaded)


def save_yaml_config(path: Path, config: DictConfig) -> None:
    temporary_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as stream:
            temporary_path = Path(stream.name)
            OmegaConf.save(config, stream, resolve=False)
            stream.flush()
            os.fsync(stream.fileno())
        temporary_path.replace(path)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=500, detail=f"Failed to write {path.name}: {exc}"
        ) from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
