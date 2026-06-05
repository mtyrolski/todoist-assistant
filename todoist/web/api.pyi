from typing import Any
from fastapi import FastAPI

app: FastAPI
_PendingGmailAuthSession: Any

def __getattr__(name: str) -> Any: ...
