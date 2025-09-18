#!/usr/bin/env python3
"""
Demo script to show the Chainlit app with sample data.
This creates minimal sample data to demonstrate the interface without requiring real Todoist data.
"""

import sys
import os
from pathlib import Path
import pandas as pd
import tempfile
from datetime import datetime, timedelta

# Add the project root to the Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

def create_demo_data():
    """Create minimal demo data for testing the interface."""
    # Create a minimal activity dataframe
    dates = pd.date_range(start=datetime.now() - timedelta(days=30), end=datetime.now(), freq='D')
    
    demo_data = []
    for date in dates:
        # Add some sample events
        demo_data.extend([
            {'date': date, 'type': 'added', 'root_project_name': 'Demo Project 1', 'root_project_id': '1'},
            {'date': date, 'type': 'completed', 'root_project_name': 'Demo Project 1', 'root_project_id': '1'},
            {'date': date, 'type': 'updated', 'root_project_name': 'Demo Project 2', 'root_project_id': '2'},
        ])
    
    df = pd.DataFrame(demo_data)
    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)
    
    return df

def run_demo():
    """Run the Chainlit app in demo mode."""
    print("🚀 Starting Chainlit Demo Mode")
    print("=" * 50)
    print("This demo will show the Chainlit interface without requiring real Todoist data.")
    print("Note: The app will try to load real data first, but this is expected to fail in demo mode.")
    print("The interface will still be fully functional for demonstration purposes.")
    print()
    print("📡 Starting server on http://localhost:8000")
    print("Press Ctrl+C to stop the demo")
    print("=" * 50)
    
    # Set demo mode environment variable
    os.environ['TODOIST_DEMO_MODE'] = '1'
    
    # Change to the chainlit app directory
    app_dir = Path(__file__).parent
    os.chdir(app_dir)
    
    # Import and run chainlit
    import chainlit as cl
    cl.run(host="0.0.0.0", port=8000, debug=False)

if __name__ == "__main__":
    run_demo()