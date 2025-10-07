# Todoist Assistant Chat - Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                         User                                 │
│                    (Browser/CLI)                             │
└────────────────────────┬────────────────────────────────────┘
                         │
                         │ HTTP (8000)
                         │
┌────────────────────────▼────────────────────────────────────┐
│                   Chainlit Server                            │
│              (ui/chainlit_app.py)                            │
│                                                              │
│  ┌─────────────────────────────────────────────────┐        │
│  │ @cl.on_chat_start                                │        │
│  │  - Load events from JSON                         │        │
│  │  - Create agent graph                            │        │
│  │  - Initialize session                            │        │
│  └─────────────────────────────────────────────────┘        │
│                                                              │
│  ┌─────────────────────────────────────────────────┐        │
│  │ @cl.on_message                                   │        │
│  │  - Parse /repl commands                          │        │
│  │  - Route to REPL or agent                        │        │
│  │  - Display results                               │        │
│  └─────────────────────────────────────────────────┘        │
└────────────────────────┬────────────────────────────────────┘
                         │
              ┌──────────┴──────────┐
              │                     │
              │ /repl command?      │
              │                     │
         ┌────▼────┐         ┌─────▼─────┐
         │   YES   │         │    NO     │
         └────┬────┘         └─────┬─────┘
              │                     │
              │                     │
┌─────────────▼────────┐  ┌────────▼──────────────────────────┐
│   Direct REPL        │  │    LangGraph Agent                 │
│   Execution          │  │    (agent/graph.py)                │
│                      │  │                                     │
│  run_python(code)    │  │  ┌──────────────────────────┐     │
│                      │  │  │ call_model()             │     │
│                      │  │  │  - Format messages       │     │
│                      │  │  │  - Call HF LLM           │     │
│                      │  │  │  - Return AI response    │     │
└─────────┬────────────┘  │  └────────┬─────────────────┘     │
          │               │           │                        │
          │               │           │ Contains tool call?    │
          │               │           │                        │
          │               │  ┌────────▼─────────────────┐     │
          │               │  │ should_continue()        │     │
          │               │  │  - Check iterations      │     │
          │               │  │  - Detect tool calls     │     │
          │               │  └────────┬─────────────────┘     │
          │               │           │                        │
          │               │      ┌────▼────┐                  │
          │               │      │  tool?  │                  │
          │               │      └────┬────┘                  │
          │               │           │                        │
          │               │  ┌────────▼─────────────────┐     │
          │               │  │ call_tool()              │     │
          │               │  │  - Extract Python code   │     │
          └───────────────┼──┤  - Call run_python()     │     │
                          │  └────────┬─────────────────┘     │
                          └───────────┼───────────────────────┘
                                      │
                         ┌────────────▼─────────────────────┐
                         │      REPL Tool                    │
                         │  (agent/tools/repl_tool.py)       │
                         │                                   │
                         │  ┌─────────────────────────┐     │
                         │  │ _validate_ast(code)     │     │
                         │  │  - Parse AST            │     │
                         │  │  - Check for imports    │     │
                         │  │  - Check for __attrs    │     │
                         │  └──────────┬──────────────┘     │
                         │             │                     │
                         │        ┌────▼────┐               │
                         │        │ Valid?  │               │
                         │        └────┬────┘               │
                         │             │                     │
                         │    ┌────────▼──────────────┐     │
                         │    │ Spawn subprocess      │     │
                         │    │ _execute_in_subprocess│     │
                         │    └────────┬──────────────┘     │
                         │             │                     │
                         │  ┌──────────▼──────────────┐     │
                         │  │ Subprocess:             │     │
                         │  │  - Capture stdout       │     │
                         │  │  - Restrict builtins    │     │
                         │  │  - Eval/Exec code       │     │
                         │  │  - Return result        │     │
                         │  └──────────┬──────────────┘     │
                         │             │                     │
                         │        ┌────▼────┐               │
                         │        │Timeout? │               │
                         │        └────┬────┘               │
                         │             │                     │
                         │  ┌──────────▼──────────────┐     │
                         │  │ Format ReplResult       │     │
                         │  │  - Truncate outputs     │     │
                         │  │  - Add timing info      │     │
                         │  └──────────┬──────────────┘     │
                         └─────────────┼───────────────────┘
                                       │
                         ┌─────────────▼─────────────┐
                         │    Read-Only Events       │
                         │   tuple[Event, ...]       │
                         │                           │
                         │  Loaded from:             │
                         │  .data/events.json        │
                         └───────────────────────────┘
```

## Component Details

### 1. Chainlit UI Layer
- **File:** `ui/chainlit_app.py`
- **Responsibilities:**
  - User session management
  - Message routing (/repl vs normal chat)
  - Event loading from JSON
  - Result formatting and display

### 2. LangGraph Agent
- **File:** `agent/graph.py`
- **Components:**
  - `create_agent_graph()` - Builds the state graph
  - `call_model()` - LLM interaction node
  - `call_tool()` - Tool execution node
  - `should_continue()` - Routing logic
- **State:** Messages history + iteration counter
- **Max Iterations:** 2 (configurable)

### 3. REPL Tool
- **File:** `agent/tools/repl_tool.py`
- **Security Layers:**
  1. AST validation (pre-execution)
  2. Import blocking
  3. Attribute filtering
  4. Process isolation
  5. Timeout enforcement
  6. Output truncation

### 4. Configuration
- **File:** `config/settings.py`
- **Environment Variables:**
  - `HUGGINGFACEHUB_API_TOKEN`
  - `HF_MODEL_ID`
  - `EVENTS_PATH`
  - `MAX_TOOL_ITERS`

## Data Flow Examples

### Example 1: Direct REPL Command

```
User: /repl
      len(events)

  ↓

Chainlit: Detect /repl prefix
          Extract code: "len(events)"

  ↓

REPL Tool: Validate AST ✓
           Create subprocess
           Execute: len(events)
           Return: ReplResult(value_repr="3", ...)

  ↓

Chainlit: Format and display:
          "💡 Result: 3"
          "⏱️ Executed in 2ms"
```

### Example 2: Natural Language Query

```
User: How many events do I have?

  ↓

Chainlit: Route to agent

  ↓

Agent: call_model()
       → LLM: "To answer this, I need to count the events.
               TOOL: REPL
               ```python
               len(events)
               ```"

  ↓

Agent: should_continue()
       → Detect tool call → "tool"

  ↓

Agent: call_tool()
       → Extract code: "len(events)"
       → Call run_python()

  ↓

REPL Tool: Execute and return: ReplResult(value_repr="3", ...)

  ↓

Agent: call_model() again
       → LLM: "You have 3 events."

  ↓

Chainlit: Display final answer
```

## Security Boundaries

```
┌──────────────────────────────────────┐
│         TRUSTED ZONE                 │
│  - Chainlit server                   │
│  - LangGraph agent                   │
│  - Event loading                     │
│  - Result formatting                 │
└──────────────────┬───────────────────┘
                   │
         ┌─────────┴─────────┐
         │  SECURITY GATE    │
         │  (AST Validation) │
         └─────────┬─────────┘
                   │
┌──────────────────▼───────────────────┐
│      SANDBOXED ZONE                  │
│  - Subprocess                        │
│  - Restricted builtins               │
│  - Timeout enforced                  │
│  - Captured stdout                   │
│  - Read-only data                    │
└──────────────────────────────────────┘
```

## File Structure

```
todoist-assistant/
├── agent/
│   ├── __init__.py
│   ├── state.py          # AgentState TypedDict
│   ├── graph.py          # LangGraph agent
│   └── tools/
│       ├── __init__.py
│       └── repl_tool.py  # Secure REPL
├── config/
│   ├── __init__.py
│   └── settings.py       # Pydantic settings
├── ui/
│   ├── __init__.py
│   └── chainlit_app.py   # Chat interface
├── .data/
│   └── events.json       # Sample events
├── chainlit.toml         # Chainlit config
├── .env.example          # Environment template
└── Makefile             # run-chat target
```

## Message Flow (LangGraph)

```
Initial State:
{
  messages: [HumanMessage("How many events?")],
  iterations: 0
}

↓ [agent node]

{
  messages: [
    HumanMessage("How many events?"),
    AIMessage("TOOL: REPL\n```python\nlen(events)\n```")
  ],
  iterations: 0
}

↓ [should_continue → "tool"]

↓ [tool node]

{
  messages: [
    HumanMessage("How many events?"),
    AIMessage("TOOL: REPL\n```python\nlen(events)\n```"),
    ToolMessage("result: 3\n(executed in 2ms)")
  ],
  iterations: 1
}

↓ [agent node]

{
  messages: [
    HumanMessage("How many events?"),
    AIMessage("TOOL: REPL\n```python\nlen(events)\n```"),
    ToolMessage("result: 3\n(executed in 2ms)"),
    AIMessage("You have 3 events.")
  ],
  iterations: 1
}

↓ [should_continue → "end"]

Final State
```

## Error Handling

```
User Code Error
    ↓
REPL catches exception
    ↓
Returns ReplResult(error="ZeroDivisionError: division by zero")
    ↓
Displayed to user with ❌ icon
```

```
Validation Error
    ↓
_validate_ast() raises CodeValidationError
    ↓
run_python() catches and re-raises
    ↓
Chainlit displays error message
```

```
Timeout
    ↓
Subprocess exceeds timeout
    ↓
Process terminated
    ↓
Returns ReplResult(error="TimeoutError: Execution exceeded timeout")
```

## Performance Characteristics

- **Startup Time:** ~2-3 seconds (load events, create graph)
- **REPL Execution:** 1-10ms for simple expressions
- **LLM Response:** 2-5 seconds (depends on HF API)
- **Memory Usage:** ~200MB base + model inference
- **Timeout Limit:** 2 seconds per REPL execution

## Scalability Considerations

- **Single User:** Current design (session-based)
- **Multi-User:** Add authentication and user-specific event loading
- **Large Events:** Consider pagination or filtering
- **High Load:** Deploy with load balancer and multiple instances

## Extension Points

1. **New Tools:** Add to `agent/tools/` and register in `agent/graph.py`
2. **Custom Models:** Change `HF_MODEL_ID` in settings
3. **Event Sources:** Modify `ui/chainlit_app.py` to load from database
4. **UI Customization:** Edit `chainlit.toml` and add custom CSS/JS
5. **Additional Security:** Add rate limiting, user authentication

---

This architecture provides a secure, minimal, and extensible foundation for analyzing Todoist events through natural language and code.
