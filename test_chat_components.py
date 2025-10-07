#!/usr/bin/env python
"""
Simple test script to verify the chat components work end-to-end.
"""
import json
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent.tools.repl_tool import run_python
from config.settings import get_settings
from todoist.types import Event, EventEntry


def test_repl_with_events():
    """Test REPL tool with sample events."""
    print("Testing REPL tool with sample events...")
    
    # Create sample events
    events = []
    for i in range(5):
        event_entry = EventEntry(
            id=f"event_{i}",
            object_type="item",
            object_id=f"task_{i}",
            event_type="completed" if i % 2 == 0 else "added",
            event_date=f"2024-01-0{i+1}T10:00:00Z",
            parent_project_id=f"project_{i}",
            parent_item_id=None,
            initiator_id="user_1",
            extra_data={"content": f"Task {i}"},
            extra_data_id=f"extra_{i}",
            v2_object_id=f"v2_task_{i}",
            v2_parent_item_id=None,
            v2_parent_project_id=f"v2_project_{i}"
        )
        import datetime as dt
        event = Event(
            event_entry=event_entry,
            id=f"event_{i}",
            date=dt.datetime(2024, 1, i+1, 10, 0, 0)
        )
        events.append(event)
    
    # Test 1: Count events
    print("\n1. Testing event count...")
    result = run_python("len(events)", events)
    if result.error:
        print(f"   ❌ Error: {result.error}")
        return False
    print(f"   ✓ Success: {result.value_repr}")
    
    # Test 2: Print output
    print("\n2. Testing print output...")
    result = run_python("print('Hello from REPL')", events)
    if result.error:
        print(f"   ❌ Error: {result.error}")
        return False
    print(f"   ✓ Output: {result.stdout.strip()}")
    
    # Test 3: List comprehension
    print("\n3. Testing list comprehension...")
    result = run_python("x = [e.event_type for e in events]", events)
    if result.error:
        print(f"   ❌ Error: {result.error}")
        return False
    print(f"   ✓ Success (completed in {result.exec_time_ms}ms)")
    
    # Test 4: Filter events
    print("\n4. Testing event filtering...")
    code = """
completed = [e for e in events if e.event_type == 'completed']
print(f"Completed: {len(completed)}")
len(completed)
"""
    result = run_python(code, events)
    if result.error:
        print(f"   ❌ Error: {result.error}")
        return False
    print(f"   ✓ Output: {result.stdout.strip()}")
    print(f"   ✓ Result: {result.value_repr}")
    
    # Test 5: Security - try to import (should fail)
    print("\n5. Testing security (import restriction)...")
    try:
        result = run_python("import os", events)
        print(f"   ❌ Import was not blocked!")
        return False
    except Exception as e:
        print(f"   ✓ Import correctly blocked: {type(e).__name__}")
    
    return True


def test_settings():
    """Test settings loading."""
    print("\nTesting settings...")
    settings = get_settings()
    print(f"   ✓ HF Model ID: {settings.HF_MODEL_ID}")
    print(f"   ✓ Events Path: {settings.EVENTS_PATH}")
    print(f"   ✓ Max Tool Iters: {settings.MAX_TOOL_ITERS}")
    return True


def test_events_json_loading():
    """Test loading events from JSON."""
    print("\nTesting events JSON loading...")
    settings = get_settings()
    events_path = settings.EVENTS_PATH
    
    if not os.path.exists(events_path):
        print(f"   ⚠️  Events file not found: {events_path}")
        return True
    
    with open(events_path, 'r') as f:
        data = json.load(f)
    
    print(f"   ✓ Loaded {len(data)} events from {events_path}")
    
    # Try to parse first event
    if data:
        first_event = data[0]
        event_entry = EventEntry(**first_event.get("event_entry", {}))
        event = Event(
            event_entry=event_entry,
            id=first_event.get("id", ""),
            date=first_event.get("date", "")
        )
        print(f"   ✓ Successfully parsed event: {event.id}")
    
    return True


def main():
    """Run all tests."""
    print("=" * 60)
    print("Todoist Assistant Chat - Component Tests")
    print("=" * 60)
    
    tests = [
        ("Settings", test_settings),
        ("Events JSON Loading", test_events_json_loading),
        ("REPL Tool", test_repl_with_events),
    ]
    
    results = []
    for name, test_func in tests:
        print(f"\n{'=' * 60}")
        print(f"Running: {name}")
        print('=' * 60)
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ Test failed with exception: {type(e).__name__}: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    for name, result in results:
        status = "✓ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
    
    all_passed = all(result for _, result in results)
    print("\n" + ("=" * 60))
    if all_passed:
        print("✓ All tests passed!")
        return 0
    else:
        print("❌ Some tests failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
