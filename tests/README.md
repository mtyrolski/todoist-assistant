# Tests for Todoist Assistant

This directory contains comprehensive tests for the data structures and database operations in the todoist-assistant project.

## Test Structure

### Test Files

- **`test_types.py`** - Tests for data structure creation, composition, and utilities
- **`test_database.py`** - Tests for database operations (CRUD, caching, API interactions)
- **`test_transformations.py`** - Tests for data transformations and dataframe operations

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

Current status: **36 tests passing, 100% success rate**

The test suite validates that data structures are created correctly, database operations work as expected, and data transformations maintain consistency and proper formatting.