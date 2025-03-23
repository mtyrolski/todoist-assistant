# Todoist Summary Plugin

This tool provides insights into your Todoist activity by analyzing task events (e.g., added, completed, updated) and visualizing them through interactive plots. It helps you track productivity trends and gain valuable insights into your Todoist usage.

---

## Table of Contents

- [Todoist Summary Plugin](#todoist-summary-plugin)
  - [Table of Contents](#table-of-contents)
  - [Introduction](#introduction)
  - [Features](#features)
  - [Installation](#installation)
  - [Getting Started](#getting-started)
    - [Updating Activity Database](#updating-activity-database)
  - [Usage](#usage)
    - [Using Todoist-Assistant as a Library](#using-todoist-assistant-as-a-library)
      - [Adding a Task](#adding-a-task)
      - [Deleting a Task](#deleting-a-task)
      - [Inserting a Task from a Template](#inserting-a-task-from-a-template)
      - [Listing Database Projects](#listing-database-projects)
      - [Fetching a Specific Project by ID](#fetching-a-specific-project-by-id)
      - [Listing Archived Projects](#listing-archived-projects)
      - [Filtering Activity by Type](#filtering-activity-by-type)
      - [Filtering Activity by Date Range](#filtering-activity-by-date-range)
    - [Using Todoist-Assistant as a Dashboard](#using-todoist-assistant-as-a-dashboard)
    - [Implementing Custom Automations](#implementing-custom-automations)
    - [Understanding Automations](#understanding-automations)
    - [Implemented Automations](#implemented-automations)
  - [Modules Overview](#modules-overview)
  - [Dashboard Pages Overview](#dashboard-pages-overview)
  - [Database Functionalities](#database-functionalities)
    - [Database Overview](#database-overview)
    - [DatabaseActivity](#databaseactivity)
    - [DatabaseProjects](#databaseprojects)
    - [DatabaseTasks](#databasetasks)
  - [Configuration](#configuration)
    - [Setting Up Environment Variables](#setting-up-environment-variables)
    - [Aligning Archive Projects](#aligning-archive-projects)
  - [Contributing](#contributing)
  - [License](#license)
  - [Additional Examples for Projects and Activity](#additional-examples-for-projects-and-activity)

---

## Introduction

Todoist Summary Plugin is designed to provide detailed insights into your Todoist activity. It extracts data related to task events (such as tasks added, completed, and updated) and visualizes the information through interactive plots. This enables you to monitor productivity trends and make informed decisions about your task management.

## Features

- **Activity Tracking**: Retrieve and summarize Todoist activity data.
- **Interactive Visualizations**: Generate plots that display cumulative trends and project-specific insights.
- **Customizable Time Range**: Analyze your data by selecting specific time periods.
- **Modular Design**: Extensible framework that facilitates the integration of custom automations and external integrations.

## Installation

1. Clone the repository:
```bash
git clone https://github.com/mtyrolski/todoist-assistant.git
cd todoist-assistant
git checkout task-inserting
```

2. Set up a virtual environment and install dependencies:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
Alternatively, using Poetry:
```bash
poetry shell
poetry install
```

3. Add your Todoist API key to a `.env` file:
```bash
echo "API_KEY=your_todoist_api_key" > .env
```

## Getting Started

### Updating Activity Database

To fetch and update your Todoist activity data, run:

```bash
python3 -m todoist activity --nweeks N_WEEKS
```

This command:
- Retrieves the latest activity data from Todoist.
- Summarizes events (e.g., task additions, completions, updates).
- Saves the processed data locally for visualization.

Example output:
```
2025-01-25 22:17:50.241 | INFO     | Fetched 876 events
2025-01-25 22:17:51.194 | INFO     | Added 18 new events, current size: 27119
2025-01-25 22:17:52.787 | INFO     | Summary of Activity:
added: 9352 (34.49%)         (+11)
updated: 6631 (24.45%)       (+5)
completed: 9286 (34.24%)     (+2)
deleted: 1393 (5.14%)
```

## Usage

### Using Todoist-Assistant as a Library

You can integrate Todoist-Assistant directly into your projects as a library. Below are some examples showing how you can manipulate tasks, fetch activity data, and generate visualizations:

```python
from todoist.activity import fetch_activity_data
from todoist.plots import plot_event_distribution_by_type

# Fetch activity data for the last 4 weeks
activity_data = fetch_activity_data(nweeks=4)

# Generate an event distribution plot
plot_event_distribution_by_type(activity_data)
```

#### Adding a Task

```python
from todoist.database import Database

db = Database()

# Adding a new task to a project
task_id = db.add_task(project_name="Daily Tasks", content="Review Pull Requests", due_date="2025-03-25")

print(f"New task created with ID: {task_id}")
```
Explanation:  
1. `Database.add_task` is used to insert a new task into the specified project.  
2. Once the task is added, the activity tracking automatically captures this event.  
3. The next time you launch the dashboard or run `python3 -m todoist activity`, the new task addition will appear in any relevant visualizations.

#### Deleting a Task

```python
from todoist.database import Database

db = Database()

# Deleting a task by task_id
db.delete_task(task_id=12345)
print("Task deleted.")
```
Explanation:  
1. `Database.delete_task` removes the task with the specified ID from Todoist.  
2. This event triggers the "deleted" action in the activity log.  
3. The deletion is reflected in the "deleted" activity counts shown on the dashboard.

#### Inserting a Task from a Template

```python
from todoist.database import Database

db = Database()

# Insert a task from a predefined template
db.insert_task_from_template(
    template_name="daily-checklist",
    insert_date="2025-04-01",
    project_name="Daily Tasks"
)
print("Task inserted from template.")
```
Explanation:  
1. `Database.insert_task_from_template` relies on a pre-configured template (e.g., "daily-checklist").  
2. The functionality automatically populates relevant fields (like description, subtasks, or priority).  
3. This is especially useful for recurring or complex tasks that follow the same structure.

#### Listing Database Projects

```python
from todoist.database import Database

db = Database()

projects = db.list_projects()
for proj in projects:
    print(f"Project: {proj.name}, ID: {proj.id}")
```
Explanation:  
1. `Database.list_projects` returns a list of your active (and possibly archived) projects.  
2. Automations (like the Project Archive Mapper) may automatically redirect tasks if an archived project's name matches a mapping entry.  
3. The next time you generate or refresh the dashboard, these consolidated changes will be reflected in each project's respective metrics.


#### Fetching a Specific Project by ID

```python
from todoist.database import Database

db = Database()

# Suppose you have a known project ID
project_id = "123456789"
project = db.db_projects.fetch_project_by_id(project_id)

print(f"Fetched project: {project.project_entry.name}")
print(f"Is archived: {project.is_archived}")
```
Explanation:  
1. Uses `fetch_project_by_id` to retrieve a project's details from Todoist.  
2. If a project is archived, `is_archived` will be set to True.  
3. Additional tasks can be fetched by setting `include_tasks=True` in `fetch_projects` if needed.

#### Listing Archived Projects

```python
from todoist.database import Database

db = Database()

archived_projects = db.db_projects.fetch_archived_projects()
for proj in archived_projects:
    print(f"Archived Project: {proj.project_entry.name} [ID: {proj.id}]")
```
Explanation:  
1. `fetch_archived_projects` returns a list of archived projects that you can examine or remap to active projects if desired.  
2. Useful when cleaning up old structures or reassigning tasks.

#### Filtering Activity by Type

```python
from todoist.database import Database

db = Database()
activity_data = db.db_activity.fetch_activity()

# Filter all 'completed' events
completed_events = [evt for evt in activity_data if evt.event_entry.event_type == "completed"]
print(f"Found {len(completed_events)} completed events.")
```
Explanation:  
1. `db_activity.fetch_activity()` fetches a paginated list of recent Todoist events.  
2. You can filter these events by any supported type: "added", "updated", "completed", "deleted".  
3. Subsequent analysis (e.g., plotting) can be done using these filtered subsets.

#### Filtering Activity by Date Range

```python
from datetime import datetime, timedelta
from todoist.database import Database

db = Database()
activity_data = db.db_activity.fetch_activity()

# Let's say we want events from the last 2 weeks
cutoff_date = datetime.utcnow() - timedelta(days=14)
filtered_events = [evt for evt in activity_data if evt.date >= cutoff_date]

print(f"Events in the last 2 weeks: {len(filtered_events)}")
```
Explanation:  
1. You can apply custom date comparisons to the fetched events.  
2. `evt.date` is a Python `datetime` object for easy filtering.  
3. Integrate such filtering with your own plotting or automation scripts for targeted insights.

### Using Todoist-Assistant as a Dashboard

You can also use Todoist-Assistant as an interactive dashboard to visualize your tasks and activities from Todoist:

```bash
streamlit run dashboard.py
```
This opens a browser window with interactive plots, allowing you to:

- Select a specific date range for analysis.
- View visualizations such as cumulative task completion and project-specific trends.
- Access a control panel in which you can manually launch automations.

### Implementing Custom Automations

Extend the capabilities of Todoist-Assistant by creating custom automation scripts. Automations are Python scripts that define specific actions triggered by Todoist events. The framework automatically discovers and executes these scripts whenever relevant events occur.

### Understanding Automations

Automations in Todoist-Assistant enable you to define custom behaviors involving data preprocessing, sending notifications, or integrating with third-party services. The logic for each automation is encapsulated in distinct Python scripts that can be placed in dedicated directories like `personal/` or `todoist/automations/`.

### Implemented Automations

Below is an overview of the automations currently implemented on the `task-inserting` branch:

1. **Auto Task Inserter**:  
   - Monitors for specific project keywords (e.g., "Daily Tasks") and automatically inserts template tasks when the project is created or updated.  
   - Helps ensure consistent task structures and reminders for recurring workflows.

2. **Project Archive Mapper**:  
   - Checks if an old or archived project name (e.g., "Old Project 1 ⚔️") references a new active project.  
   - Automatically redirects new tasks or updates to the specified active project (for example, `'Current active root project'`).  
   - Keeps your data unified even after reorganizing or archiving Todoist projects.

These automations are hooked into the data flow just before the visualizations are produced, which allows them to modify or enrich the event data before it is displayed in the dashboard.

## Modules Overview

The project is built from several interrelated modules that work together seamlessly:

- **Activity Module (`todoist/activity.py`)**:  
  Fetches and processes Todoist activity data by filtering and summarizing events.

- **Dashboard Module (`dashboard.py`)**:  
  Provides a Streamlit-based dashboard for visualizing the processed data, working closely with both the Activity and Plots modules.

- **Types Module (`todoist/types.py`)**:  
  Defines the core data structures for Todoist events, tasks, and projects to ensure consistent handling throughout the codebase.

- **Plots Module (`todoist/plots.py`)**:  
  Offers functions to generate interactive visualizations from the processed data.

- **Database Module (`todoist/database.py`)**:  
  Manages interactions with the Todoist API, including retrieving project mappings, tasks, and archived project data.

- **Integrations Module (`todoist/integrations/`)**:  
  Contains components for connecting to external services such as Gmail and Twitter, providing experimental integrations. For now, it is not incorporated into the dashboard and other scripts.

- **Automations Module (`todoist/automations/`)**:  
  Supplies a framework for creating custom automations that enhance the processing of Todoist activity data before visualization.

## Dashboard Pages Overview

When you run the Streamlit dashboard (via `dashboard.py`), you'll encounter the following main views:

1. **Overview Page**:  
   - Displays cumulative statistics of tasks added, completed, updated, and deleted.  
   - Offers a quick snapshot of your productivity trends over the selected time range.

2. **Project Trends Page**:  
   - Breaks down activity data by project.  
   - Allows you to see which projects are most active and how tasks trend over time in each project.

3. **Automation Insights Page** (if enabled in your layout):  
   - Shows details about automations triggered for each event, including the time they run and any modifications made to the tasks or projects.  
   - Useful for debugging or refining your automation scripts.

These pages rely on the **Activity Module** to gather data, and the **Plots Module** to generate visualizations that reflect the transformations and data merges performed by your automations.

## Database Functionalities

### Database Overview

The `Database` class combines multiple submodules in a cohesive way, allowing you to access your Todoist data (activity, projects, tasks) through a single instance. By loading environment variables and applying the modules’ functionality, `Database` ensures your data is fetched and manipulated consistently.

### DatabaseActivity

Handles activities such as fetching detailed logs of task events over a configurable number of pages. Key features include:
- Consolidating activity data from multiple API calls (paginated).
- Creating standardized `Event` objects for each new or updated Todoist event.
- Allowing you to gather an extensive historical record if needed.

### DatabaseProjects

Manages project-related data, including:
- Fetching active and archived projects from Todoist.
- Organizing tasks under each project when requested.
- Storing name-to-ID and ID-to-name mappings for convenience.
- Providing hierarchical lookups, allowing you to determine a project’s root.

### DatabaseTasks

Consolidates all operations related to tasks, such as:
- Creating new tasks (via `insert_task`), optionally with advanced parameters like deadlines, labels, and priority.
- Removing existing tasks from Todoist (via `remove_task`).
- Cloning or pre-populating tasks from templates (via `insert_task_from_template`).
- Fetching single tasks by ID and returning their details.

These modules can be used separately or in tandem through the `Database` class. They help maintain a clean structure for caching and reusing responses from the Todoist API.

## Configuration

### Setting Up Environment Variables

Make sure to configure the necessary environment variables by adding your Todoist API key to a `.env` file:
```bash
echo "API_KEY=your_todoist_api_key" > .env
```
**Experimental note** - If you want to use experimental Twitter integration, you should fill the following variables:
```
X_API_KEY=''
X_API_KEY_SECRET=''
X_ACCESS_TOKEN=''
X_ACCESS_TOKEN_SECRET=''
X_BAERER_TOKEN=''
```

### Aligning Archive Projects

Archived projects in Todoist are not automatically mapped to active projects. Sometimes we re-organize our structure of projects and we would like to reflect this in stats. Todoist assistant supports such alignment. To fix this, create a file in the `personal/` folder (e.g., `adj_yourname.py`) with the following content:

```python
link_adjustements = {
    'Old Project 1 ⚔️': 'Current active root project',
    'Old Project 2': 'Another active project 🔥⚔️🔥'
}
```

## Contributing

Contributions are welcome! Please open an issue or submit a pull request with improvements, new features, or bug fixes (branch off from `task-inserting` if applicable). Follow the project's coding standards and include tests where applicable.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

## Additional Examples for Projects and Activity

Below are more code snippets focused on fetching detailed project data and filtering activity events for specific projects or time ranges.
