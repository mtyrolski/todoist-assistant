"""
Tests for utility functions in todoist.utils module.
"""
import pytest
import time
import tempfile
import os
from unittest.mock import patch, MagicMock, mock_open
from dataclasses import dataclass
from typing import KeysView
from todoist.utils import MaxRetriesExceeded

from todoist.utils import (
    get_all_fields_of_dataclass,
    safe_instantiate_entry,
    last_n_years_in_weeks,
    get_api_key,
    try_n_times,
    load_config,
    LocalStorage,
    LocalStorageError,
    Cache,
    Anonymizable,
    retry_with_backoff,
    with_retry,
    RETRY_MAX_ATTEMPTS,
    RETRY_BACKOFF_MEAN,
    RETRY_BACKOFF_STD
)


# Test get_all_fields_of_dataclass
@dataclass
class SampleDataclass:
    field1: str
    field2: int
    field3: bool = False


def test_get_all_fields_of_dataclass():
    """Test that get_all_fields_of_dataclass returns all field names."""
    fields = get_all_fields_of_dataclass(SampleDataclass)
    assert isinstance(fields, KeysView)
    field_list = list(fields)
    assert 'field1' in field_list
    assert 'field2' in field_list
    assert 'field3' in field_list
    assert len(field_list) == 3


def test_get_all_fields_of_dataclass_empty():
    """Test get_all_fields_of_dataclass with empty dataclass."""
    @dataclass
    class EmptyDataclass:
        pass
    
    fields = get_all_fields_of_dataclass(EmptyDataclass)
    assert len(list(fields)) == 0


# Test safe_instantiate_entry
@dataclass
class DataclassWithKwargs:
    known_field: str
    another_field: int = 0
    new_api_kwargs: dict | None = None


def test_safe_instantiate_entry_no_unexpected_fields():
    """Test safe_instantiate_entry with only known fields."""
    result = safe_instantiate_entry(
        DataclassWithKwargs,
        known_field="test",
        another_field=42
    )
    assert result.known_field == "test"
    assert result.another_field == 42
    assert result.new_api_kwargs == {}


def test_safe_instantiate_entry_with_unexpected_fields():
    """Test safe_instantiate_entry with unexpected fields."""
    result = safe_instantiate_entry(
        DataclassWithKwargs,
        known_field="test",
        another_field=42,
        unexpected_field="value",
        another_unexpected=123
    )
    assert result.known_field == "test"
    assert result.another_field == 42
    assert result.new_api_kwargs == {
        "unexpected_field": "value",
        "another_unexpected": 123
    }


def test_safe_instantiate_entry_only_unexpected_fields():
    """Test safe_instantiate_entry with only unexpected fields."""
    result = safe_instantiate_entry(
        DataclassWithKwargs,
        known_field="test",
        unexpected1="value1",
        unexpected2="value2"
    )
    assert result.known_field == "test"
    assert result.new_api_kwargs == {
        "unexpected1": "value1",
        "unexpected2": "value2"
    }


def test_safe_instantiate_entry_missing_kwargs_field():
    """Test safe_instantiate_entry raises AssertionError when new_api_kwargs field is missing."""
    @dataclass
    class DataclassWithoutKwargs:
        field1: str
    
    with pytest.raises(AssertionError) as exc_info:
        safe_instantiate_entry(DataclassWithoutKwargs, field1="test", extra="field")
    # The assertion message says "kwargs field is not in..."
    assert "kwargs" in str(exc_info.value).lower()


# Test last_n_years_in_weeks
def test_last_n_years_in_weeks_one_year():
    """Test last_n_years_in_weeks for 1 year."""
    result = last_n_years_in_weeks(1)
    expected = int(365.25 / 7)  # ~52 weeks
    assert result == expected
    assert result == 52


def test_last_n_years_in_weeks_multiple_years():
    """Test last_n_years_in_weeks for multiple years."""
    result = last_n_years_in_weeks(2)
    expected = int(365.25 * 2 / 7)  # ~104 weeks
    assert result == expected
    assert result == 104


def test_last_n_years_in_weeks_zero():
    """Test last_n_years_in_weeks for 0 years."""
    result = last_n_years_in_weeks(0)
    assert result == 0


def test_last_n_years_in_weeks_fractional():
    """Test last_n_years_in_weeks for fractional years (should truncate)."""
    result = last_n_years_in_weeks(5)
    expected = int(365.25 * 5 / 7)
    assert result == expected
    assert result == 260  # int(1826.25 / 7) = int(260.89...) = 260


# Test get_api_key
def test_get_api_key_with_env_variable():
    """Test get_api_key when API_KEY environment variable is set."""
    with patch.dict(os.environ, {'API_KEY': 'test_api_key_12345'}):
        result = get_api_key()
        assert result == 'test_api_key_12345'


def test_get_api_key_without_env_variable():
    """Test get_api_key when API_KEY environment variable is not set."""
    with patch.dict(os.environ, {}, clear=True):
        result = get_api_key()
        assert result == ""


def test_get_api_key_empty_env_variable():
    """Test get_api_key when API_KEY environment variable is empty."""
    with patch.dict(os.environ, {'API_KEY': ''}):
        result = get_api_key()
        assert result == ""


# Test try_n_times
def test_try_n_times_success_first_attempt():
    """Test try_n_times when function succeeds on first attempt."""
    def successful_function():
        return "success"
    
    result = try_n_times(successful_function, 3)
    assert result == "success"


def test_try_n_times_success_after_failures():
    """Test try_n_times when function succeeds after some failures."""
    call_count = {'count': 0}
    
    def eventually_successful():
        call_count['count'] += 1
        if call_count['count'] < 3:
            raise ValueError("Not yet")
        return "success"
    
    with patch('todoist.utils.time.sleep'):  # Mock sleep to speed up test
        result = try_n_times(eventually_successful, 5)
    
    assert result == "success"
    assert call_count['count'] == 3


def test_try_n_times_all_failures():
    """Test try_n_times when function fails all attempts."""
    def always_fails():
        raise RuntimeError("Always fails")
    
    with patch('todoist.utils.time.sleep'):  # Mock sleep to speed up test
        result = try_n_times(always_fails, 3)
    
    assert result is None


def test_try_n_times_exponential_backoff():
    """Test try_n_times uses exponential backoff between retries."""
    def always_fails():
        raise ValueError("Fail")
    
    with patch('todoist.utils.time.sleep') as mock_sleep:
        try_n_times(always_fails, 4)
        
        # Verify exponential backoff: 2^(0+3)=8, 2^(1+3)=16, 2^(2+3)=32
        calls = mock_sleep.call_args_list
        assert len(calls) == 3  # n-1 sleeps for n attempts
        assert calls[0][0][0] == 8
        assert calls[1][0][0] == 16
        assert calls[2][0][0] == 32


def test_try_n_times_single_attempt():
    """Test try_n_times with only 1 attempt (no retries)."""
    def fails_once():
        raise ValueError("Fail")
    
    with patch('todoist.utils.time.sleep') as mock_sleep:
        result = try_n_times(fails_once, 1)
    
    assert result is None
    mock_sleep.assert_not_called()  # No sleep for single attempt


def test_try_n_times_returns_correct_value():
    """Test try_n_times returns the actual function return value."""
    def returns_dict():
        return {"key": "value", "number": 42}
    
    result = try_n_times(returns_dict, 3)
    assert result == {"key": "value", "number": 42}


# Test LocalStorage class
def test_local_storage_save_and_load():
    """Test LocalStorage save and load operations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = os.path.join(tmpdir, "test_data.joblib")
        storage = LocalStorage(filepath, set)
        
        # Save data
        test_data = {"item1", "item2", "item3"}
        storage.save(test_data)
        
        # Load data
        loaded_data = storage.load()
        assert loaded_data == test_data


def test_local_storage_load_nonexistent_file():
    """Test LocalStorage load returns default value when file doesn't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = os.path.join(tmpdir, "nonexistent.joblib")
        storage = LocalStorage(filepath, set)
        
        # Load should return empty set (default value)
        loaded_data = storage.load()
        assert loaded_data == set()
        assert isinstance(loaded_data, set)


def test_local_storage_load_with_dict_default():
    """Test LocalStorage load with dict as default resource class."""
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = os.path.join(tmpdir, "test_dict.joblib")
        storage = LocalStorage(filepath, dict)
        
        # Load non-existent file should return empty dict
        loaded_data = storage.load()
        assert loaded_data == {}
        assert isinstance(loaded_data, dict)


def test_local_storage_save_and_load_dict():
    """Test LocalStorage with dictionary data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = os.path.join(tmpdir, "test_dict.joblib")
        storage = LocalStorage(filepath, dict)
        
        # Save dict
        test_dict = {"key1": "value1", "key2": 42, "key3": [1, 2, 3]}
        storage.save(test_dict)
        
        # Load dict
        loaded_dict = storage.load()
        assert loaded_dict == test_dict


def test_local_storage_error_on_corrupted_file():
    """Test LocalStorage raises LocalStorageError on corrupted file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = os.path.join(tmpdir, "corrupted.joblib")
        
        # Create a corrupted file
        with open(filepath, 'w') as f:
            f.write("This is not valid joblib data")
        
        storage = LocalStorage(filepath, set)
        
        with pytest.raises(LocalStorageError) as exc_info:
            storage.load()
        
        assert "Failed to load data" in str(exc_info.value)
        assert filepath in str(exc_info.value)


def test_local_storage_error_on_invalid_path():
    """Test LocalStorage raises LocalStorageError on invalid save path."""
    # Use an invalid path (directory that doesn't exist and can't be created)
    invalid_path = "/nonexistent_directory/subdir/file.joblib"
    storage = LocalStorage(invalid_path, set)
    
    with pytest.raises(LocalStorageError) as exc_info:
        storage.save({"data"})
    
    assert "Failed to save data" in str(exc_info.value)


# Test Cache class
def test_cache_initialization():
    """Test Cache class initialization creates all storage instances."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = Cache(tmpdir)
        
        assert isinstance(cache.activity, LocalStorage)
        assert isinstance(cache.integration_launches, LocalStorage)
        assert isinstance(cache.automation_launches, LocalStorage)
        assert isinstance(cache.processed_gmail_messages, LocalStorage)
        
        # Verify paths
        assert cache.activity.path == os.path.join(tmpdir, 'activity.joblib')
        assert cache.integration_launches.path == os.path.join(tmpdir, 'integration_launches.joblib')
        assert cache.automation_launches.path == os.path.join(tmpdir, 'automation_launches.joblib')
        assert cache.processed_gmail_messages.path == os.path.join(tmpdir, 'processed_gmail_messages.joblib')


def test_cache_default_path():
    """Test Cache uses default path when not specified."""
    cache = Cache()
    assert cache.path == './'


def test_cache_activity_storage():
    """Test Cache activity storage can save and load."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = Cache(tmpdir)
        
        # Save activity data
        activity_data = {"event1", "event2", "event3"}
        cache.activity.save(activity_data)
        
        # Load activity data
        loaded = cache.activity.load()
        assert loaded == activity_data


def test_cache_integration_launches_storage():
    """Test Cache integration_launches storage can save and load."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = Cache(tmpdir)
        
        # Save integration launches data
        launches_data = {"integration1": 5, "integration2": 10}
        cache.integration_launches.save(launches_data)
        
        # Load integration launches data
        loaded = cache.integration_launches.load()
        assert loaded == launches_data


# Test Anonymizable class
class ConcreteAnonymizable(Anonymizable):
    """Concrete implementation of Anonymizable for testing."""
    def __init__(self):
        super().__init__()
        self.data = "original"
    
    def _anonymize(self, project_mapping: dict[str, str], label_mapping: dict[str, str]):
        self.data = "anonymized"


def test_anonymizable_initialization():
    """Test Anonymizable initialization sets is_anonymized to False."""
    obj = ConcreteAnonymizable()
    assert obj.is_anonymized is False


def test_anonymizable_anonymize_first_time():
    """Test Anonymizable anonymize method works on first call."""
    obj = ConcreteAnonymizable()
    
    project_mapping = {"proj1": "anon_proj1"}
    label_mapping = {"label1": "anon_label1"}
    
    obj.anonymize(project_mapping, label_mapping)
    
    assert obj.is_anonymized is True
    assert obj.data == "anonymized"


def test_anonymizable_anonymize_idempotent():
    """Test Anonymizable anonymize is idempotent (won't re-anonymize)."""
    obj = ConcreteAnonymizable()
    
    project_mapping = {"proj1": "anon_proj1"}
    label_mapping = {"label1": "anon_label1"}
    
    # First anonymization
    obj.anonymize(project_mapping, label_mapping)
    assert obj.data == "anonymized"
    
    # Modify data to test idempotency
    obj.data = "modified"
    
    # Second anonymization should skip
    obj.anonymize(project_mapping, label_mapping)
    assert obj.data == "modified"  # Should not be re-anonymized


def test_anonymizable_calls_abstract_method():
    """Test that Anonymizable calls the _anonymize abstract method."""
    obj = ConcreteAnonymizable()
    
    with patch.object(obj, '_anonymize', wraps=obj._anonymize) as mock_anonymize:
        project_mapping = {"proj1": "anon_proj1"}
        label_mapping = {"label1": "anon_label1"}
        
        obj.anonymize(project_mapping, label_mapping)
        
        mock_anonymize.assert_called_once_with(project_mapping, label_mapping)


# Test load_config
def test_load_config_basic():
    """Test load_config loads configuration correctly."""
    # This test requires actual config files to exist
    # We'll test with mocked Hydra components
    with patch('todoist.utils.GlobalHydra') as mock_global_hydra, \
         patch('todoist.utils.initialize') as mock_initialize, \
         patch('todoist.utils.compose') as mock_compose:
        
        # Setup mocks
        mock_instance = MagicMock()
        mock_global_hydra.instance.return_value = mock_instance
        mock_config = MagicMock()
        mock_compose.return_value = mock_config
        
        # Call load_config
        result = load_config("test_config", "../config")
        
        # Verify calls
        mock_instance.clear.assert_called_once()
        mock_initialize.assert_called_once_with(config_path="../config")
        mock_compose.assert_called_once_with(config_name="test_config")
        assert result == mock_config


def test_load_config_clears_global_hydra():
    """Test load_config clears GlobalHydra before initializing."""
    with patch('todoist.utils.GlobalHydra') as mock_global_hydra, \
         patch('todoist.utils.initialize'), \
         patch('todoist.utils.compose') as mock_compose:
        
        mock_instance = MagicMock()
        mock_global_hydra.instance.return_value = mock_instance
        mock_compose.return_value = MagicMock()
        
        load_config("config", "path")
        
        # Verify clear is called before other operations
        mock_instance.clear.assert_called_once()


# Test retry_with_backoff
def test_retry_with_backoff_success_first_attempt():
    """Test retry_with_backoff when function succeeds on first attempt."""
    def successful_function():
        return "success"
    
    result = retry_with_backoff(successful_function, max_attempts=3)
    assert result == "success"


def test_retry_with_backoff_success_after_failures():
    """Test retry_with_backoff when function succeeds after some failures."""
    call_count = {'count': 0}
    
    def eventually_successful():
        call_count['count'] += 1
        if call_count['count'] < 3:
            raise ValueError("Not yet")
        return "success"
    
    with patch('todoist.utils.time.sleep'):  # Mock sleep to speed up test
        result = retry_with_backoff(eventually_successful, max_attempts=5)
    
    assert result == "success"
    assert call_count['count'] == 3


def test_retry_with_backoff_all_failures():
    """Test retry_with_backoff when function fails all attempts."""
    def always_fails():
        raise RuntimeError("Always fails")
    
    with patch('todoist.utils.time.sleep'):  # Mock sleep to speed up test
        result = retry_with_backoff(always_fails, max_attempts=3)
    
    assert result is None


def test_retry_with_backoff_uses_gaussian_backoff():
    """Test retry_with_backoff uses Gaussian backoff between retries."""
    def always_fails():
        raise ValueError("Fail")
    
    with patch('todoist.utils.time.sleep') as mock_sleep, \
         patch('todoist.utils.random.gauss') as mock_gauss:
        # Mock Gaussian to return predictable values
        mock_gauss.side_effect = [5.5, 12.3, 8.9]
        
        retry_with_backoff(always_fails, max_attempts=4, backoff_mean=10.0, backoff_std=3.0)
        
        # Verify Gaussian was called with correct parameters
        assert mock_gauss.call_count == 3  # n-1 sleeps for n attempts
        for call in mock_gauss.call_args_list:
            assert call[0] == (10.0, 3.0)
        
        # Verify sleep was called with Gaussian values
        assert mock_sleep.call_count == 3
        assert mock_sleep.call_args_list[0][0][0] == 5.5
        assert mock_sleep.call_args_list[1][0][0] == 12.3
        assert mock_sleep.call_args_list[2][0][0] == 8.9


def test_retry_with_backoff_minimum_wait_time():
    """Test retry_with_backoff enforces minimum wait time of 0.1s."""
    def always_fails():
        raise ValueError("Fail")
    
    with patch('todoist.utils.time.sleep') as mock_sleep, \
         patch('todoist.utils.random.gauss') as mock_gauss:
        # Mock Gaussian to return negative values
        mock_gauss.side_effect = [-5.0, -2.0, 0.05]
        
        retry_with_backoff(always_fails, max_attempts=4)
        
        # Verify minimum wait time is enforced
        for call in mock_sleep.call_args_list:
            assert call[0][0] >= 0.1


def test_retry_with_backoff_constants():
    """Test that retry constants are defined and have reasonable values."""
    assert RETRY_MAX_ATTEMPTS > 0
    assert RETRY_BACKOFF_MEAN > 0
    assert RETRY_BACKOFF_STD > 0


# Test with_retry
def test_with_retry_success():
    """Test with_retry succeeds and returns result."""
    def successful_function():
        return "success"
    
    result = with_retry(successful_function, operation_name="test op")
    assert result == "success"


def test_with_retry_raises_on_failure():
    """Test with_retry raises RuntimeError when all attempts fail."""
    def always_fails():
        raise RuntimeError("Always fails")
    
    with patch('todoist.utils.time.sleep'):  # Mock sleep to speed up test
        with pytest.raises(MaxRetriesExceeded) as exc_info:
            with_retry(always_fails, operation_name="test operation", max_attempts=3)
        assert "Failed to execute test operation after 3 retry attempts" in str(exc_info.value)


def test_with_retry_uses_custom_parameters():
    """Test with_retry passes custom parameters to retry_with_backoff."""
    call_count = {'count': 0}
    
    def eventually_successful():
        call_count['count'] += 1
        if call_count['count'] < 4:
            raise ValueError("Not yet")
        return "success"
    
    with patch('todoist.utils.time.sleep'):
        result = with_retry(
            eventually_successful,
            operation_name="custom op",
            max_attempts=5,
            backoff_mean=15.0,
            backoff_std=5.0
        )
    
    assert result == "success"
    assert call_count['count'] == 4
