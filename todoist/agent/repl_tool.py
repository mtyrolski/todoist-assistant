"""Restricted Python REPL tool for analysis (read-only).

The goal is not perfect sandboxing, but a practical guardrail:
- no imports
- no dunder access
- no direct file / OS / subprocess access from generated code
"""

import ast
import io
from types import ModuleType
from typing import Any
import contextlib
import builtins
import os
import pathlib
import shutil


_BANNED_SUBSTRINGS = (
    "__",
    "import ",
    "import\t",
    "open(",
    "pathlib",
    "os.",
    "sys.",
    "subprocess",
    "shutil",
    "socket",
    "requests",
    "httpx",
    "urllib",
    "pickle",
    "joblib",
    "rm ",
    "del ",
    "unlink(",
    "remove(",
    "rmdir(",
    "rename(",
    "chmod(",
    "chown(",
    "kill(",
    "Popen",
    "system(",
    "eval(",
    "exec(",
    "compile(",
)


def _is_code_safe(code: str) -> tuple[bool, str]:
    lowered = code.lower()
    blocked_token = next(
        (token for token in _BANNED_SUBSTRINGS if token in lowered), None
    )
    if blocked_token is not None:
        return False, f"Blocked token detected: {blocked_token!r}"

    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        return False, f"SyntaxError: {exc}"

    banned_nodes = (
        ast.Import,
        ast.ImportFrom,
        ast.With,
        ast.Try,
        ast.Raise,
        ast.Lambda,
        ast.ClassDef,
        ast.FunctionDef,
    )
    reason: str | None = None
    for node in ast.walk(tree):
        if isinstance(node, banned_nodes):
            reason = f"Blocked syntax: {node.__class__.__name__}"
            break
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            reason = "Blocked attribute access"
            break
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            reason = "Blocked name access"
            break
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"open", "eval", "exec", "compile", "__import__"}
        ):
            reason = f"Blocked call: {node.func.id}"
            break

    return (False, reason) if reason else (True, "")


_SAFE_BUILTINS: dict[str, Any] = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "__import__": __import__,
    "dict": dict,
    "enumerate": enumerate,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "print": print,
    "range": range,
    "reversed": reversed,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
}


_SAFE_BUILTINS_MODULE = ModuleType("safe_builtins")
for _name, _value in _SAFE_BUILTINS.items():
    setattr(_SAFE_BUILTINS_MODULE, _name, _value)


class SafePythonReplTool:
    """A tiny REPL-like executor with persistent locals."""

    def __init__(self, context: dict[str, Any]):
        self._globals: dict[str, Any] = {
            "__builtins__": _SAFE_BUILTINS_MODULE,
            **context,
        }
        self._locals: dict[str, Any] = {}

    def run(self, code: str) -> str:
        code = (code or "").strip()
        if not code:
            return ""

        ok, reason = _is_code_safe(code)
        if not ok:
            if reason.startswith("SyntaxError:"):
                return f"ERROR: {reason}"
            label = reason or "blocked"
            return f"ERROR: blocked ({label})"

        stdout = io.StringIO()
        try:
            tree = ast.parse(code, mode="exec")
            with _read_only_sandbox(), contextlib.redirect_stdout(stdout):
                for node in tree.body:
                    if isinstance(node, ast.Expr):
                        value = eval(  # pylint: disable=eval-used
                            compile(
                                ast.Expression(node.value),
                                "<python_repl>",
                                "eval",
                            ),
                            self._globals,
                            self._locals,
                        )
                        if value is not None:
                            print(repr(value))
                        continue
                    exec(  # pylint: disable=exec-used
                        compile(
                            ast.Module(body=[node], type_ignores=[]),
                            "<python_repl>",
                            "exec",
                        ),
                        self._globals,
                        self._locals,
                    )

        except Exception as e:
            return f"ERROR: {e.__class__.__name__}: {e}"

        return stdout.getvalue().rstrip()


@contextlib.contextmanager
def _read_only_sandbox():
    """Best-effort guardrail against writes / deletes during tool execution."""

    def _blocked(*_args: Any, **_kwargs: Any):  # noqa: ANN401
        raise PermissionError("Read-only tool: operation blocked")

    def _safe_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any):  # noqa: ANN401  pylint: disable=keyword-arg-before-vararg
        write_flags = ("w", "a", "+", "x")
        if any(flag in mode for flag in write_flags):
            raise PermissionError("Read-only tool: open() for writing is blocked")
        return _orig_open(file, mode, *args, **kwargs)

    _orig_open = builtins.open

    originals: list[tuple[Any, str, Any]] = []

    def _patch(obj: Any, name: str, new: Any) -> None:  # noqa: ANN401
        if hasattr(obj, name):
            originals.append((obj, name, getattr(obj, name)))
            setattr(obj, name, new)

    try:
        _patch(builtins, "open", _safe_open)
        _patch(os, "remove", _blocked)
        _patch(os, "unlink", _blocked)
        _patch(os, "rmdir", _blocked)
        _patch(os, "mkdir", _blocked)
        _patch(os, "makedirs", _blocked)
        _patch(os, "open", _blocked)
        _patch(os, "rename", _blocked)
        _patch(os, "replace", _blocked)
        _patch(os, "system", _blocked)
        _patch(os, "popen", _blocked)
        _patch(os, "chmod", _blocked)
        _patch(os, "chown", _blocked)
        _patch(os, "utime", _blocked)
        _patch(shutil, "rmtree", _blocked)
        _patch(shutil, "move", _blocked)
        _patch(pathlib.Path, "unlink", _blocked)
        _patch(pathlib.Path, "touch", _blocked)
        _patch(pathlib.Path, "write_text", _blocked)
        _patch(pathlib.Path, "write_bytes", _blocked)
        _patch(pathlib.Path, "mkdir", _blocked)
        _patch(pathlib.Path, "rmdir", _blocked)
        _patch(pathlib.Path, "rename", _blocked)
        _patch(pathlib.Path, "replace", _blocked)
        yield
    finally:
        for obj, name, old in reversed(originals):
            setattr(obj, name, old)
