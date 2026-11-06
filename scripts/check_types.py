"""Run Pyright against the interpreter used by the current project environment."""

import subprocess
import sys


if __name__ == "__main__":
    raise SystemExit(
        subprocess.call(["pyright", "--pythonpath", sys.executable, "todoist"])
    )
