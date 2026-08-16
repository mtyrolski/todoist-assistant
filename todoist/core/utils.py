from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import MISSING, dataclass, field
import time
import random
import os
import shutil
import sys
import tempfile
from threading import RLock
from lzma import LZMAError
from os import getenv
from os.path import exists
from pathlib import Path
from pickle import HIGHEST_PROTOCOL, UnpicklingError
from typing import Any, Callable, Generic, KeysView, Type, TypeVar, cast
from zlib import error as ZlibError

from hydra import compose, initialize, initialize_config_dir
from hydra.core.global_hydra import GlobalHydra
from joblib import dump, load
from loguru import logger
from omegaconf import DictConfig

from todoist.core.env import EnvVar

try:  # pragma: no cover - platform-specific import
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None

T = TypeVar("T")
LOCAL_STORAGE_EXCEPTIONS = (
    UnpicklingError,
    EOFError,
    ZlibError,
    LZMAError,
    FileNotFoundError,
    ValueError,
    TypeError,
    OSError,
    ImportError,
    AttributeError,
    ModuleNotFoundError,
    KeyError,
)
DEFAULT_CACHE_SUBDIR = Path(".cache") / "todoist-assistant"
MIGRATION_BACKUP_DIRNAME = ".cache-migration-backup"
MIGRATION_BACKUP_REMOVAL_VERSION = "v0.3.3"
CacheStorageSpec = tuple[str, Callable[[], Any]]
CACHE_STORAGE_REGISTRY: dict[str, CacheStorageSpec] = {
    "activity": ("activity.joblib", set),
    "observer_state": ("observer_state.joblib", dict),
    "integration_launches": ("integration_launches.joblib", dict),
    "automation_launches": ("automation_launches.joblib", dict),
    "automation_run_signals": ("automation_run_signals.joblib", dict),
    "stale_task_warnings": ("stale_task_warnings.joblib", dict),
    "multiplication_label_usage": ("multiplication_label_usage.joblib", dict),
    "habit_tracker_posts": ("habit_tracker_posts.joblib", dict),
    "processed_gmail_messages": ("processed_gmail_messages.joblib", set),
    "dashboard_state": ("dashboard_state.joblib", dict),
    "archived_activity_scans": ("archived_activity_scans.joblib", dict),
    "llm_breakdown_progress": ("llm_breakdown_progress.joblib", dict),
    "llm_breakdown_queue": ("llm_breakdown_queue.joblib", dict),
    "llm_chat_conversations": ("llm_chat_conversations.joblib", list),
    "llm_usage_stats": ("llm_usage_stats.joblib", dict),
}
RUNTIME_CACHE_FILENAMES: tuple[str, ...] = tuple(
    filename for filename, _default_factory in CACHE_STORAGE_REGISTRY.values()
)
RUNTIME_LOG_FILENAMES: tuple[str, ...] = ("automation.log",)
RUNTIME_MIGRATABLE_FILENAMES: tuple[str, ...] = (
    RUNTIME_CACHE_FILENAMES + RUNTIME_LOG_FILENAMES
)
_MIGRATED_CACHE_DIRS: set[str] = set()
DEFAULT_LOG_LEVEL = "INFO"
VALID_LOG_LEVELS = frozenset(
    {"TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"}
)
API_KEY_PLACEHOLDERS = frozenset(
    {
        "put your api here",
        "put your api key here",
        "your todoist api key",
    }
)

TqdmProgressCallback = Callable[..., None]


@dataclass
class _RuntimeState:
    tqdm_progress_callback: TqdmProgressCallback | None = None
    migration_warning_logged: bool = False
    runtime_logging_signature: tuple[str | None, str] | None = None
    missing_required_field_warnings: set[tuple[str, str]] = field(default_factory=set)


_STATE = _RuntimeState()
_LOCAL_STORAGE_LOCKS: dict[str, RLock] = {}
_LOCAL_STORAGE_LOCKS_GUARD = RLock()


def set_tqdm_progress_callback(callback: TqdmProgressCallback | None) -> None:
    _STATE.tqdm_progress_callback = callback


def get_tqdm_progress_callback() -> TqdmProgressCallback | None:
    return _STATE.tqdm_progress_callback


def report_tqdm_progress(
    desc: str,
    current: int,
    total: int,
    unit: str | None = None,
    detail: str | None = None,
    *,
    lane_id: str | None = None,
    lane_label: str | None = None,
    lane_status: str | None = None,
) -> None:
    callback = _STATE.tqdm_progress_callback
    if callback is None:
        return
    try:
        if lane_id is not None:
            try:
                callback(
                    desc,
                    current,
                    total,
                    unit,
                    detail,
                    lane_id,
                    lane_label,
                    lane_status,
                )
                return
            except TypeError:
                try:
                    callback(
                        desc,
                        current,
                        total,
                        unit,
                        detail,
                        lane_id,
                        lane_label,
                    )
                    return
                except TypeError:
                    pass
        if detail is None:
            callback(desc, current, total, unit)
        else:
            try:
                callback(desc, current, total, unit, detail)
            except TypeError:
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


def _should_isolate_runtime_log_path_for_pytest(resolved_log_path: str | None) -> bool:
    if resolved_log_path is None:
        return False
    if "pytest" not in sys.modules:
        return False
    if getenv(str(EnvVar.CACHE_DIR)):
        return False

    default_runtime_log = str(
        (Path.cwd() / DEFAULT_CACHE_SUBDIR / "automation.log").resolve()
    )
    return resolved_log_path == default_runtime_log


def _resolve_runtime_log_path(log_path: str | None) -> str | None:
    resolved_log_path = str(Path(log_path).expanduser().resolve()) if log_path else None
    if not _should_isolate_runtime_log_path_for_pytest(resolved_log_path):
        return resolved_log_path

    isolated_root = (
        Path(tempfile.gettempdir()) / "todoist-assistant-pytest" / str(os.getpid())
    )
    return str((isolated_root / "automation.log").resolve())


def configure_runtime_logging(
    log_path: str | None = None, level: str | None = None
) -> None:
    resolved_level = get_log_level(level or DEFAULT_LOG_LEVEL)
    resolved_log_path = _resolve_runtime_log_path(log_path)
    signature = (resolved_log_path, resolved_level)
    if _STATE.runtime_logging_signature == signature:
        return

    logger.remove()
    logger.add(sys.stderr, level=resolved_level)
    if resolved_log_path is not None:
        Path(resolved_log_path).parent.mkdir(parents=True, exist_ok=True)
        logger.add(resolved_log_path, rotation="500 MB", level=resolved_level)
    _STATE.runtime_logging_signature = signature


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

                if not _STATE.migration_warning_logged:
                    logger.warning(
                        f"Legacy cache migration backups are temporary and will be removed in "
                        f"{MIGRATION_BACKUP_REMOVAL_VERSION}."
                    )
                    _STATE.migration_warning_logged = True
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
            if warning_key in _STATE.missing_required_field_warnings:
                continue
            logger.warning(
                f"{cls.__name__}: missing required field '{field_name}' in API payload; "
                "defaulting to None for compatibility."
            )
            _STATE.missing_required_field_warnings.add(warning_key)

    unexpected_fields = set(normalized_kwargs.keys()) - class_field_set

    assert "new_api_kwargs" in class_fields, (
        f"kwargs field is not in {cls.__name__} class"
    )

    # write unexpected fields to kwargs
    filtered_kwargs = {k: v for k, v in normalized_kwargs.items() if k in class_fields}
    unexpected_kwargs = {
        k: v for k, v in normalized_kwargs.items() if k in unexpected_fields
    }
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

    def _is_expected_type(self, value: object) -> bool:
        expected_type = type(self._default_value())
        return isinstance(value, expected_type)

    @contextmanager
    def _locked(self):
        """Serialize cache access in-process and, when available, across processes."""

        path = str(Path(self.path).expanduser().resolve())
        with _LOCAL_STORAGE_LOCKS_GUARD:
            thread_lock = _LOCAL_STORAGE_LOCKS.setdefault(path, RLock())
        with thread_lock:
            lock_file = None
            try:
                lock_file = open(f"{path}.lock", "a+b")
                if fcntl is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                yield
            finally:
                if lock_file is not None:
                    if fcntl is not None:
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                    lock_file.close()

    def _load_unlocked(self) -> T:
        if not exists(self.path):
            return self._default_value()
        value = cast(T, load(self.path))
        if not self._is_expected_type(value):
            raise TypeError(
                f"Expected {type(self._default_value()).__name__}, got {type(value).__name__}"
            )
        return value

    def _quarantine_corrupt_file(self) -> None:
        path_obj = Path(self.path)
        if not path_obj.exists():
            return
        backup = path_obj.with_name(
            f"{path_obj.name}.corrupt.{time.time_ns()}"
        )
        try:
            os.replace(path_obj, backup)
            logger.warning(
                "Quarantined corrupted cache file {} as {}",
                path_obj,
                backup,
            )
        except OSError as exc:
            logger.warning("Failed to quarantine corrupted cache file {}: {}", path_obj, exc)

    def _save_unlocked(self, data: T) -> None:
        path_obj = Path(self.path)
        parent = path_obj.parent
        parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{path_obj.name}.", suffix=".tmp", dir=parent
        )
        os.close(fd)
        temporary_path = Path(temporary_name)
        try:
            dump(data, str(temporary_path), protocol=HIGHEST_PROTOCOL)
            with temporary_path.open("rb") as temporary_file:
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, path_obj)
        finally:
            temporary_path.unlink(missing_ok=True)

    def load(self) -> T:
        try:
            with self._locked():
                try:
                    return self._load_unlocked()
                except LOCAL_STORAGE_EXCEPTIONS as exc:
                    logger.warning(
                        f"Failed to load data from {self.path}: {type(exc).__name__}: {exc}. "
                        "Quarantining and recreating cache."
                    )
                    self._quarantine_corrupt_file()
                    default_value = self._default_value()
                    self._save_unlocked(default_value)
                    return default_value
        except LOCAL_STORAGE_EXCEPTIONS as exc:
            raise LocalStorageError(f"Failed to load data from {self.path}: {exc}") from exc

    def save(self, data: T) -> None:
        try:
            if not self._is_expected_type(data):
                raise TypeError(
                    f"Expected {type(self._default_value()).__name__}, got {type(data).__name__}"
                )
            with self._locked():
                self._save_unlocked(data)
        except LOCAL_STORAGE_EXCEPTIONS as e:
            raise LocalStorageError(f"Failed to save data to {self.path}: {e}") from e

    def update(self, updater: Callable[[T], T]) -> T:
        """Atomically load, transform, and save one cache value."""

        try:
            with self._locked():
                try:
                    current = self._load_unlocked()
                except LOCAL_STORAGE_EXCEPTIONS as exc:
                    logger.warning(
                        f"Failed to load data from {self.path}: {type(exc).__name__}: {exc}. "
                        "Quarantining before applying update."
                    )
                    self._quarantine_corrupt_file()
                    current = self._default_value()
                updated = updater(current)
                if not self._is_expected_type(updated):
                    raise TypeError(
                        f"Expected updater to return {type(self._default_value()).__name__}, "
                        f"got {type(updated).__name__}"
                    )
                self._save_unlocked(updated)
                return updated
        except LOCAL_STORAGE_EXCEPTIONS as exc:
            raise LocalStorageError(f"Failed to update data in {self.path}: {exc}") from exc


class Cache:
    def __init__(self, path: str | None = None):
        explicit_path = path is not None
        self.path = resolve_cache_dir(path)
        if not explicit_path:
            migrate_legacy_runtime_files(self.path)
        Path(self.path).mkdir(parents=True, exist_ok=True)
        for name, (_filename, default_factory) in CACHE_STORAGE_REGISTRY.items():
            setattr(self, name, self.storage(name, default_factory))

    def storage(self, name: str, default_factory: Callable[[], T]) -> LocalStorage[T]:
        registry_entry = CACHE_STORAGE_REGISTRY.get(name)
        filename = registry_entry[0] if registry_entry else f"{name}.joblib"
        return LocalStorage(str(Path(self.path) / filename), default_factory)

    def __getattr__(self, name: str) -> LocalStorage[Any]:
        registry_entry = CACHE_STORAGE_REGISTRY.get(name)
        if registry_entry is None:
            raise AttributeError(
                f"{type(self).__name__!r} object has no attribute {name!r}"
            )
        storage = self.storage(name, registry_entry[1])
        setattr(self, name, storage)
        return storage


class Anonymizable(ABC):
    def __init__(self):
        super().__init__()
        logger.debug(f"Initializing {self.__class__.__name__}... somehow anonimizable")
        self.is_anonymized = False

    @abstractmethod
    def _anonymize(
        self, project_mapping: dict[str, str], label_mapping: dict[str, str]
    ):
        pass

    def anonymize(self, project_mapping: dict[str, str], label_mapping: dict[str, str]):
        """
        Anonymizes project and label names in the database.
        """
        if not self.is_anonymized:
            logger.warning("Anonymizing data...")
            self._anonymize(project_mapping, label_mapping)
            self.is_anonymized = True
        else:
            logger.debug("Already anonymized. Skipping.")


def last_n_years_in_weeks(n_years: int) -> int:
    count_f: float = 365.25 * n_years / 7
    return int(count_f)


def get_api_key() -> str:
    """Return a normalized Todoist API token or an empty string when unset."""

    raw_value = getenv("API_KEY")
    if raw_value is None:
        return ""
    value = str(raw_value).strip().strip("'\"")
    if not value:
        return ""
    if value.lower() in API_KEY_PLACEHOLDERS:
        return ""
    return value


U = TypeVar("U")

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


def _resolve_retry_wait_seconds(
    exception: Exception, backoff_mean: float, backoff_std: float
) -> float:
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
                wait_time = 2 ** (attempt + 3)
                logger.debug(f"Waiting {wait_time} seconds before retrying...")
                time.sleep(wait_time)
    return None


def retry_with_backoff(
    fn: Callable[[], U],
    max_attempts: int = RETRY_MAX_ATTEMPTS,
    backoff_mean: float = RETRY_BACKOFF_MEAN,
    backoff_std: float = RETRY_BACKOFF_STD,
) -> U | None:
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
                logger.error(
                    f"Exception {e} occurred on attempt {attempt + 1}/{max_attempts}"
                )
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


def with_retry(
    fn: Callable[[], U],
    operation_name: str = "operation",
    max_attempts: int = RETRY_MAX_ATTEMPTS,
    backoff_mean: float = RETRY_BACKOFF_MEAN,
    backoff_std: float = RETRY_BACKOFF_STD,
) -> U:
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
        raise MaxRetriesExceeded(
            f"Failed to execute {operation_name} after {max_attempts} retry attempts"
        )
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
    "berry_red": "#B8255F",
    "red": "#DC4C3E",
    "orange": "#C77100",
    "yellow": "#B29104",
    "olive_green": "#949C31",
    "lime_green": "#65A33A",
    "green": "#369307",
    "mint_green": "#42A393",
    "teal": "#148FAD",
    "sky_blue": "#319DC0",
    "light_blue": "#6988A4",
    "blue": "#4180FF",
    "grape": "#692EC2",
    "violet": "#CA3FEE",
    "lavender": "#A4698C",
    "magenta": "#E05095",
    "salmon": "#C9766F",
    "charcoal": "#808080",
    "grey": "#999999",
    "taupe": "#8F7A69",
}
