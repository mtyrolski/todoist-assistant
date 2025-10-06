"""
Chainlit chat interface for the LangGraph agent.
"""
import json
import os
from pathlib import Path

import chainlit as cl
from langchain_core.messages import BaseMessage, HumanMessage

from agent.graph import create_agent_graph, run_agent_with_message
from agent.tools.repl_tool import run_python
from config.settings import get_settings
from todoist.types import Event, EventEntry


def load_events(events_path: str) -> list[Event]:
    """
    Load events from JSON file.
    
    Args:
        events_path: Path to events JSON file
        
    Returns:
        List of Event objects
    """
    if not os.path.exists(events_path):
        return []
    
    try:
        with open(events_path, 'r') as f:
            data = json.load(f)
        
        events = []
        for item in data:
            # Parse event entry
            event_entry = EventEntry(**item.get("event_entry", {}))
            
            # Create Event
            event = Event(
                event_entry=event_entry,
                id=item.get("id", ""),
                date=item.get("date", "")  # Note: In real usage, parse datetime properly
            )
            events.append(event)
        
        return events
    except Exception as e:
        print(f"Error loading events: {e}")
        return []


@cl.on_chat_start
async def start():
    """Initialize the chat session."""
    settings = get_settings()
    
    # Load events
    events = load_events(settings.EVENTS_PATH)
    
    # Create agent graph
    graph = create_agent_graph(events)
    
    # Store in session
    cl.user_session.set("graph", graph)
    cl.user_session.set("events", events)
    cl.user_session.set("message_history", [])
    
    # Send welcome message
    await cl.Message(
        content=(
            "👋 Welcome to Todoist Assistant Chat!\n\n"
            "**How to use:**\n"
            "- Ask me questions about your Todoist events\n"
            "- Use `/repl` followed by Python code to analyze events directly\n"
            "- The `events` variable is a read-only tuple of Event objects\n\n"
            f"**Status:** {len(events)} events loaded\n\n"
            "**Example queries:**\n"
            "- How many events do I have?\n"
            "- `/repl\\nlen(events)`\n"
            "- `/repl\\n[e.event_type for e in events[:5]]`"
        )
    ).send()


@cl.on_message
async def main(message: cl.Message):
    """Handle incoming messages."""
    graph = cl.user_session.get("graph")
    events = cl.user_session.get("events")
    message_history: list[BaseMessage] = cl.user_session.get("message_history", [])
    
    user_input = message.content.strip()
    
    # Check for /repl command
    if user_input.startswith("/repl"):
        # Extract code after /repl
        code = user_input[5:].strip()
        
        if not code:
            await cl.Message(
                content="⚠️ Please provide Python code after `/repl`\n\nExample:\n```\n/repl\nlen(events)\n```"
            ).send()
            return
        
        # Execute REPL directly
        msg = cl.Message(content="")
        await msg.send()
        
        try:
            result = run_python(code, events)
            
            # Format result
            result_parts = ["**REPL Execution:**\n"]
            result_parts.append(f"```python\n{code}\n```\n")
            
            if result.error:
                result_parts.append(f"❌ **Error:** {result.error}")
            else:
                if result.stdout:
                    result_parts.append(f"**Output:**\n```\n{result.stdout}\n```")
                if result.value_repr:
                    result_parts.append(f"**Result:** `{result.value_repr}`")
                if not result.stdout and not result.value_repr:
                    result_parts.append("✅ Code executed successfully (no output)")
            
            result_parts.append(f"\n⏱️ *Executed in {result.exec_time_ms}ms*")
            
            msg.content = "\n".join(result_parts)
            await msg.update()
            
        except Exception as e:
            msg.content = f"❌ **Error:** {type(e).__name__}: {e}"
            await msg.update()
        
        return
    
    # Normal chat flow with agent
    msg = cl.Message(content="")
    await msg.send()
    
    try:
        # Run agent
        response, updated_history = run_agent_with_message(
            graph,
            user_input,
            message_history
        )
        
        # Update message history
        cl.user_session.set("message_history", updated_history)
        
        # Send response
        msg.content = response
        await msg.update()
        
    except Exception as e:
        msg.content = f"❌ **Error:** {type(e).__name__}: {e}\n\nPlease check your configuration and try again."
        await msg.update()


if __name__ == "__main__":
    # This is for reference - Chainlit runs via CLI: chainlit run ui/chainlit_app.py
    pass
