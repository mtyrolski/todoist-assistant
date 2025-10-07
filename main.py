#!/usr/bin/env python3
"""Main entry point for Todoist Assistant Windows executable.

This module launches the Streamlit dashboard with proper configuration
management and user-friendly setup process.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from typing import Final

# Configuration constants
SERVER_STARTUP_DELAY: Final[int] = 3  # seconds to wait for Streamlit server initialization
DEFAULT_PORT: Final[int] = 8501
API_KEY_PLACEHOLDER: Final[str] = 'PUT YOUR API HERE'
TODOIST_API_URL: Final[str] = 'https://todoist.com/prefs/integrations'


def get_app_data_dir() -> Path:
    """Get or create the application data directory.
    
    Returns:
        Path to the application data directory.
    """
    if sys.platform == "win32":
        app_data = Path(os.environ.get('APPDATA', ''))
        app_dir = app_data / 'TodoistAssistant'
    else:
        # For other platforms (Linux/Mac)
        app_dir = Path.home() / '.todoist-assistant'
    
    app_dir.mkdir(exist_ok=True)
    return app_dir


def create_default_config(config_file: Path) -> None:
    """Create a default configuration file.
    
    Args:
        config_file: Path where the configuration file should be created.
    """
    with open(config_file, 'w', encoding='utf-8') as f:
        f.write(f"API_KEY = '{API_KEY_PLACEHOLDER}'\n")
        f.write("FILE_ENCODING = 'utf-8'\n")


def is_api_key_configured(config_file: Path) -> bool:
    """Check if a valid API key is configured.
    
    Args:
        config_file: Path to the configuration file.
        
    Returns:
        True if API key is configured, False otherwise.
    """
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            content = f.read()
            return API_KEY_PLACEHOLDER not in content
    except (FileNotFoundError, IOError):
        return False


def setup_config() -> bool:
    """Set up configuration files if they don't exist.
    
    Returns:
        True if configuration is ready, False if user action is needed.
    """
    app_dir = get_app_data_dir()
    config_file = app_dir / '.env'
    
    # Create config if it doesn't exist
    if not config_file.exists():
        example_config = Path(__file__).parent / '.env.example'
        
        if example_config.exists():
            import shutil
            shutil.copy2(example_config, config_file)
        else:
            create_default_config(config_file)
        
        print(f"Configuration file created at: {config_file}")
        print("Please edit this file to add your Todoist API key.")
        return False
    
    # Check if API key is configured
    if not is_api_key_configured(config_file):
        print(f"Please configure your Todoist API key in: {config_file}")
        return False
    
    return True


def build_launch_command(app_path: Path) -> list[str]:
    """Build the command to launch the Streamlit dashboard.
    
    Args:
        app_path: Path to the dashboard application file.
        
    Returns:
        List of command arguments.
    """
    return [
        'uv', 'run', 'streamlit', 'run',
        str(app_path),
        '--client.showErrorDetails=False',
        '--server.headless=True',
        '--browser.gatherUsageStats=False'
    ]


def launch_dashboard() -> None:
    """Launch the Streamlit dashboard with proper environment setup."""
    # Setup environment
    app_dir = get_app_data_dir()
    config_file = app_dir / '.env'
    current_dir = Path(__file__).parent
    
    env = os.environ.copy()
    env['PYTHONPATH'] = str(current_dir)
    
    if config_file.exists():
        env['DOTENV_PATH'] = str(config_file)
    
    # Change to app directory for relative paths
    os.chdir(current_dir)
    
    # Build and execute launch command
    app_path = current_dir / 'todoist' / 'dashboard' / 'app.py'
    cmd = build_launch_command(app_path)
    
    print("Starting Todoist Assistant Dashboard...")
    print("The dashboard will open in your web browser shortly.")
    
    # Start the Streamlit process
    process = subprocess.Popen(cmd, env=env)
    
    # Wait for server initialization
    time.sleep(SERVER_STARTUP_DELAY)
    
    # Open browser
    webbrowser.open(f'http://localhost:{DEFAULT_PORT}')
    
    # Wait for process completion
    try:
        process.wait()
    except KeyboardInterrupt:
        print("\nShutting down Todoist Assistant...")
        process.terminate()
        process.wait()


def open_config_file(config_file: Path) -> None:
    """Attempt to open the configuration file for editing.
    
    Args:
        config_file: Path to the configuration file.
    """
    if sys.platform == "win32":
        try:
            os.startfile(str(config_file))
        except (OSError, AttributeError):
            pass


def show_configuration_instructions() -> None:
    """Display instructions for configuring the application."""
    print("\nConfiguration needed. Please:")
    print(f"1. Get your Todoist API key from {TODOIST_API_URL}")
    print("2. Edit the configuration file with your API key")
    print("3. Run this application again")


def is_demo_mode() -> bool:
    """Check if the application should run in demo mode.
    
    Returns:
        True if demo mode is requested, False otherwise.
    """
    return len(sys.argv) > 1 and 'demo' in sys.argv[1].lower()


def main() -> None:
    """Main entry point for the application."""
    print("=" * 50)
    print("        Todoist Assistant Dashboard")
    print("=" * 50)
    
    # Check for demo mode
    if is_demo_mode():
        print("Running in DEMO mode")
        launch_dashboard()
        return
    
    # Setup configuration
    if not setup_config():
        show_configuration_instructions()
        
        app_dir = get_app_data_dir()
        config_file = app_dir / '.env'
        
        # Try to open config file for editing
        open_config_file(config_file)
        
        input("\nPress Enter to exit...")
        return
    
    # Launch the dashboard
    launch_dashboard()


if __name__ == "__main__":
    main()