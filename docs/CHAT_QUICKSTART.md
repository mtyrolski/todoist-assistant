# Todoist Assistant Chat - Quick Start Guide

## Overview

The Todoist Assistant Chat is a LangGraph-based conversational interface that allows you to analyze your Todoist events using natural language or Python code.

## Features

- 🤖 **Natural Language Queries**: Ask questions about your events in plain English
- 🐍 **Secure Python REPL**: Execute Python code with read-only access to events
- 🔒 **Sandboxed Execution**: Safe code execution with timeout and output limits
- 💬 **Interactive Chat UI**: Clean Chainlit interface

## Prerequisites

- Python 3.11 or higher
- Hugging Face API token (free tier is sufficient)
- Todoist event data (optional - sample data provided)

## Installation

1. **Install Dependencies**
   ```bash
   pip install langgraph chainlit pydantic-settings langchain langchain-core langchain-huggingface huggingface-hub
   ```

2. **Configure Environment**
   ```bash
   cp .env.example .env
   # Edit .env and add your Hugging Face API token
   nano .env
   ```

   Required environment variables:
   ```
   HUGGINGFACEHUB_API_TOKEN=your_token_here
   HF_MODEL_ID=HuggingFaceH4/zephyr-7b-beta
   EVENTS_PATH=.data/events.json
   ```

## Usage

### Option 1: Using Make (Recommended)

```bash
make run-chat
```

### Option 2: Direct Command

```bash
PYTHONPATH=. chainlit run ui/chainlit_app.py
```

The chat interface will be available at `http://localhost:8000`

## Examples

### Natural Language Queries

```
How many events do I have?
```

```
Show me all completed tasks
```

### Direct REPL Execution

**Count Events:**
```
/repl
len(events)
```

**List Event Types:**
```
/repl
[e.event_type for e in events]
```

**Filter and Analyze:**
```
/repl
completed = [e for e in events if e.event_type == 'completed']
print(f"Completed tasks: {len(completed)}")
for event in completed[:5]:
    print(f"  - {event.name}")
len(completed)
```

**Get Event Names:**
```
/repl
[e.name for e in events if e.name]
```

## Event Data Structure

Each event has the following properties:
- `id`: Unique event identifier
- `date`: Event timestamp (datetime object)
- `name`: Event name (task content or project name)
- `event_type`: Type of event ('added', 'updated', 'completed', 'deleted')
- `event_entry`: Raw event data from Todoist API

Example:
```python
event.id         # "event_1"
event.date       # datetime(2024, 1, 1, 10, 0, 0)
event.name       # "Complete documentation"
event.event_type # "completed"
```

## Security Features

The REPL tool implements multiple security layers:

1. **Import Restrictions**: No `import` statements allowed
2. **Attribute Filtering**: Dangerous attributes like `__class__` are blocked
3. **Safe Builtins**: Only whitelisted built-in functions available
4. **Process Isolation**: Code runs in a separate process
5. **Timeout Enforcement**: Maximum 2 seconds execution time
6. **Output Truncation**: Large outputs are automatically truncated
7. **Read-Only Data**: Events exposed as immutable tuple

## Safe Built-in Functions

The following built-in functions are available:
- `len`, `sum`, `min`, `max`, `sorted`
- `enumerate`, `range`, `map`, `filter`
- `any`, `all`, `zip`
- `list`, `dict`, `set`, `tuple`
- `abs`, `round`
- `str`, `int`, `float`, `bool`
- `isinstance`, `type`, `repr`, `print`

## Preparing Your Own Event Data

To use your actual Todoist events:

1. **Fetch Events from Todoist**
   ```bash
   make init_local_env  # Fetches last 10 years of events
   ```

2. **Export to JSON**
   ```python
   import json
   from todoist.utils import Cache
   
   activity_db = Cache().activity.load()
   
   events_data = []
   for event in list(activity_db)[:1000]:  # First 1000 events
       events_data.append({
           "id": event.id,
           "date": event.date.isoformat(),
           "event_entry": {
               "id": event.event_entry.id,
               "object_type": event.event_entry.object_type,
               "object_id": event.event_entry.object_id,
               "event_type": event.event_entry.event_type,
               "event_date": event.event_entry.event_date,
               "parent_project_id": event.event_entry.parent_project_id,
               "parent_item_id": event.event_entry.parent_item_id,
               "initiator_id": event.event_entry.initiator_id,
               "extra_data": event.event_entry.extra_data,
               "extra_data_id": event.event_entry.extra_data_id,
               "v2_object_id": event.event_entry.v2_object_id,
               "v2_parent_item_id": event.event_entry.v2_parent_item_id,
               "v2_parent_project_id": event.event_entry.v2_parent_project_id,
           }
       })
   
   with open('.data/events.json', 'w') as f:
       json.dump(events_data, f, indent=2)
   ```

## Troubleshooting

**Issue: "No module named 'chainlit'"**
```bash
pip install chainlit
```

**Issue: "HUGGINGFACEHUB_API_TOKEN not set"**
- Get a free token from https://huggingface.co/settings/tokens
- Add it to your `.env` file

**Issue: "Events file not found"**
- Check that `.data/events.json` exists
- Or update `EVENTS_PATH` in `.env` to point to your events file

**Issue: "Timeout executing code"**
- Reduce complexity of your code
- Break into smaller chunks
- Check for infinite loops

## Advanced Configuration

### Using a Different Model

Edit `.env`:
```
HF_MODEL_ID=mistralai/Mistral-7B-Instruct-v0.2
```

Popular chat models:
- `HuggingFaceH4/zephyr-7b-beta` (default)
- `mistralai/Mistral-7B-Instruct-v0.2`
- `meta-llama/Llama-2-7b-chat-hf` (requires approval)
- `tiiuae/falcon-7b-instruct`

### Increasing Timeout

Edit `config/settings.py`:
```python
MAX_TOOL_ITERS: int = 5  # Allow more iterations
```

## Testing

Run the test suite:
```bash
# Run REPL tests
PYTHONPATH=. python -m pytest tests/test_repl_tool.py -v

# Run component tests
PYTHONPATH=. python test_chat_components.py

# Run interactive demo
PYTHONPATH=. python demo_repl.py
```

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Chainlit UI                        │
│          (ui/chainlit_app.py)                       │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│            LangGraph Agent                          │
│          (agent/graph.py)                           │
│                                                     │
│  ┌─────────────┐      ┌──────────────┐            │
│  │ HF LLM      │◄────►│ REPL Tool    │            │
│  │ (Zephyr-7B) │      │ (sandboxed)  │            │
│  └─────────────┘      └──────────────┘            │
└──────────────────┬──────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│         Read-Only Events Data                       │
│    (tuple of Event objects)                         │
└─────────────────────────────────────────────────────┘
```

## Contributing

To add new features:

1. **New REPL Functions**: Update `SAFE_BUILTINS` in `agent/tools/repl_tool.py`
2. **Agent Behavior**: Modify `agent/graph.py`
3. **UI Elements**: Update `ui/chainlit_app.py`

## License

See the main repository LICENSE file.

## Support

For issues and questions:
- Check existing issues on GitHub
- Review the main README.md
- Run the demo scripts to verify your setup
