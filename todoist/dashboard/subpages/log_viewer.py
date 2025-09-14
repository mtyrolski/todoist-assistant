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


def read_log_file(file_path: str, tail_lines: int = 40, page: int = 1) -> tuple[Optional[str], int]:
    """Read lines from a log file with pagination support.
    
    Args:
        file_path: Path to the log file
        tail_lines: Number of lines per page
        page: Page number (1-based)
        
    Returns:
        Tuple of (content, total_pages)
    """
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            
        total_lines = len(lines)
        total_pages = max(1, (total_lines + tail_lines - 1) // tail_lines)  # Ceiling division
        
        if page < 1:
            page = 1
        elif page > total_pages:
            page = total_pages
            
        # Calculate start and end indices for the requested page
        # Page 1 shows the most recent lines (end of file)
        # Page 2 shows the lines before that, etc.
        end_line = total_lines - (page - 1) * tail_lines
        start_line = max(0, end_line - tail_lines)
        
        if start_line < 0:
            start_line = 0
        if end_line > total_lines:
            end_line = total_lines
            
        page_lines = lines[start_line:end_line]
        return ''.join(page_lines), total_pages
        
    except Exception as e:
        return f"Error reading file: {str(e)}", 1


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
            lines_per_page = st.number_input(
                "Lines per page",
                min_value=10,
                max_value=1000,
                value=40,
                step=10,
                key="lines_per_page"
            )
        
        with col2:
            auto_refresh = st.checkbox("Auto-refresh", value=False)
            
        with col3:
            if st.button("🔄 Refresh"):
                st.rerun()
        
        # Initialize page number in session state
        if 'log_page' not in st.session_state:
            st.session_state.log_page = 1
        
        # Get log content with pagination
        log_content, total_pages = read_log_file(selected_file, lines_per_page, st.session_state.log_page)
        
        # Pagination controls
        if total_pages > 1:
            st.subheader("📄 Page Navigation")
            col1, col2, col3, col4, col5 = st.columns(5)
            
            with col1:
                if st.button("⏮️ First", disabled=(st.session_state.log_page == 1)):
                    st.session_state.log_page = 1
                    st.rerun()
                    
            with col2:
                if st.button("⬅️ Previous", disabled=(st.session_state.log_page == 1)):
                    st.session_state.log_page = max(1, st.session_state.log_page - 1)
                    st.rerun()
                    
            with col3:
                # Page selector
                new_page = st.number_input(
                    f"Page (1-{total_pages})",
                    min_value=1,
                    max_value=total_pages,
                    value=st.session_state.log_page,
                    key="page_selector"
                )
                if new_page != st.session_state.log_page:
                    st.session_state.log_page = new_page
                    st.rerun()
                    
            with col4:
                if st.button("➡️ Next", disabled=(st.session_state.log_page == total_pages)):
                    st.session_state.log_page = min(total_pages, st.session_state.log_page + 1)
                    st.rerun()
                    
            with col5:
                if st.button("⏭️ Last", disabled=(st.session_state.log_page == total_pages)):
                    st.session_state.log_page = total_pages
                    st.rerun()
            
            st.info(f"📊 Showing page {st.session_state.log_page} of {total_pages} | Page {st.session_state.log_page} contains lines from the log file")
        
        # Display log content
        st.subheader(f"Content: {os.path.basename(selected_file)} (Page {st.session_state.log_page}/{total_pages})")
        
        if log_content and not log_content.startswith("Error reading file"):
            # Use a text area for better display
            st.code(log_content, language="text")
        else:
            st.warning("Unable to read the selected log file or file is empty.")
        
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
    - Adjust the lines per page to view more or less content
    - Use pagination controls to navigate through large log files
    - Page 1 shows the most recent entries (end of file)
    - Log files are searched in the current directory and common log locations
    """)