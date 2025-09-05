#!/usr/bin/env python3
"""
Example usage of the LangGraph module for automated task synthesis.

This script demonstrates how to use the LangGraph module to generate
tasks and subtasks from natural language input.
"""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from todoist.langgraph.task_synthesizer import TaskSynthesizer

def main():
    """Demonstrate LangGraph task synthesis functionality."""
    
    print("🤖 LangGraph Task Synthesis Demo")
    print("=" * 50)
    
    # Initialize the task synthesizer
    synthesizer = TaskSynthesizer()
    
    # Example inputs covering different task types
    examples = [
        {
            "input": "I need to organize a quarterly team meeting next month",
            "description": "Meeting organization task"
        },
        {
            "input": "Research latest developments in quantum computing",
            "description": "Research task"
        },
        {
            "input": "Plan a vacation to Tokyo for next summer",
            "description": "General planning task"
        },
        {
            "input": "URGENT: Prepare presentation for tomorrow's client meeting",
            "description": "Urgent meeting task"
        },
        {
            "input": "Study machine learning algorithms for the upcoming project",
            "description": "Learning task"
        }
    ]
    
    for i, example in enumerate(examples, 1):
        print(f"\n📝 Example {i}: {example['description']}")
        print("-" * 50)
        print(f"Input: \"{example['input']}\"")
        print()
        
        try:
            # Generate tasks using LangGraph
            tasks = synthesizer.synthesize_tasks(example['input'])
            
            if tasks:
                for j, task in enumerate(tasks, 1):
                    print(f"🎯 Generated Task {j}:")
                    print(f"   Title: {task.content}")
                    print(f"   Description: {task.description}")
                    print(f"   Priority: {task.priority}")
                    print(f"   Due in: {task.due_date_days_offset} days")
                    print(f"   Labels: {', '.join(task.labels)}")
                    
                    if task.subtasks:
                        print(f"   📋 Subtasks ({len(task.subtasks)}):")
                        for k, subtask in enumerate(task.subtasks, 1):
                            print(f"      {k}. {subtask.content}")
                            print(f"         Due in: {subtask.due_date_days_offset} days")
                            print(f"         Labels: {', '.join(subtask.labels)}")
                    print()
            else:
                print("❌ No tasks generated")
                
        except Exception as e:
            print(f"❌ Error: {e}")
        
        print("=" * 60)
    
    # Demonstrate task conversion to dictionary format
    print("\n🔄 Task Conversion Demo")
    print("-" * 50)
    
    sample_input = "Write a research paper on artificial intelligence ethics"
    tasks = synthesizer.synthesize_tasks(sample_input)
    task_dicts = synthesizer.tasks_to_dict(tasks)
    
    print(f"Input: \"{sample_input}\"")
    print(f"Generated {len(task_dicts)} task(s) as dictionaries:")
    
    for i, task_dict in enumerate(task_dicts, 1):
        print(f"\nTask {i} (Dictionary format):")
        print(f"  Content: {task_dict['content']}")
        print(f"  Description: {task_dict['description']}")
        print(f"  Priority: {task_dict['priority']}")
        print(f"  Due offset: {task_dict['due_date_days_offset']} days")
        print(f"  Labels: {task_dict['labels']}")
        print(f"  Subtasks: {len(task_dict['subtasks'])}")
        
        for j, subtask in enumerate(task_dict['subtasks'], 1):
            print(f"    {j}. {subtask['content']} (due: {subtask['due_date_days_offset']} days)")
    
    print("\n✅ Demo completed successfully!")
    print("\nTo integrate with Todoist:")
    print("1. Set auto_create_tasks=True in automation configuration")
    print("2. Ensure you have a valid .env file with Todoist API key")
    print("3. Run through the automation framework")

if __name__ == "__main__":
    main()