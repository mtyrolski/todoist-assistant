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

# Using unittest directly
PYTHONPATH=. python3 -m unittest discover tests/ -v
```

### Run Specific Test Files
```bash
# Test data types
PYTHONPATH=. python3 -m unittest tests.test_types -v

# Test database operations
PYTHONPATH=. python3 -m unittest tests.test_database -v

# Test data transformations
PYTHONPATH=. python3 -m unittest tests.test_transformations -v
```

### Run Individual Test Classes
```bash
# Test data structure creation
PYTHONPATH=. python3 -m unittest tests.test_types.TestDataStructureCreation -v

# Test database tasks operations
PYTHONPATH=. python3 -m unittest tests.test_database.TestDatabaseTasksOperations -v
```

## Dependencies

The tests require the following Python packages:
- `unittest` (built-in)
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

## Test Results

Current status: **36 tests passing, 100% success rate**

The test suite validates that data structures are created correctly, database operations work as expected, and data transformations maintain consistency and proper formatting.