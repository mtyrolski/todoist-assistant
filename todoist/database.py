from dotenv import load_dotenv

from todoist.db_activity import DatabaseActivity
from todoist.db_projects import DatabaseProjects
from todoist.utils import last_n_years_in_weeks


class Database(DatabaseActivity, DatabaseProjects):
    def __init__(self, dotenv_path: str, max_pages: int = last_n_years_in_weeks(4)):
        load_dotenv(dotenv_path, override=True)
        DatabaseActivity.__init__(self, max_pages=max_pages)
        DatabaseProjects.__init__(self)
