from abc import ABC, abstractmethod
from dataclasses import dataclass
import datetime as dt
from collections.abc import Iterable
from typing import Any
from loguru import logger

from todoist.database.base import Database
from todoist.core.utils import Cache


def _coerce_count(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def record_automation_run_signal(
    automation_name: str,
    *,
    status: str,
    started_at: dt.datetime,
    finished_at: dt.datetime,
    error: str | None = None,
) -> None:
    cache = Cache()
    payload = cache.automation_run_signals.load()
    signals = payload if isinstance(payload, dict) else {}
    current_payload = signals.get(automation_name)
    current = current_payload if isinstance(current_payload, dict) else {}
    finished_at_iso = finished_at.isoformat(timespec="seconds")

    signals[automation_name] = {
        "attemptCount": _coerce_count(current.get("attemptCount")) + 1,
        "successCount": _coerce_count(current.get("successCount"))
        + int(status == "completed"),
        "failureCount": _coerce_count(current.get("failureCount"))
        + int(status == "failed"),
        "skipCount": _coerce_count(current.get("skipCount")) + int(status == "skipped"),
        "lastStatus": status,
        "lastStartedAt": started_at.isoformat(timespec="seconds"),
        "lastFinishedAt": finished_at_iso,
        "lastDurationSeconds": round((finished_at - started_at).total_seconds(), 3),
        "lastError": error,
        "lastSuccessAt": (
            finished_at_iso if status == "completed" else current.get("lastSuccessAt")
        ),
    }
    try:
        cache.automation_run_signals.save(signals)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "Failed to persist automation run signal for {}: {}: {}",
            automation_name,
            type(exc).__name__,
            exc,
        )


class Automation(ABC):
    def __init__(self, name: str, frequency: float, is_long: bool = False):
        """
        Initialize the automation with a name and frequency.
        Frequency is the number of minutes between each tick.
        """
        self.name = name
        self.frequency = frequency
        self.is_long = is_long

    def __str__(self):
        return f"Automation(name={self.name}, frequency={self.frequency}, is_long={self.is_long})"

    def tick(self, db: Database):
        launch_data = (
            Cache().automation_launches.load()
        )  # expects a dict: {automation_name: [launch_times]}
        launches = launch_data.get(self.name, [])
        last_launch = launches[-1] if launches else dt.datetime.min

        started_at = dt.datetime.now()

        # Only run if the frequency delay has not passed since the last launch
        if (started_at - last_launch) < dt.timedelta(minutes=self.frequency):
            delay = dt.timedelta(minutes=self.frequency) - (started_at - last_launch)
            logger.info(f"Automation {self.name} is not ready to run.")
            logger.info(f"Last run: {last_launch}")
            logger.info(f"Current time: {started_at}")
            logger.info(f"Time until next run: {delay}")
            return []

        logger.info(
            f"Running automation {self.name} at {started_at} since passed {(started_at - last_launch).total_seconds() / 60} minutes since last run."
        )

        try:
            task_delegations = self._tick(db)
        except Exception as exc:
            record_automation_run_signal(
                self.name,
                status="failed",
                started_at=started_at,
                finished_at=dt.datetime.now(),
                error=f"{type(exc).__name__}: {exc}",
            )
            raise

        # Update the list of launch times with the new launch
        launches.append(started_at)
        launch_data[self.name] = launches
        Cache().automation_launches.save(launch_data)
        record_automation_run_signal(
            self.name,
            status="completed",
            started_at=started_at,
            finished_at=dt.datetime.now(),
        )

        return task_delegations

    def should_run_without_new_activity(self) -> bool:
        """Return whether the observer may run this automation without fresh activity."""
        return False

    @abstractmethod
    def _tick(self, db: Database) -> Any:
        """
        Perform the automation's main operation.
        """
        pass


@dataclass(frozen=True)
class AutomationRunSummary:
    completed: int
    failed: int
    skipped: int


def run_automations_resiliently(
    automations: Iterable[Automation],
    *,
    db: Database,
    skip_long: bool = False,
) -> AutomationRunSummary:
    completed = 0
    failed = 0
    skipped = 0

    for automation in automations:
        logger.info("Running automation: {}", automation)
        if skip_long and automation.is_long:
            skipped += 1
            logger.warning("Long automation detected, skipping...")
            started_at = dt.datetime.now()
            record_automation_run_signal(
                automation.name,
                status="skipped",
                started_at=started_at,
                finished_at=started_at,
            )
            continue
        try:
            automation.tick(db)
        except Exception as exc:  # pragma: no cover - defensive
            failed += 1
            logger.exception(
                "Automation {} failed: {}: {}",
                automation.name,
                type(exc).__name__,
                exc,
            )
            continue
        completed += 1
        logger.info("Automation completed: {}", automation)

    logger.info(
        "Automation run finished (completed={}, failed={}, skipped={})",
        completed,
        failed,
        skipped,
    )
    return AutomationRunSummary(completed=completed, failed=failed, skipped=skipped)
