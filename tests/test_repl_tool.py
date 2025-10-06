"""
Tests for the REPL tool.
"""
import datetime as dt
import pytest

from agent.tools.repl_tool import (
    CodeValidationError,
    ReplResult,
    run_python,
    _validate_ast
)
from todoist.types import Event, EventEntry


@pytest.fixture
def sample_events():
    """Create sample events for testing."""
    events = []
    for i in range(3):
        event_entry = EventEntry(
            id=f"event_{i}",
            object_type="item",
            object_id=f"task_{i}",
            event_type="completed" if i % 2 == 0 else "added",
            event_date=f"2024-01-0{i+1}T10:00:00Z",
            parent_project_id=f"project_{i}",
            parent_item_id=None,
            initiator_id="user_1",
            extra_data={"content": f"Task {i}"},
            extra_data_id=f"extra_{i}",
            v2_object_id=f"v2_task_{i}",
            v2_parent_item_id=None,
            v2_parent_project_id=f"v2_project_{i}"
        )
        event = Event(
            event_entry=event_entry,
            id=f"event_{i}",
            date=dt.datetime(2024, 1, i+1, 10, 0, 0)
        )
        events.append(event)
    return events


class TestCodeValidation:
    """Tests for AST code validation."""
    
    def test_validate_simple_code(self):
        """Test that simple code passes validation."""
        code = "x = 5\ny = x + 10"
        _validate_ast(code)  # Should not raise
    
    def test_validate_forbid_import(self):
        """Test that import statements are forbidden."""
        code = "import os"
        with pytest.raises(CodeValidationError, match="Import statements are forbidden"):
            _validate_ast(code)
    
    def test_validate_forbid_import_from(self):
        """Test that from...import statements are forbidden."""
        code = "from os import path"
        with pytest.raises(CodeValidationError, match="Import statements are forbidden"):
            _validate_ast(code)
    
    def test_validate_forbid_dunder_attrs(self):
        """Test that dunder attributes are forbidden."""
        code = "x.__class__"
        with pytest.raises(CodeValidationError, match="attribute.*forbidden"):
            _validate_ast(code)
    
    def test_validate_allow_normal_attrs(self):
        """Test that normal attributes are allowed."""
        code = "events[0].name"
        _validate_ast(code)  # Should not raise
    
    def test_validate_syntax_error(self):
        """Test that syntax errors are caught."""
        code = "x = ("
        with pytest.raises(CodeValidationError, match="SyntaxError"):
            _validate_ast(code)


class TestReplExecution:
    """Tests for REPL code execution."""
    
    def test_simple_expression(self, sample_events):
        """Test executing a simple expression."""
        result = run_python("x = 42", sample_events)
        assert result.error is None
        assert result.exec_time_ms >= 0
    
    def test_access_events(self, sample_events):
        """Test accessing events tuple."""
        result = run_python("x = len(events)", sample_events)
        assert result.error is None
        # Note: The result.value_repr will be the repr of x (3)
    
    def test_print_output(self, sample_events):
        """Test capturing print output."""
        result = run_python("print('hello')", sample_events)
        assert result.error is None
        assert "hello" in result.stdout
    
    def test_safe_builtins(self, sample_events):
        """Test that safe builtins work."""
        result = run_python("x = sum([1, 2, 3])", sample_events)
        assert result.error is None
    
    def test_forbidden_import_execution(self, sample_events):
        """Test that imports are caught at validation."""
        with pytest.raises(CodeValidationError):
            run_python("import os", sample_events)
    
    def test_error_handling(self, sample_events):
        """Test that errors are captured properly."""
        result = run_python("x = 1 / 0", sample_events)
        assert result.error is not None
        assert "ZeroDivisionError" in result.error
    
    def test_timeout(self, sample_events):
        """Test that timeout is enforced."""
        result = run_python("while True: pass", sample_events, timeout_s=0.5)
        assert result.error is not None
        assert "Timeout" in result.error
    
    def test_output_truncation(self, sample_events):
        """Test that large outputs are truncated."""
        code = "print('x' * 10000)"
        result = run_python(code, sample_events, max_output_chars=100)
        assert len(result.stdout) <= 120  # 100 + truncation message
        assert "truncated" in result.stdout.lower()
    
    def test_events_immutable(self, sample_events):
        """Test that events are provided as tuple (immutable)."""
        code = "x = isinstance(events, tuple)"
        result = run_python(code, sample_events)
        assert result.error is None
        # The events should be exposed as a tuple
    
    def test_list_comprehension(self, sample_events):
        """Test list comprehensions work."""
        code = "x = [e.event_type for e in events]"
        result = run_python(code, sample_events)
        assert result.error is None


class TestReplResult:
    """Tests for ReplResult dataclass."""
    
    def test_repl_result_creation(self):
        """Test creating ReplResult."""
        result = ReplResult(
            stdout="output",
            value_repr="42",
            error=None,
            exec_time_ms=100
        )
        assert result.stdout == "output"
        assert result.value_repr == "42"
        assert result.error is None
        assert result.exec_time_ms == 100
    
    def test_repl_result_with_error(self):
        """Test ReplResult with error."""
        result = ReplResult(
            stdout="",
            value_repr=None,
            error="ValueError: invalid value",
            exec_time_ms=50
        )
        assert result.error == "ValueError: invalid value"
        assert result.value_repr is None
