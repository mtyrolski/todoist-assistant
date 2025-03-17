from os import getenv
from os.path import join
from os.path import exists
from pickle import HIGHEST_PROTOCOL
from typing import Callable, TypeVar
from joblib import load, dump
from loguru import logger

T = TypeVar('T', set, dict)


class LocalStorage:
    def __init__(self, path: str, resource_class: Callable[[], T]) -> None:
        self.path = path
        self.resource_class = resource_class

    def load(self) -> T:
        return load(self.path) if exists(self.path) else self.resource_class()

    def save(self, data: T) -> None:
        dump(data, self.path, protocol=HIGHEST_PROTOCOL)


class Cache:
    def __init__(self, path: str = './'):
        self.path = path
        self.activity = LocalStorage(join(self.path, 'activity.joblib'), set)
        self.integration_launches = LocalStorage(join(self.path, 'integration_launches.joblib'), dict)
        self.automation_launches = LocalStorage(join(self.path, 'automation_launches.joblib'), dict)


def last_n_years_in_weeks(n_years: int) -> int:
    count_f: float = 365.25 * n_years / 7
    return int(count_f)


def get_api_key() -> str:
    """Assuming that ENV variables are set"""
    return getenv('API_KEY')


U = TypeVar('U')


def try_n_times(fn: Callable[[], U], n) -> U | None:
    """
    Try to run a function n times and return the result if successful
    If the function fails, log the exception and after n trials, return None
    """
    for _ in range(n):
        try:
            return fn()
        except Exception as e:
            logger.error(f"Exception {e} occurred")
    return None
