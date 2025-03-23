from loguru import logger
from todoist.activity import fetch_activity, quick_summarize
from todoist.automations.base import Automation

class Activity(Automation):
    def __init__(self, name: str, nweeks: int = 3):
        super().__init__(name, 0.1)
        self.nweeks = nweeks
    
    def _tick(self, dbio):
        activity_db, new_items = fetch_activity(dbio)
        logger.info('Summary of Activity:')
        quick_summarize(activity_db, new_items)