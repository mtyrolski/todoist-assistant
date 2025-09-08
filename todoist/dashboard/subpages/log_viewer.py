"""
Log Viewer subpage for displaying .log files in the dashboard.
"""

import streamlit as st
import os
from typing import List, Optional
from pathlib import Path


def get_available_log_files() -> List[str]:
    """Get a list of available .log files in the current directory and common log locations."""
    log_files = []
    
    # Check current directory
    current_dir = Path.cwd()
    for log_file in current_dir.glob("*.log"):
        if log_file.is_file():
            log_files.append(str(log_file))
    
    # Check common log directories
    common_log_dirs = [
        Path.cwd() / "logs",
        Path.cwd() / "log", 
        Path("/var/log"),
        Path("/tmp")
    ]
    
    for log_dir in common_log_dirs:
        if log_dir.exists() and log_dir.is_dir():
            for log_file in log_dir.glob("*.log"):
                if log_file.is_file():
                    log_files.append(str(log_file))
    
    return sorted(list(set(log_files)))  # Remove duplicates and sort


def read_log_file(file_path: str, tail_lines: int = 100) -> Optional[str]:
    """Read the last N lines from a log file."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            if tail_lines > 0:
                lines = lines[-tail_lines:]
            return ''.join(lines)
    except Exception as e:
        return f"Error reading file: {str(e)}"


def render_log_viewer_page() -> None:
    """Render the log viewer page."""
    st.title("📋 Log Viewer")
    st.write("View and monitor log files from your Todoist Assistant automations and other processes.")
    
    # Get available log files
    log_files = get_available_log_files()
    
    if not log_files:
        st.info("No .log files found in the current directory or common log locations.")
        st.write("Log files will appear here once automations are run or other processes create log files.")
        return
    
    # Display available log files
    st.subheader("Available Log Files")
    
    # File selection
    selected_file = st.selectbox(
        "Select a log file to view:",
        options=log_files,
        format_func=lambda x: os.path.basename(x)
    )
    
    if selected_file:
        # Display file information
        file_path = Path(selected_file)
        file_stat = file_path.stat()
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("File Size", f"{file_stat.st_size / 1024:.1f} KB")
        with col2:
            st.metric("Modified", file_stat.st_mtime)
        with col3:
            st.metric("Location", str(file_path.parent))
        
        # Options for viewing
        st.subheader("Viewing Options")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            tail_lines = st.number_input(
                "Number of lines to show (from end)",
                min_value=10,
                max_value=1000,
                value=100,
                step=10
            )
        
        with col2:
            auto_refresh = st.checkbox("Auto-refresh", value=False)
            
        with col3:
            if st.button("🔄 Refresh"):
                st.rerun()
        
        # Display log content
        st.subheader(f"Content: {os.path.basename(selected_file)}")
        
        log_content = read_log_file(selected_file, tail_lines)
        
        if log_content:
            # Use a text area for better display
            st.code(log_content, language="text")
        else:
            st.warning("Unable to read the selected log file.")
        
        # Auto-refresh functionality
        if auto_refresh:
            import time
            time.sleep(2)  # Wait 2 seconds
            st.rerun()
    
    # Additional information
    st.subheader("ℹ️ About Log Files")
    st.info("""
    **Common log files you might find:**
    - `automation.log` - Contains logs from Todoist automation runs
    - Other `.log` files created by various processes
    
    **Tips:**
    - Use the refresh button or auto-refresh to see real-time updates
    - Adjust the number of lines to view more or less content
    - Log files are searched in the current directory and common log locations
    """)