"""
Unit tests for DatabaseActivity.fetch_activity_adaptively method.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import sys
import os

# Add the project root to the path so we can import todoist modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from todoist.database.db_activity import DatabaseActivity
from todoist.types import Event, _Event_API_V9


class TestDatabaseActivityAdaptive(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures."""
        self.db_activity = DatabaseActivity()
        
        # Mock the _fetch_activity_page method to return controlled test data
        self.original_fetch_page = self.db_activity._fetch_activity_page
        
    def tearDown(self):
        """Clean up after tests."""
        self.db_activity._fetch_activity_page = self.original_fetch_page
    
    def create_mock_event(self, event_id: str, event_date: str) -> _Event_API_V9:
        """Create a mock event for testing."""
        return _Event_API_V9(
            id=event_id,
            object_type="item",
            object_id="test_object_id",
            event_type="completed",
            event_date=event_date,
            parent_project_id=None,
            parent_item_id=None,
            initiator_id=None,
            extra_data={},
            extra_data_id=None,
            v2_object_id=None,
            v2_parent_item_id=None,
            v2_parent_project_id=None
        )
    
    @patch('todoist.database.db_activity.extract_task_due_date')
    def test_fetch_activity_adaptively_1_1(self, mock_extract_date):
        """Test fetch_activity_adaptively(1, 1) scenario from the problem statement."""
        # Setup mock data based on the example:
        # week0: 15, week1: 130, week2: 0, week3: 95, ...
        
        mock_extract_date.return_value = datetime.now()
        
        def mock_fetch_page(page: int):
            """Mock _fetch_activity_page with controlled data."""
            if page == 0:  # week0: 15 events
                return [self.create_mock_event(f"event_{i}", "2023-01-01T00:00:00Z") for i in range(15)]
            elif page == 1:  # week1: 130 events  
                return [self.create_mock_event(f"event_{i+15}", "2023-01-01T00:00:00Z") for i in range(130)]
            elif page == 2:  # week2: 0 events
                return []
            elif page == 3:  # week3: 95 events
                return [self.create_mock_event(f"event_{i+145}", "2023-01-01T00:00:00Z") for i in range(95)]
            else:
                return []
        
        self.db_activity._fetch_activity_page = mock_fetch_page
        
        # Test (1, 1): should fetch week0, week1, week2 and stop
        result = self.db_activity.fetch_activity_adaptively(sliding_window_size=1, early_stopping_after=1)
        
        # Should have events from week0 (15) + week1 (130) = 145 events
        # week2 has 0 events, so we stop after 1 consecutive empty window
        self.assertEqual(len(result), 145)
        
        # Verify the events are unique by checking IDs
        event_ids = {event.id for event in result}
        self.assertEqual(len(event_ids), 145)
    
    @patch('todoist.database.db_activity.extract_task_due_date')
    def test_fetch_activity_adaptively_1_2(self, mock_extract_date):
        """Test fetch_activity_adaptively(1, 2) scenario from the problem statement."""
        
        mock_extract_date.return_value = datetime.now()
        
        def mock_fetch_page(page: int):
            """Mock _fetch_activity_page with controlled data."""
            page_events = {
                0: 15,   # week0
                1: 130,  # week1  
                2: 0,    # week2
                3: 95,   # week3
                4: 100,  # week4
                5: 0,    # week5
                6: 0,    # week6
            }
            
            if page in page_events:
                count = page_events[page]
                start_id = sum(page_events[i] for i in range(page) if i in page_events)
                return [self.create_mock_event(f"event_{start_id + i}", "2023-01-01T00:00:00Z") 
                       for i in range(count)]
            return []
        
        self.db_activity._fetch_activity_page = mock_fetch_page
        
        # Test (1, 2): should fetch week0, week1, week2, week3, week4, week5, week6 and stop
        result = self.db_activity.fetch_activity_adaptively(sliding_window_size=1, early_stopping_after=2)
        
        # Should have events from week0 (15) + week1 (130) + week3 (95) + week4 (100) = 340 events
        # week2 has 0, week5 has 0, week6 has 0 - so we stop after 2 consecutive empty windows (week5, week6)
        self.assertEqual(len(result), 340)
    
    @patch('todoist.database.db_activity.extract_task_due_date')
    def test_fetch_activity_adaptively_2_2(self, mock_extract_date):
        """Test fetch_activity_adaptively(2, 2) scenario from the problem statement."""
        
        mock_extract_date.return_value = datetime.now()
        
        def mock_fetch_page(page: int):
            """Mock _fetch_activity_page with controlled data."""
            page_events = {
                0: 15,   # week0
                1: 130,  # week1  
                2: 0,    # week2
                3: 95,   # week3
                4: 100,  # week4
                5: 0,    # week5
                6: 0,    # week6
                7: 0,    # week7
            }
            
            if page in page_events:
                count = page_events[page]
                start_id = sum(page_events[i] for i in range(page) if i in page_events)
                return [self.create_mock_event(f"event_{start_id + i}", "2023-01-01T00:00:00Z") 
                       for i in range(count)]
            return []
        
        self.db_activity._fetch_activity_page = mock_fetch_page
        
        # Test (2, 2): should fetch (week0,week1), (week2,week3), (week4,week5), (week6,week7) and stop
        result = self.db_activity.fetch_activity_adaptively(sliding_window_size=2, early_stopping_after=2)
        
        # Should have events from week0 (15) + week1 (130) + week3 (95) + week4 (100) = 340 events
        # Window (week2,week3) has events, window (week4,week5) has events, 
        # Window (week6,week7) has 0 events, and there's no next window - so we stop
        self.assertEqual(len(result), 340)
    
    @patch('todoist.database.db_activity.extract_task_due_date')
    def test_fetch_activity_adaptively_3_1(self, mock_extract_date):
        """Test fetch_activity_adaptively(3, 1) scenario from the problem statement."""
        
        mock_extract_date.return_value = datetime.now()
        
        def mock_fetch_page(page: int):
            """Mock _fetch_activity_page with controlled data."""
            page_events = {
                0: 15,   # week0
                1: 130,  # week1  
                2: 0,    # week2
                3: 95,   # week3
                4: 100,  # week4
                5: 0,    # week5
                6: 0,    # week6
                7: 0,    # week7
                8: 0,    # week8
            }
            
            if page in page_events:
                count = page_events[page]
                start_id = sum(page_events[i] for i in range(page) if i in page_events)
                return [self.create_mock_event(f"event_{start_id + i}", "2023-01-01T00:00:00Z") 
                       for i in range(count)]
            return []
        
        self.db_activity._fetch_activity_page = mock_fetch_page
        
        # Test (3, 1): should fetch (week0,week1,week2), (week3,week4,week5), (week6,week7,week8) and stop
        result = self.db_activity.fetch_activity_adaptively(sliding_window_size=3, early_stopping_after=1)
        
        # Should have events from week0 (15) + week1 (130) + week3 (95) + week4 (100) = 340 events
        # Window (week0,week1,week2) has events, window (week3,week4,week5) has events,
        # Window (week6,week7,week8) has 0 events, so we stop after 1 consecutive empty window
        self.assertEqual(len(result), 340)
    
    @patch('todoist.database.db_activity.extract_task_due_date')
    def test_fetch_activity_adaptively_3_2(self, mock_extract_date):
        """Test fetch_activity_adaptively(3, 2) scenario from the problem statement."""
        
        mock_extract_date.return_value = datetime.now()
        
        def mock_fetch_page(page: int):
            """Mock _fetch_activity_page with controlled data."""
            page_events = {
                0: 15,    # week0
                1: 130,   # week1  
                2: 0,     # week2
                3: 95,    # week3
                4: 100,   # week4
                5: 0,     # week5
                6: 0,     # week6
                7: 0,     # week7
                8: 0,     # week8
                9: 0,     # week9
                10: 0,    # week10
                11: 2137, # week11
            }
            
            if page in page_events:
                count = page_events[page]
                start_id = sum(page_events[i] for i in range(page) if i in page_events)
                return [self.create_mock_event(f"event_{start_id + i}", "2023-01-01T00:00:00Z") 
                       for i in range(count)]
            return []
        
        self.db_activity._fetch_activity_page = mock_fetch_page
        
        # Test (3, 2): should fetch (week0,week1,week2), (week3,week4,week5), (week6,week7,week8), (week9,week10,week11) and stop
        result = self.db_activity.fetch_activity_adaptively(sliding_window_size=3, early_stopping_after=2)
        
        # Should have events from week0 (15) + week1 (130) + week3 (95) + week4 (100) + week11 (2137) = 2477 events  
        # Window (week0,week1,week2) has events, window (week3,week4,week5) has events,
        # Window (week6,week7,week8) has 0 events, window (week9,week10,week11) has events
        # No next window, so we can't get 2 consecutive empty windows
        self.assertEqual(len(result), 2477)


if __name__ == '__main__':
    unittest.main()