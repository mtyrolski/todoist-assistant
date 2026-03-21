from datetime import datetime
from typing import Any, Mapping, Sequence, cast

from loguru import logger

from todoist.automations.base import Automation
from todoist.database.base import Database
from todoist.stale_tasks import (
    StaleTaskConfig,
    StaleTaskDecision,
    evaluate_task_staleness,
    flatten_project_tasks,
)


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
            self.config = StaleTaskConfig(**config_data)
        self.dry_run = dry_run
        self.max_updates_per_tick = (
            None
            if max_updates_per_tick is None or int(max_updates_per_tick) <= 0
            else int(max_updates_per_tick)
        )
        self.last_run_summary: dict[str, Any] = {}

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
            "state": decision.state,
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

    def _tick(self, db: Database) -> list[dict[str, Any]]:
        projects = db.fetch_projects(include_tasks=True)
        project_tasks = flatten_project_tasks(projects)
        now = datetime.now()

        counts: dict[str, int] = {
            "scanned": 0,
            "fresh": 0,
            "old": 0,
            "very_old": 0,
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
            decision = evaluate_task_staleness(task, now=now, config=self.config)
            if decision.state == "skip":
                counts[f"skip_{decision.reason}"] = counts.get(
                    f"skip_{decision.reason}", 0
                ) + 1
                continue

            counts[decision.state] = counts.get(decision.state, 0) + 1
            if not decision.should_update or decision.desired_labels is None:
                continue

            candidates.append(
                self._summarize_decision(
                    project_name=project.project_entry.name,
                    task_id=task.id,
                    task_content=task.task_entry.content,
                    current_labels=list(task.task_entry.labels or []),
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
        else:
            for candidate in selected:
                db.update_task(
                    str(candidate["taskId"]),
                    labels=list(candidate["desiredLabels"] or []),
                )
            logger.info(
                "Stale tasks automation updated {} task(s) ({} additional candidates skipped by cap).",
                len(selected),
                skipped_by_cap,
            )

        self.last_run_summary = {
            "dryRun": self.dry_run,
            "config": {
                "oldAfterDays": self.config.old_after_days,
                "veryOldAfterDays": self.config.very_old_after_days,
                "oldLabel": self.config.old_label,
                "veryOldLabel": self.config.very_old_label,
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
