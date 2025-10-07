#!/usr/bin/env python
"""
Demo script showing how to use the chat components.

This demonstrates the REPL functionality without requiring a Hugging Face API token.
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent.tools.repl_tool import run_python, ReplResult
from todoist.types import Event, EventEntry
import datetime as dt


def load_sample_events() -> list[Event]:
    """Load sample events from .data/events.json."""
    with open('.data/events.json', 'r') as f:
        data = json.load(f)
    
    events = []
    for item in data:
        event_entry = EventEntry(**item["event_entry"])
        # Parse date string to datetime
        date_str = item["date"]
        date = dt.datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        event = Event(
            event_entry=event_entry,
            id=item["id"],
            date=date
        )
        events.append(event)
    
    return events


def format_result(result: ReplResult) -> str:
    """Format REPL result for display."""
    parts = []
    
    if result.error:
        parts.append(f"❌ Error: {result.error}")
    else:
        if result.stdout:
            parts.append(f"📝 Output:\n{result.stdout}")
        if result.value_repr:
            parts.append(f"💡 Result: {result.value_repr}")
        if not result.stdout and not result.value_repr:
            parts.append("✅ Success (no output)")
    
    parts.append(f"⏱️  Executed in {result.exec_time_ms}ms")
    return "\n".join(parts)


def demo():
    """Run interactive demo."""
    print("=" * 70)
    print("Todoist Assistant - REPL Demo")
    print("=" * 70)
    print()
    print("This demo shows the secure REPL functionality.")
    print("Events are loaded from .data/events.json")
    print()
    print("Available variables:")
    print("  - events: tuple of Event objects (read-only)")
    print()
    print("Try these examples:")
    print("  1. len(events)")
    print("  2. [e.event_type for e in events]")
    print("  3. print('Hello from REPL')")
    print("  4. completed = [e for e in events if e.event_type == 'completed']")
    print()
    print("Type 'quit' or 'exit' to quit")
    print("=" * 70)
    print()
    
    # Load events
    events = load_sample_events()
    print(f"✓ Loaded {len(events)} events")
    print()
    
    # Sample queries
    sample_queries = [
        ("Count events", "len(events)"),
        ("List event types", "[e.event_type for e in events]"),
        ("Event names", "[e.name for e in events]"),
        ("Filter completed", "[e for e in events if e.event_type == 'completed']"),
    ]
    
    print("Sample Queries:")
    print("-" * 70)
    for i, (desc, code) in enumerate(sample_queries, 1):
        print(f"\n{i}. {desc}")
        print(f"   Code: {code}")
        print()
        result = run_python(code, events)
        print(f"   {format_result(result)}")
    
    print("\n" + "=" * 70)
    print("Interactive Mode")
    print("=" * 70)
    print()
    
    while True:
        try:
            code = input("repl> ").strip()
            if code.lower() in ('quit', 'exit', 'q'):
                break
            if not code:
                continue
            
            result = run_python(code, events)
            print(format_result(result))
            print()
            
        except KeyboardInterrupt:
            print("\n\nExiting...")
            break
        except EOFError:
            break


if __name__ == "__main__":
    demo()
