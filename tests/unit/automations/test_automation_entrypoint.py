from types import SimpleNamespace
from typing import cast

from todoist.automations.activity import Activity
from todoist.automations.base import Automation
from todoist.automations.entrypoint import (
    run_configured_automations,
    select_init_env_automations,
    select_update_env_automations,
)
from todoist.database.base import Database
from omegaconf import DictConfig


class _StubAutomation(Automation):
    def __init__(self, name: str, *, is_long: bool = False):
        super().__init__(name, frequency=0, is_long=is_long)
        self.tick_calls: list[Database] = []

    def _tick(self, db: Database):
        self.tick_calls.append(db)


class _StubActivity(Activity):
    def __init__(self, name: str, nweeks: int, *, is_long: bool = False):
        super().__init__(
            name=name, nweeks_window_size=nweeks, early_stop_after_n_windows=1
        )
        self.is_long = is_long


def test_select_init_env_automations_keeps_longest_activity_first() -> None:
    short_activity = _StubActivity("short", 1)
    long_activity = _StubActivity("long", 4)
    regular = _StubAutomation("regular")

    selected = select_init_env_automations([short_activity, regular, long_activity])

    assert selected == [long_activity, regular]


def test_select_update_env_automations_filters_long_automations_before_activity_selection() -> (
    None
):
    long_regular = _StubAutomation("long-regular", is_long=True)
    long_activity = _StubActivity("long-activity", 4, is_long=True)
    short_activity = _StubActivity("short-activity", 2)
    regular = _StubAutomation("regular")

    selected = select_update_env_automations(
        [long_regular, short_activity, long_activity, regular]
    )

    assert selected == [short_activity, regular]


def test_run_configured_automations_uses_skip_long_for_run_entrypoint(
    monkeypatch,
) -> None:
    config = cast(DictConfig, SimpleNamespace(automations=["raw-config"]))
    automations = [_StubAutomation("short"), _StubAutomation("long", is_long=True)]
    selected_automations: list[list[Automation]] = []

    monkeypatch.setattr(
        "todoist.automations.entrypoint.configure_runtime_logging",
        lambda **kwargs: None,
    )
    monkeypatch.setattr("todoist.automations.entrypoint.Database", lambda path: path)
    monkeypatch.setattr(
        "todoist.automations.entrypoint.hydra.utils.instantiate",
        lambda value: automations,
    )
    monkeypatch.setattr(
        "todoist.automations.entrypoint.tqdm", lambda value, desc: value
    )

    def _capture_selected(value: list[Automation]) -> list[Automation]:
        selected_automations.append(value)
        return value

    captured: dict[str, object] = {}

    def _fake_run_automations_resiliently(value, *, db, skip_long=False):
        captured["automations"] = list(value)
        captured["db"] = db
        captured["skip_long"] = skip_long

    monkeypatch.setattr(
        "todoist.automations.entrypoint.run_automations_resiliently",
        _fake_run_automations_resiliently,
    )

    run_configured_automations(
        config, select_automations=_capture_selected, skip_long=True
    )

    assert selected_automations == [automations]
    assert captured["automations"] == automations
    assert captured["db"] == ".env"
    assert captured["skip_long"] is True
