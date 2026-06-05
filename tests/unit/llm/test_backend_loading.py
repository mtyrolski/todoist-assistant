"""Tests for lazy optional AI backend imports."""

import subprocess
import sys


def test_llm_facade_does_not_load_backend_modules() -> None:
    script = """
import importlib
import sys

importlib.import_module("todoist.llm")
importlib.import_module("todoist.llm.model_catalog")

loaded = [
    name for name in (
        "todoist.llm.backends.transformers",
        "todoist.llm.backends.triton",
        "todoist.llm.backends.codex",
    )
    if name in sys.modules
]
if loaded:
    raise SystemExit(",".join(loaded))
"""
    result = subprocess.run(
        [sys.executable, "-c", script], text=True, capture_output=True, check=False
    )

    assert result.returncode == 0, result.stderr or result.stdout
