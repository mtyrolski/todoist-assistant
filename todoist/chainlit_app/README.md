# Todoist Assistant - Chainlit Chat Interface

This directory contains the Chainlit-based chat interface for the Todoist Assistant, providing an interactive way to explore your Todoist productivity data through both button-based visualizations and future chat agent capabilities.

## Features

### 📊 Interactive Plot Visualization
- **Current Task Types** - Distribution of tasks by due date categories
- **Most Popular Labels** - Frequently used labels across projects
- **Events Over Time** - Activity patterns with time series visualization
- **Completed Tasks (Periodic)** - Task completion trends by project
- **Cumulative Completed Tasks** - Progressive completion tracking
- **Event Distribution by Type** - Pie chart of different event types
- **Top Projects by Events** - Most active projects analysis
- **Event Distribution by Project** - Activity distribution across projects
- **Event Heatmap (Day/Hour)** - When you're most active during the week
- **Event Types by Project** - Detailed breakdown of activities per project
- **Cumulative Events Over Time** - Overall activity progression
- **Cumulative Sum per Project** - Progressive activity by project

### 💬 Chat Agent Placeholder
- Interactive chat interface ready for future AI agent integration
- Placeholder responses for common queries
- Foundation for natural language productivity insights

## Running the Application

### Method 1: Using Make (Recommended)
```bash
make run_chainlit
```

### Method 2: Direct Command
```bash
cd todoist/chainlit_app
PYTHONPATH=../.. chainlit run app.py
```

### Method 3: Using the Run Script
```bash
python todoist/chainlit_app/run.py
```

## Configuration

The application uses the same data sources as the Streamlit dashboard:
- Todoist API data via the `.env` configuration
- Activity data cache (`activity.joblib`)
- Project and label color mappings

### First Time Setup

Before running the Chainlit app, ensure you have initialized your data:

```bash
make init_local_env
```

This will:
1. Sync your Todoist history
2. Fetch activity data
3. Create necessary cache files

## Architecture

```
todoist/chainlit_app/
├── app.py              # Main Chainlit application
├── run.py              # Launcher script
├── .chainlit/          # Chainlit configuration
│   └── config.toml     # UI and app settings
└── __init__.py         # Package initialization
```

### Data Flow

1. **Data Loading**: Reuses existing `todoist.dashboard.utils` for data loading
2. **Plot Generation**: Uses all functions from `todoist.plots` module
3. **Caching**: In-memory caching of loaded data for performance
4. **UI Interaction**: Button-based actions trigger specific visualizations

## Future Enhancements

The chat interface is designed to support future AI agent capabilities:

- **Natural Language Queries**: Ask questions about your productivity patterns
- **Personalized Insights**: Get AI-generated recommendations
- **Trend Analysis**: Automated pattern detection and predictions
- **Custom Reports**: Generate tailored productivity reports
- **Goal Tracking**: Set and monitor productivity goals

## Configuration Options

The Chainlit configuration (`.chainlit/config.toml`) includes:

- **Theme**: Dark theme by default
- **UI Name**: "Todoist Assistant"
- **Features**: Prompt playground enabled for future agent development
- **Session Management**: 1-hour session timeout
- **Security**: HTML rendering disabled for safety

## Troubleshooting

### Common Issues

1. **"No activity data available"**
   - Run `make init_local_env` to initialize your data
   - Check your `.env` file for correct Todoist API credentials

2. **Import Errors**
   - Ensure you're running from the project root
   - Check that all dependencies are installed: `pip install chainlit plotly pandas`

3. **Server Won't Start**
   - Check if port 8000 is available
   - Try running with different port: `chainlit run app.py --port 8001`

### Dependencies

Core dependencies:
- `chainlit>=2.8.0` - Chat interface framework
- `plotly>=6.0.0` - Interactive plotting
- `pandas>=2.0.0` - Data manipulation
- `loguru` - Logging

All other dependencies are inherited from the main Todoist Assistant project.