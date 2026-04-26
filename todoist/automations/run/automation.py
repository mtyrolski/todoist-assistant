import hydra
from omegaconf import DictConfig
from todoist.automations.entrypoint import run_configured_automations


@hydra.main(version_base=None, config_path=None)
def main(config: DictConfig) -> None:
    run_configured_automations(config, select_automations=lambda automations: automations, skip_long=True)


if __name__ == '__main__':
    # pylint: disable=no-value-for-parameter
    main()
