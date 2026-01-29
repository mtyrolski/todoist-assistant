from collections.abc import Mapping
from dataclasses import dataclass, fields
from datetime import datetime
from typing import Any, cast
from uuid import uuid4

from loguru import logger

from todoist.automations.base import Automation
from todoist.database.base import Database
from todoist.llm import LocalChatConfig, TransformersMistral3ChatModel
from todoist.llm.llm_utils import _sanitize_text
from todoist.types import Task
from todoist.utils import Cache

from .config import build_system_prompt, coerce_model_config, merge_variants, resolve_variant
from .models import BreakdownNode, InsertContext, QueueItem
from .runner import run_breakdown


# === LLM BREAKDOWN AUTOMATION ================================================


@dataclass(frozen=True)
class BreakdownSettings:
    label_prefix: str = "llm-"
    default_variant: str = "breakdown"
    max_depth: int = 3
    max_children: int = 6
    max_total_tasks: int = 60
    allow_existing_children: bool = False
    remove_label_after_processing: bool = True
    propagate_labels: bool = True
    max_tasks_per_tick: int = 1
    max_queue_depth: int = 1
    auto_queue_children: bool = True
    track_progress: bool = True


def _coerce_settings(
    settings: BreakdownSettings | Mapping[str, Any] | None,
    overrides: Mapping[str, Any],
) -> BreakdownSettings:
    if isinstance(settings, BreakdownSettings) and not overrides:
        return settings

    payload: dict[str, Any] = {}
    if settings is not None:
        if isinstance(settings, BreakdownSettings):
            payload = {field.name: getattr(settings, field.name) for field in fields(BreakdownSettings)}
        else:
            payload = dict(settings)
    payload.update(overrides)

    allowed = {field.name for field in fields(BreakdownSettings)}
    unknown = set(payload) - allowed
    if unknown:
        unknown_list = ", ".join(sorted(unknown))
        raise TypeError(f"Unexpected LLM breakdown settings: {unknown_list}")

    return BreakdownSettings(**payload)


class LLMBreakdown(Automation):
    def __init__(
        self,
        frequency_in_minutes: float = 0.1,
        *,
        settings: BreakdownSettings | Mapping[str, Any] | None = None,
        variants: Mapping[str, Mapping[str, Any]] | None = None,
        model_config: LocalChatConfig | Mapping[str, Any] | None = None,
        **overrides: Any,
    ):
        super().__init__("LLM Breakdown", frequency_in_minutes)

        settings_obj = _coerce_settings(settings, overrides)

        self.label_prefix = settings_obj.label_prefix
        self.label_prefix_lower = settings_obj.label_prefix.lower()
        self.default_variant = settings_obj.default_variant
        self.max_depth = settings_obj.max_depth
        self.max_children = settings_obj.max_children
        self.max_total_tasks = settings_obj.max_total_tasks
        self.allow_existing_children = settings_obj.allow_existing_children
        self.remove_label_after_processing = settings_obj.remove_label_after_processing
        self.propagate_labels = settings_obj.propagate_labels
        self.max_tasks_per_tick = max(0, int(settings_obj.max_tasks_per_tick))
        self.max_queue_depth = max(1, int(settings_obj.max_queue_depth))
        self.auto_queue_children = settings_obj.auto_queue_children
        self.track_progress = settings_obj.track_progress
        self.variants = merge_variants(variants)
        self.model_config = coerce_model_config(model_config)
        self._llm: TransformersMistral3ChatModel | None = None
        self._progress_storage = Cache().llm_breakdown_progress
        self._queue_storage = Cache().llm_breakdown_queue

    @staticmethod
    def _now_iso() -> str:
        return datetime.utcnow().isoformat(timespec="seconds")

    @staticmethod
    def _new_run_id() -> str:
        return str(uuid4())

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

    def _queue_load(self) -> list[QueueItem]:
        try:
            payload = self._queue_storage.load()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to load LLM breakdown queue: {}", exc)
            return []
        if not isinstance(payload, list):
            return []
        items: list[QueueItem] = []
        for raw in payload:
            if not isinstance(raw, Mapping):
                continue
            task_id = str(raw.get("task_id") or "").strip()
            label = str(raw.get("label") or "").strip()
            variant = str(raw.get("variant") or "").strip()
            depth = self._normalize_queue_depth(raw.get("depth", 1))
            if not task_id or not label or not variant:
                continue
            items.append(
                {
                    "task_id": task_id,
                    "label": label,
                    "variant": variant,
                    "depth": depth,
                }
            )
        return items

    def _queue_save(self, items: list[QueueItem]) -> None:
        try:
            self._queue_storage.save(cast(Any, items))
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to save LLM breakdown queue: {}", exc)

    def _get_llm(self) -> TransformersMistral3ChatModel:
        if self._llm is None:
            self._llm = TransformersMistral3ChatModel(self.model_config)
        return self._llm

    def _resolve_variant(self, label: str) -> tuple[str, dict[str, Any]]:
        return resolve_variant(
            label,
            label_prefix_lower=self.label_prefix_lower,
            default_variant=self.default_variant,
            variants=self.variants,
        )

    def _build_system_prompt(self, *, max_depth: int, max_children: int, instruction: str | None) -> str:
        return build_system_prompt(max_depth=max_depth, max_children=max_children, instruction=instruction)

    def now_iso(self) -> str:
        return self._now_iso()

    def new_run_id(self) -> str:
        return self._new_run_id()

    def progress_save(self, payload: dict[str, Any]) -> None:
        self._progress_save(payload)

    def progress_load(self) -> dict[str, Any]:
        return self._progress_load()

    def queue_load(self) -> list[QueueItem]:
        return self._queue_load()

    def queue_save(self, items: list[QueueItem]) -> None:
        self._queue_save(items)

    def get_llm(self) -> TransformersMistral3ChatModel:
        return self._get_llm()

    def resolve_variant(self, label: str) -> tuple[str, dict[str, Any]]:
        return self._resolve_variant(label)

    def build_system_prompt(self, *, max_depth: int, max_children: int, instruction: str | None) -> str:
        return self._build_system_prompt(max_depth=max_depth, max_children=max_children, instruction=instruction)

    @staticmethod
    def _normalize_queue_depth(value: Any) -> int:
        try:
            depth = int(value)
        except (TypeError, ValueError):
            depth = 1
        return max(1, depth)

    @staticmethod
    def _normalize_priority(value: int | None) -> int:
        if value is None:
            return 1
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return 1
        return max(1, min(4, parsed))

    def _child_labels(self, task: Task) -> list[str] | None:
        if not self.propagate_labels:
            return None
        labels = [
            label
            for label in task.task_entry.labels
            if not label.lower().startswith(self.label_prefix_lower)
        ]
        return labels or None

    @staticmethod
    def _update_root_labels(db: Database, task: Task, label_to_remove: str) -> None:
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
        context: InsertContext,
    ) -> None:
        if depth > context.max_depth:
            return
        for node in nodes[:context.max_children]:
            if context.created[0] >= context.max_total_tasks:
                logger.warning("Reached max_total_tasks={}; truncating tree", context.max_total_tasks)
                return
            content = _sanitize_text(node.content)
            if not content:
                continue
            description = _sanitize_text(node.description)
            priority = self._normalize_priority(node.priority)
            result = db.insert_task(
                content=content,
                description=description,
                project_id=root_task.task_entry.project_id,
                parent_id=parent_id,
                priority=priority,
                labels=context.labels,
            )
            if "id" not in result:
                logger.error("Failed to insert subtask '{}'", content)
                continue
            context.created[0] += 1
            child_id = str(result["id"])
            if context.queue_ctx is not None and node.expand:
                context.queue_ctx.enqueue(child_id)
            self._insert_children(
                db,
                root_task=root_task,
                parent_id=child_id,
                nodes=node.children,
                depth=depth + 1,
                context=context,
            )

    def child_labels(self, task: Task) -> list[str] | None:
        return self._child_labels(task)

    def update_root_labels(self, db: Database, task: Task, label_to_remove: str) -> None:
        self._update_root_labels(db, task, label_to_remove)

    def insert_children(
        self,
        db: Database,
        *,
        root_task: Task,
        parent_id: str,
        nodes: list[BreakdownNode],
        depth: int,
        context: InsertContext,
    ) -> None:
        self._insert_children(
            db,
            root_task=root_task,
            parent_id=parent_id,
            nodes=nodes,
            depth=depth,
            context=context,
        )

    def _tick(self, db: Database) -> None:
        run_breakdown(self, db)
