import argparse
import re
from dataclasses import dataclass
from typing import Iterable, Sequence

from loguru import logger

from todoist.automations.base import Automation
from todoist.database.base import Database
from todoist.types import Task


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
    # Flat multiplication via labels like X3
    flat_label_regex: str = r"^X(?P<n>\d+)$"
    flat_leaf_template: str = "{base} story-point-{i}"

    # Deep multiplication via labels like _X3
    # - creates N subtasks under the labeled task
    deep_label_regex: str = r"^_X(?P<n>\d+)$"
    deep_leaf_template: str = "{base} - {i}/{n}"


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
        if flat_label_pattern.match(label) is None and deep_label_pattern.match(label) is None
    ]


def _task_parent_id(task: Task) -> str | None:
    return task.task_entry.parent_id or task.task_entry.v2_parent_id


def _build_children_by_parent(tasks: Iterable[Task]) -> dict[str, list[Task]]:
    children_by_parent: dict[str, list[Task]] = {}
    for task in tasks:
        parent_id = _task_parent_id(task)
        if parent_id is None:
            continue
        children_by_parent.setdefault(parent_id, []).append(task)
    return children_by_parent


def _collect_descendants(root_id: str, *, children_by_parent: dict[str, list[Task]]) -> list[str]:
    # Post-order so callers can delete leaves first.
    ordered: list[str] = []
    stack: list[tuple[str, bool]] = [(root_id, False)]
    while stack:
        node_id, expanded = stack.pop()
        if expanded:
            ordered.append(node_id)
            continue
        stack.append((node_id, True))
        for child in children_by_parent.get(node_id, []):
            stack.append((child.id, False))

    return [task_id for task_id in ordered if task_id != root_id]


def _resolve_parent_targets(task: Task, *, flat_expansions: dict[str, list[str]]) -> Sequence[str | None]:
    """Return the parent IDs that new copies of `task` should attach to.

    If a task's parent was previously expanded (and likely deleted), we must attach
    new children to the newly created parent copies, not the original parent id.
    """

    parent_id = _task_parent_id(task)
    if parent_id is None:
        return (None,)
    return tuple(flat_expansions.get(parent_id, [parent_id]))


def _depth_sort_parent_first(tasks: list[Task]) -> list[Task]:
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

    return sorted(tasks, key=depth)


def _flat_factor_from_labels(labels: Iterable[str], flat_label_pattern: re.Pattern[str]) -> int | None:
    matched = [label for label in labels if flat_label_pattern.match(label) is not None]
    if not matched:
        return None
    if len(matched) != 1:
        raise ValueError(f"Expected exactly one flat multiplication label, found: {matched}")
    match = flat_label_pattern.match(matched[0])
    assert match is not None
    return int(match.group("n"))

def _deep_factor_from_labels(labels: Iterable[str], deep_label_pattern: re.Pattern[str]) -> int | None:
    matched = [label for label in labels if deep_label_pattern.match(label) is not None]
    if not matched:
        return None
    if len(matched) != 1:
        raise ValueError(f"Expected exactly one deep multiplication label, found: {matched}")
    match = deep_label_pattern.match(matched[0])
    assert match is not None
    return int(match.group("n"))


def _render(template: str, **kwargs) -> str:
    return template.format(**kwargs)


class Multiply(Automation):
    def __init__(
        self,
        frequency_in_minutes: float = 0.1,
        config: MultiplyConfig | None = None,
    ):
        super().__init__("Multiply", frequency_in_minutes)

        self.config = config or MultiplyConfig()

        self._flat_label_pattern = _compile(self.config.flat_label_regex)
        self._deep_label_pattern = _compile(self.config.deep_label_regex)

    def _tick(self, db: Database) -> None:
        projects = db.fetch_projects(include_tasks=True)
        all_tasks: list[Task] = [task for project in projects for task in project.tasks]
        logger.debug(f"Found {len(all_tasks)} tasks in total")

        children_by_parent = _build_children_by_parent(all_tasks)

        parent_ids: set[str] = set()
        for task in all_tasks:
            parent_id = _task_parent_id(task)
            if parent_id is not None:
                parent_ids.add(parent_id)

        tasks_to_process = self._select_tasks_to_process(all_tasks)
        tasks_to_process = _depth_sort_parent_first(tasks_to_process)

        # When a parent task is expanded we may delete the original. Any later child
        # expansions must point at the newly created parent copies.
        flat_expansions: dict[str, list[str]] = {}

        # Expanding a parent may delete its entire subtree; skip any later processing.
        deleted_ids: set[str] = set()

        logger.info(f"Found {len(tasks_to_process)} tasks to expand")
        for task in tasks_to_process:
            if task.id in deleted_ids:
                continue
            is_leaf = task.id not in parent_ids
            parent_targets = _resolve_parent_targets(task, flat_expansions=flat_expansions)
            created_ids, removed_ids = self._process_task(
                db,
                task,
                is_leaf=is_leaf,
                parent_targets=parent_targets,
                children_by_parent=children_by_parent,
            )
            deleted_ids.update(removed_ids)
            if created_ids:
                flat_expansions[task.id] = created_ids

    def _select_tasks_to_process(self, all_tasks: list[Task]) -> list[Task]:
        selected: list[Task] = []
        for task in all_tasks:
            has_flat = any(self._flat_label_pattern.match(label) for label in task.task_entry.labels)
            has_deep = any(self._deep_label_pattern.match(label) for label in task.task_entry.labels)
            if has_flat or has_deep:
                selected.append(task)
        return selected

    def _process_task(
        self,
        db: Database,
        task: Task,
        *,
        is_leaf: bool,
        parent_targets: Sequence[str | None],
        children_by_parent: dict[str, list[Task]],
    ) -> tuple[list[str], set[str]]:
        try:
            flat_n = _flat_factor_from_labels(task.task_entry.labels, self._flat_label_pattern)
            deep_n = _deep_factor_from_labels(task.task_entry.labels, self._deep_label_pattern)
        except ValueError as e:
            logger.error(f"Task {task.id}: {e}")
            return [], set()

        # Deep label (_Xn) has priority.
        if deep_n is not None:
            if deep_n <= 0:
                logger.error(f"Task {task.id}: deep multiplication factor must be > 0")
                return [], set()
            if flat_n is not None:
                logger.warning(
                    f"Task {task.id}: has both deep (_Xn) and flat (Xn) labels; applying deep and ignoring flat"
                )
            self._expand_deep(db, task, deep_n)
            return [], set()

        if flat_n is not None:
            return self._expand_flat(
                db,
                task,
                flat_n,
                parent_targets=parent_targets,
                children_by_parent=children_by_parent,
            )

        return [], set()

    def _clone_subtree_under_new_parents(
        self,
        db: Database,
        *,
        source_root_id: str,
        new_parent_ids: Sequence[str],
        children_by_parent: dict[str, list[Task]],
    ) -> list[str]:
        """Clone `source_root_id` subtree under each newly created parent copy.

        If we expand+delete a parent task, its existing children would otherwise become
        top-level tasks (Todoist doesn't support re-parenting via update).

        Returns descendant task IDs (not including the root) that should be removed
        from the source tree.
        """

        descendants_to_remove = _collect_descendants(source_root_id, children_by_parent=children_by_parent)

        for new_parent_id in new_parent_ids:
            stack: list[tuple[str, str]] = [(source_root_id, new_parent_id)]
            while stack:
                old_parent_id, current_new_parent_id = stack.pop()
                for child in children_by_parent.get(old_parent_id, []):
                    overrides: dict[str, object] = {
                        "content": child.task_entry.content,
                        "labels": list(child.task_entry.labels),
                        "parent_id": current_new_parent_id,
                    }
                    created = db.insert_task_from_template(child, **overrides)
                    new_child_id = str(created.get("id", "")) if isinstance(created, dict) else ""
                    if not new_child_id:
                        logger.error(
                            f"Task {child.id}: failed to clone under new parent {current_new_parent_id}; skipping its subtree"
                        )
                        continue

                    stack.append((child.id, new_child_id))

        return descendants_to_remove

    def _expand_flat(
        self,
        db: Database,
        task: Task,
        n: int,
        *,
        parent_targets: Sequence[str | None],
        children_by_parent: dict[str, list[Task]],
    ) -> tuple[list[str], set[str]]:
        labels = _filter_out_multiplier_labels(
            task.task_entry.labels,
            flat_label_pattern=self._flat_label_pattern,
            deep_label_pattern=self._deep_label_pattern,
        )
        base = task.task_entry.content

        created_ids: list[str] = []

        # If the parent was expanded earlier, replicate this task under each parent copy.
        for parent_id in parent_targets:
            for i in range(1, n + 1):
                content = _render(self.config.flat_leaf_template, base=base, i=i, n=n)
                logger.debug(f"Creating flat task: {content}")
                overrides: dict[str, object] = {"content": content, "labels": labels}
                if parent_id is not None:
                    overrides["parent_id"] = parent_id

                created = db.insert_task_from_template(task, **overrides)
                new_id = str(created.get("id", "")) if isinstance(created, dict) else ""
                if new_id:
                    created_ids.append(new_id)

        removed_ids: set[str] = set()
        if children_by_parent.get(task.id):
            descendants_to_remove = self._clone_subtree_under_new_parents(
                db,
                source_root_id=task.id,
                new_parent_ids=created_ids,
                children_by_parent=children_by_parent,
            )
        else:
            descendants_to_remove = []

        # Remove the expanded parent first (some tests assert parent-before-child ordering).
        removed_ids.add(task.id)
        self._remove_source_task(db, task.id)

        # Then remove original descendants so they don't become top-level or duplicate.
        for descendant_id in descendants_to_remove:
            removed_ids.add(descendant_id)
            self._remove_source_task(db, descendant_id)

        return created_ids, removed_ids

    def _expand_deep(self, db: Database, task: Task, n: int) -> None:
        """Create N subtasks under `task` and remove multiplier labels from the parent."""

        labels = _filter_out_multiplier_labels(
            task.task_entry.labels,
            flat_label_pattern=self._flat_label_pattern,
            deep_label_pattern=self._deep_label_pattern,
        )

        base = task.task_entry.content
        for i in range(1, n + 1):
            leaf_title = _render(self.config.deep_leaf_template, base=base, i=i, n=n)
            logger.debug(f"Creating deep subtask under {task.id}: {leaf_title}")
            db.insert_task_from_template(
                task,
                content=leaf_title,
                labels=labels,
                parent_id=task.id,
            )

        # Remove multiplier labels to keep the automation idempotent.
        db.update_task(task.id, labels=labels)

    def _remove_source_task(self, db: Database, task_id: str) -> None:
        logger.debug(f"Removing source task {task_id}")
        if db.remove_task(task_id):
            logger.debug(f"Task {task_id} removed")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Multiply automation standalone")
    parser.add_argument("--dotenv", default=".env", help="Path to .env file")
    parser.add_argument("--frequency-minutes", type=float, default=0.1)
    args = parser.parse_args()

    multiply = Multiply(frequency_in_minutes=args.frequency_minutes)

    db = Database(args.dotenv)
    multiply.tick(db)


if __name__ == '__main__':
    main()
