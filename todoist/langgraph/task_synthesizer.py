"""
Task Synthesizer using LangGraph for automated task generation.

This module implements a LangGraph workflow that can analyze user input
and automatically generate structured tasks and subtasks using configurable
LLMs and intelligent label assignment.
"""

from typing import Dict, List, Any, Optional
try:
    from typing import TypedDict
except ImportError:
    # Fallback for older Python versions
    TypedDict = dict
from dataclasses import dataclass
import json
from datetime import datetime, timedelta

try:
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_core.prompts import ChatPromptTemplate
    from langgraph.graph import StateGraph, END
    from langgraph.graph.message import add_messages
    from typing_extensions import Annotated
    LANGGRAPH_AVAILABLE = True
except ImportError:
    # Fallback types when LangGraph is not available
    LANGGRAPH_AVAILABLE = False
    add_messages = lambda x: x  # Simple fallback
    try:
        from typing_extensions import Annotated
    except ImportError:
        # Fallback for older Python versions
        def Annotated(x, y): return x

try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

from .constants import (
    TaskTypes, UrgencyLevels, PriorityLevels, DefaultValues, ValidationLimits
)
from .config import get_config


@dataclass
class TaskSuggestion:
    """Represents a suggested task with its properties."""
    content: str
    description: str
    priority: int = PriorityLevels.MEDIUM
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
    from natural language input using configurable LLMs and intelligent
    label assignment.
    """
    
    def __init__(self, llm_manager: Optional['LLMManager'] = None):
        """
        Initialize the TaskSynthesizer.
        
        Args:
            llm_manager: LLM manager to use. If None, will create a default one.
        """
        self.config = get_config()
        
        # Import these conditionally to avoid dependency issues
        try:
            from .llm_integration import LLMManager
            from .label_manager import LabelManager
            
            self.llm_manager = llm_manager or LLMManager()
            self.label_manager = LabelManager()
        except ImportError as e:
            logger.warning(f"LLM or Label manager not available: {e}")
            self.llm_manager = None
            self.label_manager = None
        
        if LANGGRAPH_AVAILABLE:
            self.workflow = self._build_workflow()
        else:
            logger.warning("LangGraph not available, using simplified workflow")
            self.workflow = None
        
        logger.info(f"TaskSynthesizer initialized with LLM available: {self.llm_manager is not None}")
    
    def _get_default_llm(self):
        """Get a default LLM configuration using the LLM manager."""
        return self.llm_manager
    
    def _build_workflow(self) -> Optional[Any]:
        """Build the LangGraph workflow for task synthesis."""
        if not LANGGRAPH_AVAILABLE:
            logger.warning("LangGraph not available, workflow disabled")
            return None
            
        from langgraph.graph import StateGraph, END
        
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
        """Parse user input to extract requirements and context using intelligent analysis."""
        logger.info(f"Parsing user input: {state['user_input']}")
        
        user_input = state["user_input"].lower()
        
        # Initialize requirements with defaults
        requirements = {
            "type": TaskTypes.GENERAL,
            "urgency": UrgencyLevels.MEDIUM,
            "complexity": UrgencyLevels.MEDIUM,
            "context": user_input
        }
        
        # Get available labels safely
        available_labels = []
        if self.label_manager:
            try:
                available_labels = self.label_manager.get_available_labels()
            except Exception as e:
                logger.warning(f"Error getting available labels: {e}")
        
        requirements["available_labels"] = available_labels
        
        # Intelligent urgency detection
        urgency = self._detect_urgency(user_input)
        requirements["urgency"] = urgency
        
        # Task type classification
        task_type = self._classify_task_type(user_input)
        requirements["type"] = task_type
        
        # Complexity assessment
        complexity = self._assess_complexity(user_input, state["user_input"])
        requirements["complexity"] = complexity
        
        logger.info(f"Parsed requirements: {requirements}")
        
        return {"parsed_requirements": requirements}
    
    def _detect_urgency(self, user_input: str) -> str:
        """Detect urgency level from user input using improved logic."""
        # Check for urgent keywords
        urgent_keywords = DefaultValues.URGENT_KEYWORDS
        if any(keyword in user_input for keyword in urgent_keywords):
            return UrgencyLevels.HIGH
        
        # Check for time-sensitive phrases
        time_phrases = ["today", "now", "this morning", "this afternoon", "deadline"]
        if any(phrase in user_input for phrase in time_phrases):
            return UrgencyLevels.HIGH
        
        # Check for future time references
        future_phrases = ["tomorrow", "next week", "next month", "later", "someday"]
        if any(phrase in user_input for phrase in future_phrases):
            return UrgencyLevels.LOW
        
        return UrgencyLevels.MEDIUM
    
    def _classify_task_type(self, user_input: str) -> str:
        """Classify task type based on content analysis."""
        meeting_keywords = DefaultValues.MEETING_KEYWORDS
        research_keywords = DefaultValues.RESEARCH_KEYWORDS
        
        if any(keyword in user_input for keyword in meeting_keywords):
            return TaskTypes.MEETING
        
        if any(keyword in user_input for keyword in research_keywords):
            return TaskTypes.RESEARCH
        
        return TaskTypes.GENERAL
    
    def _assess_complexity(self, user_input_lower: str, original_input: str) -> str:
        """Assess task complexity based on multiple factors."""
        complexity_indicators = 0
        
        # Word count indicator
        word_count = len(original_input.split())
        if word_count > 10:
            complexity_indicators += 1
        
        # Complex keywords
        complex_keywords = DefaultValues.COMPLEX_KEYWORDS
        if any(keyword in user_input_lower for keyword in complex_keywords):
            complexity_indicators += 1
        
        # Multiple steps/phases indicated
        step_indicators = ["first", "then", "next", "finally", "step", "phase"]
        if any(indicator in user_input_lower for indicator in step_indicators):
            complexity_indicators += 1
        
        # Return complexity level
        if complexity_indicators >= 2:
            return UrgencyLevels.HIGH
        elif complexity_indicators == 1:
            return UrgencyLevels.MEDIUM
        else:
            return UrgencyLevels.LOW
    
    def _generate_tasks_node(self, state: TaskSynthesizerState) -> Dict[str, Any]:
        """Generate task suggestions using LLM or intelligent rule-based generation."""
        logger.info("Generating task suggestions using LLM integration")
        
        requirements = state["parsed_requirements"]
        task_type = requirements.get("type", TaskTypes.GENERAL)
        urgency = requirements.get("urgency", UrgencyLevels.MEDIUM)
        available_labels = requirements.get("available_labels", [])
        
        try:
            # Try to use LLM for intelligent generation
            if self.llm_manager and self.llm_manager.is_llm_available():
                suggestions = self._generate_tasks_with_llm(
                    state["user_input"], 
                    available_labels, 
                    requirements
                )
            else:
                # Fallback to intelligent rule-based generation
                suggestions = self._generate_tasks_intelligent_rules(
                    state["user_input"], 
                    task_type, 
                    urgency, 
                    available_labels
                )
            
        except Exception as e:
            logger.error(f"Error in task generation: {e}")
            # Fallback to basic generation
            suggestions = self._generate_basic_task(state["user_input"], urgency, available_labels)
        
        # Convert TaskSuggestion objects to dictionaries
        task_dicts = []
        for task in suggestions:
            task_dict = self._task_suggestion_to_dict(task)
            task_dicts.append(task_dict)
        
        logger.info(f"Generated {len(task_dicts)} task suggestions")
        
        return {"task_suggestions": task_dicts}
    
    def _generate_tasks_with_llm(
        self, 
        user_input: str, 
        available_labels: List[str], 
        requirements: Dict[str, Any]
    ) -> List[TaskSuggestion]:
        """Generate tasks using LLM."""
        try:
            llm_response = self.llm_manager.generate_task_suggestions(
                user_input, 
                available_labels, 
                requirements
            )
            
            # Convert LLM response to TaskSuggestion objects
            suggestions = self._convert_llm_response_to_tasks(llm_response, user_input, available_labels)
            return suggestions
            
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            # Fallback to rule-based generation
            return self._generate_tasks_intelligent_rules(
                user_input,
                requirements.get("type", TaskTypes.GENERAL),
                requirements.get("urgency", UrgencyLevels.MEDIUM),
                available_labels
            )
    
    def _convert_llm_response_to_tasks(
        self, 
        llm_response: Dict[str, Any], 
        user_input: str,
        available_labels: List[str]
    ) -> List[TaskSuggestion]:
        """Convert LLM response to TaskSuggestion objects."""
        main_task_content = llm_response.get("main_task", user_input)
        description = llm_response.get("description", f"Generated from: {user_input}")
        urgency = llm_response.get("urgency", UrgencyLevels.MEDIUM)
        
        # Map urgency to priority
        priority_mapping = self.config.get_priority_mapping()
        priority = priority_mapping.get(urgency, PriorityLevels.MEDIUM)
        
        # Get suggested labels and validate them
        suggested_labels = llm_response.get("suggested_labels", [])
        valid_labels = self.label_manager.validate_labels(suggested_labels)
        
        # If no valid labels, suggest some based on content
        if not valid_labels:
            valid_labels = self.label_manager.suggest_labels_for_task(
                main_task_content, 
                TaskTypes.GENERAL
            )
        
        main_task = TaskSuggestion(
            content=main_task_content,
            description=description,
            priority=priority,
            due_date_days_offset=self._calculate_due_date_offset(urgency),
            labels=valid_labels
        )
        
        # Add subtasks if suggested by LLM
        subtasks_data = llm_response.get("subtasks", [])
        subtasks = []
        for subtask_data in subtasks_data:
            if isinstance(subtask_data, dict):
                subtask_labels = self.label_manager.validate_labels(
                    subtask_data.get("labels", [])
                )
                subtask = TaskSuggestion(
                    content=subtask_data.get("content", ""),
                    description=subtask_data.get("description", ""),
                    priority=priority,
                    due_date_days_offset=subtask_data.get("due_date_days_offset", -1),
                    labels=subtask_labels
                )
                subtasks.append(subtask)
        
        main_task.subtasks = subtasks
        return [main_task]
    
    def _generate_tasks_intelligent_rules(
        self, 
        user_input: str, 
        task_type: str, 
        urgency: str, 
        available_labels: List[str]
    ) -> List[TaskSuggestion]:
        """Generate tasks using intelligent rule-based approach."""
        priority_mapping = self.config.get_priority_mapping()
        priority = priority_mapping.get(urgency, PriorityLevels.MEDIUM)
        
        # Get appropriate labels based on task type and content
        suggested_labels = self.label_manager.suggest_labels_for_task(user_input, task_type)
        
        # Create main task
        main_task = TaskSuggestion(
            content=user_input,
            description=f"Task generated from: {user_input}",
            priority=priority,
            due_date_days_offset=self._calculate_due_date_offset(urgency),
            labels=suggested_labels
        )
        
        # Generate contextual subtasks based on type and complexity
        subtasks = self._generate_contextual_subtasks(user_input, task_type, urgency, available_labels)
        main_task.subtasks = subtasks
        
        return [main_task]
    
    def _generate_contextual_subtasks(
        self, 
        user_input: str, 
        task_type: str, 
        urgency: str, 
        available_labels: List[str]
    ) -> List[TaskSuggestion]:
        """Generate contextual subtasks based on task analysis."""
        subtasks = []
        priority_mapping = self.config.get_priority_mapping()
        priority = priority_mapping.get(urgency, PriorityLevels.MEDIUM)
        
        # Basic planning subtask for complex tasks
        if len(user_input.split()) > ValidationLimits.MAX_WORD_COUNT_SIMPLE:
            planning_labels = self.label_manager.suggest_labels_for_task("planning", "general")
            subtasks.append(TaskSuggestion(
                content=f"Plan approach for: {user_input[:50]}{'...' if len(user_input) > 50 else ''}",
                description="Planning phase for complex task",
                priority=priority,
                due_date_days_offset=-1,
                labels=planning_labels
            ))
        
        # Type-specific subtasks with intelligent label assignment
        if task_type == TaskTypes.MEETING:
            meeting_subtasks = [
                ("Prepare for meeting", "Preparation phase", -1),
                ("Follow up after meeting", "Post-meeting activities", 1)
            ]
            for content, desc, offset in meeting_subtasks:
                labels = self.label_manager.suggest_labels_for_task(content, task_type)
                subtasks.append(TaskSuggestion(
                    content=content,
                    description=desc,
                    priority=priority,
                    due_date_days_offset=offset,
                    labels=labels
                ))
        
        elif task_type == TaskTypes.RESEARCH:
            research_subtasks = [
                ("Define research scope", "Scope definition phase", 0),
                ("Gather information", "Information collection phase", 1),
                ("Analyze findings", "Analysis phase", 2)
            ]
            for content, desc, offset in research_subtasks:
                labels = self.label_manager.suggest_labels_for_task(content, task_type)
                subtasks.append(TaskSuggestion(
                    content=content,
                    description=desc,
                    priority=priority,
                    due_date_days_offset=offset,
                    labels=labels
                ))
        
        return subtasks
    
    def _calculate_due_date_offset(self, urgency: str) -> int:
        """Calculate due date offset based on urgency level."""
        if urgency == UrgencyLevels.HIGH:
            return 0  # Today
        elif urgency == UrgencyLevels.MEDIUM:
            return 1  # Tomorrow
        else:  # LOW
            return 3  # In 3 days
    
    def _generate_basic_task(
        self, 
        user_input: str, 
        urgency: str, 
        available_labels: List[str]
    ) -> List[TaskSuggestion]:
        """Generate a basic task as fallback."""
        priority_mapping = self.config.get_priority_mapping()
        priority = priority_mapping.get(urgency, PriorityLevels.MEDIUM)
        
        # Get some basic labels
        basic_labels = self.label_manager.get_most_common_labels(2)
        
        task = TaskSuggestion(
            content=user_input,
            description=f"Basic task from: {user_input}",
            priority=priority,
            due_date_days_offset=self._calculate_due_date_offset(urgency),
            labels=basic_labels
        )
        
        return [task]
    
    def _validate_tasks_node(self, state: TaskSynthesizerState) -> Dict[str, Any]:
        """Validate generated tasks for quality and completeness."""
        logger.info("Validating task suggestions")
        
        validation_results = {
            "valid_tasks": [],
            "issues": []
        }
        
        for task_dict in state["task_suggestions"]:
            issues = []
            
            # Content validation
            content = task_dict.get("content", "").strip()
            if not content or len(content) < ValidationLimits.MIN_CONTENT_LENGTH:
                issues.append("Task content too short or empty")
            
            # Priority validation
            priority = task_dict.get("priority", PriorityLevels.MEDIUM)
            if not (ValidationLimits.MIN_PRIORITY <= priority <= ValidationLimits.MAX_PRIORITY):
                issues.append(f"Invalid priority level: {priority}")
                # Fix the priority
                task_dict["priority"] = PriorityLevels.MEDIUM
            
            # Label validation - ensure labels exist in Todoist
            labels = task_dict.get("labels", [])
            if labels and self.label_manager:
                try:
                    valid_labels = self.label_manager.validate_labels(labels)
                    if len(valid_labels) != len(labels):
                        logger.warning(f"Some labels were invalid and removed: {labels} -> {valid_labels}")
                    task_dict["labels"] = valid_labels
                except Exception as e:
                    logger.warning(f"Error validating labels: {e}")
                    task_dict["labels"] = []
            
            # Subtask validation
            subtasks = task_dict.get("subtasks", [])
            valid_subtasks = []
            for subtask in subtasks:
                if isinstance(subtask, dict) and subtask.get("content"):
                    # Validate subtask labels too
                    subtask_labels = subtask.get("labels", [])
                    if subtask_labels and self.label_manager:
                        try:
                            valid_subtask_labels = self.label_manager.validate_labels(subtask_labels)
                            subtask["labels"] = valid_subtask_labels
                        except Exception as e:
                            logger.warning(f"Error validating subtask labels: {e}")
                            subtask["labels"] = []
                    valid_subtasks.append(subtask)
            task_dict["subtasks"] = valid_subtasks
            
            if not issues:
                validation_results["valid_tasks"].append(task_dict)
            else:
                validation_results["issues"].extend(issues)
                # Still include the task but with fixes applied
                validation_results["valid_tasks"].append(task_dict)
        
        logger.info(f"Validation complete. {len(validation_results['valid_tasks'])} valid tasks, {len(validation_results['issues'])} issues")
        
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
        
        if self.workflow is not None and LANGGRAPH_AVAILABLE:
            return self._synthesize_with_langgraph(user_input)
        else:
            return self._synthesize_with_fallback(user_input)
    
    def _synthesize_with_langgraph(self, user_input: str) -> List[TaskSuggestion]:
        """Synthesize tasks using LangGraph workflow."""
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
    
    def _synthesize_with_fallback(self, user_input: str) -> List[TaskSuggestion]:
        """Fallback task synthesis when LangGraph is not available."""
        logger.info("Using fallback task synthesis")
        
        try:
            # Parse input manually
            requirements = self._parse_input_manually(user_input)
            
            # Generate tasks
            if self.llm_manager and self.llm_manager.is_llm_available():
                available_labels = self.label_manager.get_available_labels() if self.label_manager else []
                tasks = self._generate_tasks_with_llm(user_input, available_labels, requirements)
            else:
                tasks = self._generate_fallback_task(user_input, requirements)
            
            logger.info(f"Fallback synthesis complete. Generated {len(tasks)} tasks")
            return tasks
            
        except Exception as e:
            logger.error(f"Error in fallback synthesis: {e}")
            return self._generate_basic_fallback_task(user_input)
    
    def _parse_input_manually(self, user_input: str) -> Dict[str, Any]:
        """Manual input parsing when LangGraph is not available."""
        user_input_lower = user_input.lower()
        
        # Basic urgency detection
        urgency = UrgencyLevels.MEDIUM
        if any(keyword in user_input_lower for keyword in DefaultValues.URGENT_KEYWORDS):
            urgency = UrgencyLevels.HIGH
        elif any(phrase in user_input_lower for phrase in ["tomorrow", "next week", "later"]):
            urgency = UrgencyLevels.LOW
        
        # Basic task type detection
        task_type = TaskTypes.GENERAL
        if any(keyword in user_input_lower for keyword in DefaultValues.MEETING_KEYWORDS):
            task_type = TaskTypes.MEETING
        elif any(keyword in user_input_lower for keyword in DefaultValues.RESEARCH_KEYWORDS):
            task_type = TaskTypes.RESEARCH
        
        return {
            "type": task_type,
            "urgency": urgency,
            "complexity": UrgencyLevels.MEDIUM,
            "context": user_input_lower,
            "available_labels": self.label_manager.get_available_labels() if self.label_manager else []
        }
    
    def _generate_fallback_task(self, user_input: str, requirements: Dict[str, Any]) -> List[TaskSuggestion]:
        """Generate a basic task when advanced methods are not available."""
        urgency = requirements.get("urgency", UrgencyLevels.MEDIUM)
        priority_mapping = self.config.get_priority_mapping()
        priority = priority_mapping.get(urgency, PriorityLevels.MEDIUM)
        
        # Basic label assignment
        labels = []
        if self.label_manager:
            try:
                labels = self.label_manager.suggest_labels_for_task(
                    user_input, 
                    requirements.get("type", TaskTypes.GENERAL)
                )
            except Exception as e:
                logger.warning(f"Error getting labels: {e}")
        
        task = TaskSuggestion(
            content=user_input,
            description=f"Task created from: {user_input}",
            priority=priority,
            due_date_days_offset=self._calculate_due_date_offset(urgency),
            labels=labels
        )
        
        return [task]
    
    def _generate_basic_fallback_task(self, user_input: str) -> List[TaskSuggestion]:
        """Generate the most basic task possible."""
        task = TaskSuggestion(
            content=user_input,
            description=f"Basic task from: {user_input}",
            priority=PriorityLevels.MEDIUM,
            due_date_days_offset=1,
            labels=[]
        )
        
        return [task]
    
    def tasks_to_dict(self, tasks: List[TaskSuggestion]) -> List[Dict[str, Any]]:
        """Convert TaskSuggestion objects to dictionary format for easier integration."""
        return [self._task_suggestion_to_dict(task) for task in tasks]