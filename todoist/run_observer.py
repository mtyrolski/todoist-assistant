"""Entry point for running the automation observer."""

import hydra
from loguru import logger
from omegaconf import DictConfig

from todoist.automations.activity import Activity
from todoist.automations.base import Automation
from todoist.automations.observer import AutomationObserver
from todoist.database.base import Database


@hydra.main(version_base=None, config_path=None)
def main(config: DictConfig) -> None:
    logger.add("automation.log", rotation="500 MB")
    db = Database('.env')

    # Instantiate activity automation explicitly to avoid cross-instantiation.
    activity_automation: Activity = hydra.utils.instantiate(config.activity)

    # Instantiate remaining automations (may include Activity in config.automations; filter it out).
    automations: list[Automation] = hydra.utils.instantiate(config.automations)
    short_automations = [auto for auto in automations if not isinstance(auto, Activity)]

    observer = AutomationObserver(
        db=db,
        automations=short_automations,
        activity=activity_automation,
    )
    observer.run_forever()


if __name__ == "__main__":
    # pylint: disable=no-value-for-parameter
    main()
