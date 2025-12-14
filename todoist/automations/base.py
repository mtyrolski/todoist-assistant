from abc import ABC, abstractmethod
import datetime as dt
from loguru import logger

from todoist.database.base import Database
from todoist.utils import Cache


class Automation(ABC):
    def __init__(self, name: str, frequency: float, is_long: bool = False):
        """
        Initialize the automation with a name and frequency.
        Frequency is the number of minutes between each tick.
        """
        self.name = name
        self.frequency = frequency
        self.is_long = is_long

    def __str__(self):
        return f"Automation(name={self.name}, frequency={self.frequency}, is_long={self.is_long})"

    def tick(self, db: Database):
        launch_data = Cache().automation_launches.load()    # expects a dict: {automation_name: [launch_times]}
        launches = launch_data.get(self.name, [])
        last_launch = launches[-1] if launches else dt.datetime.min

        now = dt.datetime.now()

        # Only run if the frequency delay has not passed since the last launch
        if (now - last_launch) < dt.timedelta(minutes=self.frequency):
            delay = dt.timedelta(minutes=self.frequency) - (now - last_launch)
            logger.info(f"Automation {self.name} is not ready to run.")
            logger.info(f"Last run: {last_launch}")
            logger.info(f"Current time: {now}")
            logger.info(f"Time until next run: {delay}")
            return []

        logger.info(
            f"Running automation {self.name} at {now} since passed {(now - last_launch).total_seconds() / 60} minutes since last run."
        )

        task_delegations = self._tick(db)

        # Update the list of launch times with the new launch
        launches.append(now)
        launch_data[self.name] = launches
        Cache().automation_launches.save(launch_data)

        return task_delegations

    @abstractmethod
    def _tick(self, db: Database):
        """
        Perform the automation's main operation.
        """
        pass
