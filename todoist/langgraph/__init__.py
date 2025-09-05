"""
LangGraph module for automated task synthesis and generation.

This module provides functionality to automatically synthesize and generate 
tasks and subtasks based on user input using LangGraph workflows.
"""

from .task_synthesizer import TaskSynthesizer

# Import automation only when needed to avoid dependency issues
def get_automation():
    from .automation import LangGraphAutomation
    return LangGraphAutomation

__all__ = ['TaskSynthesizer', 'get_automation']