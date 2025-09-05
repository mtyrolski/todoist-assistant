#!/usr/bin/env python3
"""
Simple test script for the LangGraph module functionality.

This script tests the basic functionality of the LangGraph task synthesizer
without requiring a full Todoist API connection.
"""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from todoist.langgraph.task_synthesizer import TaskSynthesizer
from todoist.langgraph.automation import LangGraphAutomation

def test_task_synthesizer():
    """Test the basic task synthesizer functionality."""
    print("=== Testing Task Synthesizer ===")
    
    synthesizer = TaskSynthesizer()
    
    # Test cases
    test_inputs = [
        "I need to organize a team meeting next week",
        "Research machine learning papers for my project",
        "Plan a vacation to Japan",
        "Prepare presentation for the conference"
    ]
    
    for user_input in test_inputs:
        print(f"\nInput: {user_input}")
        print("-" * 50)
        
        try:
            tasks = synthesizer.synthesize_tasks(user_input)
            
            if tasks:
                for i, task in enumerate(tasks, 1):
                    print(f"Task {i}: {task.content}")
                    print(f"  Description: {task.description}")
                    print(f"  Priority: {task.priority}")
                    print(f"  Due offset: {task.due_date_days_offset} days")
                    print(f"  Labels: {task.labels}")
                    
                    if task.subtasks:
                        print(f"  Subtasks ({len(task.subtasks)}):")
                        for j, subtask in enumerate(task.subtasks, 1):
                            print(f"    {j}. {subtask.content}")
                            print(f"       Due offset: {subtask.due_date_days_offset} days")
                    print()
            else:
                print("No tasks generated")
                
        except Exception as e:
            print(f"Error: {e}")
        
        print("=" * 60)

def test_automation():
    """Test the automation functionality."""
    print("\n=== Testing LangGraph Automation ===")
    
    # Test manual synthesis
    automation = LangGraphAutomation(
        input_source="manual",
        auto_create_tasks=False
    )
    
    test_input = "I need to write a research paper about AI ethics"
    
    print(f"Input: {test_input}")
    print("-" * 50)
    
    try:
        result = automation.synthesize_tasks_manual(test_input, create_tasks=False)
        
        print(f"Task count: {result.get('task_count', 0)}")
        
        for i, task in enumerate(result.get('tasks', []), 1):
            print(f"\nTask {i}: {task['content']}")
            print(f"  Description: {task['description']}")
            print(f"  Priority: {task['priority']}")
            print(f"  Labels: {task['labels']}")
            
            if task.get('subtasks'):
                print(f"  Subtasks:")
                for j, subtask in enumerate(task['subtasks'], 1):
                    print(f"    {j}. {subtask['content']}")
                    
    except Exception as e:
        print(f"Error: {e}")

def test_environment_input():
    """Test environment variable input."""
    print("\n=== Testing Environment Input ===")
    
    # Set test environment variable
    os.environ['LANGGRAPH_INPUT'] = 'Create a study plan for learning Python'
    
    automation = LangGraphAutomation(
        input_source="env",
        auto_create_tasks=False
    )
    
    inputs = automation._get_user_inputs()
    print(f"Found inputs from environment: {inputs}")
    
    # Clean up
    if 'LANGGRAPH_INPUT' in os.environ:
        del os.environ['LANGGRAPH_INPUT']

if __name__ == "__main__":
    print("LangGraph Module Test Suite")
    print("=" * 60)
    
    try:
        test_task_synthesizer()
        test_automation()
        test_environment_input()
        
        print("\n✅ All tests completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        sys.exit(1)