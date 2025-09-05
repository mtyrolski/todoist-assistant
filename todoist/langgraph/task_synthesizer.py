"""
Task Synthesizer using LangGraph for automated task generation.

This module implements a LangGraph workflow that can analyze user input
and automatically generate structured tasks and subtasks.
"""

from typing import Dict, List, Any, Optional, TypedDict
from dataclasses import dataclass
import json
from datetime import datetime, timedelta

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from typing_extensions import Annotated

from loguru import logger


@dataclass
class TaskSuggestion:
    """Represents a suggested task with its properties."""
    content: str
    description: str
    priority: int = 1
    due_date_days_offset: int = 0
    labels: List[str] = None
    subtasks: List['TaskSuggestion'] = None
    
    def __post_init__(self):
        if self.labels is None:
            self.labels = []
        if self.subtasks is None:
            self.subtasks = []


class TaskSynthesizerState(TypedDict):
    """State management for the LangGraph workflow."""
    messages: Annotated[list, add_messages]
    user_input: str
    parsed_requirements: Dict[str, Any]
    task_suggestions: List[Dict[str, Any]]  # Store as dicts for JSON serialization
    validation_results: Dict[str, Any]
    final_tasks: List[Dict[str, Any]]


class TaskSynthesizer:
    """
    LangGraph-based task synthesizer that can generate tasks and subtasks
    from natural language input.
    """
    
    def __init__(self, llm=None):
        """
        Initialize the TaskSynthesizer.
        
        Args:
            llm: Language model to use. If None, will use a default configuration.
        """
        self.llm = llm or self._get_default_llm()
        self.workflow = self._build_workflow()
    
    def _get_default_llm(self):
        """Get a default LLM configuration. For now, returns None to use mock responses."""
        # In a real implementation, this would configure an actual LLM
        # For this minimal implementation, we'll use rule-based generation
        return None
    
    def _build_workflow(self) -> StateGraph:
        """Build the LangGraph workflow for task synthesis."""
        workflow = StateGraph(TaskSynthesizerState)
        
        # Add nodes
        workflow.add_node("parse_input", self._parse_input_node)
        workflow.add_node("generate_tasks", self._generate_tasks_node)
        workflow.add_node("validate_tasks", self._validate_tasks_node)
        workflow.add_node("finalize_tasks", self._finalize_tasks_node)
        
        # Add edges
        workflow.set_entry_point("parse_input")
        workflow.add_edge("parse_input", "generate_tasks")
        workflow.add_edge("generate_tasks", "validate_tasks")
        workflow.add_edge("validate_tasks", "finalize_tasks")
        workflow.add_edge("finalize_tasks", END)
        
        return workflow.compile()
    
    def _parse_input_node(self, state: TaskSynthesizerState) -> Dict[str, Any]:
        """Parse user input to extract requirements and context."""
        logger.info(f"Parsing user input: {state['user_input']}")
        
        # Simple rule-based parsing for minimal implementation
        # In a real implementation, this would use the LLM
        requirements = {
            "type": "general_task",
            "urgency": "medium",
            "complexity": "medium",
            "context": state["user_input"].lower()
        }
        
        # Extract common patterns
        if any(word in state["user_input"].lower() for word in ["urgent", "asap", "immediately"]):
            requirements["urgency"] = "high"
        
        if any(word in state["user_input"].lower() for word in ["project", "complex", "multiple"]):
            requirements["complexity"] = "high"
        
        if any(word in state["user_input"].lower() for word in ["meeting", "call", "presentation"]):
            requirements["type"] = "meeting_task"
        
        if any(word in state["user_input"].lower() for word in ["research", "study", "learn"]):
            requirements["type"] = "research_task"
        
        logger.info(f"Parsed requirements: {requirements}")
        
        return {"parsed_requirements": requirements}
    
    def _generate_tasks_node(self, state: TaskSynthesizerState) -> Dict[str, Any]:
        """Generate task suggestions based on parsed requirements."""
        logger.info("Generating task suggestions")
        
        requirements = state["parsed_requirements"]
        task_type = requirements.get("type", "general_task")
        urgency = requirements.get("urgency", "medium")
        
        # Rule-based task generation based on type
        if task_type == "meeting_task":
            suggestions = self._generate_meeting_tasks(state["user_input"], urgency)
        elif task_type == "research_task":
            suggestions = self._generate_research_tasks(state["user_input"], urgency)
        else:
            suggestions = self._generate_general_tasks(state["user_input"], urgency)
        
        # Convert TaskSuggestion objects to dictionaries
        task_dicts = []
        for task in suggestions:
            task_dict = self._task_suggestion_to_dict(task)
            task_dicts.append(task_dict)
        
        logger.info(f"Generated {len(task_dicts)} task suggestions")
        
        return {"task_suggestions": task_dicts}
    
    def _generate_meeting_tasks(self, user_input: str, urgency: str) -> List[TaskSuggestion]:
        """Generate tasks for meeting-related requests."""
        priority = 2 if urgency == "high" else 1
        
        main_task = TaskSuggestion(
            content=f"Organize meeting: {user_input}",
            description="Main meeting organization task",
            priority=priority,
            due_date_days_offset=0 if urgency == "high" else 1,
            labels=["meeting", "organization"]
        )
        
        # Add common meeting subtasks
        subtasks = [
            TaskSuggestion(
                content="Schedule meeting time",
                description="Find suitable time for all participants",
                priority=priority,
                due_date_days_offset=-2,
                labels=["scheduling"]
            ),
            TaskSuggestion(
                content="Prepare meeting agenda",
                description="Create detailed agenda with topics to cover",
                priority=priority,
                due_date_days_offset=-1,
                labels=["preparation"]
            ),
            TaskSuggestion(
                content="Send meeting invitations",
                description="Send calendar invites to all participants",
                priority=priority,
                due_date_days_offset=-1,
                labels=["communication"]
            )
        ]
        
        main_task.subtasks = subtasks
        return [main_task]
    
    def _generate_research_tasks(self, user_input: str, urgency: str) -> List[TaskSuggestion]:
        """Generate tasks for research-related requests."""
        priority = 2 if urgency == "high" else 1
        
        main_task = TaskSuggestion(
            content=f"Research task: {user_input}",
            description="Main research task",
            priority=priority,
            due_date_days_offset=3 if urgency == "low" else 1,
            labels=["research", "learning"]
        )
        
        # Add common research subtasks
        subtasks = [
            TaskSuggestion(
                content="Define research scope",
                description="Clearly define what needs to be researched",
                priority=priority,
                due_date_days_offset=0,
                labels=["planning"]
            ),
            TaskSuggestion(
                content="Gather initial sources",
                description="Find relevant articles, papers, and resources",
                priority=priority,
                due_date_days_offset=1,
                labels=["information_gathering"]
            ),
            TaskSuggestion(
                content="Analyze findings",
                description="Review and analyze collected information",
                priority=priority,
                due_date_days_offset=2,
                labels=["analysis"]
            ),
            TaskSuggestion(
                content="Summarize results",
                description="Create summary of research findings",
                priority=priority,
                due_date_days_offset=3,
                labels=["documentation"]
            )
        ]
        
        main_task.subtasks = subtasks
        return [main_task]
    
    def _generate_general_tasks(self, user_input: str, urgency: str) -> List[TaskSuggestion]:
        """Generate tasks for general requests."""
        priority = 2 if urgency == "high" else 1
        
        main_task = TaskSuggestion(
            content=user_input,
            description=f"Task generated from: {user_input}",
            priority=priority,
            due_date_days_offset=0 if urgency == "high" else 1,
            labels=["auto_generated"]
        )
        
        # Add a simple subtask if the input suggests complexity
        if len(user_input.split()) > 5:  # More complex request
            subtask = TaskSuggestion(
                content=f"Plan approach for: {user_input[:50]}...",
                description="Planning subtask for complex request",
                priority=priority,
                due_date_days_offset=-1,
                labels=["planning"]
            )
            main_task.subtasks = [subtask]
        
        return [main_task]
    
    def _validate_tasks_node(self, state: TaskSynthesizerState) -> Dict[str, Any]:
        """Validate generated tasks for quality and completeness."""
        logger.info("Validating task suggestions")
        
        validation_results = {
            "valid_tasks": [],
            "issues": []
        }
        
        for task_dict in state["task_suggestions"]:
            issues = []
            
            # Basic validation
            if not task_dict.get("content") or len(task_dict["content"].strip()) < 3:
                issues.append("Task content too short")
            
            if task_dict.get("priority", 1) not in [1, 2, 3, 4]:
                issues.append("Invalid priority level")
            
            if not issues:
                validation_results["valid_tasks"].append(task_dict)
            else:
                validation_results["issues"].extend(issues)
        
        logger.info(f"Validation complete. {len(validation_results['valid_tasks'])} valid tasks")
        
        return {"validation_results": validation_results}
    
    def _finalize_tasks_node(self, state: TaskSynthesizerState) -> Dict[str, Any]:
        """Finalize the task suggestions for output."""
        logger.info("Finalizing task suggestions")
        
        # Use validated tasks
        final_tasks = state["validation_results"].get("valid_tasks", [])
        
        logger.info(f"Finalized {len(final_tasks)} tasks for creation")
        return {"final_tasks": final_tasks}
    
    def _task_suggestion_to_dict(self, task: TaskSuggestion) -> Dict[str, Any]:
        """Convert TaskSuggestion to dictionary."""
        task_dict = {
            'content': task.content,
            'description': task.description,
            'priority': task.priority,
            'due_date_days_offset': task.due_date_days_offset,
            'labels': task.labels,
            'subtasks': []
        }
        
        # Convert subtasks recursively
        for subtask in task.subtasks:
            subtask_dict = {
                'content': subtask.content,
                'description': subtask.description,
                'priority': subtask.priority,
                'due_date_days_offset': subtask.due_date_days_offset,
                'labels': subtask.labels
            }
            task_dict['subtasks'].append(subtask_dict)
        
        return task_dict
    
    def _dict_to_task_suggestion(self, task_dict: Dict[str, Any]) -> TaskSuggestion:
        """Convert dictionary to TaskSuggestion."""
        subtasks = []
        for subtask_dict in task_dict.get('subtasks', []):
            subtask = TaskSuggestion(
                content=subtask_dict['content'],
                description=subtask_dict['description'],
                priority=subtask_dict['priority'],
                due_date_days_offset=subtask_dict['due_date_days_offset'],
                labels=subtask_dict['labels']
            )
            subtasks.append(subtask)
        
        task = TaskSuggestion(
            content=task_dict['content'],
            description=task_dict['description'],
            priority=task_dict['priority'],
            due_date_days_offset=task_dict['due_date_days_offset'],
            labels=task_dict['labels'],
            subtasks=subtasks
        )
        
        return task
    
    def synthesize_tasks(self, user_input: str) -> List[TaskSuggestion]:
        """
        Main method to synthesize tasks from user input.
        
        Args:
            user_input: Natural language description of what the user wants to accomplish
            
        Returns:
            List of TaskSuggestion objects representing the generated tasks
        """
        logger.info(f"Starting task synthesis for input: {user_input}")
        
        # Initialize state
        initial_state: TaskSynthesizerState = {
            "messages": [],
            "user_input": user_input,
            "parsed_requirements": {},
            "task_suggestions": [],
            "validation_results": {},
            "final_tasks": []
        }
        
        # Run the workflow
        final_state = self.workflow.invoke(initial_state)
        
        # Convert final tasks back to TaskSuggestion objects
        tasks = []
        for task_dict in final_state["final_tasks"]:
            task = self._dict_to_task_suggestion(task_dict)
            tasks.append(task)
        
        logger.info(f"Task synthesis complete. Generated {len(tasks)} tasks")
        return tasks
    
    def tasks_to_dict(self, tasks: List[TaskSuggestion]) -> List[Dict[str, Any]]:
        """Convert TaskSuggestion objects to dictionary format for easier integration."""
        return [self._task_suggestion_to_dict(task) for task in tasks]