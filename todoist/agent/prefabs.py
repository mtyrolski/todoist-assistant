"""YAML instruction prefabs used by the agent."""

from dataclasses import dataclass
from pathlib import Path

import yaml
from loguru import logger


@dataclass(frozen=True)
class InstructionPrefab:
    prefab_id: str
    description: str
    content: str
    path: Path


def load_instruction_prefabs(prefabs_dir: str | Path) -> list[InstructionPrefab]:
    root = Path(prefabs_dir)
    if not root.exists():
        return []

    prefabs: list[InstructionPrefab] = []
    for path in sorted(root.glob("*.y*ml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            logger.warning("Skipping prefab (not a mapping): {}", str(path))
            continue

        description = raw.get("describtion") or raw.get("description") or ""
        content = raw.get("content") or ""
        if not isinstance(description, str) or not isinstance(content, str) or not content.strip():
            logger.warning("Skipping prefab (invalid fields): {}", str(path))
            continue

        prefabs.append(
            InstructionPrefab(
                prefab_id=path.stem,
                description=description.strip(),
                content=content.strip(),
                path=path,
            ))
    return prefabs
