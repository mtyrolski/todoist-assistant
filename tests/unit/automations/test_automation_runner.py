import pytest
from typing import cast

from todoist.automations.base import Automation, run_automations_resiliently
from todoist.database.base import Database
from todoist.core.env import EnvVar
from todoist.core.utils import Cache


class _StubAutomation(Automation):
    def __init__(self, name: str, *, is_long: bool = False):
        super().__init__(name, frequency=0, is_long=is_long)
        self.tick_calls: list[Database] = []

    def _tick(self, db: Database):
        self.tick_calls.append(db)


class _FailingAutomation(_StubAutomation):
    def _tick(self, db: Database):
        super()._tick(db)
        raise RuntimeError("boom")


def test_run_automations_resiliently_continues_after_failure() -> None:
    db = object()
    failing = _FailingAutomation("broken")
    healthy = _StubAutomation("healthy")

    summary = run_automations_resiliently(
        [failing, healthy],
        db=cast(Database, db),
    )

    assert len(failing.tick_calls) == 1
    assert len(healthy.tick_calls) == 1
    assert summary.completed == 1
    assert summary.failed == 1
    assert summary.skipped == 0


def test_run_automations_resiliently_skips_long_when_requested() -> None:
    db = object()
    long_automation = _StubAutomation("long", is_long=True)
    healthy = _StubAutomation("healthy")

    summary = run_automations_resiliently(
        [long_automation, healthy],
        db=cast(Database, db),
        skip_long=True,
    )

    assert len(long_automation.tick_calls) == 0
    assert len(healthy.tick_calls) == 1
    assert summary.completed == 1
    assert summary.failed == 0
    assert summary.skipped == 1


def test_automation_tick_records_completed_signal(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    db = object()
    automation = _StubAutomation("healthy")

    automation.tick(cast(Database, db))

    signal = Cache().automation_run_signals.load()["healthy"]
    assert signal["lastStatus"] == "completed"
    assert signal["attemptCount"] == 1
    assert signal["successCount"] == 1
    assert signal["failureCount"] == 0
    assert signal["skipCount"] == 0
    assert signal["lastError"] is None
    assert signal["lastStartedAt"] is not None
    assert signal["lastFinishedAt"] is not None
    assert signal["lastSuccessAt"] == signal["lastFinishedAt"]


def test_automation_tick_records_failed_signal(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    db = object()
    automation = _FailingAutomation("broken")

    with pytest.raises(RuntimeError, match="boom"):
        automation.tick(cast(Database, db))

    signal = Cache().automation_run_signals.load()["broken"]
    assert signal["lastStatus"] == "failed"
    assert signal["attemptCount"] == 1
    assert signal["successCount"] == 0
    assert signal["failureCount"] == 1
    assert signal["skipCount"] == 0
    assert signal["lastError"] == "RuntimeError: boom"
    assert signal["lastStartedAt"] is not None
    assert signal["lastFinishedAt"] is not None
    assert signal["lastSuccessAt"] is None


def test_run_automations_resiliently_records_skipped_signal(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    db = object()
    automation = _StubAutomation("long", is_long=True)

    summary = run_automations_resiliently(
        [automation],
        db=cast(Database, db),
        skip_long=True,
    )

    signal = Cache().automation_run_signals.load()["long"]
    assert summary.completed == 0
    assert summary.failed == 0
    assert summary.skipped == 1
    assert signal["lastStatus"] == "skipped"
    assert signal["attemptCount"] == 1
    assert signal["successCount"] == 0
    assert signal["failureCount"] == 0
    assert signal["skipCount"] == 1
