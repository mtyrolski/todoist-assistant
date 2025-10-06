"""
State management for the LangGraph agent.
"""
from dataclasses import dataclass, field
from typing import TypedDict

from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """State for the LangGraph agent."""
    messages: list[BaseMessage]
    iterations: int
