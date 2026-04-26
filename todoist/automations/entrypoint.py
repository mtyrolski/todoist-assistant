from collections.abc import Callable

import hydra
from loguru import logger
from omegaconf import DictConfig
from tqdm import tqdm

from todoist.automations.activity import Activity
from todoist.automations.base import Automation, run_automations_resiliently
from todoist.database.base import Database
from todoist.utils import automation_log_path, configure_runtime_logging

_ENV_PATH = ".env"


def load_automations(config: DictConfig) -> list[Automation]:
    automations = hydra.utils.instantiate(config.automations)
    return list(automations)


def configure_automation_runtime() -> Database:
    configure_runtime_logging(log_path=automation_log_path())
    return Database(_ENV_PATH)


def select_init_env_automations(automations: list[Automation]) -> list[Automation]:
    activity_automations = [automation for automation in automations if isinstance(automation, Activity)]
    if not activity_automations:
        logger.info("No activity automations found, running all remaining automations.")
        return list(automations)

    longest_activity = max(activity_automations, key=lambda automation: automation.nweeks)
    logger.info(
        "Activity automations found, running the longest one - last {} weeks of activity collection.",
        int(longest_activity.nweeks),
    )
    rest_automations = [automation for automation in automations if not isinstance(automation, Activity)]
    return [longest_activity] + rest_automations


def select_update_env_automations(automations: list[Automation]) -> list[Automation]:
    logger.info("Filtering only for short ones")
    short_automations = [automation for automation in automations if not automation.is_long]
    return select_init_env_automations(short_automations)


def run_configured_automations(
    config: DictConfig,
    *,
    select_automations: Callable[[list[Automation]], list[Automation]],
    skip_long: bool = False,
) -> None:
    db = configure_automation_runtime()
    automations = load_automations(config)
    logger.info("Loaded automations: {}", list(map(str, automations)))
    automations = select_automations(automations)

    if not automations:
        logger.warning("No automations to run. Exiting.")
        return

    logger.info("Starting automations...")
    run_automations_resiliently(
        tqdm(automations, desc="Processing automations"),
        db=db,
        skip_long=skip_long,
    )
