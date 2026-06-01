from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, fields
from datetime import datetime
import os
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from loguru import logger

from todoist.automations.base import Automation
from todoist.database.base import Database
from todoist.env import EnvVar
from todoist.llm import DEFAULT_MODEL_ID, LocalChatConfig
from todoist.llm.factory import ChatModel, build_codex_chat_model, build_triton_chat_model
from todoist.llm.llm_utils import _sanitize_text
from todoist.llm.model_catalog import coerce_model_id_for_backend
from todoist.runtime_env import (
    load_runtime_env_values,
    normalize_llm_backend,
    resolve_runtime_env_path,
)
from todoist.types import Task
from todoist.utils import Cache

from .config import build_system_prompt, coerce_model_config, merge_variants, resolve_variant
from .models import BreakdownNode, InsertContext, QueueItem
from .runner import run_breakdown


# === LLM BREAKDOWN AUTOMATION ================================================

_REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class BreakdownSettings:
    label_prefix: str = "ai-breakdown"
    default_variant: str = "breakdown"
    max_depth: int = 3
    max_children: int = 6
    max_total_tasks: int = 60
    allow_existing_children: bool = False
    remove_label_after_processing: bool = True
    propagate_labels: bool = True
    max_tasks_per_tick: int = 4
    max_queue_depth: int = 1
    auto_queue_children: bool = True
    track_progress: bool = True
    failed_label: str = "ai-breakdown-failed"
    max_failures_per_task: int = 3


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
        raise TypeError(f"Unexpected AI breakdown settings: {unknown_list}")

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
        super().__init__("@ai-breakdown", frequency_in_minutes)

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
        self.failed_label = _sanitize_text(settings_obj.failed_label) or "ai-breakdown-failed"
        self.failed_label_lower = self.failed_label.lower()
        self.max_failures_per_task = max(1, int(settings_obj.max_failures_per_task))
        self.variants = merge_variants(variants)
        self.model_config = coerce_model_config(model_config)
        self._llm: ChatModel | None = None
        self._llm_backend: str | None = None
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
            logger.warning("Failed to save AI breakdown progress: {}", exc)

    def _progress_load(self) -> dict[str, Any]:
        if not self.track_progress:
            return {}
        try:
            payload = self._progress_storage.load()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to load AI breakdown progress: {}", exc)
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        return payload

    def _queue_load(self) -> list[QueueItem]:
        try:
            payload = self._queue_storage.load()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to load AI breakdown queue: {}", exc)
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
            logger.warning("Failed to save AI breakdown queue: {}", exc)

    @staticmethod
    def _resolve_env_path() -> Path:
        return resolve_runtime_env_path(repo_root=_REPO_ROOT)

    @staticmethod
    def _env_values() -> dict[str, Any]:
        return load_runtime_env_values(LLMBreakdown._resolve_env_path())

    @staticmethod
    def _locked_backend() -> str | None:
        raw_backend = os.getenv("TODOIST_DASHBOARD_LLM_BACKEND_LOCK")
        if _sanitize_text(raw_backend) is None:
            return None
        backend = normalize_llm_backend(raw_backend)
        if backend in {"codex", "triton_local", "disabled"}:
            return backend
        return None

    def _resolve_selected_backend(self) -> tuple[str, dict[str, Any]]:
        values = self._env_values()
        locked_backend = self._locked_backend()
        if locked_backend is not None:
            return locked_backend, values
        backend = normalize_llm_backend(
            os.getenv(str(EnvVar.AGENT_BACKEND)) or values.get(str(EnvVar.AGENT_BACKEND))
        )
        return backend, values

    @staticmethod
    def _build_codex_llm(values: Mapping[str, Any]) -> ChatModel:
        return build_codex_chat_model(values, cwd=_REPO_ROOT)

    def _build_triton_llm(self, values: Mapping[str, Any]) -> ChatModel:
        base_url = _sanitize_text(
            os.getenv(str(EnvVar.AGENT_TRITON_URL)) or values.get(str(EnvVar.AGENT_TRITON_URL))
        )
        model_name = _sanitize_text(
            os.getenv(str(EnvVar.AGENT_TRITON_MODEL_NAME))
            or values.get(str(EnvVar.AGENT_TRITON_MODEL_NAME))
        )
        model_id = _sanitize_text(
            os.getenv(str(EnvVar.AGENT_MODEL_ID))
            or values.get(str(EnvVar.AGENT_MODEL_ID))
        )
        coerced_model_id = coerce_model_id_for_backend(model_id, "triton")
        return build_triton_chat_model(
            base_url=base_url,
            model_name=model_name,
            model_id=coerced_model_id or DEFAULT_MODEL_ID,
            temperature=float(self.model_config.temperature),
            top_p=float(self.model_config.top_p),
            max_output_tokens=int(self.model_config.max_new_tokens),
        )

    def _get_llm(
        self,
    ) -> ChatModel:
        backend, values = self._resolve_selected_backend()
        if self._llm is None or self._llm_backend != backend:
            if backend == "codex":
                self._llm = self._build_codex_llm(values)
            elif backend == "triton_local":
                self._llm = self._build_triton_llm(values)
            else:
                raise RuntimeError("AI breakdown backend is disabled.")
            self._llm_backend = backend
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

    def get_llm(
        self,
    ) -> ChatModel:
        return self._get_llm()

    def selected_backend(self) -> str:
        backend, _values = self._resolve_selected_backend()
        if backend in {"codex", "triton_local"}:
            return backend
        return "disabled"

    def llm_request_parallelism(self, task_count: int) -> int:
        if task_count <= 0:
            return 1
        if self.selected_backend() != "triton_local":
            return 1
        if self.max_tasks_per_tick <= 0:
            return max(1, int(task_count))
        return max(1, min(int(self.max_tasks_per_tick), int(task_count)))

    @staticmethod
    def concurrent_executor(max_workers: int) -> ThreadPoolExecutor:
        return ThreadPoolExecutor(max_workers=max_workers)

    def resolve_variant(self, label: str) -> tuple[str, dict[str, Any]]:
        return self._resolve_variant(label)

    def build_system_prompt(self, *, max_depth: int, max_children: int, instruction: str | None) -> str:
        return self._build_system_prompt(max_depth=max_depth, max_children=max_children, instruction=instruction)

    def should_run_without_new_activity(self) -> bool:
        """Allow observer polling to process labeled tasks even without fresh activity."""
        return self.selected_backend() != "disabled"

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
    def _fallback_nodes(task: Task, *, reason: str | None = None) -> list[BreakdownNode]:
        description_parts = [f"Fallback rollout for task: {task.task_entry.content.strip()}"]
        task_description = _sanitize_text(task.task_entry.description)
        if task_description:
            description_parts.append(f"Context: {task_description}")
        if reason:
            description_parts.append(f"Reason: {reason}")
        return [
            BreakdownNode(
                content="Define first concrete step",
                description="\n".join(description_parts),
                expand=False,
                children=[],
            )
        ]

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

    def _mark_root_failed(self, db: Database, task: Task, label_to_replace: str) -> None:
        labels = task.task_entry.labels
        target = label_to_replace.lower()
        updated = [label for label in labels if label.lower() != target]
        if not any(label.lower() == self.failed_label_lower for label in updated):
            updated.append(self.failed_label)
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
            try:
                result = db.insert_task(
                    content=content,
                    description=description,
                    project_id=root_task.task_entry.project_id if parent_id is None else None,
                    parent_id=parent_id,
                    priority=priority,
                    labels=context.labels,
                )
            except Exception as exc:  # pragma: no cover - network safety
                message = (
                    f"Failed inserting subtask '{content}' for root task {root_task.id} "
                    f"under parent {parent_id}: {type(exc).__name__}: {exc}"
                )
                context.errors.append(message)
                logger.error(message)
                continue
            if "id" not in result:
                message = (
                    f"Todoist did not return an id for subtask '{content}' "
                    f"(root task {root_task.id}, parent {parent_id})"
                )
                context.errors.append(message)
                logger.error(message)
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

    def fallback_nodes(self, task: Task, *, reason: str | None = None) -> list[BreakdownNode]:
        return self._fallback_nodes(task, reason=reason)

    def update_root_labels(self, db: Database, task: Task, label_to_remove: str) -> None:
        self._update_root_labels(db, task, label_to_remove)

    def mark_root_failed(self, db: Database, task: Task, label_to_replace: str) -> None:
        self._mark_root_failed(db, task, label_to_replace)

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
        if self.selected_backend() == "disabled":
            logger.info("Skipping AI Breakdown automation because AI backend is disabled.")
            return
        refresh = getattr(db, "reset", None)
        if callable(refresh):
            try:
                logger.debug("Refreshing active Todoist tasks before AI breakdown selection")
                refresh()
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "Failed to refresh active Todoist tasks before AI breakdown selection: {}",
                    exc,
                )
        run_breakdown(self, db)
