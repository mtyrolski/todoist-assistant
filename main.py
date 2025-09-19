#!/usr/bin/env python3
"""
Main entry point for Todoist Assistant Windows executable.
This script launches the Streamlit dashboard with proper configuration.
"""

import os
import sys
import subprocess
import webbrowser
import time
from pathlib import Path
import shutil


def get_app_data_dir():
    """Get or create the application data directory."""
    if sys.platform == "win32":
        app_data = Path(os.environ.get('APPDATA', ''))
        app_dir = app_data / 'TodoistAssistant'
    else:
        # For other platforms (Linux/Mac)
        home = Path.home()
        app_dir = home / '.todoist-assistant'
    
    app_dir.mkdir(exist_ok=True)
    return app_dir


def setup_config():
    """Set up configuration files if they don't exist."""
    app_dir = get_app_data_dir()
    config_file = app_dir / '.env'
    
    # Copy example config if .env doesn't exist
    if not config_file.exists():
        example_config = Path(__file__).parent / '.env.example'
        if example_config.exists():
            shutil.copy2(example_config, config_file)
            print(f"Configuration file created at: {config_file}")
            print("Please edit this file to add your Todoist API key.")
            return False
        else:
            # Create a basic .env file
            with open(config_file, 'w') as f:
                f.write("API_KEY = 'PUT YOUR API HERE'\n")
                f.write("FILE_ENCODING = 'utf-8'\n")
            print(f"Configuration file created at: {config_file}")
            print("Please edit this file to add your Todoist API key.")
            return False
    
    # Check if API key is configured
    with open(config_file, 'r') as f:
        content = f.read()
        if 'PUT YOUR API HERE' in content:
            print(f"Please configure your Todoist API key in: {config_file}")
            return False
    
    return True


def launch_dashboard():
    """Launch the Streamlit dashboard."""
    # Set environment variables
    app_dir = get_app_data_dir()
    config_file = app_dir / '.env'
    
    # Set PYTHONPATH to current directory
    current_dir = Path(__file__).parent
    env = os.environ.copy()
    env['PYTHONPATH'] = str(current_dir)
    
    # Set config file location
    if config_file.exists():
        env['DOTENV_PATH'] = str(config_file)
    
    # Change to app directory for relative paths
    os.chdir(current_dir)
    
    # Launch Streamlit
    app_path = current_dir / 'todoist' / 'dashboard' / 'app.py'
    cmd = [
        sys.executable, '-m', 'streamlit', 'run', 
        str(app_path),
        '--client.showErrorDetails=False',
        '--server.headless=True',
        '--browser.gatherUsageStats=False'
    ]
    
    print("Starting Todoist Assistant Dashboard...")
    print("The dashboard will open in your web browser shortly.")
    
    # Start the Streamlit process
    process = subprocess.Popen(cmd, env=env)
    
    # Wait a bit for the server to start
    time.sleep(3)
    
    # Open browser
    webbrowser.open('http://localhost:8501')
    
    try:
        # Wait for the process to complete
        process.wait()
    except KeyboardInterrupt:
        print("\nShutting down Todoist Assistant...")
        process.terminate()
        process.wait()


def main():
    """Main entry point."""
    print("=" * 50)
    print("        Todoist Assistant Dashboard")
    print("=" * 50)
    
    # Check if this is a demo run
    demo_mode = len(sys.argv) > 1 and 'demo' in sys.argv[1].lower()
    
    if demo_mode:
        print("Running in DEMO mode")
        # For demo mode, skip config setup
        launch_dashboard()
    else:
        # Setup configuration
        if not setup_config():
            print("\nConfiguration needed. Please:")
            print("1. Get your Todoist API key from https://todoist.com/prefs/integrations")
            print("2. Edit the configuration file with your API key")
            print("3. Run this application again")
            
            app_dir = get_app_data_dir()
            config_file = app_dir / '.env'
            
            # Try to open the config file for editing
            if sys.platform == "win32":
                try:
                    os.startfile(str(config_file))
                except:
                    pass
            
            input("\nPress Enter to exit...")
            return
        
        # Launch the dashboard
        launch_dashboard()


if __name__ == "__main__":
    main()