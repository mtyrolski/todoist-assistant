#!/usr/bin/env python3
"""
Test runner for todoist-assistant tests.

This script runs all the tests in the tests/ directory using pytest.
"""

import subprocess
import sys
import os

def run_tests():
    """Run all tests using pytest and return the result."""
    # Add the current directory to Python path for imports
    current_dir = os.path.dirname(os.path.abspath(__file__))
    env = os.environ.copy()
    if 'PYTHONPATH' in env:
        env['PYTHONPATH'] = f"{current_dir}:{env['PYTHONPATH']}"
    else:
        env['PYTHONPATH'] = current_dir
    
    # Run pytest with verbose output
    cmd = [sys.executable, '-m', 'pytest', 'tests/', '-v', '--tb=short']
    
    try:
        result = subprocess.run(cmd, cwd=current_dir, env=env, 
                              capture_output=False, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        print("Error: pytest not found. Please install pytest: pip install pytest")
        return False

if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)