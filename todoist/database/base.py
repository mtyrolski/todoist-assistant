from dotenv import load_dotenv

from todoist.database.db_activity import DatabaseActivity
from todoist.database.db_labels import DatabaseLabels
from todoist.database.db_projects import DatabaseProjects
from todoist.database.db_tasks import DatabaseTasks
from todoist.utils import Anonymizable, last_n_years_in_weeks
from loguru import logger


class Database(Anonymizable, DatabaseActivity, DatabaseProjects, DatabaseTasks, DatabaseLabels):
    def __init__(self, dotenv_path: str):
        load_dotenv(dotenv_path, override=True)
        super().__init__()

    def reset(self):
        for bs in Database.__bases__:
            if hasattr(bs, 'reset'):
                logger.debug(f'Resetting {bs.__name__}...')
                assert hasattr(bs, 'reset'), f'{bs.__name__} is not resettable'

    @property
    def anonimizable_subdatabases(self):
        """
        Returns a list of sub-databases that are anonymizable.
        """
        return list(filter(lambda x: hasattr(x, 'anonymize_sub_db'), Database.__bases__))

    def _anonymize(self, project_mapping: dict[str, str], label_mapping: dict[str, str]):
        """
        Anonymizes project and label names in the database.
        """

        for bs in self.anonimizable_subdatabases:
            logger.debug(f'Anonymizing {bs.__name__}...')
            assert hasattr(bs, 'anonymize_sub_db'), f'{bs.__name__} is not anonymizable'
            bs.anonymize_sub_db(self, project_mapping, label_mapping)
