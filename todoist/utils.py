from os import getenv
from typing import Callable, TypeVar

from loguru import logger


def last_n_years_in_weeks(n_years: int) -> int:
    count_f: float = 365.25 * n_years / 7
    return int(count_f)


def get_api_key() -> str:
    """Assuming that ENV variables are set"""
    return getenv('API_KEY')


T = TypeVar('T')


def try_n_times(fn: Callable[[], T], n) -> T | None:
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
