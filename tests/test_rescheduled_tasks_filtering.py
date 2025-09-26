#!/usr/bin/env python3
"""
Test for the updated rescheduled tasks filtering logic.
This test verifies that recurring tasks are properly filtered out while
retaining all other rescheduled task data.
"""

import sys
import unittest
from unittest.mock import Mock
import pandas as pd

# Add the project root to Python path
sys.path.insert(0, '/home/runner/work/todoist-assistant/todoist-assistant')

from todoist.types import Task, TaskEntry
from todoist.dashboard.subpages.tasks import process_rescheduled_tasks


class TestRescheduledTasksFiltering(unittest.TestCase):
    
    def create_task(self, task_id, content, is_recurring=False, due_date=None):
        """Helper method to create a task."""
        due = None
        if is_recurring:
            due = {"date": due_date or "2024-01-15", "is_recurring": True}
        elif due_date:
            due = {"date": due_date, "is_recurring": False}
        
        task_entry = TaskEntry(
            id=task_id,
            is_deleted=False,
            added_at="2024-01-01T00:00:00Z",
            child_order=1,
            responsible_uid=None,
            content=content,
            description="",
            user_id="user123",
            assigned_by_uid="user123",
            project_id="project123",
            section_id="section123",
            sync_id=None,
            collapsed=False,
            due=due,
            parent_id=None,
            labels=[],
            checked=False,
            priority=1,
            note_count=0,
            added_by_uid="user123",
            completed_at=None,
            deadline=None,
            duration=None,
            updated_at="2024-01-01T00:00:00Z",
            v2_id=f"v2_{task_id}",
            v2_parent_id=None,
            v2_project_id="v2_project123",
            v2_section_id="v2_section123",
            day_order=None
        )
        
        return Task(id=task_id, task_entry=task_entry)
    
    def test_filters_out_recurring_tasks(self):
        """Test that recurring tasks are excluded from rescheduled list."""
        
        # Create active tasks
        active_tasks = [
            self.create_task("task1", "Daily Standup", is_recurring=True),  # Should be filtered out
            self.create_task("task2", "Review PR", is_recurring=False),     # Should be included
            self.create_task("task3", "Weekly Meeting", is_recurring=True),  # Should be filtered out
            self.create_task("task4", "Fix Bug", is_recurring=False),       # Should be included
        ]
        
        # Create activity data with rescheduled events
        df_activity = pd.DataFrame({
            'type': ['rescheduled'] * 4,
            'title': ['Daily Standup', 'Review PR', 'Weekly Meeting', 'Fix Bug'],
            'parent_project_name': ['Project A'] * 4,
            'root_project_name': ['Root A'] * 4
        })
        
        result = process_rescheduled_tasks(df_activity, active_tasks)
        
        # Should only include non-recurring tasks
        expected_tasks = {'Review PR', 'Fix Bug'}
        actual_tasks = set(result['title'].tolist())
        
        self.assertEqual(actual_tasks, expected_tasks)
        self.assertEqual(len(result), 2)
    
    def test_includes_historical_non_recurring_tasks(self):
        """Test that historical (deleted/completed) non-recurring tasks are included."""
        
        # Only include currently active tasks (none of which match the historical reschedules)
        active_tasks = [
            self.create_task("task1", "Current Task", is_recurring=False),
        ]
        
        # Include historical rescheduled tasks
        df_activity = pd.DataFrame({
            'type': ['rescheduled'] * 4,
            'title': ['Current Task', 'Old Deleted Task', 'Completed Task', 'Changed Task'],
            'parent_project_name': ['Project A'] * 4,
            'root_project_name': ['Root A'] * 4
        })
        
        result = process_rescheduled_tasks(df_activity, active_tasks)
        
        # Should include all tasks since none are currently recurring
        expected_tasks = {'Current Task', 'Old Deleted Task', 'Completed Task', 'Changed Task'}
        actual_tasks = set(result['title'].tolist())
        
        self.assertEqual(actual_tasks, expected_tasks)
        self.assertEqual(len(result), 4)
    
    def test_mixed_scenario(self):
        """Test mixed scenario with various task types."""
        
        active_tasks = [
            # Recurring tasks (should cause filtering)
            self.create_task("task1", "Daily Standup", is_recurring=True),
            self.create_task("task2", "Weekly Planning", is_recurring=True),
            
            # Non-recurring tasks (should be included if rescheduled)
            self.create_task("task3", "Review Pull Request", is_recurring=False),
            self.create_task("task4", "Update Documentation", is_recurring=False),
        ]
        
        df_activity = pd.DataFrame({
            'type': ['rescheduled'] * 8,
            'title': [
                'Daily Standup',        # Currently recurring - EXCLUDE
                'Weekly Planning',      # Currently recurring - EXCLUDE  
                'Review Pull Request',  # Currently non-recurring - INCLUDE
                'Update Documentation', # Currently non-recurring - INCLUDE
                'Old Task 1',          # Historical - INCLUDE (not currently recurring)
                'Old Task 2',          # Historical - INCLUDE (not currently recurring)
                'Completed Project',   # Historical - INCLUDE (not currently recurring)
                'Legacy Task'          # Historical - INCLUDE (not currently recurring)
            ],
            'parent_project_name': ['Project A'] * 8,
            'root_project_name': ['Root A'] * 8
        })
        
        result = process_rescheduled_tasks(df_activity, active_tasks)
        
        # Should exclude only the currently recurring tasks
        expected_tasks = {
            'Review Pull Request', 'Update Documentation', 
            'Old Task 1', 'Old Task 2', 'Completed Project', 'Legacy Task'
        }
        actual_tasks = set(result['title'].tolist())
        
        self.assertEqual(actual_tasks, expected_tasks)
        self.assertEqual(len(result), 6)
        
        # Verify the excluded tasks
        excluded_tasks = {'Daily Standup', 'Weekly Planning'}
        all_rescheduled_tasks = set(df_activity['title'].tolist())
        actual_excluded = all_rescheduled_tasks - actual_tasks
        self.assertEqual(actual_excluded, excluded_tasks)
    
    def test_no_recurring_tasks(self):
        """Test when there are no recurring tasks (should include all rescheduled tasks)."""
        
        active_tasks = [
            self.create_task("task1", "Task A", is_recurring=False),
            self.create_task("task2", "Task B", is_recurring=False),
        ]
        
        df_activity = pd.DataFrame({
            'type': ['rescheduled'] * 4,
            'title': ['Task A', 'Task B', 'Historical Task 1', 'Historical Task 2'],
            'parent_project_name': ['Project A'] * 4,
            'root_project_name': ['Root A'] * 4
        })
        
        result = process_rescheduled_tasks(df_activity, active_tasks)
        
        # Should include all tasks since none are recurring
        expected_tasks = {'Task A', 'Task B', 'Historical Task 1', 'Historical Task 2'}
        actual_tasks = set(result['title'].tolist())
        
        self.assertEqual(actual_tasks, expected_tasks)
        self.assertEqual(len(result), 4)
    
    def test_all_recurring_tasks(self):
        """Test when all active tasks are recurring (should exclude all matching rescheduled tasks)."""
        
        active_tasks = [
            self.create_task("task1", "Daily Task", is_recurring=True),
            self.create_task("task2", "Weekly Task", is_recurring=True),
        ]
        
        df_activity = pd.DataFrame({
            'type': ['rescheduled'] * 4,
            'title': ['Daily Task', 'Weekly Task', 'Historical Task 1', 'Historical Task 2'],
            'parent_project_name': ['Project A'] * 4,
            'root_project_name': ['Root A'] * 4
        })
        
        result = process_rescheduled_tasks(df_activity, active_tasks)
        
        # Should only include historical tasks (not currently recurring)
        expected_tasks = {'Historical Task 1', 'Historical Task 2'}
        actual_tasks = set(result['title'].tolist())
        
        self.assertEqual(actual_tasks, expected_tasks)
        self.assertEqual(len(result), 2)


if __name__ == '__main__':
    unittest.main()