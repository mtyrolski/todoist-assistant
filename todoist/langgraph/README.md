# LangGraph Module for Automated Task Synthesis

## Overview

The LangGraph module provides automated task synthesis and generation capabilities for the Todoist Assistant. It uses LangGraph workflows to analyze user input and automatically generate structured tasks and subtasks based on natural language descriptions.

## Features

- **Natural Language Processing**: Analyzes user input to understand intent and context
- **Intelligent Task Generation**: Creates structured tasks with appropriate subtasks based on task type
- **Flexible Workflow**: Uses LangGraph state management for robust task synthesis
- **Integration Ready**: Seamlessly integrates with existing Todoist automation framework
- **Multiple Input Sources**: Supports environment variables, files, and manual input
- **Automatic Classification**: Identifies task types (meeting, research, general) and generates appropriate subtasks

## Architecture

### Core Components

1. **TaskSynthesizer**: Main LangGraph workflow for task synthesis
2. **LangGraphAutomation**: Integration with existing automation framework
3. **TaskSuggestion**: Data structure for generated tasks
4. **State Management**: TypedDict-based state for LangGraph workflow

### Workflow Steps

1. **Parse Input**: Analyzes user input to extract requirements and context
2. **Generate Tasks**: Creates task suggestions based on parsed requirements
3. **Validate Tasks**: Validates generated tasks for quality and completeness
4. **Finalize Tasks**: Prepares final task suggestions for output

## Usage

### Basic Task Synthesis

```python
from todoist.langgraph.task_synthesizer import TaskSynthesizer

# Initialize the synthesizer
synthesizer = TaskSynthesizer()

# Generate tasks from natural language input
user_input = "I need to organize a team meeting next week"
tasks = synthesizer.synthesize_tasks(user_input)

# Access generated tasks
for task in tasks:
    print(f"Task: {task.content}")
    print(f"Description: {task.description}")
    print(f"Priority: {task.priority}")
    print(f"Labels: {task.labels}")
    
    for subtask in task.subtasks:
        print(f"  Subtask: {subtask.content}")
```

### Using the Automation Framework

The LangGraph module integrates with the existing automation framework. Configure it in `configs/automations.yaml`:

```yaml
- _target_: todoist.langgraph.automation.LangGraphAutomation
  name: "LangGraph Task Synthesizer"
  frequency: 1440  # Run once per day (in minutes)
  is_long: false
  input_source: "env"  # Options: "env", "file", "manual"
  auto_create_tasks: false  # Set to true to automatically create tasks in Todoist
```

### Input Sources

#### Environment Variables
Set `LANGGRAPH_INPUT` or `LANGGRAPH_INPUT_1`, `LANGGRAPH_INPUT_2`, etc.:

```bash
export LANGGRAPH_INPUT="Research AI safety papers for next week"
```

#### File Input
Create a file with user inputs (one per line):

```bash
echo "Plan team retrospective meeting" > langgraph_inputs.txt
echo "Research competitor analysis" >> langgraph_inputs.txt
```

Set the file path:
```bash
export LANGGRAPH_INPUT_FILE="langgraph_inputs.txt"
export LANGGRAPH_CLEAR_FILE_AFTER_READ="true"  # Optional: clear file after reading
```

#### Manual Testing
```python
from todoist.langgraph.automation import LangGraphAutomation

automation = LangGraphAutomation(input_source="manual")
result = automation.synthesize_tasks_manual(
    "I need to write a research paper about AI ethics",
    create_tasks=False
)
print(result)
```

## Task Types and Generation

### Meeting Tasks
**Triggers**: "meeting", "call", "presentation"

**Generated subtasks**:
- Schedule meeting time
- Prepare meeting agenda  
- Send meeting invitations

### Research Tasks
**Triggers**: "research", "study", "learn"

**Generated subtasks**:
- Define research scope
- Gather initial sources
- Analyze findings
- Summarize results

### General Tasks
**Default for other inputs**

**Generated subtasks**:
- Planning subtask (for complex requests)

## Task Properties

Each generated task includes:

- **Content**: Main task description
- **Description**: Detailed task description
- **Priority**: Task priority (1-4, default: 1)
- **Due Date Offset**: Days from now for due date
- **Labels**: Categorization labels
- **Subtasks**: List of related subtasks

## Configuration Options

### LangGraphAutomation Parameters

- `name`: Automation name (default: "LangGraph Task Synthesizer")
- `frequency`: Run frequency in minutes (default: 1440 = daily)
- `is_long`: Whether this is a long-running automation (default: false)
- `input_source`: Input source ("env", "file", "manual")
- `auto_create_tasks`: Whether to create tasks in Todoist (default: false)

### Environment Variables

- `LANGGRAPH_INPUT`: Single input for processing
- `LANGGRAPH_INPUT_N`: Multiple inputs (N = 1, 2, 3, ...)
- `LANGGRAPH_INPUT_FILE`: Path to input file
- `LANGGRAPH_CLEAR_FILE_AFTER_READ`: Clear file after reading ("true"/"false")
- `LANGGRAPH_DEMO_INPUTS`: Demo inputs for testing

## Integration with Todoist

When `auto_create_tasks=True`, the automation will:

1. Create main tasks using the existing `db.insert_task()` method
2. Create subtasks linked to the main task
3. Set appropriate due dates based on offset
4. Apply labels and priorities
5. Return creation results

## Example Outputs

### Meeting Organization
**Input**: "I need to organize a team meeting next week"

**Generated**:
- Main task: "Organize meeting: I need to organize a team meeting next week"
- Subtasks:
  - "Schedule meeting time" (due: -2 days)
  - "Prepare meeting agenda" (due: -1 days)  
  - "Send meeting invitations" (due: -1 days)

### Research Task
**Input**: "Research machine learning papers for my project"

**Generated**:
- Main task: "Research task: Research machine learning papers for my project"
- Subtasks:
  - "Define research scope" (due: 0 days)
  - "Gather initial sources" (due: +1 days)
  - "Analyze findings" (due: +2 days)
  - "Summarize results" (due: +3 days)

## Testing

Run the test suite to verify functionality:

```bash
# Test core synthesizer functionality
python test_langgraph_simple.py

# Test full automation framework (requires dependencies)
python test_langgraph.py
```

## Dependencies

- `langgraph>=0.6.0`: Core LangGraph functionality
- `langchain>=0.3.0`: LangChain components
- `loguru`: Logging
- `python-dotenv`: Environment variable loading (for automation)
- `joblib`: Caching (for automation)

## Error Handling

The module includes robust error handling:

- Invalid inputs are logged and skipped
- Task validation prevents malformed tasks
- Automation failures are logged without stopping other automations
- State management errors are handled gracefully

## Future Enhancements

- **LLM Integration**: Replace rule-based generation with actual language models
- **Custom Templates**: User-defined task templates
- **Learning**: Adapt task generation based on user feedback
- **Advanced Classification**: More sophisticated task type detection
- **Calendar Integration**: Smart due date scheduling
- **Priority Inference**: Automatic priority assignment based on context

## Troubleshooting

### Common Issues

1. **State Management Errors**: Ensure you're using the latest version with TypedDict state
2. **Import Errors**: Install required dependencies (`pip install langgraph langchain loguru`)
3. **No Tasks Generated**: Check input format and ensure it's not empty
4. **Automation Not Running**: Verify configuration in `automations.yaml`

### Debug Mode

Enable debug logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Testing Without Full Framework

Use the standalone test script to avoid dependency issues:

```bash
python test_langgraph_simple.py
```

This tests only the core synthesizer without requiring the full Todoist framework.