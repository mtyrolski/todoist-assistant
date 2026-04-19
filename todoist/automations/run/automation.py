import hydra
from loguru import logger
from tqdm import tqdm
from omegaconf import DictConfig
from todoist.automations.base import Automation, run_automations_resiliently
from todoist.database.base import Database
from todoist.utils import automation_log_path, configure_runtime_logging


@hydra.main(version_base=None, config_path=None)
def main(config: DictConfig) -> None:
    configure_runtime_logging(log_path=automation_log_path())

    dbio = Database('.env')
    automations: list[Automation] = hydra.utils.instantiate(config.automations)
    logger.info("Loaded automations: {}", list(map(str, automations)))
    logger.info("Starting automations...")
    run_automations_resiliently(
        tqdm(automations, desc="Processing automations"),
        db=dbio,
        skip_long=True,
    )


if __name__ == '__main__':
    # pylint: disable=no-value-for-parameter
    main()
