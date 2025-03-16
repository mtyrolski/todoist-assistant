# Multiply integration which look up over all active tasks, identify those with tag X2 X3 X5 or X10, then remove the tag and create new 2, 3, 5 or 10 tasks with the same content and other attributes. Only change is suffix of the task name identifying the multiplication factor.

from todoist.automations.base import Automation

SUPPORTED_FACTORS = [2, 3, 5, 10]

class Multiply(Automation):
    def __init__(self):
        super().__init__("Multiply", 1)
        
    def _tick(self, db):
        all_tasks = db.get_all_tasks()
        task_delegations = []
        for task in all_tasks:
            for factor in SUPPORTED_FACTORS:
                if f"X{factor}" in task.tags:
                    task_delegations.extend(self._multiply_task(task, factor))
        
        return task_delegations
    
    def _multiply_task(self, task, factor):
        task_delegations = []
        for i in range(factor):
            new_task = task.copy()
            new_task.content = f"{task.content} x {factor}"
            task_delegations.append(new_task)
        
        return task_delegations