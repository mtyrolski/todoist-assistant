"""
Prompt templates for LangGraph LLM integration.
Separated for better organization and maintainability.
"""

from typing import List, Dict, Any


class TaskGenerationPrompts:
    """Collection of prompts for task generation."""
    
    SYSTEM_PROMPT = """You are a helpful task management assistant that generates structured tasks and subtasks.
Given a user request, create appropriate tasks with realistic subtasks, proper urgency assessment, and relevant labels.
Always respond with well-structured, actionable tasks."""

    TASK_GENERATION_TEMPLATE = """Based on the user input: '{user_input}', create a comprehensive task breakdown.

Available labels in Todoist: {available_labels}

Generate:
- A clear main task title
- Detailed description
- Appropriate urgency level (low/medium/high)
- Relevant labels from the available ones
- Useful subtasks if the task is complex

Focus on being practical and actionable."""

    TASK_WITH_CONTEXT_TEMPLATE = """Based on the user input: '{user_input}', create a comprehensive task breakdown.

Available labels in Todoist: {available_labels}

Additional context:
{context}

Generate:
- A clear main task title
- Detailed description
- Appropriate urgency level (low/medium/high)
- Relevant labels from the available ones
- Useful subtasks if the task is complex
- Priority level (1-4) based on urgency

Consider the provided context when determining task structure and priorities."""

    LABEL_SUGGESTION_TEMPLATE = """Based on the task content: '{task_content}', suggest the most appropriate labels.

Available labels: {available_labels}

Consider:
- Task type and category
- Urgency and importance
- Content keywords
- Project context

Return only the most relevant label names from the available list."""

    URGENCY_ASSESSMENT_TEMPLATE = """Analyze the urgency of this task: '{task_content}'

Consider:
- Time-sensitive keywords (urgent, asap, immediately, deadline, etc.)
- Context clues about timing
- Importance indicators
- Impact if delayed

Respond with one of: low, medium, high"""


class RuleBasedPrompts:
    """Prompts for rule-based fallback generation."""
    
    GENERATE_TASK_RESPONSE = "Generated task based on input with appropriate subtasks."
    SUGGEST_LABELS_RESPONSE = "Suggested labels: general, planning, action"
    DEFAULT_RESPONSE = "Task processed using rule-based generation."


def build_task_generation_prompt(
    user_input: str,
    available_labels: List[str],
    context: Dict[str, Any] = None
) -> str:
    """
    Build a complete prompt for task generation.
    
    Args:
        user_input: User's natural language input
        available_labels: List of available labels from Todoist
        context: Optional context dictionary
        
    Returns:
        Complete prompt string
    """
    labels_str = ', '.join(available_labels) if available_labels else 'none'
    
    if context:
        context_str = '\n'.join([f"- {k}: {v}" for k, v in context.items()])
        task_prompt = TaskGenerationPrompts.TASK_WITH_CONTEXT_TEMPLATE.format(
            user_input=user_input,
            available_labels=labels_str,
            context=context_str
        )
    else:
        task_prompt = TaskGenerationPrompts.TASK_GENERATION_TEMPLATE.format(
            user_input=user_input,
            available_labels=labels_str
        )
    
    return f"{TaskGenerationPrompts.SYSTEM_PROMPT}\n\n{task_prompt}"


def build_label_suggestion_prompt(task_content: str, available_labels: List[str]) -> str:
    """
    Build prompt for label suggestion.
    
    Args:
        task_content: Content to analyze for labels
        available_labels: List of available labels
        
    Returns:
        Label suggestion prompt
    """
    labels_str = ', '.join(available_labels) if available_labels else 'none'
    return TaskGenerationPrompts.LABEL_SUGGESTION_TEMPLATE.format(
        task_content=task_content,
        available_labels=labels_str
    )


def build_urgency_assessment_prompt(task_content: str) -> str:
    """
    Build prompt for urgency assessment.
    
    Args:
        task_content: Content to analyze for urgency
        
    Returns:
        Urgency assessment prompt
    """
    return TaskGenerationPrompts.URGENCY_ASSESSMENT_TEMPLATE.format(
        task_content=task_content
    )


def get_rule_based_response(prompt_type: str) -> str:
    """
    Get rule-based response for fallback scenarios.
    
    Args:
        prompt_type: Type of prompt (generate_task, suggest_labels, etc.)
        
    Returns:
        Appropriate rule-based response
    """
    if "generate task" in prompt_type.lower():
        return RuleBasedPrompts.GENERATE_TASK_RESPONSE
    elif "suggest labels" in prompt_type.lower():
        return RuleBasedPrompts.SUGGEST_LABELS_RESPONSE
    else:
        return RuleBasedPrompts.DEFAULT_RESPONSE