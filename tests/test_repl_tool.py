import numpy as np

from todoist.agent.repl_tool import SafePythonReplTool


def test_python_repl_allows_context_and_expressions():
    tool = SafePythonReplTool({"x": 1, "np": np})
    assert tool.run("x + 1") == "2"
    assert tool.run("int(np.array([1, 2, 3]).sum())") == "6"


def test_python_repl_blocks_imports_and_writes():
    tool = SafePythonReplTool({})
    assert "ERROR: blocked" in tool.run("import os")
    assert "ERROR: blocked" in tool.run("open('x.txt', 'w').write('nope')")
