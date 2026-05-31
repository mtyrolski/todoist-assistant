
from collections.abc import Callable, Mapping
from pathlib import Path
import re
from typing import Any, cast

from fastapi import HTTPException
from omegaconf import DictConfig, OmegaConf


_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_-]*$")


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
    if loaded is None:
        return OmegaConf.create({})
    return cast(DictConfig, loaded)


def save_yaml_config(path: Path, config: DictConfig) -> None:
    try:
        OmegaConf.save(config, path, resolve=False)
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=500, detail=f"Failed to write {path.name}: {exc}"
        ) from exc


def ensure_identifier(value: str, *, label: str) -> str:
    cleaned = value.strip().lower()
    if not cleaned or not _IDENTIFIER_RE.match(cleaned):
        raise HTTPException(
            status_code=400,
            detail=f"{label} must match /^[a-z][a-z0-9_-]*$/",
        )
    return cleaned


def template_path(templates_dir: Path, category: str, name: str) -> Path:
    safe_category = ensure_identifier(category, label="category")
    safe_name = ensure_identifier(name, label="template name")
    return templates_dir / safe_category / f"{safe_name}.yaml"


def template_defaults_key(category: str, name: str) -> str:
    return f"templates/{category}@{category}.{name}"


def load_defaults_list(config: DictConfig) -> list[Any]:
    defaults = config.get("defaults")
    if defaults is None:
        return []
    data = OmegaConf.to_container(defaults, resolve=False)
    return data if isinstance(data, list) else []


def normalize_template_node(raw: Mapping[str, Any]) -> dict[str, Any]:
    content = str(raw.get("content", "")).strip()
    if not content:
        raise HTTPException(status_code=400, detail="Template content is required")
    payload: dict[str, Any] = {"content": content}
    description = raw.get("description")
    if description not in (None, ""):
        payload["description"] = str(description)
    due_delta = raw.get("due_date_days_difference")
    if due_delta is None:
        due_delta = raw.get("dueDateDaysDifference")
    if due_delta not in (None, ""):
        try:
            payload["due_date_days_difference"] = int(due_delta)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=400, detail="due_date_days_difference must be an integer"
            ) from exc
    children = raw.get("children") or []
    if children:
        if not isinstance(children, list):
            raise HTTPException(status_code=400, detail="children must be a list")
        payload["children"] = [normalize_template_node(child) for child in children]
    return payload


def template_to_camel(raw: Mapping[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "content": raw.get("content", ""),
    }
    if raw.get("description") not in (None, ""):
        payload["description"] = raw.get("description")
    if raw.get("due_date_days_difference") not in (None, ""):
        payload["dueDateDaysDifference"] = raw.get("due_date_days_difference")
    children = raw.get("children") or []
    if isinstance(children, list) and children:
        payload["children"] = [
            template_to_camel(child)
            for child in children
            if isinstance(child, Mapping)
        ]
    return payload


def template_summary(
    path: Path,
    *,
    config_dir: Path,
    read_config: Callable[[Path], DictConfig],
) -> dict[str, Any]:
    cfg = read_config(path)
    data = OmegaConf.to_container(cfg, resolve=False)
    if not isinstance(data, dict):
        data = {}
    category = path.parent.name
    name = path.stem
    raw_children = data.get("children")
    children: list[Any] = raw_children if isinstance(raw_children, list) else []
    return {
        "category": category,
        "name": name,
        "title": data.get("content", name),
        "description": data.get("description"),
        "path": str(path.relative_to(config_dir)),
        "label": f"template-{name}",
        "childrenCount": len(children),
    }
