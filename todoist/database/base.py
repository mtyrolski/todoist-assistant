from dotenv import load_dotenv

from todoist.database.db_activity import DatabaseActivity
from todoist.database.db_labels import DatabaseLabels
from todoist.database.db_projects import DatabaseProjects
from todoist.database.db_tasks import DatabaseTasks
from todoist.utils import Anonymizable
from loguru import logger


class Database(Anonymizable, DatabaseActivity, DatabaseProjects, DatabaseTasks, DatabaseLabels):
    def __init__(self, dotenv_path: str):
        load_dotenv(dotenv_path, override=True)
        super().__init__()

    def reset(self):
        # Walk through MRO and invoke reset on each mixin that defines it
        for cls in type(self).__mro__:
            if cls in (Database, object, Anonymizable):
                continue
            reset_fn = getattr(cls, 'reset', None)
            if callable(reset_fn):
                logger.debug(f'Resetting {cls.__name__}...')
                # Call the bound method on self if it exists
                try:
                    reset_fn(self)  # type: ignore[misc]
                except Exception as e:  # pragma: no cover - defensive
                    logger.error(f"Reset failed for {cls.__name__}: {e.__class__.__name__}: {e}")

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
            # Call the mixin method on self; signature may accept label_mapping optionally
            try:
                bs.anonymize_sub_db(self, project_mapping, label_mapping=label_mapping)  # type: ignore[arg-type]
            except TypeError:
                # Backward compatibility for methods that accept only project_mapping
                bs.anonymize_sub_db(self, project_mapping)  # type: ignore[misc]
