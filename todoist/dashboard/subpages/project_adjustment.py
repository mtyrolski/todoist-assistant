"""
Project Adjustment GUI for managing archived project to active project mappings.
Provides a drag-and-drop interface to replace manual file editing.
"""

import streamlit as st
from pathlib import Path
from typing import Dict, List

from todoist.database.base import Database
from todoist.database.dataframe import ADJUSTMENTS_VARIABLE_NAME


DEFAULT_MAPPING_FILE = 'archived_root_projects.py'


def get_available_mapping_files() -> List[str]:
    """Get list of available mapping files in personal directory"""
    personal_dir = Path('personal')
    
    if not personal_dir.exists():
        return [DEFAULT_MAPPING_FILE]
    
    # Get all Python files that contain the adjustment variable
    mapping_files = []
    for file in personal_dir.glob('*.py'):
        if file.name.startswith('__'):
            continue
        try:
            # Quick check if file contains the variable name
            with open(file, 'r', encoding='utf-8') as f:
                content = f.read()
                if ADJUSTMENTS_VARIABLE_NAME in content:
                    mapping_files.append(file.name)
        except Exception:
            continue
    
    return sorted(mapping_files) if mapping_files else [DEFAULT_MAPPING_FILE]


def load_mapping_from_file(filename: str) -> Dict[str, str]:
    """Load mappings from a specific file"""
    personal_dir = Path('personal')
    
    if not personal_dir.exists():
        personal_dir.mkdir(exist_ok=True)
    
    file_path = personal_dir / filename
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


def render_project_adjustment_page(dbio: Database) -> None:
    """
    Renders the project adjustment management page.
    
    Args:
        dbio: Database instance for fetching projects
    """
    st.header("Project Adjustment Manager")
    st.write("Map archived projects to current active projects for better statistics and reporting.")
    st.info("This tool helps you link old archived projects to current main projects, making your statistics more cohesive.")
    
    # Select mapping file
    available_files = get_available_mapping_files()
    
    if len(available_files) > 1:
        st.subheader("Select Mapping File")
        selected_file = st.selectbox(
            "Choose which mapping file to edit:",
            options=available_files,
            key="selected_mapping_file",
            help="Select the mapping configuration file you want to work with"
        )
    else:
        selected_file = available_files[0] if available_files else DEFAULT_MAPPING_FILE
    
    # Display file path prominently
    file_path = Path('personal') / selected_file
    st.info(f"📄 **Mapping File:** `{file_path.absolute()}`")
    
    # Load current mappings
    try:
        current_mappings = load_mapping_from_file(selected_file)
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
        
        # Demo current mappings
        demo_current_mappings = {
            "Old Work Project 📊": "Current Work 💼",
            "Archived Travel Plans ✈️": "Travel & Adventures 🌍",
            "2022 Fitness Goals 💪": "Health & Fitness 🏃"
        }
        
        # Show demo current mappings with improved UI
        st.subheader("Current Mappings (Demo)")
        if demo_current_mappings:
            # Group by active project (master project)
            grouped_mappings = {}
            for archived_name, active_name in demo_current_mappings.items():
                if active_name not in grouped_mappings:
                    grouped_mappings[active_name] = []
                grouped_mappings[active_name].append(archived_name)
            
            # Display grouped mappings in nice boxes
            for active_project, archived_projects in grouped_mappings.items():
                with st.container():
                    st.markdown(f"### 📁 {active_project}")
                    cols = st.columns(min(len(archived_projects), 3))
                    for idx, archived_proj in enumerate(archived_projects):
                        with cols[idx % 3]:
                            st.info(f"📦 {archived_proj}")
                    st.divider()
        
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
        
        with st.expander("📄 Preview Adjustment File (Demo)", expanded=False):
            st.code(f"""# Adjustments for archived root projects
# This file was generated by the Project Adjustment Manager GUI

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
    
    # Show current mappings with improved UI
    st.subheader("Current Mappings")
    if current_mappings:
        # Group by active project (master project)
        grouped_mappings = {}
        for archived_name, active_name in current_mappings.items():
            if active_name not in grouped_mappings:
                grouped_mappings[active_name] = []
            grouped_mappings[active_name].append(archived_name)
        
        # Display grouped mappings in nice boxes
        for active_project, archived_projects in grouped_mappings.items():
            with st.container():
                st.markdown(f"### 📁 {active_project}")
                cols = st.columns(min(len(archived_projects), 3))
                for idx, archived_proj in enumerate(archived_projects):
                    with cols[idx % 3]:
                        st.info(f"📦 {archived_proj}")
                st.divider()
    else:
        st.info("No current mappings found. Create your first mapping below!")
    
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
        if st.button("➕ Add Mapping", key="add_mapping", use_container_width=True):
            if selected_archived and selected_active:
                # Store in session state for preview
                if 'new_mappings' not in st.session_state:
                    st.session_state.new_mappings = {}
                st.session_state.new_mappings[selected_archived] = selected_active
                st.success(f"✅ Mapping added: {selected_archived} → {selected_active}")
                st.rerun()
    elif not unmapped_archived:
        st.info("All archived projects are already mapped.")
    elif not active_root_projects:
        st.warning("No active root projects available for mapping.")
    
    # Preview section (optional, collapsible)
    with st.expander("📄 Preview Adjustment File", expanded=False):
        # Combine current and new mappings for preview
        preview_mappings = current_mappings.copy()
        if 'new_mappings' in st.session_state:
            preview_mappings.update(st.session_state.new_mappings)
        
        # Generate preview content
        preview_content = generate_adjustment_file_content(preview_mappings)
        
        st.code(preview_content, language='python')
    
    # Remove mapping functionality
    if 'new_mappings' in st.session_state and st.session_state.new_mappings:
        st.subheader("Pending Mappings")
        st.write("These mappings will be added when you save:")
        for archived_name, active_name in list(st.session_state.new_mappings.items()):
            col1, col2 = st.columns([4, 1])
            with col1:
                st.success(f"📦 **{archived_name}** → 📁 **{active_name}**")
            with col2:
                if st.button("Remove", key=f"remove_{archived_name}"):
                    del st.session_state.new_mappings[archived_name]
                    st.rerun()
    
    # Save functionality
    if 'new_mappings' in st.session_state and st.session_state.new_mappings:
        st.divider()
        st.subheader("💾 Save Changes")
        
        # Combine current and new mappings for saving
        preview_mappings = current_mappings.copy()
        preview_mappings.update(st.session_state.new_mappings)
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("💾 Save to File", type="primary", key="save_mappings", use_container_width=True):
                try:
                    save_adjustment_file(preview_mappings, selected_file)
                    st.success("✅ Adjustment file saved successfully!")
                    st.success(f"📄 File saved to: `{(Path('personal') / selected_file).absolute()}`")
                    # Clear session state
                    st.session_state.new_mappings = {}
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error saving file: {str(e)}")
        
        with col2:
            if st.button("🗑️ Clear All Changes", key="clear_changes", use_container_width=True):
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


def save_adjustment_file(mappings: Dict[str, str], filename: str = DEFAULT_MAPPING_FILE) -> None:
    """
    Save the adjustment mappings to a file in the personal directory.
    
    Args:
        mappings: Dictionary of archived project name to active project name mappings
        filename: Name of the file to save to (default: archived_root_projects.py)
    """
    personal_dir = Path('personal')
    personal_dir.mkdir(exist_ok=True)
    
    file_path = personal_dir / filename
    content = generate_adjustment_file_content(mappings)
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)