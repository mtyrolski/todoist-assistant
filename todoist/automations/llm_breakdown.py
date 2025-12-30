from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from datetime import datetime
from enum import StrEnum
from typing import Any, TypeAlias
from uuid import uuid4

from loguru import logger
from pydantic import BaseModel, Field, field_validator

from todoist.automations.base import Automation
from todoist.database.base import Database
from todoist.llm import LocalChatConfig, TransformersMistral3ChatModel
from todoist.llm.types import MessageRole
from todoist.types import Task
from todoist.utils import Cache


DEFAULT_VARIANTS: dict[str, dict[str, Any]] = {
    "breakdown": {
        "instruction": "Balanced breakdown with 4-6 top-level tasks.",
        "queue_depth": 1,
    },
    "breakdown-lite": {
        "instruction": "Keep it short and light.",
        "max_depth": 2,
        "max_children": 4,
        "queue_depth": 1,
    },
    "breakdown-deep": {
        "instruction": "Provide more detail and intermediate steps.",
        "max_depth": 2,
        "max_children": 6,
        "queue_depth": 2,
    },
}

BASE_SYSTEM_PROMPT = (
    "You are a task decomposition assistant for Todoist. "
    "Create a hierarchy of actionable subtasks. "
    "Use short imperative phrases with no numbering or markdown. "
    "Do not repeat the current task as a child. "
    "Limit depth to {max_depth} levels and at most {max_children} children per task. "
    "Each child should be an object with `content` and an `expand` boolean that says whether "
    "the child should be further decomposed in a later pass. "
    "Prefer returning only immediate children; avoid nested children unless necessary. "
    "The current task is provided in `task` with `content` (title) and `description`. "
    "If provided, `ancestors` lists parent tasks from root to direct parent; use them for context only."
)


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




def _normalize_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _normalize_children(value: object) -> list[NormalizedChild]:
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
            return int(value)
        except (TypeError, ValueError):
            return None

    @field_validator("children", mode="before")
    @classmethod
    def _normalize_children(cls, value: object) -> list[NormalizedChild]:
        return _normalize_children(value)


class TaskBreakdown(BaseModel):
    children: list[BreakdownNode] = Field(default_factory=list)

    @field_validator("children", mode="before")
    @classmethod
    def _normalize_children(cls, value: object) -> list[NormalizedChild]:
        return _normalize_children(value)


BreakdownNode.model_rebuild()

NormalizedChild: TypeAlias = dict[str, Any] | BreakdownNode


def _build_children_by_parent(tasks: Iterable[Task]) -> dict[str, list[Task]]:
    children_by_parent: dict[str, list[Task]] = {}
    for task in tasks:
        parent_id = _get_parent_id(task)
        if parent_id is None:
            continue
        children_by_parent.setdefault(parent_id, []).append(task)
    return children_by_parent


def _get_parent_id(task: Task) -> str | None:
    parent_id = task.task_entry.parent_id or task.task_entry.v2_parent_id
    if parent_id is None:
        return None
    return str(parent_id)


def _build_task_lookup(tasks: Iterable[Task]) -> dict[str, Task]:
    lookup: dict[str, Task] = {}
    for task in tasks:
        lookup[str(task.id)] = task
        v2_id = task.task_entry.v2_id
        if v2_id is not None:
            v2_id_str = str(v2_id)
            lookup.setdefault(v2_id_str, task)
    return lookup


def _find_llm_label(labels: Iterable[str], prefix_lower: str) -> str | None:
    for label in labels:
        if label.lower().startswith(prefix_lower):
            return label
    return None


def _sanitize_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _normalize_priority(value: int | None) -> int:
    if value is None:
        return 1
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 1
    return max(1, min(4, parsed))


def _build_ancestor_context(task: Task, tasks_by_id: Mapping[str, Task]) -> list[dict[str, str | None]]:
    ancestors: list[dict[str, str | None]] = []
    seen: set[str] = set()
    parent_id = _get_parent_id(task)
    while parent_id:
        if parent_id in seen:
            logger.warning("Detected cycle in task ancestry for task {}", task.id)
            break
        seen.add(parent_id)
        parent = tasks_by_id.get(parent_id)
        if parent is None:
            break
        ancestors.append(
            {
                "content": parent.task_entry.content,
                "description": parent.task_entry.description,
            }
        )
        parent_id = _get_parent_id(parent)
    ancestors.reverse()
    return ancestors


class LLMBreakdown(Automation):
    def __init__(
        self,
        frequency_in_minutes: float = 0.1,
        *,
        label_prefix: str = "llm-",
        default_variant: str = "breakdown",
        max_depth: int = 3,
        max_children: int = 6,
        max_total_tasks: int = 60,
        allow_existing_children: bool = False,
        remove_label_after_processing: bool = True,
        propagate_labels: bool = True,
        max_tasks_per_tick: int = 1,
        max_queue_depth: int = 1,
        auto_queue_children: bool = True,
        track_progress: bool = True,
        variants: Mapping[str, Mapping[str, Any]] | None = None,
        model_config: LocalChatConfig | Mapping[str, Any] | None = None,
    ):
        super().__init__("LLM Breakdown", frequency_in_minutes)

        self.label_prefix = label_prefix
        self.label_prefix_lower = label_prefix.lower()
        self.default_variant = default_variant
        self.max_depth = max_depth
        self.max_children = max_children
        self.max_total_tasks = max_total_tasks
        self.allow_existing_children = allow_existing_children
        self.remove_label_after_processing = remove_label_after_processing
        self.propagate_labels = propagate_labels
        self.max_tasks_per_tick = max(1, int(max_tasks_per_tick))
        self.max_queue_depth = max(1, int(max_queue_depth))
        self.auto_queue_children = auto_queue_children
        self.track_progress = track_progress
        self.variants = self._merge_variants(variants)
        self.model_config = self._coerce_model_config(model_config)
        self._llm: TransformersMistral3ChatModel | None = None
        self._progress_storage = Cache().llm_breakdown_progress

    def _merge_variants(
        self,
        variants: Mapping[str, Mapping[str, Any]] | None,
    ) -> dict[str, dict[str, Any]]:
        merged = {key: dict(value) for key, value in DEFAULT_VARIANTS.items()}
        if variants is None:
            return merged
        for key, value in variants.items():
            merged[key] = dict(value) if isinstance(value, Mapping) else {}
        return merged

    def _coerce_model_config(
        self,
        model_config: LocalChatConfig | Mapping[str, Any] | None,
    ) -> LocalChatConfig:
        if model_config is None:
            return LocalChatConfig()
        if isinstance(model_config, LocalChatConfig):
            return model_config
        if isinstance(model_config, Mapping):
            return LocalChatConfig(**dict(model_config))
        raise TypeError("model_config must be LocalChatConfig or Mapping[str, Any]")

    @staticmethod
    def _now_iso() -> str:
        return datetime.utcnow().isoformat(timespec="seconds")

    def _progress_save(self, payload: dict[str, Any]) -> None:
        if not self.track_progress:
            return
        try:
            self._progress_storage.save(payload)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to save LLM breakdown progress: {}", exc)

    def _progress_load(self) -> dict[str, Any]:
        if not self.track_progress:
            return {}
        try:
            payload = self._progress_storage.load()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to load LLM breakdown progress: {}", exc)
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        return payload

    def _get_llm(self) -> TransformersMistral3ChatModel:
        if self._llm is None:
            self._llm = TransformersMistral3ChatModel(self.model_config)
        return self._llm

    def _resolve_variant(self, label: str) -> tuple[str, dict[str, Any]]:
        label_lower = label.lower()
        variant_key = label_lower[len(self.label_prefix_lower):].strip() if label_lower.startswith(
            self.label_prefix_lower) else ""
        if not variant_key:
            variant_key = self.default_variant
        variant_cfg = self.variants.get(variant_key)
        if variant_cfg is None:
            logger.warning("Unknown LLM variant '{}'; falling back to '{}'", variant_key, self.default_variant)
            variant_key = self.default_variant
            variant_cfg = self.variants.get(variant_key, {})
        return variant_key, variant_cfg

    def _build_system_prompt(self, *, max_depth: int, max_children: int, instruction: str | None) -> str:
        prompt = BASE_SYSTEM_PROMPT.format(max_depth=max_depth, max_children=max_children)
        if instruction:
            prompt = f"{prompt} {instruction}"
        return prompt

    def _child_labels(self, task: Task) -> list[str] | None:
        if not self.propagate_labels:
            return None
        labels = [
            label
            for label in task.task_entry.labels
            if not label.lower().startswith(self.label_prefix_lower)
        ]
        return labels or None

    def _update_root_labels(self, db: Database, task: Task, label_to_remove: str) -> None:
        labels = task.task_entry.labels
        if not labels:
            return
        target = label_to_remove.lower()
        updated = [label for label in labels if label.lower() != target]
        if updated == labels:
            return
        db.update_task(task.id, labels=updated)

    def _insert_children(
        self,
        db: Database,
        *,
        root_task: Task,
        parent_id: str,
        nodes: list[BreakdownNode],
        depth: int,
        max_depth: int,
        max_children: int,
        max_total_tasks: int,
        labels: list[str] | None,
        created: list[int],
    ) -> None:
        if depth > max_depth:
            return
        for node in nodes[:max_children]:
            if created[0] >= max_total_tasks:
                logger.warning("Reached max_total_tasks={}; truncating tree", max_total_tasks)
                return
            content = _sanitize_text(node.content)
            if not content:
                continue
            description = _sanitize_text(node.description)
            priority = _normalize_priority(node.priority)
            result = db.insert_task(
                content=content,
                description=description,
                project_id=root_task.task_entry.project_id,
                parent_id=parent_id,
                priority=priority,
                labels=labels,
            )
            if "id" not in result:
                logger.error("Failed to insert subtask '{}'", content)
                continue
            created[0] += 1
            child_id = str(result["id"])
            self._insert_children(
                db,
                root_task=root_task,
                parent_id=child_id,
                nodes=node.children,
                depth=depth + 1,
                max_depth=max_depth,
                max_children=max_children,
                max_total_tasks=max_total_tasks,
                labels=labels,
                created=created,
            )

    def _tick(self, db: Database) -> None:
        logger.info("Running LLM Breakdown automation")
        projects = db.fetch_projects(include_tasks=True)
        all_tasks: list[Task] = [task for project in projects for task in project.tasks]
        logger.debug("Found {} tasks in total", len(all_tasks))

        children_by_parent = _build_children_by_parent(all_tasks)
        tasks_by_id = _build_task_lookup(all_tasks)
        now = self._now_iso()

        processed_ids: set[str] = set()
        previous_progress = self._progress_load()
        if not self.remove_label_after_processing:
            raw_processed = previous_progress.get(ProgressKey.PROCESSED_IDS.value)
            if isinstance(raw_processed, list):
                processed_ids = {str(task_id) for task_id in raw_processed if isinstance(task_id, str)}

        candidates: list[dict[str, Any]] = []
        for task in all_tasks:
            llm_label = _find_llm_label(task.task_entry.labels, self.label_prefix_lower)
            if llm_label is None:
                continue
            if not self.allow_existing_children and children_by_parent.get(task.id):
                logger.info("Skipping task {} (already has children)", task.id)
                continue
            if task.id in processed_ids:
                continue
            variant_key, _ = self._resolve_variant(llm_label)
            candidates.append(
                {
                    "task": task,
                    "label": llm_label,
                    "variant": variant_key,
                    "depth": 1,
                }
            )

        if not candidates:
            if self.track_progress:
                idle_progress = {
                    ProgressKey.ACTIVE.value: False,
                    ProgressKey.STATUS.value: ProgressStatus.IDLE.value,
                    ProgressKey.RUN_ID.value: None,
                    ProgressKey.STARTED_AT.value: None,
                    ProgressKey.UPDATED_AT.value: now,
                    ProgressKey.TASKS_TOTAL.value: 0,
                    ProgressKey.TASKS_COMPLETED.value: 0,
                    ProgressKey.TASKS_FAILED.value: 0,
                    ProgressKey.TASKS_PENDING.value: 0,
                    ProgressKey.CURRENT.value: None,
                    ProgressKey.ERROR.value: None,
                }
                if not self.remove_label_after_processing:
                    idle_progress[ProgressKey.PROCESSED_IDS.value] = list(processed_ids)
                self._progress_save(idle_progress)
            logger.info("No LLM breakdown tasks queued.")
            return

        tasks_to_process = candidates[:self.max_tasks_per_tick]
        tasks_total = len(candidates)
        tasks_pending = tasks_total - len(tasks_to_process)
        run_id = str(uuid4())

        progress = {
            ProgressKey.ACTIVE.value: True,
            ProgressKey.STATUS.value: ProgressStatus.RUNNING.value,
            ProgressKey.RUN_ID.value: run_id,
            ProgressKey.STARTED_AT.value: now,
            ProgressKey.UPDATED_AT.value: now,
            ProgressKey.TASKS_TOTAL.value: tasks_total,
            ProgressKey.TASKS_COMPLETED.value: 0,
            ProgressKey.TASKS_FAILED.value: 0,
            ProgressKey.TASKS_PENDING.value: tasks_pending,
            ProgressKey.CURRENT.value: None,
            ProgressKey.ERROR.value: None,
        }
        if not self.remove_label_after_processing:
            progress[ProgressKey.PROCESSED_IDS.value] = list(processed_ids)
        self._progress_save(progress)

        try:
            llm = self._get_llm()
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Failed to initialize LLM: {}", exc)
            progress.update(
                {
                    ProgressKey.ACTIVE.value: False,
                    ProgressKey.STATUS.value: ProgressStatus.FAILED.value,
                    ProgressKey.ERROR.value: f"{type(exc).__name__}: {exc}",
                    ProgressKey.UPDATED_AT.value: self._now_iso(),
                }
            )
            self._progress_save(progress)
            return

        completed = 0
        failed = 0

        for item in tasks_to_process:
            task = item["task"]
            label = item["label"]
            variant_key = item["variant"]
            depth = item["depth"]

            progress[ProgressKey.CURRENT.value] = {
                CurrentKey.TASK_ID.value: task.id,
                CurrentKey.CONTENT.value: task.task_entry.content,
                CurrentKey.LABEL.value: label,
                CurrentKey.DEPTH.value: depth,
            }
            progress[ProgressKey.UPDATED_AT.value] = self._now_iso()
            self._progress_save(progress)

            variant_cfg = self.variants.get(variant_key, {})
            max_depth = int(variant_cfg.get("max_depth", self.max_depth))
            max_children = int(variant_cfg.get("max_children", self.max_children))
            max_total_tasks = int(variant_cfg.get("max_total_tasks", self.max_total_tasks))
            queue_depth_limit = int(variant_cfg.get("queue_depth", self.max_queue_depth))
            instruction = variant_cfg.get("instruction")
            if queue_depth_limit > 0:
                max_allowed = max(1, queue_depth_limit - depth + 1)
                max_depth = min(max_depth, max_allowed)

            system_prompt = self._build_system_prompt(
                max_depth=max_depth,
                max_children=max_children,
                instruction=instruction,
            )

            ancestor_context = _build_ancestor_context(task, tasks_by_id)
            payload = {
                "task": {
                    "content": task.task_entry.content,
                    "description": task.task_entry.description,
                },
                "ancestors": ancestor_context,
                "variant": variant_key,
                "constraints": {
                    "max_depth": max_depth,
                    "max_children": max_children,
                },
            }
            messages = [
                {"role": MessageRole.SYSTEM, "content": system_prompt},
                {"role": MessageRole.USER, "content": json.dumps(payload, ensure_ascii=False)},
            ]

            try:
                breakdown = llm.structured_chat(messages, TaskBreakdown)
            except ValueError as exc:
                logger.error("LLM breakdown failed for task {}: {}", task.id, exc)
                failed += 1
                processed_ids.add(task.id)
                progress.update(
                    {
                        ProgressKey.TASKS_COMPLETED.value: completed,
                        ProgressKey.TASKS_FAILED.value: failed,
                        ProgressKey.TASKS_PENDING.value: tasks_total - (completed + failed),
                        ProgressKey.TASKS_TOTAL.value: tasks_total,
                        ProgressKey.CURRENT.value: None,
                        ProgressKey.UPDATED_AT.value: self._now_iso(),
                    }
                )
                if not self.remove_label_after_processing:
                    progress[ProgressKey.PROCESSED_IDS.value] = list(processed_ids)
                self._progress_save(progress)
                continue

            nodes = breakdown.children
            created_count = 0
            if not nodes:
                logger.info("LLM returned no subtasks for task {}", task.id)
                if self.remove_label_after_processing:
                    self._update_root_labels(db, task, label)
                completed += 1
            else:
                created = [0]
                self._insert_children(
                    db,
                    root_task=task,
                    parent_id=task.id,
                    nodes=nodes,
                    depth=1,
                    max_depth=max_depth,
                    max_children=max_children,
                    max_total_tasks=max_total_tasks,
                    labels=self._child_labels(task),
                    created=created,
                )
                created_count = created[0]
                if self.remove_label_after_processing:
                    self._update_root_labels(db, task, label)
                completed += 1

            processed_ids.add(task.id)
            pending = tasks_total - (completed + failed)
            progress.update(
                {
                    ProgressKey.TASKS_COMPLETED.value: completed,
                    ProgressKey.TASKS_FAILED.value: failed,
                    ProgressKey.TASKS_PENDING.value: pending,
                    ProgressKey.TASKS_TOTAL.value: tasks_total,
                    ProgressKey.CURRENT.value: None,
                    ProgressKey.UPDATED_AT.value: self._now_iso(),
                }
            )
            if not self.remove_label_after_processing:
                progress[ProgressKey.PROCESSED_IDS.value] = list(processed_ids)
            self._progress_save(progress)

            logger.info(
                "Expanded task {} with label '{}' (variant={}, created={}, pending={})",
                task.id,
                label,
                variant_key,
                created_count,
                pending,
            )

        pending = tasks_total - (completed + failed)
        progress.update(
            {
                ProgressKey.ACTIVE.value: pending > 0,
                ProgressKey.STATUS.value: ProgressStatus.RUNNING.value
                if pending > 0
                else ProgressStatus.COMPLETED.value,
                ProgressKey.TASKS_COMPLETED.value: completed,
                ProgressKey.TASKS_FAILED.value: failed,
                ProgressKey.TASKS_PENDING.value: pending,
                ProgressKey.TASKS_TOTAL.value: tasks_total,
                ProgressKey.CURRENT.value: None,
                ProgressKey.UPDATED_AT.value: self._now_iso(),
            }
        )
        if not self.remove_label_after_processing:
            progress[ProgressKey.PROCESSED_IDS.value] = list(processed_ids)
        self._progress_save(progress)
