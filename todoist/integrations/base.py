from abc import ABC, abstractmethod
from dataclasses import dataclass
import datetime as dt

from loguru import logger
from todoist.utils import Cache


@dataclass
class TodoistTaskRequest:
    """
    Represents a task to be created in Todoist.
    Stores the task content, project ID, and due date.
    """
    content: str
    description: str
    project_id: int
    due_date: str
    priority: int


class Integration(ABC):
    def __init__(self, name: str, frequency: float):
        """
        Initialize the integration with a name and frequency.
        Frequency is the number of seconds between each tick.
        """
        self.name = name
        self.frequency = frequency

    def tick(self):
        last_launches: dict[str, dt.datetime] = Cache().integration_launches.load()
        last_launch = last_launches.get(self.name, dt.datetime.min)

        now = dt.datetime.now()

        # Only run if at least a week has passed since last launch
        if (now - last_launch) < dt.timedelta(weeks=1):
            logger.info("Less than a week since last integration run; no new tasks generated.")
            logger.info(f"Last run: {last_launch}")
            logger.info(f"Current time: {now}")
            logger.info(f"Time until next run: {dt.timedelta(weeks=1) - (now - last_launch)}")
            return []

        self._tick()
        Cache().integration_launches.save({self.name: now})

    @abstractmethod
    def _tick(self):
        """
        Perform the integration's main operation.
        """
        pass
