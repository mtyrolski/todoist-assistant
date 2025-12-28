from __future__ import annotations

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


class BreakdownNode(BaseModel):
    content: str | None = None
    description: str | None = None
    priority: int | None = None
    expand: bool | None = None
    children: list["BreakdownNode"] = Field(default_factory=list)

    @field_validator("content", "description", mode="before")
    @classmethod
    def _normalize_text(cls, value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    @field_validator("priority", mode="before")
    @classmethod
    def _normalize_priority(cls, value: object) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @field_validator("children", mode="before")
    @classmethod
    def _normalize_children(cls, value: object) -> list["BreakdownNode"]:
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


class TaskBreakdown(BaseModel):
    children: list[BreakdownNode] = Field(default_factory=list)

    @field_validator("children", mode="before")
    @classmethod
    def _normalize_children(cls, value: object) -> list[BreakdownNode]:
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
        self._queue_storage = Cache().llm_breakdown_queue

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
        try:
            payload = self._progress_storage.load()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to load LLM breakdown progress: {}", exc)
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        return payload

    def _queue_load(self) -> dict[str, Any]:
        try:
            payload = self._queue_storage.load()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to load LLM breakdown queue: {}", exc)
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        return payload

    def _queue_save(self, payload: dict[str, Any]) -> None:
        try:
            self._queue_storage.save(payload)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to save LLM breakdown queue: {}", exc)

    def _queue_item(
        self,
        *,
        task_id: str,
        content: str,
        description: str | None,
        label: str,
        variant: str,
        depth: int,
        parent_id: str | None,
    ) -> dict[str, Any]:
        return {
            "task_id": task_id,
            "content": content,
            "description": description,
            "label": label,
            "variant": variant,
            "depth": depth,
            "parent_id": parent_id,
        }

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
    ) -> list[dict[str, Any]]:
        created_nodes: list[dict[str, Any]] = []
        if depth > max_depth:
            return created_nodes
        for node in nodes[:max_children]:
            if created[0] >= max_total_tasks:
                logger.warning("Reached max_total_tasks={}; truncating tree", max_total_tasks)
                return created_nodes
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
            child_children = self._insert_children(
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
            created_nodes.append(
                {
                    "id": child_id,
                    "content": content,
                    "description": description,
                    "priority": priority,
                    "expand": bool(node.expand) if node.expand is not None else None,
                    "parent_id": parent_id,
                    "children": child_children,
                }
            )
        return created_nodes

    def _tick(self, db: Database) -> None:
        logger.info("Running LLM Breakdown automation")
        projects = db.fetch_projects(include_tasks=True)
        all_tasks: list[Task] = [task for project in projects for task in project.tasks]
        logger.debug("Found {} tasks in total", len(all_tasks))

        tasks_by_id = {task.id: task for task in all_tasks}
        children_by_parent = _build_children_by_parent(all_tasks)

        now = self._now_iso()
        queue_state = self._queue_load()
        progress = self._progress_load()

        queue = queue_state.get("queue", [])
        if not isinstance(queue, list):
            queue = []
        completed_ids = queue_state.get("completed_ids", [])
        if not isinstance(completed_ids, list):
            completed_ids = []
        completed_set = {task_id for task_id in completed_ids if isinstance(task_id, str)}
        known_ids = {item.get("task_id") for item in queue if isinstance(item, dict)} | completed_set

        tasks_flagged = 0
        tasks_skipped: list[dict[str, Any]] = []
        for task in all_tasks:
            llm_label = _find_llm_label(task.task_entry.labels, self.label_prefix_lower)
            if llm_label is None:
                continue
            tasks_flagged += 1
            if not self.allow_existing_children and children_by_parent.get(task.id):
                logger.info("Skipping task {} (already has children)", task.id)
                tasks_skipped.append(
                    {
                        "task_id": task.id,
                        "content": task.task_entry.content,
                        "label": llm_label,
                        "reason": "already_has_children",
                    }
                )
                continue
            if task.id in known_ids:
                continue
            variant_key, _ = self._resolve_variant(llm_label)
            queue.append(
                self._queue_item(
                    task_id=task.id,
                    content=task.task_entry.content,
                    description=task.task_entry.description,
                    label=llm_label,
                    variant=variant_key,
                    depth=1,
                    parent_id=None,
                )
            )
            known_ids.add(task.id)

        active = bool(queue_state.get("active"))
        run_id = queue_state.get("run_id")
        if not active and queue:
            active = True
            run_id = str(uuid4())
            progress = {
                "active": True,
                "run_id": run_id,
                "status": "running",
                "started_at": now,
                "updated_at": now,
                "tasks_flagged": tasks_flagged,
                "tasks_skipped": tasks_skipped,
                "tasks_total": len(queue),
                "tasks_completed": 0,
                "tasks_failed": 0,
                "tasks_pending": len(queue),
                "current": None,
                "results": [],
                "error": None,
            }
        elif active and run_id is None:
            run_id = str(uuid4())
            progress["run_id"] = run_id
        elif active:
            progress.setdefault("results", [])
            progress.setdefault("tasks_completed", 0)
            progress.setdefault("tasks_failed", 0)
            progress.setdefault("tasks_pending", len(queue))
            progress.setdefault("tasks_flagged", tasks_flagged)
            progress.setdefault("tasks_skipped", tasks_skipped)
            progress["active"] = True
            progress["status"] = progress.get("status") or "running"
            progress["run_id"] = run_id
            progress["updated_at"] = now

        queue_state.update(
            {
                "active": active,
                "run_id": run_id,
                "queue": queue,
                "completed_ids": list(completed_set),
                "updated_at": now,
            }
        )
        self._queue_save(queue_state)

        if not active and not queue:
            if self.track_progress:
                idle_progress = {
                    "active": False,
                    "status": "idle",
                    "run_id": None,
                    "started_at": None,
                    "updated_at": now,
                    "tasks_flagged": tasks_flagged,
                    "tasks_skipped": tasks_skipped,
                    "tasks_total": 0,
                    "tasks_completed": 0,
                    "tasks_failed": 0,
                    "tasks_pending": 0,
                    "current": None,
                    "results": progress.get("results", []) if isinstance(progress, dict) else [],
                    "error": None,
                }
                self._progress_save(idle_progress)
            logger.info("No LLM breakdown tasks queued.")
            return

        if not queue and active:
            progress.update(
                {
                    "active": False,
                    "status": "completed",
                    "updated_at": now,
                    "tasks_pending": 0,
                    "tasks_total": progress.get("tasks_completed", 0) + progress.get("tasks_failed", 0),
                    "current": None,
                }
            )
            self._progress_save(progress)
            queue_state.update({"active": False, "updated_at": now, "queue": queue})
            self._queue_save(queue_state)
            logger.info("LLM breakdown queue completed.")
            return

        logger.info("LLM breakdown queue size: {}", len(queue))

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
            queue_state.update({"active": False, "updated_at": self._now_iso()})
            self._queue_save(queue_state)
            return

        def update_counts() -> None:
            pending = len(queue)
            completed = int(progress.get("tasks_completed") or 0)
            failed = int(progress.get("tasks_failed") or 0)
            progress["tasks_pending"] = pending
            progress["tasks_total"] = completed + failed + pending

        tasks_to_process = min(self.max_tasks_per_tick, len(queue))
        for _ in range(tasks_to_process):
            if not queue:
                break
            item = queue.pop(0)
            if not isinstance(item, dict):
                continue
            task_id = str(item.get("task_id") or "")
            label = str(item.get("label") or "")
            variant_key = str(item.get("variant") or "") or self.default_variant
            depth = int(item.get("depth") or 1)

            progress["current"] = {
                "task_id": task_id,
                "content": item.get("content"),
                "label": label,
                "depth": depth,
            }
            progress["updated_at"] = self._now_iso()
            self._progress_save(progress)

            task = tasks_by_id.get(task_id)
            if task is None:
                logger.warning("Task {} not found; skipping", task_id)
                progress["tasks_failed"] = int(progress.get("tasks_failed") or 0) + 1
                progress.setdefault("results", []).append(
                    {
                        "task_id": task_id,
                        "content": item.get("content"),
                        "description": item.get("description"),
                        "label": label,
                        "variant": variant_key,
                        "status": "missing",
                        "created_count": 0,
                        "tree": None,
                        "error": "task_not_found",
                        "label_removed": False,
                        "depth": depth,
                        "parent_id": item.get("parent_id"),
                    }
                )
                completed_set.add(task_id)
                update_counts()
                progress["current"] = None
                progress["updated_at"] = self._now_iso()
                self._progress_save(progress)
                continue

            variant_cfg = self.variants.get(variant_key, {})
            max_depth = int(variant_cfg.get("max_depth", self.max_depth))
            max_children = int(variant_cfg.get("max_children", self.max_children))
            max_total_tasks = int(variant_cfg.get("max_total_tasks", self.max_total_tasks))
            queue_depth_limit = int(variant_cfg.get("queue_depth", self.max_queue_depth))
            instruction = variant_cfg.get("instruction")
            if queue_depth_limit > 0:
                max_allowed = max(1, queue_depth_limit - depth + 1)
                if max_depth > max_allowed:
                    max_depth = max_allowed

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

            result_record: dict[str, Any] = {
                "task_id": task.id,
                "content": task.task_entry.content,
                "description": task.task_entry.description,
                "label": label,
                "variant": variant_key,
                "status": "pending",
                "created_count": 0,
                "tree": None,
                "error": None,
                "label_removed": False,
                "depth": depth,
                "parent_id": item.get("parent_id"),
            }

            try:
                breakdown = llm.structured_chat(messages, TaskBreakdown)
            except ValueError as exc:
                logger.error("LLM breakdown failed for task {}: {}", task.id, exc)
                result_record.update(
                    {
                        "status": "failed",
                        "error": str(exc),
                    }
                )
                progress["tasks_failed"] = int(progress.get("tasks_failed") or 0) + 1
                progress.setdefault("results", []).append(result_record)
                completed_set.add(task_id)
                update_counts()
                progress["current"] = None
                progress["updated_at"] = self._now_iso()
                self._progress_save(progress)
                continue

            nodes = breakdown.children
            if not nodes:
                logger.info("LLM returned no subtasks for task {}", task.id)
                if self.remove_label_after_processing:
                    self._update_root_labels(db, task, label)
                result_record.update(
                    {
                        "status": "empty",
                        "label_removed": self.remove_label_after_processing,
                    }
                )
                progress["tasks_completed"] = int(progress.get("tasks_completed") or 0) + 1
                progress.setdefault("results", []).append(result_record)
                completed_set.add(task_id)
                update_counts()
                progress["current"] = None
                progress["updated_at"] = self._now_iso()
                self._progress_save(progress)
                continue

            created = [0]
            created_tree = self._insert_children(
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

            if self.remove_label_after_processing:
                self._update_root_labels(db, task, label)

            result_record.update(
                {
                    "status": "completed",
                    "created_count": created[0],
                    "tree": {
                        "id": task.id,
                        "content": task.task_entry.content,
                        "description": task.task_entry.description,
                        "children": created_tree,
                    },
                    "label_removed": self.remove_label_after_processing,
                }
            )
            progress.setdefault("results", []).append(result_record)
            progress["tasks_completed"] = int(progress.get("tasks_completed") or 0) + 1
            completed_set.add(task_id)

            if self.auto_queue_children and depth < queue_depth_limit:
                def enqueue_children(nodes_to_check: list[dict[str, Any]], parent_depth: int) -> None:
                    for node in nodes_to_check:
                        if not isinstance(node, dict):
                            continue
                        node_depth = parent_depth + 1
                        child_id = node.get("id")
                        if not child_id:
                            continue
                        should_expand = bool(node.get("expand"))
                        has_children = bool(node.get("children"))
                        if should_expand and not has_children and node_depth <= queue_depth_limit:
                            queue.append(
                                self._queue_item(
                                    task_id=str(child_id),
                                    content=str(node.get("content") or ""),
                                    description=node.get("description"),
                                    label=label,
                                    variant=variant_key,
                                    depth=node_depth,
                                    parent_id=str(task.id),
                                )
                            )
                        if node.get("children"):
                            enqueue_children(node["children"], node_depth)

                enqueue_children(created_tree, depth)

            update_counts()
            progress["current"] = None
            progress["updated_at"] = self._now_iso()
            self._progress_save(progress)

            logger.info(
                "Expanded task {} with label '{}' (variant={}, created={}, queue={})",
                task.id,
                label,
                variant_key,
                created[0],
                len(queue),
            )

        queue_state.update(
            {
                "active": True,
                "run_id": run_id,
                "queue": queue,
                "completed_ids": list(completed_set),
                "updated_at": self._now_iso(),
            }
        )
        self._queue_save(queue_state)

        if not queue:
            progress.update(
                {
                    "active": False,
                    "status": "completed",
                    "tasks_pending": 0,
                    "tasks_total": progress.get("tasks_completed", 0) + progress.get("tasks_failed", 0),
                    "current": None,
                    "updated_at": self._now_iso(),
                }
            )
            self._progress_save(progress)
            queue_state.update({"active": False, "updated_at": self._now_iso()})
            self._queue_save(queue_state)
