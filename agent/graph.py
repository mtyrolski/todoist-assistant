"""
LangGraph agent with Hugging Face LLM and REPL tool.
"""
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_huggingface import HuggingFaceEndpoint
from langgraph.graph import END, StateGraph

from agent.state import AgentState
from agent.tools.repl_tool import run_python
from config.settings import get_settings
from todoist.types import Event


def create_agent_graph(events: list[Event]) -> StateGraph:
    """
    Create a LangGraph agent with HF LLM and REPL tool.
    
    Args:
        events: List of Event objects to provide to REPL
        
    Returns:
        Compiled LangGraph StateGraph
    """
    settings = get_settings()
    
    # Initialize Hugging Face LLM
    llm = HuggingFaceEndpoint(
        repo_id=settings.HF_MODEL_ID,
        huggingfacehub_api_token=settings.HUGGINGFACEHUB_API_TOKEN,
        temperature=0.7,
        max_new_tokens=512,
        top_k=50,
    )
    
    def should_continue(state: AgentState) -> str:
        """Decide whether to continue with tool execution or end."""
        messages = state["messages"]
        last_message = messages[-1]
        
        # Check iteration limit
        if state["iterations"] >= settings.MAX_TOOL_ITERS:
            return "end"
        
        # Check if last message is from AI and contains tool call indicator
        if isinstance(last_message, AIMessage):
            content = last_message.content.lower()
            if "tool:" in content or "repl:" in content or "```python" in content:
                return "tool"
        
        return "end"
    
    def call_model(state: AgentState) -> dict[str, Any]:
        """Call the LLM with current state."""
        messages = state["messages"]
        
        # Create system message if not present
        if not messages or not isinstance(messages[0], SystemMessage):
            system_msg = SystemMessage(content=(
                "You are a helpful assistant that can analyze Todoist events. "
                "You have access to a Python REPL tool that can execute code with read-only access to 'events' tuple. "
                "When you need to analyze events, respond with 'TOOL: REPL' followed by the Python code in a code block. "
                "Example:\nTOOL: REPL\n```python\nlen(events)\n```"
            ))
            messages = [system_msg] + messages
        
        # Get LLM response
        response = llm.invoke([msg.content if hasattr(msg, 'content') else str(msg) for msg in messages])
        
        ai_message = AIMessage(content=response)
        
        return {
            "messages": state["messages"] + [ai_message],
            "iterations": state["iterations"]
        }
    
    def call_tool(state: AgentState) -> dict[str, Any]:
        """Execute the REPL tool based on the last AI message."""
        messages = state["messages"]
        last_message = messages[-1]
        
        # Extract Python code from the message
        content = last_message.content
        code = ""
        
        # Try to extract code from markdown code blocks
        if "```python" in content:
            start = content.find("```python") + len("```python")
            end = content.find("```", start)
            if end != -1:
                code = content[start:end].strip()
        elif "```" in content:
            start = content.find("```") + len("```")
            end = content.find("```", start)
            if end != -1:
                code = content[start:end].strip()
        else:
            # Try to extract code after "TOOL: REPL" or similar markers
            lines = content.split("\n")
            capturing = False
            code_lines = []
            for line in lines:
                if "tool:" in line.lower() or "repl:" in line.lower():
                    capturing = True
                    continue
                if capturing:
                    code_lines.append(line)
            code = "\n".join(code_lines).strip()
        
        if not code:
            # Fallback: use the entire message as code
            code = content
        
        # Execute REPL
        try:
            result = run_python(code, events)
            
            # Format tool result
            result_parts = []
            if result.stdout:
                result_parts.append(f"stdout:\n{result.stdout}")
            if result.value_repr:
                result_parts.append(f"result: {result.value_repr}")
            if result.error:
                result_parts.append(f"error: {result.error}")
            result_parts.append(f"(executed in {result.exec_time_ms}ms)")
            
            tool_result = "\n".join(result_parts)
            
        except Exception as e:
            tool_result = f"Tool execution error: {type(e).__name__}: {e}"
        
        tool_message = ToolMessage(content=tool_result, tool_call_id="repl_tool")
        
        return {
            "messages": state["messages"] + [tool_message],
            "iterations": state["iterations"] + 1
        }
    
    # Build the graph
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("agent", call_model)
    workflow.add_node("tool", call_tool)
    
    # Set entry point
    workflow.set_entry_point("agent")
    
    # Add conditional edges
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tool": "tool",
            "end": END
        }
    )
    
    # Tool always goes back to agent
    workflow.add_edge("tool", "agent")
    
    return workflow.compile()


def run_agent_with_message(
    graph: Any,
    user_message: str,
    message_history: list[BaseMessage] | None = None
) -> tuple[str, list[BaseMessage]]:
    """
    Run the agent with a user message.
    
    Args:
        graph: Compiled LangGraph StateGraph
        user_message: User's message
        message_history: Previous message history
        
    Returns:
        Tuple of (response, updated_message_history)
    """
    if message_history is None:
        message_history = []
    
    # Add user message
    messages = message_history + [HumanMessage(content=user_message)]
    
    # Run the graph
    initial_state: AgentState = {
        "messages": messages,
        "iterations": 0
    }
    
    final_state = graph.invoke(initial_state)
    
    # Get the last AI message as response
    response = ""
    for msg in reversed(final_state["messages"]):
        if isinstance(msg, AIMessage):
            response = msg.content
            break
    
    return response, final_state["messages"]
