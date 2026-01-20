import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, TypeAlias, cast

from pydantic import BaseModel, Field, field_validator


# === LLM BREAKDOWN MODELS ====================================================

QueueItem: TypeAlias = dict[str, Any]


@dataclass
class QueueContext:
    items: list[QueueItem]
    ids: set[str]
    next_depth: int
    limit: int
    label: str
    variant: str
    enabled: bool = True

    def enqueue(self, task_id: str) -> None:
        if not self.enabled or self.next_depth > self.limit:
            return
        if task_id in self.ids:
            return
        self.items.append(
            {
                "task_id": task_id,
                "label": self.label,
                "variant": self.variant,
                "depth": self.next_depth,
            }
        )
        self.ids.add(task_id)


def _normalize_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _normalize_children(value: object) -> list[dict[str, Any] | "BreakdownNode"]:
    if value is None:
        return []
    if isinstance(value, list):
        normalized: list[NormalizedChild] = []
        for item in value:
            if isinstance(item, str):
                normalized.append({"content": item})
            elif isinstance(item, BreakdownNode):
                normalized.append(item)
            elif isinstance(item, dict):
                normalized.append(item)
            else:
                normalized.append({"content": _normalize_text(item)})
        return normalized
    return []


class BreakdownNode(BaseModel):
    content: str | None = None
    description: str | None = None
    priority: int | None = None
    expand: bool | None = None
    children: list["BreakdownNode"] = Field(default_factory=list)

    @field_validator("content", "description", mode="before")
    @classmethod
    def _normalize_text(cls, value: object) -> str | None:
        return _normalize_text(value)

    @field_validator("priority", mode="before")
    @classmethod
    def _coerce_priority(cls, value: object) -> int | None:
        if value is None:
            return None
        try:
            return int(cast(Any, value))
        except (TypeError, ValueError):
            return None

    @field_validator("children", mode="before")
    @classmethod
    def _normalize_children(cls, value: object) -> list[dict[str, Any] | "BreakdownNode"]:
        return _normalize_children(value)


class TaskBreakdown(BaseModel):
    children: list[BreakdownNode] = Field(default_factory=list)

    @field_validator("children", mode="before")
    @classmethod
    def _normalize_children(cls, value: object) -> list[dict[str, Any] | "BreakdownNode"]:
        return _normalize_children(value)


BreakdownNode.model_rebuild()


NormalizedChild: TypeAlias = dict[str, Any] | BreakdownNode


class ProgressKey(StrEnum):
    ACTIVE = "active"
    STATUS = "status"
    RUN_ID = "run_id"
    STARTED_AT = "started_at"
    UPDATED_AT = "updated_at"
    TASKS_TOTAL = "tasks_total"
    TASKS_COMPLETED = "tasks_completed"
    TASKS_FAILED = "tasks_failed"
    TASKS_PENDING = "tasks_pending"
    CURRENT = "current"
    ERROR = "error"
    PROCESSED_IDS = "processed_ids"
    RESULTS = "results"


class ProgressStatus(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    FAILED = "failed"
    COMPLETED = "completed"


class CurrentKey(StrEnum):
    TASK_ID = "task_id"
    CONTENT = "content"
    LABEL = "label"
    DEPTH = "depth"
