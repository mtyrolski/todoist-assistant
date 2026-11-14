from typing import Any
from fastapi import FastAPI

app: FastAPI

def __getattr__(name: str) -> Any: ...
