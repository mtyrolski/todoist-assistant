from os import getenv
from os.path import join
from os.path import exists
from pickle import HIGHEST_PROTOCOL
from typing import Callable, TypeVar
from joblib import load, dump
from loguru import logger

from hydra import compose
from hydra import initialize
from hydra.core.global_hydra import GlobalHydra
from omegaconf import DictConfig
from omegaconf import OmegaConf
from abc import ABC, abstractmethod

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


def load_config(config_name: str, config_path: str) -> OmegaConf:
    GlobalHydra.instance().clear()
    initialize(config_path=config_path)
    config: DictConfig = compose(config_name=config_name)
    return OmegaConf.create(config)


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
