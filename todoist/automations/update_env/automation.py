import hydra
from omegaconf import DictConfig
from todoist.automations.entrypoint import (
    run_configured_automations,
    select_update_env_automations,
)


@hydra.main(version_base=None, config_path=None)
def main(config: DictConfig) -> None:
    run_configured_automations(config, select_automations=select_update_env_automations)


if __name__ == "__main__":
    # pylint: disable=no-value-for-parameter
    main()
