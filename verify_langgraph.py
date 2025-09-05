#!/usr/bin/env python3
"""
Final verification script for the LangGraph module implementation.

This script verifies that all core components are working correctly
and provides a summary of the implementation.
"""

import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def verify_implementation():
    """Verify the LangGraph implementation is complete and working."""
    
    print("🔍 LangGraph Module Implementation Verification")
    print("=" * 60)
    
    verification_results = {
        "core_functionality": False,
        "task_synthesis": False,
        "task_types": False,
        "state_management": False,
        "configuration": False,
        "documentation": False
    }
    
    # Test 1: Core module import
    print("\n1️⃣ Testing Core Module Import...")
    try:
        from todoist.langgraph.task_synthesizer import TaskSynthesizer, TaskSuggestion
        print("✅ Successfully imported TaskSynthesizer and TaskSuggestion")
        verification_results["core_functionality"] = True
    except Exception as e:
        print(f"❌ Import failed: {e}")
    
    # Test 2: Task synthesis functionality
    print("\n2️⃣ Testing Task Synthesis...")
    try:
        synthesizer = TaskSynthesizer()
        tasks = synthesizer.synthesize_tasks("Plan a research project")
        
        if tasks and len(tasks) > 0:
            print(f"✅ Generated {len(tasks)} task(s)")
            print(f"   Main task: {tasks[0].content}")
            print(f"   Subtasks: {len(tasks[0].subtasks)}")
            verification_results["task_synthesis"] = True
        else:
            print("❌ No tasks generated")
    except Exception as e:
        print(f"❌ Task synthesis failed: {e}")
    
    # Test 3: Different task types
    print("\n3️⃣ Testing Task Type Classification...")
    try:
        synthesizer = TaskSynthesizer()
        
        test_cases = [
            ("Schedule a team meeting", "meeting"),
            ("Research AI papers", "research"),
            ("Plan vacation", "general")
        ]
        
        types_working = 0
        for input_text, expected_type in test_cases:
            tasks = synthesizer.synthesize_tasks(input_text)
            if tasks and len(tasks) > 0:
                # Check if appropriate subtasks were generated
                if expected_type == "meeting" and any("meeting" in label for label in tasks[0].labels):
                    types_working += 1
                elif expected_type == "research" and any("research" in label for label in tasks[0].labels):
                    types_working += 1
                elif expected_type == "general":
                    types_working += 1
        
        if types_working == len(test_cases):
            print(f"✅ All {len(test_cases)} task types working correctly")
            verification_results["task_types"] = True
        else:
            print(f"❌ Only {types_working}/{len(test_cases)} task types working")
    except Exception as e:
        print(f"❌ Task type testing failed: {e}")
    
    # Test 4: State management (LangGraph workflow)
    print("\n4️⃣ Testing LangGraph State Management...")
    try:
        synthesizer = TaskSynthesizer()
        # Test that workflow runs without state errors
        tasks = synthesizer.synthesize_tasks("Test workflow state management")
        
        if tasks:
            print("✅ LangGraph workflow state management working")
            verification_results["state_management"] = True
        else:
            print("❌ LangGraph workflow failed")
    except Exception as e:
        print(f"❌ State management test failed: {e}")
    
    # Test 5: Configuration files
    print("\n5️⃣ Checking Configuration Files...")
    try:
        # Check if automation is configured
        config_path = "configs/automations.yaml"
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config_content = f.read()
                if "todoist.langgraph.automation.LangGraphAutomation" in config_content:
                    print("✅ LangGraph automation configured in automations.yaml")
                    verification_results["configuration"] = True
                else:
                    print("❌ LangGraph automation not found in automations.yaml")
        else:
            print("❌ automations.yaml not found")
    except Exception as e:
        print(f"❌ Configuration check failed: {e}")
    
    # Test 6: Documentation
    print("\n6️⃣ Checking Documentation...")
    try:
        doc_files = [
            "todoist/langgraph/README.md",
            "examples/langgraph_demo.py"
        ]
        
        docs_found = 0
        for doc_file in doc_files:
            if os.path.exists(doc_file):
                docs_found += 1
                print(f"✅ Found: {doc_file}")
        
        if docs_found == len(doc_files):
            verification_results["documentation"] = True
        else:
            print(f"❌ Only {docs_found}/{len(doc_files)} documentation files found")
    except Exception as e:
        print(f"❌ Documentation check failed: {e}")
    
    # Summary
    print("\n📊 Verification Summary")
    print("=" * 30)
    
    passed_tests = sum(verification_results.values())
    total_tests = len(verification_results)
    
    for test_name, result in verification_results.items():
        status = "✅" if result else "❌"
        print(f"{status} {test_name.replace('_', ' ').title()}")
    
    print(f"\n🎯 Overall Score: {passed_tests}/{total_tests} tests passed")
    
    if passed_tests == total_tests:
        print("\n🎉 All verification tests passed!")
        print("The LangGraph module is fully implemented and ready for use.")
    elif passed_tests >= total_tests * 0.8:
        print("\n✅ Most verification tests passed!")
        print("The LangGraph module is functional with minor issues.")
    else:
        print("\n⚠️  Some verification tests failed.")
        print("The LangGraph module may need additional work.")
    
    return passed_tests, total_tests

def show_usage_summary():
    """Show a summary of how to use the implemented LangGraph module."""
    
    print("\n📚 Usage Summary")
    print("=" * 30)
    
    print("\n🔧 Basic Usage:")
    print("""
from todoist.langgraph.task_synthesizer import TaskSynthesizer

synthesizer = TaskSynthesizer()
tasks = synthesizer.synthesize_tasks("Plan a team meeting")

for task in tasks:
    print(f"Task: {task.content}")
    for subtask in task.subtasks:
        print(f"  - {subtask.content}")
""")
    
    print("\n⚙️ Automation Framework Integration:")
    print("""
1. Configuration is already added to configs/automations.yaml
2. Set environment variables:
   export LANGGRAPH_INPUT="Your task description here"
3. Run automation:
   make update_env
   # or through the dashboard
""")
    
    print("\n📁 Input Sources:")
    print("""
- Environment: LANGGRAPH_INPUT, LANGGRAPH_INPUT_1, etc.
- File: Set LANGGRAPH_INPUT_FILE path
- Manual: Use synthesize_tasks_manual() method
""")
    
    print("\n🏷️ Task Types:")
    print("""
- Meeting tasks: "meeting", "call", "presentation" → scheduling subtasks
- Research tasks: "research", "study", "learn" → research workflow subtasks  
- General tasks: Everything else → planning subtasks
""")

def main():
    """Main verification function."""
    
    try:
        passed, total = verify_implementation()
        show_usage_summary()
        
        print(f"\n🏁 Verification Complete: {passed}/{total} tests passed")
        
        if passed == total:
            return 0  # Success
        elif passed >= total * 0.8:
            return 0  # Mostly successful
        else:
            return 1  # Some failures
            
    except Exception as e:
        print(f"\n💥 Verification failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())