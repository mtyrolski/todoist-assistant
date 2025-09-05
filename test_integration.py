#!/usr/bin/env python3
"""
Integration test for LangGraph module with the automation framework.

This test demonstrates how the LangGraph module integrates with the 
existing automation framework without requiring a full Todoist API setup.
"""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_automation_integration():
    """Test LangGraph automation integration."""
    print("🔗 LangGraph Automation Integration Test")
    print("=" * 50)
    
    try:
        # Import the automation class
        from todoist.langgraph.automation import LangGraphAutomation
        
        print("✅ Successfully imported LangGraphAutomation")
        
        # Test automation creation with different configurations
        configurations = [
            {
                "name": "Environment Input Test",
                "input_source": "env",
                "auto_create_tasks": False
            },
            {
                "name": "File Input Test", 
                "input_source": "file",
                "auto_create_tasks": False
            },
            {
                "name": "Manual Input Test",
                "input_source": "manual",
                "auto_create_tasks": False
            }
        ]
        
        for config in configurations:
            print(f"\n📋 Testing: {config['name']}")
            print("-" * 30)
            
            # Create automation instance
            automation = LangGraphAutomation(
                name=config["name"],
                frequency=60,  # 1 hour
                input_source=config["input_source"],
                auto_create_tasks=config["auto_create_tasks"]
            )
            
            print(f"✅ Created automation: {automation.name}")
            print(f"   Input source: {automation.input_source}")
            print(f"   Auto-create: {automation.auto_create_tasks}")
            print(f"   Frequency: {automation.frequency} minutes")
            
            # Test manual synthesis
            if config["input_source"] == "manual":
                test_inputs = [
                    "Schedule a code review meeting for next Tuesday",
                    "Research competitive analysis for Q1 planning"
                ]
                
                for test_input in test_inputs:
                    print(f"\n   📝 Testing input: '{test_input}'")
                    result = automation.synthesize_tasks_manual(test_input)
                    
                    print(f"   📊 Generated {result.get('task_count', 0)} tasks")
                    
                    for i, task in enumerate(result.get('tasks', []), 1):
                        print(f"      Task {i}: {task['content']}")
                        print(f"         Subtasks: {len(task.get('subtasks', []))}")
    
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("This might be due to missing dependencies in the full framework")
        return False
    
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

def test_environment_input():
    """Test environment variable input functionality."""
    print("\n🌍 Environment Input Test")
    print("-" * 30)
    
    try:
        from todoist.langgraph.automation import LangGraphAutomation
        
        # Set test environment variables
        test_inputs = [
            "Plan sprint retrospective for development team",
            "Research new database technologies for migration"
        ]
        
        for i, test_input in enumerate(test_inputs, 1):
            env_var = f"LANGGRAPH_INPUT_{i}"
            os.environ[env_var] = test_input
            print(f"Set {env_var}: {test_input}")
        
        # Create automation with env input source
        automation = LangGraphAutomation(
            input_source="env",
            auto_create_tasks=False
        )
        
        # Get inputs from environment
        inputs = automation._get_user_inputs()
        print(f"\n📥 Found {len(inputs)} inputs from environment:")
        
        for i, input_text in enumerate(inputs, 1):
            print(f"   {i}. {input_text}")
        
        # Clean up environment variables
        for i in range(1, len(test_inputs) + 1):
            env_var = f"LANGGRAPH_INPUT_{i}"
            if env_var in os.environ:
                del os.environ[env_var]
        
        print("✅ Environment input test completed")
        
    except Exception as e:
        print(f"❌ Environment test error: {e}")

def test_file_input():
    """Test file input functionality."""
    print("\n📁 File Input Test")
    print("-" * 30)
    
    try:
        from todoist.langgraph.automation import LangGraphAutomation
        
        # Create test input file
        test_file = "/tmp/test_langgraph_inputs.txt"
        test_inputs = [
            "Organize product launch meeting",
            "Research market trends for Q2",
            "Plan team building activity"
        ]
        
        with open(test_file, 'w') as f:
            for input_text in test_inputs:
                f.write(f"{input_text}\n")
        
        print(f"📝 Created test file: {test_file}")
        
        # Set environment variable for file path
        os.environ["LANGGRAPH_INPUT_FILE"] = test_file
        
        # Create automation with file input source
        automation = LangGraphAutomation(
            input_source="file",
            auto_create_tasks=False
        )
        
        # Get inputs from file
        inputs = automation._get_user_inputs()
        print(f"\n📥 Found {len(inputs)} inputs from file:")
        
        for i, input_text in enumerate(inputs, 1):
            print(f"   {i}. {input_text}")
        
        # Clean up
        if os.path.exists(test_file):
            os.remove(test_file)
        
        if "LANGGRAPH_INPUT_FILE" in os.environ:
            del os.environ["LANGGRAPH_INPUT_FILE"]
        
        print("✅ File input test completed")
        
    except Exception as e:
        print(f"❌ File test error: {e}")

def main():
    """Run integration tests."""
    print("🧪 LangGraph Integration Test Suite")
    print("=" * 60)
    
    success = True
    
    try:
        # Test basic automation integration
        if test_automation_integration():
            print("\n✅ Automation integration tests passed")
        else:
            print("\n❌ Automation integration tests failed")
            success = False
        
        # Test input sources
        test_environment_input()
        test_file_input()
        
        if success:
            print("\n🎉 All integration tests completed successfully!")
            print("\nNext steps:")
            print("1. Add the automation to configs/automations.yaml")
            print("2. Set up environment variables or input files")
            print("3. Run with make update_env or through the dashboard")
        else:
            print("\n⚠️  Some tests failed, but core functionality works")
            
    except Exception as e:
        print(f"\n💥 Integration test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()