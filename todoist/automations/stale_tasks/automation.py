from datetime import datetime, timedelta
from typing import Any, Mapping, Sequence, cast

from loguru import logger

from todoist.automations.base import Automation
from todoist.database.base import Database
from todoist.features.stale_tasks import (
    StaleTaskConfig,
    StaleTaskDecision,
    StaleState,
    evaluate_task_staleness,
    flatten_project_tasks,
    managed_stale_label_names,
    stale_label_for_state,
)
from todoist.core.utils import Cache


class StaleTasksAutomation(Automation):
    def __init__(
        self,
        name: str = "Stale Tasks",
        frequency_in_minutes: float = 60.0 * 24.0,
        *,
        config: StaleTaskConfig | Mapping[str, Any] | None = None,
        dry_run: bool = True,
        max_updates_per_tick: int | None = 25,
    ) -> None:
        super().__init__(name=name, frequency=frequency_in_minutes, is_long=False)
        if config is None:
            self.config = StaleTaskConfig()
        elif isinstance(config, StaleTaskConfig):
            self.config = config
        else:
            config_data = dict(config)
            exempt_labels = config_data.get("exempt_labels")
            if exempt_labels is not None:
                config_data["exempt_labels"] = tuple(cast(Sequence[str], exempt_labels))
            if "exclude_due_within_days" in config_data:
                config_data["exclude_due_within_days"] = max(
                    0, int(config_data["exclude_due_within_days"])
                )
            if "delete_after_warning_days" in config_data:
                config_data["delete_after_warning_days"] = max(
                    0, int(config_data["delete_after_warning_days"])
                )
            self.config = StaleTaskConfig(**config_data)
        self.dry_run = dry_run
        self.max_updates_per_tick = (
            None
            if max_updates_per_tick is None or int(max_updates_per_tick) <= 0
            else int(max_updates_per_tick)
        )
        self.last_run_summary: dict[str, Any] = {}

    @staticmethod
    def _load_warning_tracking() -> dict[str, dict[str, Any]]:
        payload = Cache().stale_task_warnings.load()
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _save_warning_tracking(payload: dict[str, dict[str, Any]]) -> None:
        Cache().stale_task_warnings.save(payload)

    def _current_managed_label(self, labels: Sequence[str]) -> str | None:
        managed = managed_stale_label_names(self.config)
        for label in labels:
            if label.strip().lower() in managed:
                return label
        return None

    @staticmethod
    def _tracked_warning_at(record: Mapping[str, Any] | None) -> datetime | None:
        if record is None:
            return None
        value = record.get("warningLabelAddedAt")
        if isinstance(value, datetime):
            return value
        if isinstance(value, str) and value:
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None
        return None

    def _summarize_decision(
        self,
        *,
        project_name: str,
        task_id: str,
        task_content: str,
        current_labels: list[str],
        decision: StaleTaskDecision,
    ) -> dict[str, Any]:
        return {
            "taskId": task_id,
            "projectName": project_name,
            "content": task_content,
            "state": decision.state.value,
            "reason": decision.reason,
            "staleDays": decision.stale_days,
            "lastTouchedAt": (
                decision.last_touched_at.isoformat(timespec="seconds")
                if decision.last_touched_at is not None
                else None
            ),
            "currentLabels": current_labels,
            "desiredLabels": decision.desired_labels,
        }

    def _summarize_removal(
        self,
        *,
        project_name: str,
        task_id: str,
        task_content: str,
        current_labels: list[str],
        warning_label: str,
        warning_label_added_at: datetime,
        now: datetime,
    ) -> dict[str, Any]:
        return {
            "taskId": task_id,
            "projectName": project_name,
            "content": task_content,
            "state": "remove",
            "reason": "stale_warning_expired",
            "warningLabel": warning_label,
            "warningLabelAddedAt": warning_label_added_at.isoformat(timespec="seconds"),
            "warningAgeDays": max(0, (now.date() - warning_label_added_at.date()).days),
            "currentLabels": current_labels,
            "desiredLabels": None,
        }

    def _tick(self, db: Database) -> list[dict[str, Any]]:
        projects = db.fetch_projects(include_tasks=True)
        project_tasks = flatten_project_tasks(projects)
        now = datetime.now()
        tracking = self._load_warning_tracking()
        seen_task_ids: set[str] = set()

        counts: dict[str, int] = {
            "scanned": 0,
            "fresh": 0,
            "old": 0,
            "very_old": 0,
            "remove": 0,
            "skip_exempt_label": 0,
            "skip_recurring": 0,
            "skip_subtask": 0,
            "skip_due_soon": 0,
            "skip_overdue": 0,
            "skip_missing_timestamp": 0,
        }
        candidates: list[dict[str, Any]] = []

        for project, task in project_tasks:
            counts["scanned"] += 1
            seen_task_ids.add(task.id)
            decision = evaluate_task_staleness(task, now=now, config=self.config)
            if decision.state is StaleState.SKIP:
                counts[f"skip_{decision.reason}"] = (
                    counts.get(f"skip_{decision.reason}", 0) + 1
                )
                continue

            counts[decision.state.value] = counts.get(decision.state.value, 0) + 1
            current_labels = list(task.task_entry.labels or [])
            current_warning_label = self._current_managed_label(current_labels)

            if decision.state is StaleState.FRESH:
                tracking.pop(task.id, None)
            else:
                warning_label = current_warning_label or stale_label_for_state(
                    decision.state,
                    config=self.config,
                )
                tracked_at = self._tracked_warning_at(tracking.get(task.id))
                if tracked_at is None:
                    tracked_at = now
                    tracking[task.id] = {
                        "warningLabel": warning_label,
                        "warningLabelAddedAt": tracked_at,
                    }
                else:
                    tracking[task.id] = {
                        "warningLabel": warning_label,
                        "warningLabelAddedAt": tracked_at,
                    }

                should_remove = (
                    current_warning_label is not None
                    and now - tracked_at
                    >= timedelta(days=self.config.delete_after_warning_days)
                )
                if should_remove:
                    counts["remove"] += 1
                    candidates.append(
                        self._summarize_removal(
                            project_name=project.project_entry.name,
                            task_id=task.id,
                            task_content=task.task_entry.content,
                            current_labels=current_labels,
                            warning_label=warning_label,
                            warning_label_added_at=tracked_at,
                            now=now,
                        )
                    )
                    continue

            if not decision.should_update or decision.desired_labels is None:
                continue

            candidates.append(
                self._summarize_decision(
                    project_name=project.project_entry.name,
                    task_id=task.id,
                    task_content=task.task_entry.content,
                    current_labels=current_labels,
                    decision=decision,
                )
            )

        selected = (
            candidates
            if self.max_updates_per_tick is None
            else candidates[: self.max_updates_per_tick]
        )
        skipped_by_cap = len(candidates) - len(selected)

        if self.dry_run:
            logger.info(
                "Stale tasks dry run: {} candidate updates detected ({} selected, {} skipped by cap).",
                len(candidates),
                len(selected),
                skipped_by_cap,
            )
            for candidate in selected:
                if candidate.get("state") == "remove":
                    logger.warning(
                        "Stale tasks dry run would delete task {} ({!r}) from project {!r}; warning label {!r} was added at {}.",
                        candidate["taskId"],
                        candidate["content"],
                        candidate["projectName"],
                        candidate.get("warningLabel"),
                        candidate.get("warningLabelAddedAt"),
                    )
                else:
                    logger.info(
                        "Stale tasks dry run would update task {} ({!r}) labels: {} -> {}.",
                        candidate["taskId"],
                        candidate["content"],
                        candidate.get("currentLabels"),
                        candidate.get("desiredLabels"),
                    )
        else:
            for candidate in selected:
                task_id = str(candidate["taskId"])
                if candidate.get("state") == "remove":
                    removed = db.remove_task(task_id)
                    if removed:
                        logger.warning(
                            "Deleted stale task {} ({!r}) from project {!r}; warning label {!r} was added at {}.",
                            task_id,
                            candidate["content"],
                            candidate["projectName"],
                            candidate.get("warningLabel"),
                            candidate.get("warningLabelAddedAt"),
                        )
                        tracking.pop(task_id, None)
                    else:
                        logger.error(
                            "Failed to delete stale task {} ({!r}) from project {!r}.",
                            task_id,
                            candidate["content"],
                            candidate["projectName"],
                        )
                    continue
                labels = list(candidate["desiredLabels"] or [])
                db.update_task(task_id, labels=labels)
                logger.info(
                    "Updated stale task {} ({!r}) labels in project {!r}: {} -> {}.",
                    task_id,
                    candidate["content"],
                    candidate["projectName"],
                    candidate.get("currentLabels"),
                    labels,
                )
            logger.info(
                "Stale tasks automation updated {} task(s) ({} additional candidates skipped by cap).",
                len(selected),
                skipped_by_cap,
            )

        for task_id in list(tracking):
            if task_id not in seen_task_ids:
                tracking.pop(task_id, None)
        self._save_warning_tracking(tracking)

        self.last_run_summary = {
            "dryRun": self.dry_run,
            "config": {
                "oldAfterDays": self.config.old_after_days,
                "veryOldAfterDays": self.config.very_old_after_days,
                "oldLabel": self.config.old_label,
                "veryOldLabel": self.config.very_old_label,
                "deleteAfterWarningDays": self.config.delete_after_warning_days,
                "exemptLabels": list(self.config.exempt_labels),
                "excludeRecurring": self.config.exclude_recurring,
                "excludeDueWithinDays": self.config.exclude_due_within_days,
                "excludeOverdue": self.config.exclude_overdue,
                "applyToSubtasks": self.config.apply_to_subtasks,
            },
            "counts": {
                **counts,
                "candidateUpdates": len(candidates),
                "selectedUpdates": len(selected),
                "skippedByCap": skipped_by_cap,
            },
            "changes": selected,
        }
        return selected
