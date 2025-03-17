from abc import ABC, abstractmethod
from dataclasses import dataclass
import datetime as dt
from loguru import logger
from todoist.database.base import Database

from todoist.utils import Cache


class Automation(ABC):
    def __init__(self, name: str,
                 frequency: float):
        """
        Initialize the automation with a name and frequency.
        Frequency is the number of minutes between each tick.
        """
        self.name = name
        self.frequency = frequency

    def tick(self, db: Database):
        last_launches = Cache().automation_launches.load()
        last_launch = last_launches.get(self.name, dt.datetime.min)
        
        now = dt.datetime.now()

        # Only run if at least a week has passed since last launch
        if (now - last_launch) < dt.timedelta(minutes=self.frequency):
            logger.info(f"Automation {self.name} is not ready to run.")
            logger.info(f"Last run: {last_launch}")
            logger.info(f"Current time: {now}")
            logger.info(f"Time until next run: {dt.timedelta(minutes=self.frequency) - (now - last_launch)}")
            return []
        
        task_delegations = self._tick(db)        
        Cache().automation_launches.save({self.name: now})
        
        return task_delegations
        
    @abstractmethod
    def _tick(self, db: Database):
        """
        Perform the automation's main operation.
        """
        pass