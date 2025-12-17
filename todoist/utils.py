from abc import ABC, abstractmethod
import time
import random
import os
from lzma import LZMAError
from os import getenv
from os.path import exists, join
from pickle import HIGHEST_PROTOCOL, UnpicklingError
from typing import Any, Callable, KeysView, Type, TypeVar, cast
from zlib import error as ZlibError

from hydra import compose, initialize, initialize_config_dir
from hydra.core.global_hydra import GlobalHydra
from joblib import dump, load
from loguru import logger
from omegaconf import DictConfig

T = TypeVar('T', set, dict)
LOCAL_STORAGE_EXCEPTIONS = (UnpicklingError, EOFError, ZlibError, LZMAError, FileNotFoundError, ValueError, TypeError,
                            OSError, ImportError, AttributeError, ModuleNotFoundError, KeyError)


def get_all_fields_of_dataclass(cls: Type[Any]) -> KeysView[str]:
    """
    Get all fields of a dataclass class.
    """
    return cls.__dataclass_fields__.keys()


def safe_instantiate_entry(cls: Type[Any], **entry_kwargs):
    """Safely instantiates a class by writing unexpected (i.e now in todoist api) field to kwargs parameter"""
    class_fields = get_all_fields_of_dataclass(cls)
    unexpected_fields = set(entry_kwargs.keys()) - set(class_fields)

    assert 'new_api_kwargs' in class_fields, f"kwargs field is not in {cls.__name__} class"

    # write unexpected fields to kwargs
    filtered_kwargs = {k: v for k, v in entry_kwargs.items() if k in class_fields}
    unexpected_kwargs = {k: v for k, v in entry_kwargs.items() if k in unexpected_fields}
    return cls(**filtered_kwargs, new_api_kwargs=unexpected_kwargs)


class LocalStorageError(Exception):
    """
    Custom exception for LocalStorage-related errors.
    Logs the error message when the exception is instantiated.
    """
    def __init__(self, message: str):
        super().__init__(message)
        logger.error(f"LocalStorageError: {message}")


class LocalStorage:
    def __init__(self, path: str, resource_class: Callable[[], T]) -> None:
        self.path = path
        self.resource_class = resource_class

    def load(self) -> T:
        try:
            if exists(self.path):
                return cast(T, load(self.path))
            default_value = self.resource_class()
            return cast(T, default_value)
        except LOCAL_STORAGE_EXCEPTIONS as e:
            raise LocalStorageError(f"Failed to load data from {self.path}: {type(e)}. {e}") from e

    def save(self, data: T) -> None:
        try:
            dump(data, self.path, protocol=HIGHEST_PROTOCOL)
        except LOCAL_STORAGE_EXCEPTIONS as e:
            raise LocalStorageError(f"Failed to save data to {self.path}: {e}") from e


class Cache:
    def __init__(self, path: str = './'):
        self.path = path
        self.activity = LocalStorage(join(self.path, 'activity.joblib'), set)
        self.integration_launches = LocalStorage(join(self.path, 'integration_launches.joblib'), dict)
        self.automation_launches = LocalStorage(join(self.path, 'automation_launches.joblib'), dict)
        self.processed_gmail_messages = LocalStorage(join(self.path, 'processed_gmail_messages.joblib'), set)


class Anonymizable(ABC):
    def __init__(self):
        super().__init__()
        logger.debug(f'Initializing {self.__class__.__name__}... somehow anonimizable')
        self.is_anonymized = False

    @abstractmethod
    def _anonymize(self, project_mapping: dict[str, str], label_mapping: dict[str, str]):
        pass

    def anonymize(self, project_mapping: dict[str, str], label_mapping: dict[str, str]):
        """
        Anonymizes project and label names in the database.
        """
        if not self.is_anonymized:
            logger.warning('Anonymizing data...')
            self._anonymize(project_mapping, label_mapping)
            self.is_anonymized = True
        else:
            logger.debug("Already anonymized. Skipping.")


def last_n_years_in_weeks(n_years: int) -> int:
    count_f: float = 365.25 * n_years / 7
    return int(count_f)


def get_api_key() -> str:
    """Assuming that ENV variables are set"""
    return getenv('API_KEY') or ""


U = TypeVar('U')

# Retry configuration constants
RETRY_MAX_ATTEMPTS = 3
RETRY_BACKOFF_MEAN = 10.0  # seconds
RETRY_BACKOFF_STD = 3.0    # seconds

# Rate limit configuration constants
DEFAULT_MAX_REQUESTS_PER_MINUTE = 45
RATE_LIMIT_WINDOW_SECONDS = 60.0


def try_n_times(fn: Callable[[], U], n) -> U | None:
    """
    Try to run a function n times and return the result if successful.
    If the function fails, log the exception and after n trials, return None.
    Waits exponentially longer after each failure (1s, 2s, 4s, ...).
    """
    # pylint: disable=broad-exception-caught
    for attempt in range(n):
        try:
            return fn()
        except Exception as e:  # pragma: no cover - logged and retried
            logger.error(f"Exception {e} occurred on attempt {attempt + 1}")
            if attempt < n - 1:
                wait_time = 2**(attempt + 3)
                logger.debug(f"Waiting {wait_time} seconds before retrying...")
                time.sleep(wait_time)
    return None


def retry_with_backoff(fn: Callable[[], U], max_attempts: int = RETRY_MAX_ATTEMPTS,
                       backoff_mean: float = RETRY_BACKOFF_MEAN,
                       backoff_std: float = RETRY_BACKOFF_STD) -> U | None:
    """
    Try to run a function with Gaussian backoff retry logic.

    Args:
        fn: Function to retry (should take no arguments)
        max_attempts: Maximum number of retry attempts
        backoff_mean: Mean wait time in seconds for Gaussian backoff
        backoff_std: Standard deviation for Gaussian backoff

    Returns:
        Result of the function if successful, None if all attempts fail
    """
    # pylint: disable=broad-exception-caught
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as e:  # pragma: no cover - logged and retried
            logger.error(f"Exception {e} occurred on attempt {attempt + 1}/{max_attempts}")
            if attempt < max_attempts - 1:
                # Gaussian backoff with floor of 0.1s to ensure positive wait time
                wait_time = max(0.1, random.gauss(backoff_mean, backoff_std))
                logger.debug(f"Waiting {wait_time:.2f} seconds before retrying...")
                time.sleep(wait_time)
    return None

class MaxRetriesExceeded(Exception):
    """Custom exception to indicate that maximum retry attempts have been exceeded."""
    pass

def with_retry(fn: Callable[[], U], operation_name: str = "operation",
               max_attempts: int = RETRY_MAX_ATTEMPTS,
               backoff_mean: float = RETRY_BACKOFF_MEAN,
               backoff_std: float = RETRY_BACKOFF_STD) -> U:
    """
    Wrapper that executes a function with retry logic and raises exception on failure.

    Args:
        fn: Function to execute with retry
        operation_name: Name of operation for error messages
        max_attempts: Maximum number of retry attempts
        backoff_mean: Mean wait time in seconds for Gaussian backoff
        backoff_std: Standard deviation for Gaussian backoff

    Returns:
        Result of the function

    Raises:
        RuntimeError: If all retry attempts fail
    """
    result = retry_with_backoff(fn, max_attempts, backoff_mean, backoff_std)
    if result is None:
        raise MaxRetriesExceeded(f"Failed to execute {operation_name} after {max_attempts} retry attempts")
    return result


def load_config(config_name: str, config_path: str) -> DictConfig:
    GlobalHydra.instance().clear()
    if os.path.isabs(config_path):
        initialize_config_dir(config_dir=config_path)
    else:
        initialize(config_path=config_path)
    config: DictConfig = compose(config_name=config_name)
    return config


TODOIST_COLOR_NAME_TO_RGB: dict[str, str] = {
    'berry_red': '#B8255F',
    'red': '#DC4C3E',
    'orange': '#C77100',
    'yellow': '#B29104',
    'olive_green': '#949C31',
    'lime_green': '#65A33A',
    'green': '#369307',
    'mint_green': '#42A393',
    'teal': '#148FAD',
    'sky_blue': '#319DC0',
    'light_blue': '#6988A4',
    'blue': '#4180FF',
    'grape': '#692EC2',
    'violet': '#CA3FEE',
    'lavender': '#A4698C',
    'magenta': '#E05095',
    'salmon': '#C9766F',
    'charcoal': '#808080',
    'grey': '#999999',
    'taupe': '#8F7A69'
}
