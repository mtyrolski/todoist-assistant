import hydra
from loguru import logger
from tqdm import tqdm
from omegaconf import DictConfig
from todoist.automations.base import Automation
from todoist.database.base import Database


@hydra.main(version_base=None, config_path=None)
def main(config: DictConfig) -> None:
    # Setup logging to a file with rotation
    logger.add("automation.log", rotation="500 MB")

    dbio = Database('.env')
    automations: list[Automation] = hydra.utils.instantiate(config.automations)
    logger.info("Loaded automations: {}", list(map(str, automations)))
    logger.info("Starting automations...")
    for automation in tqdm(automations, desc="Processing automations"):
        logger.info("Running automation: {}", automation)
        if automation.is_long:
            logger.warning("Long automation detected, skipping...")
            continue
        automation.tick(dbio)
        logger.info("Automation completed: {}", automation)
    logger.success("All automations completed.")


if __name__ == '__main__':
    # pylint: disable=no-value-for-parameter
    main()
