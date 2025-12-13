import argparse
import re
from dataclasses import dataclass
from typing import Iterable

from loguru import logger

from todoist.automations.base import Automation
from todoist.database.base import Database
from todoist.types import Task


def is_multiplication_label(tag: str) -> bool:
    return bool(re.match(r"X\d+$", tag))


def extract_multiplication_factor(tag: str) -> int:
    match = re.match(r"X(\d+)$", tag)
    if match:
        return int(match.group(1))
    raise ValueError(f"Invalid multiplication label: {tag}")


@dataclass(frozen=True, slots=True)
class MultiplyConfig:
    # Flat multiplication via labels like X3
    flat_label_regex: str = r"^X(?P<n>\d+)$"
    flat_leaf_template: str = "{base} story-point-{i}"

    # Deep multiplication via a token in task content like: "... @_X5 - part J"
    # - creates a (batch) subtask under the (replacement) parent task
    # - creates N subtasks under that batch task
    deep_token_regex: str = r"@_X(?P<n>\d+)(?:\s*-\s*part\s*(?P<part>[A-Za-z0-9]+))?"
    deep_batch_template: str = "Batch of work{part_suffix}"
    deep_part_suffix_template: str = " - part {part}"
    deep_leaf_template: str = "{base}{part_suffix} - {i}/{n}"

    # Safety/idempotency: without an update-task endpoint, we replace+delete the source task.
    replace_parent_for_deep: bool = True
    remove_source_task_after_expansion: bool = True


@dataclass(frozen=True, slots=True)
class _DeepDirective:
    n: int
    part: str | None
    token_span: tuple[int, int]


def _compile(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern)


def _find_deep_directive(content: str, deep_pattern: re.Pattern[str]) -> _DeepDirective | None:
    match = deep_pattern.search(content)
    if match is None:
        return None
    n = int(match.group("n"))
    part = match.groupdict().get("part")
    return _DeepDirective(n=n, part=part, token_span=match.span())


def _strip_span(content: str, span: tuple[int, int]) -> str:
    before = content[: span[0]].rstrip()
    after = content[span[1] :].lstrip()
    joined = (before + " " + after).strip()
    # Clean up common punctuation left around the token.
    joined = re.sub(r"\s{2,}", " ", joined)
    joined = re.sub(r"\s+-\s+$", "", joined).strip()
    joined = re.sub(r"\s+\|\s+$", "", joined).strip()
    return joined


def _filter_out_flat_labels(labels: Iterable[str], flat_label_pattern: re.Pattern[str]) -> list[str]:
    return [label for label in labels if flat_label_pattern.match(label) is None]


def _task_parent_id(task: Task) -> str | None:
    return task.task_entry.parent_id or task.task_entry.v2_parent_id


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


def _render_part_suffix(part: str | None, template: str) -> str:
    if not part:
        return ""
    return template.format(part=part)


def _render(template: str, **kwargs) -> str:
    return template.format(**kwargs)


class Multiply(Automation):
    def __init__(
        self,
        frequency_in_minutes: float = 0.1,
        config: MultiplyConfig | None = None,
        *,
        deep_token_regex: str | None = None,
        flat_label_regex: str | None = None,
        flat_leaf_template: str | None = None,
        deep_batch_template: str | None = None,
        deep_leaf_template: str | None = None,
        replace_parent_for_deep: bool | None = None,
        remove_source_task_after_expansion: bool | None = None,
    ):
        super().__init__("Multiply", frequency_in_minutes)

        base = config or MultiplyConfig()
        self.config = MultiplyConfig(
            flat_label_regex=flat_label_regex or base.flat_label_regex,
            flat_leaf_template=flat_leaf_template or base.flat_leaf_template,
            deep_token_regex=deep_token_regex or base.deep_token_regex,
            deep_batch_template=deep_batch_template or base.deep_batch_template,
            deep_part_suffix_template=base.deep_part_suffix_template,
            deep_leaf_template=deep_leaf_template or base.deep_leaf_template,
            replace_parent_for_deep=(
                base.replace_parent_for_deep if replace_parent_for_deep is None else replace_parent_for_deep
            ),
            remove_source_task_after_expansion=(
                base.remove_source_task_after_expansion
                if remove_source_task_after_expansion is None
                else remove_source_task_after_expansion
            ),
        )

        self._flat_label_pattern = _compile(self.config.flat_label_regex)
        self._deep_token_pattern = _compile(self.config.deep_token_regex)

    def _tick(self, db: Database) -> None:
        projects = db.fetch_projects(include_tasks=True)
        all_tasks: list[Task] = [task for project in projects for task in project.tasks]
        logger.debug(f"Found {len(all_tasks)} tasks in total")

        parent_ids: set[str] = set()
        for task in all_tasks:
            parent_id = _task_parent_id(task)
            if parent_id is not None:
                parent_ids.add(parent_id)

        tasks_to_process = self._select_tasks_to_process(all_tasks)
        tasks_to_process = _depth_sort_parent_first(tasks_to_process)

        logger.info(f"Found {len(tasks_to_process)} tasks to expand")
        for task in tasks_to_process:
            is_leaf = task.id not in parent_ids
            self._process_task(db, task, is_leaf=is_leaf)

    def _select_tasks_to_process(self, all_tasks: list[Task]) -> list[Task]:
        selected: list[Task] = []
        for task in all_tasks:
            has_flat = any(self._flat_label_pattern.match(label) for label in task.task_entry.labels)
            has_deep = _find_deep_directive(task.task_entry.content, self._deep_token_pattern) is not None
            if has_flat or has_deep:
                selected.append(task)
        return selected

    def _process_task(self, db: Database, task: Task, *, is_leaf: bool) -> None:
        deep = _find_deep_directive(task.task_entry.content, self._deep_token_pattern)

        try:
            flat_n = _flat_factor_from_labels(task.task_entry.labels, self._flat_label_pattern)
        except ValueError as e:
            logger.error(f"Task {task.id}: {e}")
            return

        # Deep token has priority and must be applied only to leaf tasks.
        if deep is not None:
            if not is_leaf:
                self._strip_deep_token_on_non_leaf(db, task, deep)
                return
            if flat_n is not None:
                logger.warning(
                    f"Task {task.id}: has both deep token and flat label; applying deep and ignoring flat"
                )
            self._expand_deep(db, task, deep)
            return

        if flat_n is not None:
            self._expand_flat(db, task, flat_n)
            return

    def _strip_deep_token_on_non_leaf(self, db: Database, task: Task, deep: _DeepDirective) -> None:
        stripped = _strip_span(task.task_entry.content, deep.token_span)
        if stripped == task.task_entry.content:
            return

        logger.warning(
            f"Task {task.id}: deep token present on non-leaf task; stripping token and skipping expansion"
        )
        db.update_task_content(task.id, stripped)

    def _expand_flat(self, db: Database, task: Task, n: int) -> None:
        labels = _filter_out_flat_labels(task.task_entry.labels, self._flat_label_pattern)
        base = task.task_entry.content

        for i in range(1, n + 1):
            content = _render(self.config.flat_leaf_template, base=base, i=i, n=n)
            logger.debug(f"Creating flat task: {content}")
            db.insert_task_from_template(task, content=content, labels=labels)

        self._remove_source_task_if_configured(db, task.id)

    def _expand_deep(self, db: Database, task: Task, deep: _DeepDirective) -> None:
        if deep.n <= 0:
            logger.error(f"Task {task.id}: deep multiplication factor must be > 0")
            return

        labels = _filter_out_flat_labels(task.task_entry.labels, self._flat_label_pattern)
        part_suffix = _render_part_suffix(deep.part, self.config.deep_part_suffix_template)

        # We cannot update task content via API (no endpoint wired), so to avoid
        # re-processing we replace+delete the source task by default.
        root_task_id = task.id
        base_content = _strip_span(task.task_entry.content, deep.token_span)
        if self.config.replace_parent_for_deep:
            logger.debug(f"Creating replacement parent for task {task.id}")
            created = db.insert_task_from_template(task, content=base_content, labels=labels)
            root_task_id = str(created.get("id", ""))
            if not root_task_id:
                logger.error(f"Task {task.id}: failed to create replacement parent; skipping")
                return
        else:
            # Keep original task as the parent; strip the token in-place for idempotency.
            db.update_task_content(task.id, base_content)

        batch_title = _render(self.config.deep_batch_template, part_suffix=part_suffix, part=deep.part)
        logger.debug(f"Creating batch subtask under {root_task_id}: {batch_title}")
        batch_created = db.insert_task_from_template(
            task,
            content=batch_title,
            labels=labels,
            parent_id=root_task_id,
        )
        batch_id = str(batch_created.get("id", ""))
        if not batch_id:
            logger.error(f"Task {task.id}: failed to create batch task; skipping")
            return

        for i in range(1, deep.n + 1):
            leaf_title = _render(
                self.config.deep_leaf_template,
                base=base_content,
                i=i,
                n=deep.n,
                part_suffix=part_suffix,
                part=deep.part,
            )
            logger.debug(f"Creating deep subtask under {batch_id}: {leaf_title}")
            db.insert_task_from_template(
                task,
                content=leaf_title,
                labels=labels,
                parent_id=batch_id,
            )

        # Remove the original task (the one containing the token) to keep this idempotent.
        if self.config.replace_parent_for_deep or self.config.remove_source_task_after_expansion:
            self._remove_source_task_if_configured(db, task.id)

    def _remove_source_task_if_configured(self, db: Database, task_id: str) -> None:
        if not self.config.remove_source_task_after_expansion:
            return
        logger.debug(f"Removing source task {task_id}")
        if db.remove_task(task_id):
            logger.debug(f"Task {task_id} removed")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Multiply automation standalone")
    parser.add_argument("--dotenv", default=".env", help="Path to .env file")
    parser.add_argument("--frequency-minutes", type=float, default=0.1)
    parser.add_argument("--flat-label-regex", default=None)
    parser.add_argument("--deep-token-regex", default=None)
    parser.add_argument("--flat-leaf-template", default=None)
    parser.add_argument("--deep-batch-template", default=None)
    parser.add_argument("--deep-leaf-template", default=None)
    parser.add_argument("--keep-source-task", action="store_true")
    parser.add_argument("--no-replace-parent", action="store_true")
    args = parser.parse_args()

    multiply = Multiply(
        frequency_in_minutes=args.frequency_minutes,
        flat_label_regex=args.flat_label_regex,
        deep_token_regex=args.deep_token_regex,
        flat_leaf_template=args.flat_leaf_template,
        deep_batch_template=args.deep_batch_template,
        deep_leaf_template=args.deep_leaf_template,
        remove_source_task_after_expansion=not args.keep_source_task,
        replace_parent_for_deep=not args.no_replace_parent,
    )

    db = Database(args.dotenv)
    multiply.tick(db)


if __name__ == '__main__':
    main()
