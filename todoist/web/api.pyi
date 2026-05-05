from typing import Any
from fastapi import FastAPI
from todoist.automations.base import Automation
from todoist.automations.observer import AutomationObserver
from todoist.automations.llm_breakdown.models import BreakdownNode, TaskBreakdown
from todoist.database.base import Database
from todoist.env import EnvVar
from todoist.llm import TransformersMistral3ChatModel

app: FastAPI
_PendingGmailAuthSession: Any

def __getattr__(name: str) -> Any: ...
