"""
Project Adjustment GUI for managing archived project to active project mappings.
Provides a drag-and-drop interface to replace manual file editing.
"""

import streamlit as st
import os
from pathlib import Path
from typing import Dict, List, Tuple

from todoist.types import Project
from todoist.database.base import Database
from todoist.database.dataframe import get_adjusting_mapping, ADJUSTMENTS_VARIABLE_NAME


def render_project_adjustment_page(dbio: Database) -> None:
    """
    Renders the project adjustment management page.
    
    Args:
        dbio: Database instance for fetching projects
    """
    st.header("Project Adjustment Manager")
    st.write("Map archived projects to current active projects for better statistics and reporting.")
    st.info("This tool helps you link old archived projects to current main projects, making your statistics more cohesive.")
    
    # Load current mappings
    try:
        current_mappings = get_adjusting_mapping()
    except Exception as e:
        st.error(f"Error loading current mappings: {str(e)}")
        current_mappings = {}
    
    # Fetch projects
    try:
        with st.spinner("Loading projects..."):
            active_projects = dbio.fetch_projects(include_tasks=False)
            archived_projects = dbio.fetch_archived_projects()
    except Exception as e:
        st.error(f"Error loading projects: {str(e)}")
        st.warning("This feature requires a valid Todoist API connection. Please ensure your .env file is configured correctly.")
        
        # Create demo data for testing
        st.subheader("Demo Mode")
        st.write("Since no projects could be loaded, here's a demonstration of how the interface works:")
        
        # Demo data
        demo_archived = ["Old Work Project 📊", "Legacy Personal Tasks 📝", "Archived Travel Plans ✈️"]
        demo_active = ["Current Work 💼", "Personal Life 🏠", "Travel & Adventures 🌍"]
        
        col1, col2 = st.columns(2)
        with col1:
            st.write("**Demo Archived Projects**")
            for project in demo_archived:
                st.write(f"📦 {project}")
        
        with col2:
            st.write("**Demo Active Projects**")
            for project in demo_active:
                st.write(f"📁 {project}")
        
        # Demo mapping interface
        st.subheader("Demo Mapping Interface")
        selected_archived = st.selectbox("Select archived project:", demo_archived, key="demo_archived")
        selected_active = st.selectbox("Map to active project:", demo_active, key="demo_active")
        
        if st.button("Add Mapping (Demo)", key="demo_add"):
            st.success(f"Demo mapping: {selected_archived} → {selected_active}")
            
        st.code(f"""# Demo adjustment file content
{ADJUSTMENTS_VARIABLE_NAME} = {{
    "{selected_archived}": "{selected_active}",
    # Add more mappings as needed
}}""", language='python')
        
        return
    
    # Filter root projects (projects without parent)
    active_root_projects = [p for p in active_projects if p.project_entry.parent_id is None]
    archived_root_projects = [p for p in archived_projects if p.project_entry.parent_id is None]
    
    # Filter out already mapped archived projects
    unmapped_archived = [p for p in archived_root_projects if p.project_entry.name not in current_mappings]
    
    st.subheader("Current Mappings")
    if current_mappings:
        st.write("Existing archived project mappings:")
        for archived_name, active_name in current_mappings.items():
            st.write(f"📦 **{archived_name}** → 📁 **{active_name}**")
    else:
        st.info("No current mappings found.")
    
    st.subheader("Available Projects")
    
    # Create two columns
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**Unmapped Archived Projects** (select from here)")
        if unmapped_archived:
            for project in unmapped_archived:
                st.write(f"📦 {project.project_entry.name}")
        else:
            st.info("All archived projects are already mapped.")
    
    with col2:
        st.write("**Active Root Projects** (map targets)")
        if active_root_projects:
            for project in active_root_projects:
                st.write(f"📁 {project.project_entry.name}")
        else:
            st.warning("No active root projects found.")
    
    # Simple mapping interface
    st.subheader("Create New Mapping")
    
    if unmapped_archived and active_root_projects:
        # Selectboxes for mapping
        selected_archived = st.selectbox(
            "Select archived project:",
            options=[p.project_entry.name for p in unmapped_archived],
            key="select_archived"
        )
        
        selected_active = st.selectbox(
            "Map to active project:",
            options=[p.project_entry.name for p in active_root_projects],
            key="select_active"
        )
        
        # Add mapping button
        if st.button("Add Mapping", key="add_mapping"):
            if selected_archived and selected_active:
                # Add to current mappings for preview
                new_mappings = current_mappings.copy()
                new_mappings[selected_archived] = selected_active
                
                # Show preview
                st.success(f"Mapping added: {selected_archived} → {selected_active}")
                
                # Store in session state for preview
                if 'new_mappings' not in st.session_state:
                    st.session_state.new_mappings = {}
                st.session_state.new_mappings[selected_archived] = selected_active
    elif not unmapped_archived:
        st.info("All archived projects are already mapped.")
    elif not active_root_projects:
        st.warning("No active root projects available for mapping.")
    
    # Preview section
    st.subheader("Preview Adjustment File")
    
    # Combine current and new mappings for preview
    preview_mappings = current_mappings.copy()
    if 'new_mappings' in st.session_state:
        preview_mappings.update(st.session_state.new_mappings)
    
    # Generate preview content
    preview_content = generate_adjustment_file_content(preview_mappings)
    
    st.code(preview_content, language='python')
    
    # Remove mapping functionality
    if 'new_mappings' in st.session_state and st.session_state.new_mappings:
        st.subheader("Remove Pending Mappings")
        for archived_name, active_name in st.session_state.new_mappings.items():
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"📦 **{archived_name}** → 📁 **{active_name}**")
            with col2:
                if st.button("Remove", key=f"remove_{archived_name}"):
                    del st.session_state.new_mappings[archived_name]
                    st.rerun()
    
    # Save functionality
    if 'new_mappings' in st.session_state and st.session_state.new_mappings:
        st.subheader("Save Changes")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Save to File", type="primary", key="save_mappings"):
                try:
                    save_adjustment_file(preview_mappings)
                    st.success("Adjustment file saved successfully!")
                    # Clear session state
                    st.session_state.new_mappings = {}
                    st.rerun()
                except Exception as e:
                    st.error(f"Error saving file: {str(e)}")
        
        with col2:
            if st.button("Clear All Changes", key="clear_changes"):
                st.session_state.new_mappings = {}
                st.rerun()


def generate_adjustment_file_content(mappings: Dict[str, str]) -> str:
    """
    Generate the content for the adjustment file.
    
    Args:
        mappings: Dictionary of archived project name to active project name mappings
        
    Returns:
        String content for the Python adjustment file
    """
    content = [
        "# Adjustments for archived root projects",
        "# This file was generated by the Project Adjustment Manager GUI",
        "",
        f"{ADJUSTMENTS_VARIABLE_NAME} = {{"
    ]
    
    # Add mappings
    for archived_name, active_name in sorted(mappings.items()):
        content.append(f'    "{archived_name}": "{active_name}",')
    
    content.append("}")
    content.append("")
    
    return "\n".join(content)


def save_adjustment_file(mappings: Dict[str, str]) -> None:
    """
    Save the adjustment mappings to a file in the personal directory.
    
    Args:
        mappings: Dictionary of archived project name to active project name mappings
    """
    personal_dir = Path('personal')
    personal_dir.mkdir(exist_ok=True)
    
    file_path = personal_dir / 'archived_root_projects.py'
    content = generate_adjustment_file_content(mappings)
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)