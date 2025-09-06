"""
LangGraph module for automated task synthesis and generation.

This module provides intelligent task generation capabilities using
configurable LLMs, dynamic label management, and LangGraph workflows.
"""

from .task_synthesizer import TaskSynthesizer, TaskSuggestion
from .config import get_config, reload_config
from .constants import (
    InputSources, TaskTypes, UrgencyLevels, PriorityLevels,
    EnvironmentVariables, ModelProviders, DefaultValues
)

# Import automation only when needed to avoid dependency issues
def get_automation():
    from .automation import LangGraphAutomation
    return LangGraphAutomation

def get_llm_manager():
    from .llm_integration import LLMManager
    return LLMManager

def get_label_manager():
    from .label_manager import LabelManager
    return LabelManager

__all__ = [
    "TaskSynthesizer",
    "TaskSuggestion", 
    "get_automation",
    "get_llm_manager",
    "get_label_manager",
    "get_config",
    "reload_config",
    "InputSources",
    "TaskTypes", 
    "UrgencyLevels",
    "PriorityLevels",
    "EnvironmentVariables",
    "ModelProviders",
    "DefaultValues"
]