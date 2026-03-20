from abc import ABC, abstractmethod
from dataclasses import MISSING
import time
import random
import os
import shutil
import sys
from lzma import LZMAError
from os import getenv
from os.path import exists, join
from pathlib import Path
from pickle import HIGHEST_PROTOCOL, UnpicklingError
from typing import Any, Callable, Generic, KeysView, Type, TypeVar, cast
from zlib import error as ZlibError

from hydra import compose, initialize, initialize_config_dir
from hydra.core.global_hydra import GlobalHydra
from joblib import dump, load
from loguru import logger
from omegaconf import DictConfig

from todoist.env import EnvVar
T = TypeVar('T')
LOCAL_STORAGE_EXCEPTIONS = (UnpicklingError, EOFError, ZlibError, LZMAError, FileNotFoundError, ValueError, TypeError,
                            OSError, ImportError, AttributeError, ModuleNotFoundError, KeyError)
DEFAULT_CACHE_SUBDIR = Path(".cache") / "todoist-assistant"
MIGRATION_BACKUP_DIRNAME = ".cache-migration-backup"
MIGRATION_BACKUP_REMOVAL_VERSION = "v0.3.0"
RUNTIME_CACHE_FILENAMES: tuple[str, ...] = (
    "activity.joblib",
    "observer_state.joblib",
    "integration_launches.joblib",
    "automation_launches.joblib",
    "habit_tracker_posts.joblib",
    "processed_gmail_messages.joblib",
    "dashboard_state.joblib",
    "llm_breakdown_progress.joblib",
    "llm_breakdown_queue.joblib",
    "llm_chat_queue.joblib",
    "llm_chat_conversations.joblib",
)
RUNTIME_LOG_FILENAMES: tuple[str, ...] = ("automation.log",)
RUNTIME_MIGRATABLE_FILENAMES: tuple[str, ...] = RUNTIME_CACHE_FILENAMES + RUNTIME_LOG_FILENAMES
_MIGRATION_WARNING_LOGGED = False
_MIGRATED_CACHE_DIRS: set[str] = set()
_MISSING_REQUIRED_FIELD_WARNINGS: set[tuple[str, str]] = set()
_RUNTIME_LOGGING_SIGNATURE: tuple[str | None, str] | None = None
DEFAULT_LOG_LEVEL = "INFO"
VALID_LOG_LEVELS = frozenset({"TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"})

TqdmProgressCallback = Callable[[str, int, int, str | None], None]
_TQDM_PROGRESS_CALLBACK: TqdmProgressCallback | None = None


def set_tqdm_progress_callback(callback: TqdmProgressCallback | None) -> None:
    global _TQDM_PROGRESS_CALLBACK
    _TQDM_PROGRESS_CALLBACK = callback


def get_tqdm_progress_callback() -> TqdmProgressCallback | None:
    return _TQDM_PROGRESS_CALLBACK


def report_tqdm_progress(desc: str, current: int, total: int, unit: str | None = None) -> None:
    callback = _TQDM_PROGRESS_CALLBACK
    if callback is None:
        return
    try:
        callback(desc, current, total, unit)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug(f"Progress callback failed: {exc}")


def resolve_cache_dir(path: str | None = None) -> str:
    if path:
        return str(Path(path).expanduser().resolve())

    env_path = getenv(str(EnvVar.CACHE_DIR))
    if env_path:
        return str(Path(env_path).expanduser().resolve())

    return str((Path.cwd() / DEFAULT_CACHE_SUBDIR).resolve())


def runtime_file_path(filename: str, cache_dir: str | None = None) -> str:
    cache_root = Path(resolve_cache_dir(cache_dir))
    return str(cache_root / filename)


def automation_log_path(cache_dir: str | None = None) -> str:
    resolved_cache_dir = resolve_cache_dir(cache_dir)
    Path(resolved_cache_dir).mkdir(parents=True, exist_ok=True)
    migrate_legacy_runtime_files(resolved_cache_dir)
    return runtime_file_path("automation.log", cache_dir=resolved_cache_dir)


def get_log_level(default: str = DEFAULT_LOG_LEVEL) -> str:
    raw = getenv(str(EnvVar.LOG_LEVEL), default)
    normalized = str(raw).strip().upper() if raw is not None else default
    if normalized in VALID_LOG_LEVELS:
        return normalized

    logger.warning(
        f"Invalid {EnvVar.LOG_LEVEL} value '{raw}'. Falling back to {default.upper()}."
    )
    return default.upper()


def configure_runtime_logging(log_path: str | None = None, level: str | None = None) -> None:
    global _RUNTIME_LOGGING_SIGNATURE

    resolved_level = get_log_level(level or DEFAULT_LOG_LEVEL)
    resolved_log_path = str(Path(log_path).expanduser().resolve()) if log_path else None
    signature = (resolved_log_path, resolved_level)
    if _RUNTIME_LOGGING_SIGNATURE == signature:
        return

    logger.remove()
    logger.add(sys.stderr, level=resolved_level)
    if resolved_log_path is not None:
        Path(resolved_log_path).parent.mkdir(parents=True, exist_ok=True)
        logger.add(resolved_log_path, rotation="500 MB", level=resolved_level)
    _RUNTIME_LOGGING_SIGNATURE = signature


def _migration_backup_path(legacy_root: Path, filename: str) -> Path:
    backup_dir = legacy_root / MIGRATION_BACKUP_DIRNAME
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / filename
    if not backup_path.exists():
        return backup_path

    timestamp = int(time.time())
    return backup_dir / f"{filename}.{timestamp}.bak"


def _legacy_cache_roots(cache_root: Path) -> list[Path]:
    candidates: list[Path] = []
    data_dir = getenv(str(EnvVar.DATA_DIR))
    if data_dir:
        candidates.append(Path(data_dir).expanduser().resolve())
    candidates.append(Path.cwd().resolve())

    roots: list[Path] = []
    for candidate in candidates:
        if candidate == cache_root:
            continue
        if candidate in roots:
            continue
        roots.append(candidate)
    return roots


def migrate_legacy_runtime_files(cache_dir: str | None = None) -> None:
    global _MIGRATION_WARNING_LOGGED
    cache_root = Path(resolve_cache_dir(cache_dir))
    cache_root.mkdir(parents=True, exist_ok=True)

    cache_root_key = str(cache_root)
    if cache_root_key in _MIGRATED_CACHE_DIRS:
        return
    _MIGRATED_CACHE_DIRS.add(cache_root_key)

    for legacy_root in _legacy_cache_roots(cache_root):
        for filename in RUNTIME_MIGRATABLE_FILENAMES:
            legacy_path = legacy_root / filename
            if not legacy_path.exists() or not legacy_path.is_file():
                continue

            try:
                target_path = cache_root / filename
                copied = False
                if not target_path.exists():
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(legacy_path, target_path)
                    copied = True

                backup_path = _migration_backup_path(legacy_root, filename)
                shutil.move(str(legacy_path), str(backup_path))

                if copied:
                    logger.warning(
                        f"Migrated legacy runtime file '{legacy_path}' -> '{target_path}' "
                        f"(backup: '{backup_path}')"
                    )
                else:
                    logger.warning(
                        f"Found legacy runtime file '{legacy_path}' with existing target '{target_path}'. "
                        f"Skipped copy to avoid overwrite and moved legacy file to backup '{backup_path}'"
                    )

                if not _MIGRATION_WARNING_LOGGED:
                    logger.warning(
                        f"Legacy cache migration backups are temporary and will be removed in "
                        f"{MIGRATION_BACKUP_REMOVAL_VERSION}."
                    )
                    _MIGRATION_WARNING_LOGGED = True
            except OSError as exc:
                logger.warning(
                    f"Failed to migrate legacy runtime file '{legacy_path}' into cache "
                    f"'{cache_root}': {exc}"
                )


def get_all_fields_of_dataclass(cls: Type[Any]) -> KeysView[str]:
    """
    Get all fields of a dataclass class.
    """
    return cls.__dataclass_fields__.keys()


def safe_instantiate_entry(cls: Type[Any], **entry_kwargs):
    """Safely instantiates a class by writing unexpected (i.e now in todoist api) field to kwargs parameter"""
    # pylint: disable=global-statement
    global _MISSING_REQUIRED_FIELD_WARNINGS
    class_fields = get_all_fields_of_dataclass(cls)
    class_field_set = set(class_fields)
    normalized_kwargs = dict(entry_kwargs)
    missing_required_fields: list[str] = []

    if "access" in class_field_set and "access" in normalized_kwargs:
        access_value = normalized_kwargs["access"]
        if isinstance(access_value, str):
            normalized_kwargs["access"] = {"visibility": access_value}

    if "day_order" in class_field_set and "day_order" in normalized_kwargs:
        day_order_value = normalized_kwargs["day_order"]
        if isinstance(day_order_value, str):
            stripped_value = day_order_value.strip()
            if stripped_value == "":
                normalized_kwargs["day_order"] = None
            else:
                try:
                    normalized_kwargs["day_order"] = int(stripped_value)
                except ValueError:
                    normalized_kwargs["day_order"] = None

    # Keep dataclass instantiation resilient if API omits some required fields.
    for field_name, field_def in cls.__dataclass_fields__.items():
        if field_name == "new_api_kwargs" or field_name in normalized_kwargs:
            continue
        if field_def.default is MISSING and field_def.default_factory is MISSING:
            normalized_kwargs[field_name] = None
            missing_required_fields.append(field_name)

    if missing_required_fields:
        for field_name in missing_required_fields:
            warning_key = (cls.__name__, field_name)
            if warning_key in _MISSING_REQUIRED_FIELD_WARNINGS:
                continue
            logger.warning(
                f"{cls.__name__}: missing required field '{field_name}' in API payload; "
                "defaulting to None for compatibility."
            )
            _MISSING_REQUIRED_FIELD_WARNINGS.add(warning_key)

    unexpected_fields = set(normalized_kwargs.keys()) - class_field_set

    assert 'new_api_kwargs' in class_fields, f"kwargs field is not in {cls.__name__} class"

    # write unexpected fields to kwargs
    filtered_kwargs = {k: v for k, v in normalized_kwargs.items() if k in class_fields}
    unexpected_kwargs = {k: v for k, v in normalized_kwargs.items() if k in unexpected_fields}
    return cls(**filtered_kwargs, new_api_kwargs=unexpected_kwargs)


class LocalStorageError(Exception):
    """
    Custom exception for LocalStorage-related errors.
    Logs the error message when the exception is instantiated.
    """
    def __init__(self, message: str):
        super().__init__(message)
        logger.error(f"LocalStorageError: {message}")


class LocalStorage(Generic[T]):
    def __init__(self, path: str, resource_class: Callable[[], T]) -> None:
        self.path = path
        self.resource_class = resource_class

    def _default_value(self) -> T:
        return cast(T, self.resource_class())

    def _recreate_after_load_failure(self) -> T:
        default_value = self._default_value()
        path_obj = Path(self.path)
        try:
            path_obj.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning(f"Failed to remove corrupted cache file {self.path}: {exc}")
        try:
            self.save(default_value)
        except LocalStorageError as exc:
            logger.error(f"Failed to recreate cache file {self.path}: {exc}")
        return default_value

    def load(self) -> T:
        if not exists(self.path):
            return self._default_value()

        try:
            return cast(T, load(self.path))
        except LOCAL_STORAGE_EXCEPTIONS as exc:
            logger.warning(
                f"Failed to load data from {self.path}: {type(exc).__name__}: {exc}. "
                "Removing and recreating cache."
            )
            return self._recreate_after_load_failure()

    def save(self, data: T) -> None:
        try:
            dump(data, self.path, protocol=HIGHEST_PROTOCOL)
        except LOCAL_STORAGE_EXCEPTIONS as e:
            raise LocalStorageError(f"Failed to save data to {self.path}: {e}") from e


class Cache:
    def __init__(self, path: str | None = None):
        explicit_path = path is not None
        self.path = resolve_cache_dir(path)
        if not explicit_path:
            migrate_legacy_runtime_files(self.path)
        Path(self.path).mkdir(parents=True, exist_ok=True)
        self.activity = LocalStorage(join(self.path, 'activity.joblib'), set)
        self.observer_state = LocalStorage(join(self.path, 'observer_state.joblib'), dict)
        self.integration_launches = LocalStorage(join(self.path, 'integration_launches.joblib'), dict)
        self.automation_launches = LocalStorage(join(self.path, 'automation_launches.joblib'), dict)
        self.habit_tracker_posts = LocalStorage(join(self.path, 'habit_tracker_posts.joblib'), dict)
        self.processed_gmail_messages = LocalStorage(join(self.path, 'processed_gmail_messages.joblib'), set)
        self.dashboard_state = LocalStorage(join(self.path, 'dashboard_state.joblib'), dict)
        self.llm_breakdown_progress = LocalStorage(join(self.path, 'llm_breakdown_progress.joblib'), dict)
        self.llm_breakdown_queue = LocalStorage(join(self.path, 'llm_breakdown_queue.joblib'), dict)
        self.llm_chat_queue = LocalStorage(join(self.path, 'llm_chat_queue.joblib'), list)
        self.llm_chat_conversations = LocalStorage(join(self.path, 'llm_chat_conversations.joblib'), list)


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
RETRY_BACKOFF_MEAN = 10.0  # seconds (conservative default to avoid burst retries)
RETRY_BACKOFF_STD = 3.0  # seconds

# Rate limit configuration constants
DEFAULT_MAX_REQUESTS_PER_MINUTE = 45
RATE_LIMIT_WINDOW_SECONDS = 60.0

# Concurrency configuration constants
DEFAULT_MAX_CONCURRENT_REQUESTS = 4


def get_max_concurrent_requests() -> int:
    """
    Returns the max number of concurrent Todoist API requests used by thread pools.
    Override with EnvVar.MAX_CONCURRENT_REQUESTS env var.
    """
    raw = getenv(str(EnvVar.MAX_CONCURRENT_REQUESTS))
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            logger.warning(f"Invalid {EnvVar.MAX_CONCURRENT_REQUESTS} value: {raw}")
    return DEFAULT_MAX_CONCURRENT_REQUESTS


def get_max_requests_per_minute() -> int:
    """
    Returns the Todoist API client requests-per-minute throttle.
    Override with EnvVar.MAX_REQUESTS_PER_MINUTE env var.
    """
    raw = getenv(str(EnvVar.MAX_REQUESTS_PER_MINUTE))
    if raw:
        try:
            value = int(raw)
            if value > 0:
                return value
        except ValueError:
            logger.warning(f"Invalid {EnvVar.MAX_REQUESTS_PER_MINUTE} value: {raw}")
    return DEFAULT_MAX_REQUESTS_PER_MINUTE


def _get_positive_float_env(var_name: EnvVar, *, default: float) -> float:
    raw = getenv(str(var_name))
    if raw:
        try:
            value = float(raw)
            if value >= 0:
                return value
        except ValueError:
            logger.warning(f"Invalid {var_name} value: {raw}")
    return default


def get_rate_pacing_base_delay_seconds() -> float:
    """Additional minimum delay applied between rate-limited requests."""
    return _get_positive_float_env(EnvVar.RATE_PACING_BASE_DELAY_SECONDS, default=0.0)


def get_rate_pacing_jitter_min_seconds() -> float:
    """Lower bound for random jitter added to pacing delay."""
    return _get_positive_float_env(EnvVar.RATE_PACING_JITTER_MIN_SECONDS, default=0.0)


def get_rate_pacing_jitter_max_seconds() -> float:
    """Upper bound for random jitter added to pacing delay."""
    return _get_positive_float_env(EnvVar.RATE_PACING_JITTER_MAX_SECONDS, default=0.0)


def _resolve_retry_wait_seconds(exception: Exception, backoff_mean: float, backoff_std: float) -> float:
    retry_after_seconds = getattr(exception, "retry_after_seconds", None)
    if retry_after_seconds is not None:
        try:
            return max(0.1, float(retry_after_seconds))
        except (TypeError, ValueError):
            pass
    return max(0.1, random.gauss(backoff_mean, backoff_std))


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
            retry_after_seconds = getattr(e, "retry_after_seconds", None)
            if retry_after_seconds is not None:
                logger.warning(
                    f"Rate limit on attempt {attempt + 1}/{max_attempts}: {e}"
                )
            else:
                logger.error(f"Exception {e} occurred on attempt {attempt + 1}/{max_attempts}")
            if attempt < max_attempts - 1:
                wait_time = _resolve_retry_wait_seconds(e, backoff_mean, backoff_std)
                if retry_after_seconds is not None:
                    logger.warning(f"Retrying after {wait_time:.2f} seconds.")
                else:
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
