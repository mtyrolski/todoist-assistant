"""Tests for utility functions in ``todoist.utils``."""

# pylint: disable=protected-access

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, KeysView
from unittest.mock import MagicMock, patch

import pytest

from todoist.env import EnvVar
from todoist.utils import (
    DEFAULT_CACHE_SUBDIR,
    DEFAULT_MAX_CONCURRENT_REQUESTS,
    DEFAULT_LOG_LEVEL,
    DEFAULT_MAX_REQUESTS_PER_MINUTE,
    MIGRATION_BACKUP_DIRNAME,
    RETRY_BACKOFF_MEAN,
    RETRY_BACKOFF_STD,
    RETRY_MAX_ATTEMPTS,
    Anonymizable,
    Cache,
    LocalStorage,
    LocalStorageError,
    MaxRetriesExceeded,
    configure_runtime_logging,
    get_all_fields_of_dataclass,
    get_api_key,
    get_log_level,
    get_max_concurrent_requests,
    get_max_requests_per_minute,
    get_rate_pacing_base_delay_seconds,
    get_rate_pacing_jitter_max_seconds,
    get_rate_pacing_jitter_min_seconds,
    last_n_years_in_weeks,
    load_config,
    retry_with_backoff,
    safe_instantiate_entry,
    try_n_times,
    with_retry,
)


@dataclass
class SampleDataclass:
    field1: str
    field2: int
    field3: bool = False


@dataclass
class DataclassWithKwargs:
    known_field: str
    another_field: int = 0
    new_api_kwargs: dict[str, Any] | None = None


def _eventually_successful(failures_before_success: int, error_message: str = "Not yet"):
    state = {"count": 0}

    def _fn() -> str:
        state["count"] += 1
        if state["count"] <= failures_before_success:
            raise ValueError(error_message)
        return "success"

    return _fn, state


def test_get_all_fields_of_dataclass_returns_all_fields():
    fields = get_all_fields_of_dataclass(SampleDataclass)
    assert isinstance(fields, KeysView)
    assert list(fields) == ["field1", "field2", "field3"]


def test_get_all_fields_of_dataclass_empty():
    @dataclass
    class EmptyDataclass:
        pass

    assert list(get_all_fields_of_dataclass(EmptyDataclass)) == []


@pytest.mark.parametrize(
    ("entry_kwargs", "expected_known_field", "expected_another_field", "expected_unexpected"),
    [
        ({"known_field": "test", "another_field": 42}, "test", 42, {}),
        (
            {
                "known_field": "test",
                "another_field": 42,
                "unexpected_field": "value",
                "another_unexpected": 123,
            },
            "test",
            42,
            {"unexpected_field": "value", "another_unexpected": 123},
        ),
        (
            {
                "known_field": "test",
                "unexpected1": "value1",
                "unexpected2": "value2",
            },
            "test",
            0,
            {"unexpected1": "value1", "unexpected2": "value2"},
        ),
    ],
)
def test_safe_instantiate_entry_collects_unexpected_fields(
    entry_kwargs: dict[str, Any],
    expected_known_field: str,
    expected_another_field: int,
    expected_unexpected: dict[str, Any],
):
    result = safe_instantiate_entry(DataclassWithKwargs, **entry_kwargs)
    assert result.known_field == expected_known_field
    assert result.another_field == expected_another_field
    assert result.new_api_kwargs == expected_unexpected


def test_safe_instantiate_entry_warns_once_for_missing_required_fields():
    # pylint: disable=protected-access
    import todoist.utils as utils

    @dataclass
    class DataclassWithRequiredAndKwargs:
        required_field: str
        new_api_kwargs: dict[str, Any] | None = None

    utils._MISSING_REQUIRED_FIELD_WARNINGS.clear()
    with patch("todoist.utils.logger.warning") as mock_warning:
        first = safe_instantiate_entry(DataclassWithRequiredAndKwargs)
        second = safe_instantiate_entry(DataclassWithRequiredAndKwargs)

    assert first.required_field is None
    assert second.required_field is None
    assert mock_warning.call_count == 1
    warning_message = mock_warning.call_args.args[0]
    assert "missing required field 'required_field'" in warning_message


def test_safe_instantiate_entry_requires_kwargs_field():
    @dataclass
    class DataclassWithoutKwargs:
        field1: str

    with pytest.raises(AssertionError, match="kwargs field"):
        safe_instantiate_entry(DataclassWithoutKwargs, field1="test", extra="field")


def test_safe_instantiate_entry_keeps_unknown_api_v1_fields_in_new_api_kwargs():
    from todoist.types import EventEntry, ProjectEntry, TaskEntry

    project_payload = {
        "id": "proj1",
        "name": "Project 1",
        "color": "blue",
        "parent_id": None,
        "child_order": 1,
        "view_style": "list",
        "is_favorite": False,
        "is_archived": False,
        "is_deleted": False,
        "is_frozen": False,
        "can_assign_tasks": True,
        "is_shared": True,
        "access": "team",
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-02T00:00:00Z",
        "is_collapsed": False,
    }
    project_entry = safe_instantiate_entry(ProjectEntry, **project_payload)
    assert project_entry.shared is None
    assert project_entry.collapsed is None
    assert project_entry.v2_id is None
    assert project_entry.is_shared is True
    assert project_entry.is_collapsed is False
    assert project_entry.access == {"visibility": "team"}
    assert project_entry.new_api_kwargs is not None
    assert project_entry.new_api_kwargs == {}

    task_payload = {
        "id": "task1",
        "user_id": "user1",
        "project_id": "proj1",
        "section_id": None,
        "parent_id": None,
        "added_by_uid": "user1",
        "assigned_by_uid": None,
        "responsible_uid": None,
        "labels": [],
        "deadline": None,
        "duration": None,
        "checked": False,
        "is_deleted": False,
        "added_at": "2024-01-01T00:00:00Z",
        "completed_at": None,
        "updated_at": "2024-01-01T00:00:00Z",
        "due": None,
        "priority": 1,
        "child_order": 1,
        "content": "Task 1",
        "description": "",
        "note_count": 0,
        "goal_ids": ["goal-1"],
        "day_order": "0",
        "is_collapsed": False,
    }
    task_entry = safe_instantiate_entry(TaskEntry, **task_payload)
    assert task_entry.collapsed is None
    assert task_entry.v2_id is None
    assert task_entry.v2_project_id is None
    assert task_entry.is_collapsed is False
    assert task_entry.goal_ids == ["goal-1"]
    assert task_entry.day_order == 0
    assert task_entry.new_api_kwargs is not None
    assert task_entry.new_api_kwargs == {}

    event_payload = {
        "id": "event1",
        "object_type": "item",
        "object_id": "task1",
        "event_type": "added",
        "event_date": "2024-01-01T00:00:00Z",
        "parent_project_id": "proj1",
        "parent_item_id": None,
        "initiator_id": "user1",
        "extra_data": {"content": "Task 1"},
        "extra_data_id": None,
        "source": "api",
    }
    event_entry = safe_instantiate_entry(EventEntry, **event_payload)
    assert event_entry.v2_object_id is None
    assert event_entry.v2_parent_project_id is None
    assert event_entry.source == "api"


def test_safe_instantiate_entry_does_not_warn_for_current_project_and_task_payloads():
    # pylint: disable=protected-access
    import todoist.utils as utils
    from todoist.types import ProjectEntry, TaskEntry

    project_payload = {
        "id": "proj1",
        "name": "Project 1",
        "color": "blue",
        "parent_id": None,
        "child_order": 1,
        "view_style": "list",
        "is_favorite": False,
        "is_archived": False,
        "is_deleted": False,
        "is_frozen": False,
        "can_assign_tasks": True,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-02T00:00:00Z",
        "is_shared": True,
        "is_collapsed": False,
        "access": {"visibility": "restricted", "configuration": {}},
    }
    task_payload = {
        "id": "task1",
        "user_id": "user1",
        "project_id": "proj1",
        "section_id": None,
        "parent_id": None,
        "added_by_uid": "user1",
        "assigned_by_uid": None,
        "responsible_uid": None,
        "labels": [],
        "deadline": None,
        "duration": None,
        "checked": False,
        "is_deleted": False,
        "added_at": "2024-01-01T00:00:00Z",
        "completed_at": None,
        "updated_at": "2024-01-01T00:00:00Z",
        "due": None,
        "priority": 1,
        "child_order": 1,
        "content": "Task 1",
        "description": "",
        "note_count": 0,
        "goal_ids": ["goal-1"],
        "is_collapsed": False,
    }

    utils._MISSING_REQUIRED_FIELD_WARNINGS.clear()
    with patch("todoist.utils.logger.warning") as mock_warning:
        project_entry = safe_instantiate_entry(ProjectEntry, **project_payload)
        task_entry = safe_instantiate_entry(TaskEntry, **task_payload)

    assert project_entry.shared is None
    assert task_entry.sync_id is None
    assert task_entry.collapsed is None
    assert task_entry.goal_ids == ["goal-1"]
    assert mock_warning.call_count == 0


@pytest.mark.parametrize(
    ("years", "expected_weeks"),
    [
        (0, 0),
        (1, 52),
        (2, 104),
        (5, 260),
        (-1, -52),
    ],
)
def test_last_n_years_in_weeks(years: int, expected_weeks: int):
    assert last_n_years_in_weeks(years) == expected_weeks


@pytest.mark.parametrize(
    ("env_payload", "expected"),
    [
        ({"API_KEY": "test_api_key_12345"}, "test_api_key_12345"),
        ({}, ""),
        ({"API_KEY": ""}, ""),
    ],
)
def test_get_api_key(env_payload: dict[str, str], expected: str):
    with patch.dict(os.environ, env_payload, clear=True):
        assert get_api_key() == expected


def test_get_log_level_defaults_to_info():
    with patch.dict(os.environ, {}, clear=True):
        assert get_log_level() == DEFAULT_LOG_LEVEL


def test_get_log_level_normalizes_env_value():
    with patch.dict(os.environ, {EnvVar.LOG_LEVEL: "debug"}, clear=True):
        assert get_log_level() == "DEBUG"


def test_get_log_level_falls_back_on_invalid_env_value():
    with (
        patch.dict(os.environ, {EnvVar.LOG_LEVEL: "nope"}, clear=True),
        patch("todoist.utils.logger.warning") as mock_warning,
    ):
        assert get_log_level() == DEFAULT_LOG_LEVEL
    mock_warning.assert_called_once()


@pytest.mark.parametrize(
    ("env_value", "expected"),
    [
        (None, DEFAULT_MAX_CONCURRENT_REQUESTS),
        ("8", 8),
        ("0", DEFAULT_MAX_CONCURRENT_REQUESTS),
        ("-4", DEFAULT_MAX_CONCURRENT_REQUESTS),
        ("not-an-int", DEFAULT_MAX_CONCURRENT_REQUESTS),
    ],
)
def test_get_max_concurrent_requests_parses_env_value(env_value: str | None, expected: int):
    if env_value is None:
        payload: dict[str, str] = {}
    else:
        payload = {EnvVar.MAX_CONCURRENT_REQUESTS: env_value}
        with patch.dict(os.environ, payload, clear=True):
            assert get_max_concurrent_requests() == expected


@pytest.mark.parametrize(
    ("env_value", "expected"),
    [
        (None, DEFAULT_MAX_REQUESTS_PER_MINUTE),
        ("30", 30),
        ("1", 1),
        ("0", DEFAULT_MAX_REQUESTS_PER_MINUTE),
        ("-5", DEFAULT_MAX_REQUESTS_PER_MINUTE),
        ("not-an-int", DEFAULT_MAX_REQUESTS_PER_MINUTE),
    ],
)
def test_get_max_requests_per_minute_parses_env_value(env_value: str | None, expected: int):
    if env_value is None:
        payload: dict[str, str] = {}
    else:
        payload = {EnvVar.MAX_REQUESTS_PER_MINUTE: env_value}
    with patch.dict(os.environ, payload, clear=True):
        assert get_max_requests_per_minute() == expected


@pytest.mark.parametrize(
    ("env_value", "expected"),
    [
        (None, 0.0),
        ("5", 5.0),
        ("2.5", 2.5),
        ("-1", 0.0),
        ("oops", 0.0),
    ],
)
def test_get_rate_pacing_base_delay_seconds_parses_env_value(env_value: str | None, expected: float):
    payload = {} if env_value is None else {EnvVar.RATE_PACING_BASE_DELAY_SECONDS: env_value}
    with patch.dict(os.environ, payload, clear=True):
        assert get_rate_pacing_base_delay_seconds() == expected


@pytest.mark.parametrize(
    ("min_raw", "max_raw", "expected_min", "expected_max"),
    [
        (None, None, 0.0, 0.0),
        ("1", "5", 1.0, 5.0),
        ("0.5", "2.5", 0.5, 2.5),
        ("-1", "3", 0.0, 3.0),
        ("oops", "bad", 0.0, 0.0),
    ],
)
def test_get_rate_pacing_jitter_range_parses_env_values(
    min_raw: str | None,
    max_raw: str | None,
    expected_min: float,
    expected_max: float,
):
    payload: dict[str, str] = {}
    if min_raw is not None:
        payload[EnvVar.RATE_PACING_JITTER_MIN_SECONDS] = min_raw
    if max_raw is not None:
        payload[EnvVar.RATE_PACING_JITTER_MAX_SECONDS] = max_raw
    with patch.dict(os.environ, payload, clear=True):
        assert get_rate_pacing_jitter_min_seconds() == expected_min
        assert get_rate_pacing_jitter_max_seconds() == expected_max


def test_try_n_times_success_first_attempt():
    assert try_n_times(lambda: "success", 3) == "success"


def test_try_n_times_success_after_failures():
    fn, state = _eventually_successful(failures_before_success=2)
    with patch("todoist.utils.time.sleep"):
        result = try_n_times(fn, 5)
    assert result == "success"
    assert state["count"] == 3


def test_try_n_times_all_failures_returns_none():
    call_count = {"count": 0}

    def _always_fail():
        call_count["count"] += 1
        raise RuntimeError("Always fails")

    with patch("todoist.utils.time.sleep"):
        result = try_n_times(_always_fail, 3)
    assert result is None
    assert call_count["count"] == 3


def test_try_n_times_exponential_backoff():
    with patch("todoist.utils.time.sleep") as mock_sleep:
        try_n_times(lambda: (_ for _ in ()).throw(ValueError("Fail")), 4)
    assert [call.args[0] for call in mock_sleep.call_args_list] == [8, 16, 32]


def test_try_n_times_zero_attempts_does_not_call_function():
    called = {"count": 0}

    def _fn():
        called["count"] += 1
        return "ok"

    assert try_n_times(_fn, 0) is None
    assert called["count"] == 0


@pytest.mark.parametrize(
    ("resource_class", "payload"),
    [
        (set, {"item1", "item2", "item3"}),
        (dict, {"key1": "value1", "key2": 42}),
        (list, [1, 2, 3]),
    ],
)
def test_local_storage_save_and_load_roundtrip(tmp_path, resource_class, payload):
    storage = LocalStorage(str(tmp_path / "data.joblib"), resource_class)
    storage.save(payload)
    assert storage.load() == payload


@pytest.mark.parametrize("resource_class, expected_default", [(set, set()), (dict, {}), (list, [])])
def test_local_storage_load_nonexistent_returns_default(tmp_path, resource_class, expected_default):
    storage = LocalStorage(str(tmp_path / "missing.joblib"), resource_class)
    loaded_data = storage.load()
    assert loaded_data == expected_default
    assert isinstance(loaded_data, type(expected_default))


def test_local_storage_corrupted_file_is_recreated(tmp_path):
    file_path = tmp_path / "corrupted.joblib"
    file_path.write_text("This is not valid joblib data", encoding="utf-8")
    storage = LocalStorage(str(file_path), set)
    loaded_data = storage.load()
    assert loaded_data == set()
    assert storage.load() == set()


def test_local_storage_error_on_invalid_save_path(tmp_path):
    invalid_path = tmp_path / "missing_dir" / "nested" / "file.joblib"
    storage = LocalStorage(str(invalid_path), set)
    with pytest.raises(LocalStorageError, match="Failed to save data"):
        storage.save({"data"})


def test_cache_initialization_creates_expected_storages(tmp_path):
    cache = Cache(str(tmp_path))
    expected_files = {
        "activity": "activity.joblib",
        "observer_state": "observer_state.joblib",
        "integration_launches": "integration_launches.joblib",
        "automation_launches": "automation_launches.joblib",
        "processed_gmail_messages": "processed_gmail_messages.joblib",
        "dashboard_state": "dashboard_state.joblib",
        "llm_breakdown_progress": "llm_breakdown_progress.joblib",
        "llm_breakdown_queue": "llm_breakdown_queue.joblib",
        "llm_chat_queue": "llm_chat_queue.joblib",
        "llm_chat_conversations": "llm_chat_conversations.joblib",
    }
    for attr_name, filename in expected_files.items():
        storage = getattr(cache, attr_name)
        assert isinstance(storage, LocalStorage)
        assert storage.path == str(tmp_path / filename)


def test_cache_uses_env_path_by_default(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    with patch.dict(os.environ, {EnvVar.CACHE_DIR: str(tmp_path)}, clear=True):
        cache = Cache()
    assert cache.path == str(tmp_path)


def test_cache_uses_dot_cache_default_when_env_missing(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    with patch.dict(os.environ, {}, clear=True):
        cache = Cache()
    assert Path(cache.path) == (tmp_path / DEFAULT_CACHE_SUBDIR).resolve()


def test_configure_runtime_logging_sets_stderr_and_file_sink(tmp_path, monkeypatch):
    import todoist.utils as utils

    monkeypatch.setattr(utils, "_RUNTIME_LOGGING_SIGNATURE", None)
    log_path = tmp_path / "automation.log"
    with (
        patch("todoist.utils.logger.remove") as mock_remove,
        patch("todoist.utils.logger.add") as mock_add,
    ):
        configure_runtime_logging(str(log_path), level="debug")

    mock_remove.assert_called_once()
    assert mock_add.call_args_list[0].args[0] == sys.stderr
    assert mock_add.call_args_list[0].kwargs["level"] == "DEBUG"
    assert mock_add.call_args_list[1].args[0] == str(log_path.resolve())
    assert mock_add.call_args_list[1].kwargs["level"] == "DEBUG"


def test_configure_runtime_logging_is_idempotent(monkeypatch):
    import todoist.utils as utils

    monkeypatch.setattr(utils, "_RUNTIME_LOGGING_SIGNATURE", None)
    with (
        patch("todoist.utils.logger.remove") as mock_remove,
        patch("todoist.utils.logger.add") as mock_add,
    ):
        configure_runtime_logging(level="info")
        configure_runtime_logging(level="info")

    mock_remove.assert_called_once()
    assert mock_add.call_count == 1


def test_cache_migrates_legacy_runtime_files(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    legacy_activity = tmp_path / "activity.joblib"
    legacy_log = tmp_path / "automation.log"
    LocalStorage(str(legacy_activity), set).save({"event1"})
    legacy_log.write_text("legacy-log", encoding="utf-8")

    with patch.dict(os.environ, {}, clear=True):
        cache = Cache()

    cache_root = Path(cache.path)
    backup_root = tmp_path / MIGRATION_BACKUP_DIRNAME

    assert cache.activity.load() == {"event1"}
    assert (cache_root / "activity.joblib").exists()
    assert (cache_root / "automation.log").exists()
    assert (backup_root / "activity.joblib").exists()
    assert (backup_root / "automation.log").exists()
    assert not legacy_activity.exists()
    assert not legacy_log.exists()


@pytest.mark.parametrize(
    ("storage_attr", "payload"),
    [
        ("activity", {"event1", "event2"}),
        ("integration_launches", {"integration1": 5}),
        ("automation_launches", {"automation1": 2}),
        ("processed_gmail_messages", {"msg1"}),
    ],
)
def test_cache_storage_roundtrip(tmp_path, storage_attr: str, payload):
    cache = Cache(str(tmp_path))
    storage = getattr(cache, storage_attr)
    storage.save(payload)
    assert storage.load() == payload


class ConcreteAnonymizable(Anonymizable):
    """Concrete Anonymizable implementation for tests."""

    def __init__(self):
        super().__init__()
        self.data = "original"

    def _anonymize(self, project_mapping: dict[str, str], label_mapping: dict[str, str]):
        self.data = f"{project_mapping.get('proj1')}::{label_mapping.get('label1')}"


def test_anonymizable_initialization_sets_flag_false():
    assert ConcreteAnonymizable().is_anonymized is False


def test_anonymizable_first_call_applies_anonymization():
    obj = ConcreteAnonymizable()
    obj.anonymize({"proj1": "anon_proj1"}, {"label1": "anon_label1"})
    assert obj.is_anonymized is True
    assert obj.data == "anon_proj1::anon_label1"


def test_anonymizable_is_idempotent():
    obj = ConcreteAnonymizable()
    project_mapping = {"proj1": "anon_proj1"}
    label_mapping = {"label1": "anon_label1"}
    obj.anonymize(project_mapping, label_mapping)
    obj.data = "modified"
    obj.anonymize(project_mapping, label_mapping)
    assert obj.data == "modified"


def test_anonymizable_calls_abstract_method_once():
    obj = ConcreteAnonymizable()
    with patch.object(obj, "_anonymize", wraps=obj._anonymize) as mock_anonymize:
        obj.anonymize({"proj1": "anon_proj1"}, {"label1": "anon_label1"})
    mock_anonymize.assert_called_once_with({"proj1": "anon_proj1"}, {"label1": "anon_label1"})


def test_load_config_with_relative_path():
    with (
        patch("todoist.utils.GlobalHydra") as mock_global_hydra,
        patch("todoist.utils.initialize") as mock_initialize,
        patch("todoist.utils.initialize_config_dir") as mock_initialize_config_dir,
        patch("todoist.utils.compose") as mock_compose,
    ):
        mock_instance = MagicMock()
        mock_global_hydra.instance.return_value = mock_instance
        expected_config = MagicMock()
        mock_compose.return_value = expected_config

        result = load_config("test_config", "../config")

        mock_instance.clear.assert_called_once()
        mock_initialize.assert_called_once_with(config_path="../config")
        mock_initialize_config_dir.assert_not_called()
        mock_compose.assert_called_once_with(config_name="test_config")
        assert result == expected_config


def test_load_config_with_absolute_path():
    absolute_config_dir = str((Path.cwd() / "tmp" / "todoist-config").resolve())

    with (
        patch("todoist.utils.GlobalHydra") as mock_global_hydra,
        patch("todoist.utils.initialize") as mock_initialize,
        patch("todoist.utils.initialize_config_dir") as mock_initialize_config_dir,
        patch("todoist.utils.compose") as mock_compose,
    ):
        mock_instance = MagicMock()
        mock_global_hydra.instance.return_value = mock_instance
        mock_compose.return_value = MagicMock()

        load_config("config", absolute_config_dir)

        mock_instance.clear.assert_called_once()
        mock_initialize.assert_not_called()
        mock_initialize_config_dir.assert_called_once_with(config_dir=absolute_config_dir)


def test_retry_with_backoff_success_first_attempt():
    assert retry_with_backoff(lambda: "success", max_attempts=3) == "success"


def test_retry_with_backoff_success_after_failures():
    fn, state = _eventually_successful(failures_before_success=2)
    with patch("todoist.utils.time.sleep"):
        result = retry_with_backoff(fn, max_attempts=5)
    assert result == "success"
    assert state["count"] == 3


def test_retry_with_backoff_all_failures_returns_none():
    with patch("todoist.utils.time.sleep"):
        result = retry_with_backoff(lambda: (_ for _ in ()).throw(RuntimeError("Always fails")), max_attempts=3)
    assert result is None


def test_retry_with_backoff_uses_gaussian_values_for_sleep():
    with (
        patch("todoist.utils.time.sleep") as mock_sleep,
        patch("todoist.utils.random.gauss", side_effect=[5.5, 12.3, 8.9]) as mock_gauss,
    ):
        retry_with_backoff(
            lambda: (_ for _ in ()).throw(ValueError("Fail")),
            max_attempts=4,
            backoff_mean=10.0,
            backoff_std=3.0,
        )

    assert mock_gauss.call_count == 3
    for call in mock_gauss.call_args_list:
        assert call.args == (10.0, 3.0)
    assert [call.args[0] for call in mock_sleep.call_args_list] == [5.5, 12.3, 8.9]


def test_retry_with_backoff_enforces_minimum_wait_time():
    with (
        patch("todoist.utils.time.sleep") as mock_sleep,
        patch("todoist.utils.random.gauss", side_effect=[-5.0, -2.0, 0.05]),
    ):
        retry_with_backoff(lambda: (_ for _ in ()).throw(ValueError("Fail")), max_attempts=4)

    assert [call.args[0] for call in mock_sleep.call_args_list] == [0.1, 0.1, 0.1]


def test_retry_with_backoff_zero_attempts_does_not_call_function():
    call_count = {"count": 0}

    def _fn():
        call_count["count"] += 1
        return "success"

    assert retry_with_backoff(_fn, max_attempts=0) is None
    assert call_count["count"] == 0


def test_retry_constants_have_positive_values():
    assert RETRY_MAX_ATTEMPTS > 0
    assert RETRY_BACKOFF_MEAN > 0
    assert RETRY_BACKOFF_STD > 0


def test_with_retry_success():
    assert with_retry(lambda: "success", operation_name="test op") == "success"


def test_with_retry_raises_on_failure():
    with patch("todoist.utils.time.sleep"):
        with pytest.raises(MaxRetriesExceeded, match="Failed to execute test operation after 3 retry attempts"):
            with_retry(
                lambda: (_ for _ in ()).throw(RuntimeError("Always fails")),
                operation_name="test operation",
                max_attempts=3,
            )


def test_with_retry_uses_custom_parameters():
    call_count = {"count": 0}

    def eventually_successful():
        call_count["count"] += 1
        if call_count["count"] < 4:
            raise ValueError("Not yet")
        return "success"

    with patch("todoist.utils.time.sleep"):
        result = with_retry(
            eventually_successful,
            operation_name="custom op",
            max_attempts=5,
            backoff_mean=15.0,
            backoff_std=5.0,
        )

    assert result == "success"
    assert call_count["count"] == 4


def test_with_retry_zero_attempts_raises_immediately():
    with pytest.raises(MaxRetriesExceeded, match="after 0 retry attempts"):
        with_retry(lambda: "success", operation_name="zero attempts", max_attempts=0)
