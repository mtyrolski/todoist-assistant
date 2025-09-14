"""
Standalone Project Adjustment GUI
A simple tool for managing archived project to active project mappings.
"""

import streamlit as st
import os
from pathlib import Path
from typing import Dict, List


# Constants
ADJUSTMENTS_VARIABLE_NAME = 'link_adjustements'


def main():
    """Main function for the standalone project adjustment tool"""
    st.set_page_config(page_title="Project Adjustment Manager", layout="wide")
    
    st.title("Project Adjustment Manager")
    st.write("Map archived projects to current active projects for better statistics and reporting.")
    st.info("This tool helps you link old archived projects to current main projects, making your statistics more cohesive.")
    
    # Load current mappings
    try:
        current_mappings = get_adjusting_mapping()
    except Exception as e:
        st.error(f"Error loading current mappings: {str(e)}")
        current_mappings = {}
    
    # Show current mappings
    st.subheader("Current Mappings")
    if current_mappings:
        st.write("Existing archived project mappings:")
        for archived_name, active_name in current_mappings.items():
            col1, col2, col3 = st.columns([2, 1, 2])
            with col1:
                st.write(f"📦 **{archived_name}**")
            with col2:
                st.write("→")
            with col3:
                st.write(f"📁 **{active_name}**")
    else:
        st.info("No current mappings found.")
    
    # Demo/Sample data section
    st.subheader("Demo: Create New Mappings")
    st.write("Since this is a demo mode, here are some sample projects you can work with:")
    
    # Sample data
    sample_archived = [
        "Old Work Project 📊", 
        "Legacy Personal Tasks 📝", 
        "Archived Travel Plans ✈️",
        "2022 Fitness Goals 💪",
        "Old Learning Projects 📚"
    ]
    
    sample_active = [
        "Current Work 💼", 
        "Personal Life 🏠", 
        "Travel & Adventures 🌍",
        "Health & Fitness 🏃",
        "Learning & Development 🎓"
    ]
    
    # Show available projects
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**Sample Archived Projects**")
        # Filter out already mapped projects
        available_archived = [p for p in sample_archived if not any(p.startswith(mapped.split(' ')[0]) for mapped in current_mappings.keys())]
        
        if available_archived:
            for project in available_archived:
                st.write(f"📦 {project}")
        else:
            st.info("All sample archived projects are already mapped.")
    
    with col2:
        st.write("**Sample Active Projects**")
        for project in sample_active:
            st.write(f"📁 {project}")
    
    # Mapping interface
    st.subheader("Create New Mapping")
    
    if available_archived:
        # Selectboxes for mapping
        selected_archived = st.selectbox(
            "Select archived project:",
            options=available_archived,
            key="select_archived"
        )
        
        selected_active = st.selectbox(
            "Map to active project:",
            options=sample_active,
            key="select_active"
        )
        
        # Add mapping button
        if st.button("Add Mapping", key="add_mapping"):
            if selected_archived and selected_active:
                # Store in session state for preview
                if 'new_mappings' not in st.session_state:
                    st.session_state.new_mappings = {}
                st.session_state.new_mappings[selected_archived] = selected_active
                st.success(f"Mapping added: {selected_archived} → {selected_active}")
                st.rerun()
    else:
        st.info("All available archived projects are already mapped.")
    
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
            col1, col2 = st.columns([4, 1])
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
                    st.success(f"File saved to: {Path('personal/archived_root_projects.py').absolute()}")
                    # Clear session state
                    st.session_state.new_mappings = {}
                    st.rerun()
                except Exception as e:
                    st.error(f"Error saving file: {str(e)}")
        
        with col2:
            if st.button("Clear All Changes", key="clear_changes"):
                st.session_state.new_mappings = {}
                st.rerun()
    
    # Instructions
    st.subheader("How to Use")
    st.markdown("""
    1. **Review Current Mappings**: See what archived projects are already mapped to active projects
    2. **Select Projects**: Choose an archived project and the active project you want to map it to
    3. **Add Mapping**: Click "Add Mapping" to add the relationship
    4. **Preview**: Review the generated adjustment file content
    5. **Save**: Click "Save to File" to write the mappings to `personal/archived_root_projects.py`
    
    The adjustment file is used by the Todoist Assistant to consolidate statistics from archived projects 
    into their current active counterparts, providing a more cohesive view of your productivity data.
    """)


def get_adjusting_mapping() -> Dict[str, str]:
    """
    Loads mapping adjustments from Python scripts in the 'personal' directory.
    """
    personal_dir = Path('personal')
    
    if not personal_dir.exists():
        personal_dir.mkdir(exist_ok=True)
        # Create empty file
        file_path = personal_dir / 'archived_root_projects.py'
        content = generate_adjustment_file_content({})
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return {}
    
    file_path = personal_dir / 'archived_root_projects.py'
    if not file_path.exists():
        # Create empty file
        content = generate_adjustment_file_content({})
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return {}
    
    # Load the file and extract the mappings
    try:
        import importlib.util
        import sys
        
        spec = importlib.util.spec_from_file_location("adjustment_module", file_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules["adjustment_module"] = module
        spec.loader.exec_module(module)
        
        if hasattr(module, ADJUSTMENTS_VARIABLE_NAME):
            mappings = getattr(module, ADJUSTMENTS_VARIABLE_NAME)
            if isinstance(mappings, dict):
                return mappings
        
        return {}
    except Exception:
        return {}


def generate_adjustment_file_content(mappings: Dict[str, str]) -> str:
    """
    Generate the content for the adjustment file.
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
    """
    personal_dir = Path('personal')
    personal_dir.mkdir(exist_ok=True)
    
    file_path = personal_dir / 'archived_root_projects.py'
    content = generate_adjustment_file_content(mappings)
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)


if __name__ == '__main__':
    main()