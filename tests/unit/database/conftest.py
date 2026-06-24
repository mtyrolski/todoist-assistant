import pytest

from tests.factories import make_project_entry, make_task_entry
from todoist.database.db_activity import DatabaseActivity
from todoist.database.db_projects import DatabaseProjects
from todoist.database.db_tasks import DatabaseTasks


@pytest.fixture
def db_tasks():
    return DatabaseTasks()


@pytest.fixture
def db_projects():
    return DatabaseProjects()


@pytest.fixture
def db_activity():
    return DatabaseActivity()


@pytest.fixture
def sample_task_entry():
    return make_task_entry(task_id="task123", content="Test Task")


@pytest.fixture
def sample_project_entry():
    return make_project_entry(project_id="12345", name="Test Project")
