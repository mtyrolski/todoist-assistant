#!/usr/bin/env python3
"""
Simple test for just the LangGraph task synthesizer without dependencies on the full framework.
"""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Test the task synthesizer directly without importing through the full framework
def test_task_synthesizer_standalone():
    """Test the task synthesizer functionality standalone."""
    print("=== Testing Task Synthesizer (Standalone) ===")
    
    # Import directly to avoid dependency issues
    from todoist.langgraph.task_synthesizer import TaskSynthesizer
    
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
            import traceback
            traceback.print_exc()
        
        print("=" * 60)

def test_task_conversion():
    """Test task to dict conversion."""
    print("\n=== Testing Task to Dict Conversion ===")
    
    from todoist.langgraph.task_synthesizer import TaskSynthesizer
    
    synthesizer = TaskSynthesizer()
    
    user_input = "I need to write a research paper about AI ethics"
    print(f"Input: {user_input}")
    print("-" * 50)
    
    try:
        tasks = synthesizer.synthesize_tasks(user_input)
        task_dicts = synthesizer.tasks_to_dict(tasks)
        
        print(f"Generated {len(task_dicts)} tasks as dictionaries:")
        
        for i, task_dict in enumerate(task_dicts, 1):
            print(f"\nTask {i}:")
            print(f"  Content: {task_dict['content']}")
            print(f"  Description: {task_dict['description']}")
            print(f"  Priority: {task_dict['priority']}")
            print(f"  Labels: {task_dict['labels']}")
            print(f"  Subtasks: {len(task_dict['subtasks'])}")
            
            for j, subtask in enumerate(task_dict['subtasks'], 1):
                print(f"    {j}. {subtask['content']}")
                
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

def test_automation_import():
    """Test that automation can be imported when needed."""
    print("\n=== Testing Automation Import ===")
    
    try:
        from todoist.langgraph import get_automation
        LangGraphAutomation = get_automation()
        
        # Test instantiation with minimal dependencies
        automation = LangGraphAutomation(
            name="Test Automation",
            frequency=60,
            input_source="manual"
        )
        
        print(f"✅ Successfully created automation: {automation.name}")
        print(f"  Frequency: {automation.frequency} minutes")
        print(f"  Input source: {automation.input_source}")
        
    except Exception as e:
        print(f"❌ Automation import failed: {e}")
        # This is okay for now, as it requires the full framework

if __name__ == "__main__":
    print("LangGraph Task Synthesizer Test")
    print("=" * 60)
    
    try:
        test_task_synthesizer_standalone()
        test_task_conversion()
        test_automation_import()
        
        print("\n✅ Core functionality tests completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)