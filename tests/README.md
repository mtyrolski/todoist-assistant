# Tests for Todoist Assistant

This directory contains comprehensive tests for the data structures and database operations in the todoist-assistant project.

## Test Structure

### Test Files

- **`test_types.py`** - Tests for data structure creation, composition, and utilities
- **`test_database.py`** - Tests for database operations (CRUD, caching, API interactions)
- **`test_transformations.py`** - Tests for data transformations and dataframe operations
- **`test_utils.py`** - Tests for utility helper functions (storage, config, caching, anonymization)
- **`test_stats.py`** - Tests for statistics and task analysis helper functions
- **`test_dashboard_utils.py`** - Tests for dashboard utilities and automation helpers
- **`test_gmail_automation.py`** - Tests for Gmail task automation integration
- **`test_rescheduled_tasks_filtering.py`** - Tests for task filtering and rescheduling logic

### Test Categories

1. **Data Structure Creation (12 tests)**
   - ProjectEntry, TaskEntry, EventEntry dataclass creation
   - Property validation and default values
   - Duration and datetime handling

2. **Database Operations (17 tests)**
   - Task CRUD operations (insert, fetch, remove)
   - Project fetching and caching
   - Activity data fetching
   - Template-based task creation
   - Parameter validation

3. **Data Transformations (7 tests)**
   - Event-to-dataframe conversion
   - Chronological ordering
   - Data filtering and validation
   - Column type verification

4. **Utility Functions (35 tests)**
   - Dataclass field manipulation
   - Configuration loading
   - Storage operations (LocalStorage, Cache)
   - Retry mechanisms with exponential backoff
   - Anonymization functionality

5. **Statistics & Analysis (40 tests)**
   - Task counting and aggregation
   - Priority-based task filtering (P1-P4)
   - Label analysis
   - Date parsing and extraction
   - Due date handling

6. **Dashboard & Automation Helpers (28 tests)**
   - Metrics extraction and calculation
   - Badge generation for task priorities
   - Multiplication label parsing
   - Event type filtering

7. **Gmail Automation (10 tests)**
   - Email actionability detection
   - Task content extraction
   - Gmail authentication

8. **Task Filtering (8 tests)**
   - Recurring task filtering
   - Historical task inclusion
   - Reschedule count aggregation

## Running Tests

### Run All Tests
```bash
# Using the test runner script
PYTHONPATH=. python3 run_tests.py

# Using pytest directly
PYTHONPATH=. python3 -m pytest tests/ -v
```

### Run Specific Test Files
```bash
# Test data types
PYTHONPATH=. python3 -m pytest tests/test_types.py -v

# Test database operations
PYTHONPATH=. python3 -m pytest tests/test_database.py -v

# Test data transformations
PYTHONPATH=. python3 -m pytest tests/test_transformations.py -v

# Test utility functions
PYTHONPATH=. python3 -m pytest tests/test_utils.py -v

# Test statistics functions
PYTHONPATH=. python3 -m pytest tests/test_stats.py -v

# Test dashboard utilities
PYTHONPATH=. python3 -m pytest tests/test_dashboard_utils.py -v

# Test Gmail automation
PYTHONPATH=. python3 -m pytest tests/test_gmail_automation.py -v

# Test task filtering
PYTHONPATH=. python3 -m pytest tests/test_rescheduled_tasks_filtering.py -v
```

### Run Specific Tests
```bash
# Run a specific test function
PYTHONPATH=. python3 -m pytest tests/test_types.py::test_project_entry_creation -v

# Run tests matching a pattern
PYTHONPATH=. python3 -m pytest tests/ -k "database" -v
```

## Dependencies

The tests require the following Python packages:
- `pytest` (testing framework)
- `pytest-mock` (enhanced mocking capabilities)
- `loguru`
- `pandas`
- `joblib`
- `tqdm`
- `hydra-core`
- `omegaconf`

## Test Coverage

The tests cover:

✅ **Data Structure Creation and Validation**
- All dataclass instantiation
- Property access and computed properties
- Default value handling
- Edge cases and error conditions

✅ **Database Operations**
- CRUD operations for tasks and projects
- Caching mechanisms
- API interaction patterns
- Error handling and validation

✅ **Data Transformations**
- Event processing and filtering
- DataFrame creation and structure
- Data type consistency
- Chronological ordering

✅ **Utility Functions**
- Dataclass field inspection and manipulation
- Safe instantiation with unexpected fields
- Configuration loading with Hydra
- Local storage operations (save/load with joblib)
- Cache management for activity and automation data
- Anonymization patterns
- Retry mechanisms with exponential backoff
- API key retrieval from environment

✅ **Statistics and Analysis**
- Task counting and aggregation by project
- Priority-based task filtering (P1/P2/P3/P4)
- Label analysis and filtering
- Date parsing with multiple format support
- Due date extraction from various formats
- Partial function application for priority levels

✅ **Dashboard and Automation Helpers**
- Metrics extraction with time-based granularity
- Percentage change calculations
- Badge generation for task priorities with emojis
- Multiplication label pattern matching
- Factor extraction for task duplication
- Event type filtering and aggregation

✅ **Gmail Automation Integration**
- Email actionability detection
- Task content extraction from emails
- Gmail authentication flow
- Task keyword coverage validation

✅ **Task Filtering and Processing**
- Recurring task filtering logic
- Historical task inclusion
- Reschedule count aggregation
- Mixed scenario handling

✅ **Bug Fixes**
- Fixed `TaskEntry.duration_kwargs` property implementation
- Proper error handling in API calls

## Test Framework Migration

The test suite has been migrated from `unittest` to `pytest`:

### Key Changes
- Converted from `TestCase` classes to plain functions with `test_` prefix
- Replaced `self.assertEqual()` with plain `assert` statements
- Converted `setUp()` methods to pytest fixtures
- Enhanced mocking with `pytest-mock`
- Simplified test runner using pytest's built-in discovery

### Benefits
- More concise and readable test code
- Better fixture management and dependency injection
- Enhanced parametrization capabilities
- Improved test discovery and reporting
- More flexible test execution options

## Test Results

Current status: **158 tests passing, 100% success rate**

### Test Breakdown by Module
- **test_types.py**: 12 tests - Data structure creation and validation
- **test_database.py**: 17 tests - Database operations and caching
- **test_transformations.py**: 7 tests - Data transformations and dataframe operations
- **test_utils.py**: 35 tests - Utility functions and helper classes
- **test_stats.py**: 40 tests - Statistics and task analysis functions
- **test_dashboard_utils.py**: 28 tests - Dashboard utilities and automation helpers
- **test_gmail_automation.py**: 10 tests - Gmail integration automation
- **test_rescheduled_tasks_filtering.py**: 8 tests - Task filtering logic

The comprehensive test suite validates that:
- Data structures are created correctly with proper defaults
- Database operations work as expected with proper caching
- Data transformations maintain consistency and formatting
- Utility functions handle edge cases and errors gracefully
- Statistics calculations are accurate across various scenarios
- Dashboard helpers generate correct metrics and badges
- Automation functions parse and process data correctly