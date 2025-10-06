"""
Secure REPL tool for executing Python code with read-only access to Event data.

This module provides a sandboxed Python interpreter that:
- Only exposes events as a read-only tuple
- Allows a limited set of safe builtins
- Forbids imports and dangerous attribute access
- Runs code in a separate process with timeout
- Captures stdout and truncates large outputs
"""
import ast
import io
import multiprocessing
import sys
import time
from dataclasses import dataclass
from typing import Any

from todoist.types import Event

# Allowlist of safe builtin functions
SAFE_BUILTINS = {
    "len", "sum", "min", "max", "sorted", "enumerate", "range",
    "map", "filter", "any", "all", "zip", "list", "dict", "set",
    "tuple", "abs", "round", "str", "int", "float", "bool",
    "isinstance", "type", "repr", "print"
}

# Dangerous attributes to forbid
FORBIDDEN_ATTRS = {
    "__class__", "__subclasses__", "__globals__", "__getattribute__",
    "__dict__", "__mro__", "__base__", "__bases__", "__import__",
    "__builtins__", "__code__", "__closure__"
}


@dataclass(slots=True)
class ReplResult:
    """Result from executing Python code in the REPL."""
    stdout: str
    value_repr: str | None
    error: str | None
    exec_time_ms: int


class CodeValidationError(Exception):
    """Raised when code fails security validation."""
    pass


def _validate_ast(code: str) -> None:
    """
    Validate that code doesn't contain forbidden constructs.
    
    Args:
        code: Python code to validate
        
    Raises:
        CodeValidationError: If code contains forbidden constructs
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise CodeValidationError(f"SyntaxError: {e}") from e
    
    for node in ast.walk(tree):
        # Forbid imports
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise CodeValidationError("Import statements are forbidden")
        
        # Forbid dangerous attribute access
        if isinstance(node, ast.Attribute):
            attr_name = node.attr
            if attr_name.startswith("__") or attr_name in FORBIDDEN_ATTRS:
                raise CodeValidationError(
                    f"Access to attribute '{attr_name}' is forbidden"
                )


def _execute_in_subprocess(
    code: str,
    events: tuple[Event, ...],
    result_queue: multiprocessing.Queue,
    timeout_s: float
) -> None:
    """
    Execute code in a subprocess with timeout.
    
    Args:
        code: Python code to execute
        events: Tuple of Event objects (read-only)
        result_queue: Queue to return the result
        timeout_s: Maximum execution time in seconds
    """
    try:
        start_time = time.perf_counter()
        
        # Capture stdout
        old_stdout = sys.stdout
        sys.stdout = captured_output = io.StringIO()
        
        # Create restricted globals with only safe builtins and events
        restricted_globals = {
            "__builtins__": {name: __builtins__[name] for name in SAFE_BUILTINS if name in __builtins__}
        }
        restricted_globals["events"] = events
        
        # Compile and execute code
        compiled_code = compile(code, "<repl>", "exec")
        local_vars: dict[str, Any] = {}
        exec(compiled_code, restricted_globals, local_vars)
        
        # Get the last expression value if any
        last_value = None
        if local_vars:
            # Try to get the last assigned variable or expression result
            for key in reversed(list(local_vars.keys())):
                if not key.startswith("_"):
                    last_value = local_vars[key]
                    break
        
        # Restore stdout
        sys.stdout = old_stdout
        stdout_value = captured_output.getvalue()
        
        exec_time_ms = int((time.perf_counter() - start_time) * 1000)
        
        result_queue.put({
            "stdout": stdout_value,
            "value_repr": repr(last_value) if last_value is not None else None,
            "error": None,
            "exec_time_ms": exec_time_ms
        })
        
    except Exception as e:
        sys.stdout = old_stdout
        exec_time_ms = int((time.perf_counter() - start_time) * 1000)
        error_type = type(e).__name__
        error_msg = str(e)
        result_queue.put({
            "stdout": "",
            "value_repr": None,
            "error": f"{error_type}: {error_msg}",
            "exec_time_ms": exec_time_ms
        })


def run_python(
    code: str,
    events: list[Event],
    *,
    timeout_s: float = 2.0,
    max_output_chars: int = 4096
) -> ReplResult:
    """
    Execute Python code in a secure sandbox with read-only access to events.
    
    Args:
        code: Python code to execute
        events: List of Event objects (will be exposed as read-only tuple)
        timeout_s: Maximum execution time in seconds (default: 2.0)
        max_output_chars: Maximum characters in output strings (default: 4096)
        
    Returns:
        ReplResult with stdout, value representation, error (if any), and execution time
        
    Raises:
        CodeValidationError: If code contains forbidden constructs
    """
    # Validate code first
    _validate_ast(code)
    
    # Convert events to tuple for read-only access
    events_tuple = tuple(events)
    
    # Create result queue for subprocess communication
    result_queue: multiprocessing.Queue = multiprocessing.Queue()
    
    # Execute in subprocess with timeout
    process = multiprocessing.Process(
        target=_execute_in_subprocess,
        args=(code, events_tuple, result_queue, timeout_s)
    )
    
    process.start()
    process.join(timeout=timeout_s)
    
    if process.is_alive():
        # Timeout occurred
        process.terminate()
        process.join(timeout=1.0)
        if process.is_alive():
            process.kill()
            process.join()
        
        return ReplResult(
            stdout="",
            value_repr=None,
            error="TimeoutError: Execution exceeded timeout",
            exec_time_ms=int(timeout_s * 1000)
        )
    
    # Get result from queue
    if not result_queue.empty():
        result_data = result_queue.get()
        
        # Truncate outputs if necessary
        stdout = result_data["stdout"][:max_output_chars]
        if len(result_data["stdout"]) > max_output_chars:
            stdout += "\n... (truncated)"
        
        value_repr = result_data["value_repr"]
        if value_repr and len(value_repr) > max_output_chars:
            value_repr = value_repr[:max_output_chars] + "... (truncated)"
        
        return ReplResult(
            stdout=stdout,
            value_repr=value_repr,
            error=result_data["error"],
            exec_time_ms=result_data["exec_time_ms"]
        )
    else:
        # Process ended without result (likely crashed)
        return ReplResult(
            stdout="",
            value_repr=None,
            error="RuntimeError: Process terminated unexpectedly",
            exec_time_ms=0
        )
