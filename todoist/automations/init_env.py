import hydra
from loguru import logger
from tqdm import tqdm
from omegaconf import DictConfig
from todoist.automations.base import Automation
from todoist.database.base import Database
from todoist.utils import try_n_times
from functools import partial
from todoist.automations.activity import Activity

@hydra.main(version_base=None, config_path=None)
def main(config: DictConfig) -> None:
    # Setup logging to a file with rotation
    logger.add("automation.log", rotation="500 MB")

    dbio = Database('.env')
    automations: list[Automation] = hydra.utils.instantiate(config.automations)
    logger.info("Loaded automations: {}", list(map(str, automations)))

    # If Activity among automations, we need to run the longest one.
    activity_automations: list[Activity] = [a for a in automations if isinstance(a, Activity)]
    rest_automations: list[Automation] = [a for a in automations if not isinstance(a, Activity)]
    if activity_automations:
        longest_automation = max(activity_automations, key=lambda x: x.nweeks)
        logger.info(f"Activity automations found, running the longest one - last {int(longest_automation.nweeks)} weeks of activity collection.")
        automations = [longest_automation] + rest_automations
    else:
        logger.info("No activity automations found, running all remaining automations.")

    if not automations:
        logger.warning("No automations to run. Exiting.")
        return


    logger.info("Starting automations...")
    for automation in tqdm(automations, desc="Processing automations"):
        logger.info("Running automation: {}", automation)
        try_n_times(partial(automation.tick, dbio), 5)
        logger.info("Automation completed: {}", automation)
    logger.success("All automations completed.")


if __name__ == '__main__':
    # pylint: disable=no-value-for-parameter
    main()
