import argparse
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from collections.abc import Mapping
from typing import Any, Callable, Iterable, Sequence, cast

from omegaconf import DictConfig

from loguru import logger

from todoist.automations.base import Automation
from todoist.core.constants import TaskField
from todoist.database.base import Database
from todoist.database.db_tasks import TaskTemplateInsertRequest
from todoist.core.types import Task
from todoist.core.utils import Cache


_MULTIPLICATION_LABEL_PATTERN = re.compile(r"^X(?P<n>\d+)$")


def is_multiplication_label(label: str) -> bool:
    """Return True iff `label` is a flat multiplication label like `X3`.

    Note: this helper is intentionally case-sensitive ("X" must be uppercase),
    as it's used by dashboard/utils tests.
    """

    return _MULTIPLICATION_LABEL_PATTERN.match(label) is not None


def extract_multiplication_factor(label: str) -> int:
    """Extract the integer factor from a flat multiplication label like `X3`."""

    match = _MULTIPLICATION_LABEL_PATTERN.match(label)
    if match is None:
        raise ValueError(f"Invalid multiplication label: {label!r}")
    return int(match.group("n"))


@dataclass(frozen=True, slots=True)
class MultiplyConfig:
    # Legacy flat labels like X3 are removed from tasks; they no longer expand inline copies.
    flat_label_regex: str = r"^X(?P<n>\d+)$"
    flat_leaf_template: str = "{base} story-point-{i}"

    # Deep multiplication via labels like _X3
    # - creates N subtasks under the labeled task
    deep_label_regex: str = r"^_X(?P<n>\d+)$"
    deep_leaf_template: str = "{base} - {i}/{n}"
    deep_child_label: str = "effort-point"
    cleanup_unused_labels: bool = True
    cleanup_unused_labels_after_days: int = 7


def _compile(pattern: str) -> re.Pattern[str]:
    # Be permissive: Todoist content/labels are user-typed.
    return re.compile(pattern, flags=re.IGNORECASE)


def _filter_out_multiplier_labels(
    labels: Iterable[str],
    *,
    flat_label_pattern: re.Pattern[str],
    deep_label_pattern: re.Pattern[str],
) -> list[str]:
    return [
        label
        for label in labels
        if flat_label_pattern.match(label) is None
        and deep_label_pattern.match(label) is None
    ]


def _append_unique_label(labels: Iterable[str], label: str) -> list[str]:
    normalized = label.strip()
    result = list(labels)
    if not normalized:
        return result
    if all(item.strip().lower() != normalized.lower() for item in result):
        result.append(normalized)
    return result


def _task_parent_id(task: Task) -> str | None:
    return task.task_entry.parent_id


def _insert_tasks_from_templates_compat(
    db: Database,
    requests: list[TaskTemplateInsertRequest],
) -> list[dict[str, Any]]:
    insert_many = getattr(db, "insert_tasks_from_templates", None)
    if callable(insert_many):
        typed_insert_many = cast(
            Callable[[list[TaskTemplateInsertRequest]], list[dict[str, Any]]],
            insert_many,
        )
        return typed_insert_many(requests)

    return [
        db.insert_task_from_template(request.template, **request.overrides)
        for request in requests
    ]


def _depth_sort_children_first(tasks: list[Task]) -> list[Task]:
    """Sort tasks so that children are processed before parents (DFS post-order).

    This ensures that a deep-labeled child is expanded before a flat-labeled
    parent has its legacy label removed.
    """
    task_by_id: dict[str, Task] = {task.id: task for task in tasks}
    depth_cache: dict[str, int] = {}

    def depth(task: Task) -> int:
        task_id = task.id
        if task_id in depth_cache:
            return depth_cache[task_id]

        seen: set[str] = set()
        current: Task | None = task
        current_depth = 0
        while current is not None:
            if current.id in seen:
                logger.warning(
                    f"Detected parent cycle while computing depth for task {task_id}; treating as root"
                )
                current_depth = 0
                break
            seen.add(current.id)

            parent_id = _task_parent_id(current)
            if parent_id is None:
                break

            parent = task_by_id.get(parent_id)
            if parent is None:
                break

            if parent.id in depth_cache:
                current_depth += 1 + depth_cache[parent.id]
                break

            current_depth += 1
            current = parent

        depth_cache[task_id] = current_depth
        return current_depth

    # Sort by depth DESCENDING so deepest (children) come first
    return sorted(tasks, key=depth, reverse=True)


def _factor_from_labels(
    labels: Iterable[str], label_pattern: re.Pattern[str], *, kind: str
) -> int | None:
    matched = [label for label in labels if label_pattern.match(label) is not None]
    if not matched:
        return None
    if len(matched) != 1:
        raise ValueError(
            f"Expected exactly one {kind} multiplication label, found: {matched}"
        )
    match = label_pattern.match(matched[0])
    assert match is not None
    return int(match.group("n"))


def _render(template: str, **kwargs) -> str:
    return template.format(**kwargs)


class Multiply(Automation):
    def __init__(
        self,
        frequency_in_minutes: float = 0.1,
        config: MultiplyConfig | Mapping[str, Any] | None = None,
    ):
        super().__init__("Multiply", frequency_in_minutes)

        if config is None:
            self.config = MultiplyConfig()
        elif isinstance(config, MultiplyConfig):
            self.config = config
        elif isinstance(config, (Mapping, DictConfig)):
            config_data = dict(config)
            if "cleanup_unused_labels_after_days" in config_data:
                config_data["cleanup_unused_labels_after_days"] = max(
                    0, int(config_data["cleanup_unused_labels_after_days"])
                )
            self.config = MultiplyConfig(**config_data)
        else:
            raise TypeError("config must be MultiplyConfig or Mapping[str, Any]")

        self._flat_label_pattern = _compile(self.config.flat_label_regex)
        self._deep_label_pattern = _compile(self.config.deep_label_regex)

    def should_run_without_new_activity(self) -> bool:
        """Run from the observer even when multiplier labels predate the latest event poll."""
        return True

    def _tick(self, db: Database) -> None:
        now = datetime.now()
        projects = db.fetch_projects(include_tasks=True)
        all_tasks: list[Task] = [task for project in projects for task in project.tasks]
        logger.debug(f"Found {len(all_tasks)} tasks in total")
        seen_multiplier_labels = self._multiplier_labels_on_tasks(all_tasks)
        self._record_multiplier_label_usage(seen_multiplier_labels, now=now)

        tasks_to_process = self._select_tasks_to_process(all_tasks)
        tasks_to_process = _depth_sort_children_first(tasks_to_process)

        logger.info(f"Found {len(tasks_to_process)} tasks to expand")
        for task in tasks_to_process:
            self._process_task(db, task)

        self._cleanup_unused_multiplier_labels(
            db,
            seen_multiplier_labels=seen_multiplier_labels,
            now=now,
        )

    def _multiplier_labels_on_tasks(self, tasks: Iterable[Task]) -> set[str]:
        labels: set[str] = set()
        for task in tasks:
            for label in task.task_entry.labels:
                if (
                    self._flat_label_pattern.match(label) is not None
                    or self._deep_label_pattern.match(label) is not None
                ):
                    labels.add(label)
        return labels

    @staticmethod
    def _load_multiplier_label_usage() -> dict[str, dict[str, Any]]:
        payload = Cache().multiplication_label_usage.load()
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _save_multiplier_label_usage(payload: dict[str, dict[str, Any]]) -> None:
        Cache().multiplication_label_usage.save(payload)

    @staticmethod
    def _label_last_seen_at(record: Mapping[str, Any] | None) -> datetime | None:
        if record is None:
            return None
        value = record.get("lastSeenAt")
        if isinstance(value, datetime):
            return value
        if isinstance(value, str) and value:
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None
        return None

    def _record_multiplier_label_usage(
        self, labels: Iterable[str], *, now: datetime
    ) -> None:
        usage = self._load_multiplier_label_usage()
        for label in labels:
            usage[label] = {"lastSeenAt": now}
        self._save_multiplier_label_usage(usage)

    def _cleanup_unused_multiplier_labels(
        self,
        db: Database,
        *,
        seen_multiplier_labels: set[str],
        now: datetime,
    ) -> None:
        if not self.config.cleanup_unused_labels:
            return
        list_labels = getattr(db, "list_labels", None)
        delete_label_by_name = getattr(db, "delete_label_by_name", None)
        if not callable(list_labels) or not callable(delete_label_by_name):
            return

        usage = self._load_multiplier_label_usage()
        try:
            raw_labels = list_labels()
        except Exception as exc:  # pragma: no cover - defensive around API failures
            logger.warning(f"Failed to list labels for multiplier cleanup: {exc}")
            return
        if not isinstance(raw_labels, Sequence):
            logger.warning(
                "Failed to list labels for multiplier cleanup: unexpected payload"
            )
            return
        labels = cast(Sequence[object], raw_labels)

        cutoff = timedelta(days=self.config.cleanup_unused_labels_after_days)
        changed = False
        for label_record in labels:
            if not isinstance(label_record, Mapping):
                continue
            raw_name = label_record.get("name")
            if not isinstance(raw_name, str):
                continue
            if (
                self._flat_label_pattern.match(raw_name) is None
                and self._deep_label_pattern.match(raw_name) is None
            ):
                continue
            if raw_name in seen_multiplier_labels:
                continue

            last_seen_at = self._label_last_seen_at(usage.get(raw_name))
            if last_seen_at is None:
                logger.warning(
                    "Deleting unused multiplier label {!r}; it is not attached to any active task and has no recent usage record.",
                    raw_name,
                )
            elif now - last_seen_at < cutoff:
                logger.debug(
                    "Keeping unused multiplier label {!r}; last seen at {} and retention is {} day(s).",
                    raw_name,
                    last_seen_at.isoformat(timespec="seconds"),
                    self.config.cleanup_unused_labels_after_days,
                )
                continue
            else:
                logger.warning(
                    "Deleting unused multiplier label {!r}; last seen at {} and retention is {} day(s).",
                    raw_name,
                    last_seen_at.isoformat(timespec="seconds"),
                    self.config.cleanup_unused_labels_after_days,
                )

            try:
                deleted = bool(delete_label_by_name(raw_name))
            except Exception as exc:  # pragma: no cover - defensive around API failures
                logger.warning(
                    f"Failed to delete unused multiplier label {raw_name!r}: {exc}"
                )
                continue
            if deleted:
                usage.pop(raw_name, None)
                changed = True
                logger.info(f"Deleted unused multiplier label {raw_name!r}.")

        if changed:
            self._save_multiplier_label_usage(usage)

    def _select_tasks_to_process(self, all_tasks: list[Task]) -> list[Task]:
        selected: list[Task] = []
        for task in all_tasks:
            has_flat = any(
                self._flat_label_pattern.match(label)
                for label in task.task_entry.labels
            )
            has_deep = any(
                self._deep_label_pattern.match(label)
                for label in task.task_entry.labels
            )
            if has_flat or has_deep:
                selected.append(task)
        return selected

    def _process_task(
        self,
        db: Database,
        task: Task,
    ) -> None:
        try:
            flat_n = _factor_from_labels(
                task.task_entry.labels, self._flat_label_pattern, kind="flat"
            )
            deep_n = _factor_from_labels(
                task.task_entry.labels, self._deep_label_pattern, kind="deep"
            )
        except ValueError as e:
            logger.error(f"Task {task.id}: {e}")
            return

        # Deep label (_Xn) has priority.
        if deep_n is not None:
            if deep_n <= 0:
                logger.error(f"Task {task.id}: deep multiplication factor must be > 0")
                return
            if flat_n is not None:
                logger.warning(
                    f"Task {task.id}: has both deep (_Xn) and flat (Xn) labels; applying deep and ignoring flat"
                )
            self._expand_deep(db, task, deep_n)
            return

        if flat_n is not None:
            labels = _filter_out_multiplier_labels(
                task.task_entry.labels,
                flat_label_pattern=self._flat_label_pattern,
                deep_label_pattern=self._deep_label_pattern,
            )
            db.update_task(task.id, labels=labels)
            logger.info(
                "Removed legacy flat multiplier label from task {} ({!r}); labels are now {}.",
                task.id,
                task.task_entry.content,
                labels,
            )
            return

    def _expand_deep(self, db: Database, task: Task, n: int) -> None:
        """Create N subtasks under `task` and remove multiplier labels from the parent."""

        parent_labels = _filter_out_multiplier_labels(
            task.task_entry.labels,
            flat_label_pattern=self._flat_label_pattern,
            deep_label_pattern=self._deep_label_pattern,
        )
        child_labels = _append_unique_label(parent_labels, self.config.deep_child_label)

        base = task.task_entry.content
        requests: list[TaskTemplateInsertRequest] = []
        leaf_titles: list[str] = []
        for i in range(1, n + 1):
            leaf_title = _render(self.config.deep_leaf_template, base=base, i=i, n=n)
            logger.debug(f"Creating deep subtask under {task.id}: {leaf_title}")
            requests.append(
                TaskTemplateInsertRequest(
                    template=task,
                    overrides={
                        TaskField.CONTENT.value: leaf_title,
                        TaskField.LABELS.value: child_labels,
                        TaskField.PARENT_ID.value: task.id,
                    },
                )
            )
            leaf_titles.append(leaf_title)

        created_batch = _insert_tasks_from_templates_compat(db, requests)
        for leaf_title, created in zip(leaf_titles, created_batch, strict=False):
            new_id = str(created.get("id", "")) if isinstance(created, dict) else ""
            if new_id:
                logger.info(
                    "Created effort-point subtask {} ({!r}) under task {} with labels {}.",
                    new_id,
                    leaf_title,
                    task.id,
                    child_labels,
                )

        # Remove multiplier labels to keep the automation idempotent.
        db.update_task(task.id, labels=parent_labels)
        logger.info(
            "Removed deep multiplier label from task {} ({!r}); labels are now {}.",
            task.id,
            task.task_entry.content,
            parent_labels,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Multiply automation standalone")
    parser.add_argument("--dotenv", default=".env", help="Path to .env file")
    parser.add_argument("--frequency-minutes", type=float, default=0.1)
    args = parser.parse_args()

    multiply = Multiply(frequency_in_minutes=args.frequency_minutes)

    db = Database(args.dotenv)
    multiply.tick(db)


if __name__ == "__main__":
    main()
