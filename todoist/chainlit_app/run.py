#!/usr/bin/env python3
"""
Launch script for the Todoist Assistant Chainlit application.
"""

import sys
import os
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

if __name__ == "__main__":
    import chainlit as cl
    
    # Change to the chainlit app directory
    app_dir = Path(__file__).parent
    os.chdir(app_dir)
    
    # Run the Chainlit app
    cl.run(
        app="app.py",
        host="0.0.0.0",
        port=8000,
        debug=False,
        watch=True
    )