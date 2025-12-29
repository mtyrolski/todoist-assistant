import json
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any
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
    "Do not repeat the root task as a child. "
    "Limit depth to {max_depth} levels and at most {max_children} children per task. "
    "Each child should be an object with `content` and an `expand` boolean that says whether "
    "the child should be further decomposed in a later pass. "
    "Prefer returning only immediate children; avoid nested children unless necessary."
)


def _normalize_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _normalize_children(value: object) -> list[object]:
    if value is None:
        return []
    if isinstance(value, list):
        normalized: list[object] = []
        for item in value:
            if isinstance(item, str):
                normalized.append({"content": item})
            else:
                normalized.append(item)
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
    def _normalize_children(cls, value: object) -> list["BreakdownNode"]:
        return _normalize_children(value)


class TaskBreakdown(BaseModel):
    children: list[BreakdownNode] = Field(default_factory=list)

    @field_validator("children", mode="before")
    @classmethod
    def _normalize_children(cls, value: object) -> list[BreakdownNode]:
        return _normalize_children(value)


BreakdownNode.model_rebuild()


def _build_children_by_parent(tasks: Iterable[Task]) -> dict[str, list[Task]]:
    children_by_parent: dict[str, list[Task]] = {}
    for task in tasks:
        parent_id = task.task_entry.parent_id or task.task_entry.v2_parent_id
        if parent_id is None:
            continue
        children_by_parent.setdefault(parent_id, []).append(task)
    return children_by_parent


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
        now = self._now_iso()

        processed_ids: set[str] = set()
        previous_progress = self._progress_load()
        if not self.remove_label_after_processing:
            raw_processed = previous_progress.get("processed_ids")
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
                    "active": False,
                    "status": "idle",
                    "run_id": None,
                    "started_at": None,
                    "updated_at": now,
                    "tasks_total": 0,
                    "tasks_completed": 0,
                    "tasks_failed": 0,
                    "tasks_pending": 0,
                    "current": None,
                    "error": None,
                }
                if not self.remove_label_after_processing:
                    idle_progress["processed_ids"] = list(processed_ids)
                self._progress_save(idle_progress)
            logger.info("No LLM breakdown tasks queued.")
            return

        tasks_to_process = candidates[:self.max_tasks_per_tick]
        tasks_total = len(candidates)
        tasks_pending = tasks_total - len(tasks_to_process)
        run_id = str(uuid4())

        progress = {
            "active": True,
            "status": "running",
            "run_id": run_id,
            "started_at": now,
            "updated_at": now,
            "tasks_total": tasks_total,
            "tasks_completed": 0,
            "tasks_failed": 0,
            "tasks_pending": tasks_pending,
            "current": None,
            "error": None,
        }
        if not self.remove_label_after_processing:
            progress["processed_ids"] = list(processed_ids)
        self._progress_save(progress)

        try:
            llm = self._get_llm()
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Failed to initialize LLM: {}", exc)
            progress.update(
                {
                    "active": False,
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                    "updated_at": self._now_iso(),
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

            progress["current"] = {
                "task_id": task.id,
                "content": task.task_entry.content,
                "label": label,
                "depth": depth,
            }
            progress["updated_at"] = self._now_iso()
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

            payload = {
                "task": {
                    "content": task.task_entry.content,
                    "description": task.task_entry.description,
                },
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
                        "tasks_completed": completed,
                        "tasks_failed": failed,
                        "tasks_pending": tasks_total - (completed + failed),
                        "tasks_total": tasks_total,
                        "current": None,
                        "updated_at": self._now_iso(),
                    }
                )
                if not self.remove_label_after_processing:
                    progress["processed_ids"] = list(processed_ids)
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
                    "tasks_completed": completed,
                    "tasks_failed": failed,
                    "tasks_pending": pending,
                    "tasks_total": tasks_total,
                    "current": None,
                    "updated_at": self._now_iso(),
                }
            )
            if not self.remove_label_after_processing:
                progress["processed_ids"] = list(processed_ids)
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
                "active": pending > 0,
                "status": "running" if pending > 0 else "completed",
                "tasks_completed": completed,
                "tasks_failed": failed,
                "tasks_pending": pending,
                "tasks_total": tasks_total,
                "current": None,
                "updated_at": self._now_iso(),
            }
        )
        if not self.remove_label_after_processing:
            progress["processed_ids"] = list(processed_ids)
        self._progress_save(progress)
