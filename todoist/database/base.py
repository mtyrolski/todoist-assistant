from dotenv import load_dotenv

from todoist.database.db_activity import DatabaseActivity
from todoist.database.db_labels import DatabaseLabels
from todoist.database.db_projects import DatabaseProjects
from todoist.database.db_tasks import DatabaseTasks
from todoist.utils import Anonymizable, last_n_years_in_weeks


class Database(DatabaseActivity, DatabaseProjects, DatabaseTasks, DatabaseLabels):
    def __init__(self, dotenv_path: str, max_pages: int = last_n_years_in_weeks(4)):
        load_dotenv(dotenv_path, override=True)
        DatabaseActivity.__init__(self, max_pages=max_pages)
        DatabaseProjects.__init__(self)
        DatabaseTasks.__init__(self)
        DatabaseLabels.__init__(self)

    def reset(self):
        for bs in Database.__bases__:
            bs.reset(self)

    def anonymize(self, project_mapping: dict[str, str], label_mapping: dict[str, str]):
        """
        Anonymizes project and label names in the database.
        """
        for bs in Database.__bases__:
            print(
                f'Checking if {bs} is anonymizable, i.e. if it has the anonymize method ({issubclass(bs, Anonymizable)})'
            )
            if issubclass(bs, Anonymizable):
                bs.anonymize(self, project_mapping, label_mapping)
