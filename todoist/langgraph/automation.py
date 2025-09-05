"""
LangGraph Automation for Todoist Assistant.

This module provides an automation that integrates LangGraph task synthesis
with the existing Todoist automation framework.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import os

from loguru import logger

from todoist.automations.base import Automation
from todoist.database.base import Database
from .task_synthesizer import TaskSynthesizer, TaskSuggestion


class LangGraphAutomation(Automation):
    """
    Automation that uses LangGraph to synthesize and create tasks automatically.
    
    This automation can process user input and automatically generate
    structured tasks and subtasks using the LangGraph workflow.
    """
    
    def __init__(
        self, 
        name: str = "LangGraph Task Synthesizer", 
        frequency: float = 1440,  # Run once per day by default
        is_long: bool = False,
        input_source: str = "manual",
        auto_create_tasks: bool = False
    ):
        """
        Initialize the LangGraph automation.
        
        Args:
            name: Name of the automation
            frequency: Frequency in minutes between runs
            is_long: Whether this is a long-running automation
            input_source: Source of input ("manual", "file", "env")
            auto_create_tasks: Whether to automatically create tasks in Todoist
        """
        super().__init__(name, frequency, is_long)
        self.input_source = input_source
        self.auto_create_tasks = auto_create_tasks
        self.task_synthesizer = TaskSynthesizer()
        
        logger.info(f"Initialized LangGraph automation with input_source='{input_source}', auto_create={auto_create_tasks}")
    
    def _tick(self, db: Database) -> List[Dict[str, Any]]:
        """
        Main automation tick that processes input and synthesizes tasks.
        
        Args:
            db: Database connection for task creation
            
        Returns:
            List of task delegation results
        """
        logger.info("Starting LangGraph automation tick")
        
        try:
            # Get user input based on source
            user_inputs = self._get_user_inputs()
            
            if not user_inputs:
                logger.info("No user inputs found, skipping task synthesis")
                return []
            
            results = []
            
            for user_input in user_inputs:
                logger.info(f"Processing input: {user_input}")
                
                # Synthesize tasks using LangGraph
                task_suggestions = self.task_synthesizer.synthesize_tasks(user_input)
                
                if not task_suggestions:
                    logger.warning(f"No tasks generated for input: {user_input}")
                    continue
                
                # Process the generated tasks
                task_results = self._process_task_suggestions(db, task_suggestions, user_input)
                results.extend(task_results)
            
            logger.info(f"LangGraph automation completed. Processed {len(results)} tasks")
            return results
            
        except Exception as e:
            logger.error(f"Error in LangGraph automation: {e}")
            return []
    
    def _get_user_inputs(self) -> List[str]:
        """
        Get user inputs based on the configured input source.
        
        Returns:
            List of user input strings to process
        """
        if self.input_source == "env":
            return self._get_inputs_from_env()
        elif self.input_source == "file":
            return self._get_inputs_from_file()
        elif self.input_source == "manual":
            return self._get_manual_inputs()
        else:
            logger.warning(f"Unknown input source: {self.input_source}")
            return []
    
    def _get_inputs_from_env(self) -> List[str]:
        """Get inputs from environment variables."""
        inputs = []
        
        # Check for LANGGRAPH_INPUT environment variable
        env_input = os.getenv("LANGGRAPH_INPUT")
        if env_input:
            inputs.append(env_input)
            logger.info(f"Found input from environment: {env_input}")
        
        # Check for multiple inputs (LANGGRAPH_INPUT_1, LANGGRAPH_INPUT_2, etc.)
        i = 1
        while True:
            env_key = f"LANGGRAPH_INPUT_{i}"
            env_value = os.getenv(env_key)
            if env_value:
                inputs.append(env_value)
                logger.info(f"Found input from {env_key}: {env_value}")
                i += 1
            else:
                break
        
        return inputs
    
    def _get_inputs_from_file(self) -> List[str]:
        """Get inputs from a file."""
        file_path = os.getenv("LANGGRAPH_INPUT_FILE", "langgraph_inputs.txt")
        
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    inputs = [line.strip() for line in f.readlines() if line.strip()]
                
                logger.info(f"Read {len(inputs)} inputs from file: {file_path}")
                
                # Clear the file after reading (optional)
                if os.getenv("LANGGRAPH_CLEAR_FILE_AFTER_READ", "false").lower() == "true":
                    open(file_path, 'w').close()
                    logger.info(f"Cleared input file: {file_path}")
                
                return inputs
            else:
                logger.info(f"Input file not found: {file_path}")
                return []
                
        except Exception as e:
            logger.error(f"Error reading input file {file_path}: {e}")
            return []
    
    def _get_manual_inputs(self) -> List[str]:
        """Get manual inputs (for demonstration/testing)."""
        # This would typically be empty for production
        # For demo purposes, we can include some sample inputs
        demo_inputs = os.getenv("LANGGRAPH_DEMO_INPUTS")
        if demo_inputs:
            return [demo_inputs]
        
        return []
    
    def _process_task_suggestions(
        self, 
        db: Database, 
        task_suggestions: List[TaskSuggestion], 
        original_input: str
    ) -> List[Dict[str, Any]]:
        """
        Process the task suggestions and optionally create them in Todoist.
        
        Args:
            db: Database connection
            task_suggestions: List of generated task suggestions
            original_input: Original user input
            
        Returns:
            List of processing results
        """
        results = []
        
        for task in task_suggestions:
            result = {
                'action': 'task_synthesis',
                'original_input': original_input,
                'task_content': task.content,
                'task_description': task.description,
                'priority': task.priority,
                'labels': task.labels,
                'subtask_count': len(task.subtasks),
                'created': False,
                'error': None
            }
            
            try:
                if self.auto_create_tasks:
                    # Create the main task
                    task_result = self._create_task_in_todoist(db, task)
                    result['created'] = task_result.get('success', False)
                    result['task_id'] = task_result.get('task_id')
                    
                    if result['created']:
                        logger.info(f"Created task: {task.content}")
                        
                        # Create subtasks
                        subtask_results = []
                        for subtask in task.subtasks:
                            subtask_result = self._create_task_in_todoist(
                                db, 
                                subtask, 
                                parent_id=task_result.get('task_id')
                            )
                            subtask_results.append(subtask_result)
                            
                            if subtask_result.get('success'):
                                logger.info(f"Created subtask: {subtask.content}")
                        
                        result['subtask_results'] = subtask_results
                    else:
                        logger.error(f"Failed to create task: {task.content}")
                        result['error'] = task_result.get('error', 'Unknown error')
                
                else:
                    logger.info(f"Task suggestion generated (not created): {task.content}")
                    result['message'] = 'Task suggested but not created (auto_create_tasks=False)'
                
            except Exception as e:
                logger.error(f"Error processing task suggestion: {e}")
                result['error'] = str(e)
            
            results.append(result)
        
        return results
    
    def _create_task_in_todoist(
        self, 
        db: Database, 
        task: TaskSuggestion, 
        parent_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a task in Todoist using the database interface.
        
        Args:
            db: Database connection
            task: Task suggestion to create
            parent_id: Parent task ID for subtasks
            
        Returns:
            Dictionary with creation result
        """
        try:
            # Calculate due date if offset is specified
            due_date = None
            if task.due_date_days_offset != 0:
                target_date = datetime.now() + timedelta(days=task.due_date_days_offset)
                due_date = target_date.strftime("%Y-%m-%d")
            
            # Prepare task parameters
            task_params = {
                'content': task.content,
                'description': task.description,
                'priority': task.priority
            }
            
            if due_date:
                task_params['due_date'] = due_date
            
            if parent_id:
                task_params['parent_id'] = parent_id
            
            if task.labels:
                # Note: This depends on how labels are handled in the database
                task_params['labels'] = task.labels
            
            # Create the task using the database interface
            result = db.insert_task(**task_params)
            
            if isinstance(result, dict) and 'error' not in result:
                return {
                    'success': True,
                    'task_id': result.get('id'),
                    'result': result
                }
            else:
                return {
                    'success': False,
                    'error': result.get('error', 'Unknown error') if isinstance(result, dict) else str(result)
                }
                
        except Exception as e:
            logger.error(f"Error creating task in Todoist: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def synthesize_tasks_manual(self, user_input: str, create_tasks: bool = False) -> Dict[str, Any]:
        """
        Manual method to synthesize tasks for testing/development.
        
        Args:
            user_input: User input to process
            create_tasks: Whether to create tasks in Todoist
            
        Returns:
            Dictionary with synthesis results
        """
        logger.info(f"Manual task synthesis for: {user_input}")
        
        try:
            # Synthesize tasks
            task_suggestions = self.task_synthesizer.synthesize_tasks(user_input)
            
            result = {
                'user_input': user_input,
                'task_count': len(task_suggestions),
                'tasks': self.task_synthesizer.tasks_to_dict(task_suggestions),
                'created_tasks': []
            }
            
            if create_tasks:
                # This would require a database connection
                # For now, just log that creation was requested
                logger.info("Task creation requested but no database connection available")
                result['creation_requested'] = True
            
            return result
            
        except Exception as e:
            logger.error(f"Error in manual task synthesis: {e}")
            return {
                'user_input': user_input,
                'error': str(e)
            }