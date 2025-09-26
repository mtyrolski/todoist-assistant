"""Tests for Gmail Tasks Automation."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from todoist.automations.gmail_tasks import GmailTasksAutomation
import re


class TestGmailTasksAutomation:
    """Test cases for Gmail Tasks Automation."""

    def test_initialization(self):
        """Test that the automation initializes correctly."""
        automation = GmailTasksAutomation()
        assert automation.name == "Gmail Tasks"
        assert automation.frequency == 60
        assert automation.SCOPES == ['https://www.googleapis.com/auth/gmail.readonly']
        assert len(automation.TASK_KEYWORDS) > 0

    def test_is_actionable_email_positive(self):
        """Test that emails with actionable keywords are identified."""
        automation = GmailTasksAutomation()
        
        # Test cases with actionable content
        test_cases = [
            ("TODO: Review the project proposal", ""),
            ("", "action required for the meeting"),
            ("Meeting tomorrow", "please follow up"),
            ("Urgent: Deadline approaching", ""),
            ("", "reminder to complete the task"),
        ]
        
        for subject, snippet in test_cases:
            assert automation._is_actionable_email(subject, snippet), \
                f"Failed for subject='{subject}', snippet='{snippet}'"

    def test_is_actionable_email_negative(self):
        """Test that non-actionable emails are not identified."""
        automation = GmailTasksAutomation()
        
        # Test cases without actionable content
        test_cases = [
            ("Newsletter: Tech updates", "Just sharing some news"),
            ("Happy birthday!", "Hope you have a great day"),
            ("Receipt from purchase", "Thank you for your order"),
            ("Welcome to our service", "Getting started guide"),
        ]
        
        for subject, snippet in test_cases:
            assert not automation._is_actionable_email(subject, snippet), \
                f"False positive for subject='{subject}', snippet='{snippet}'"

    def test_extract_task_content_basic(self):
        """Test basic task content extraction."""
        automation = GmailTasksAutomation()
        
        subject = "TODO: Review the proposal"
        snippet = "Please review the attached proposal document"
        sender = "john@example.com"
        
        result = automation._extract_task_content(subject, snippet, sender)
        
        assert result['content'] == "TODO: Review the proposal"
        assert "john@example.com" in result['description']
        assert snippet in result['description']
        assert result['priority'] == 1  # Normal priority

    def test_extract_task_content_urgent(self):
        """Test task content extraction with urgent priority."""
        automation = GmailTasksAutomation()
        
        subject = "URGENT: Critical bug fix needed"
        snippet = "This is very important and needs immediate attention"
        sender = "admin@company.com"
        
        result = automation._extract_task_content(subject, snippet, sender)
        
        assert result['content'] == "URGENT: Critical bug fix needed"
        assert result['priority'] == 3  # High priority due to "urgent"

    def test_extract_task_content_email_prefix_removal(self):
        """Test that email prefixes are removed from subject."""
        automation = GmailTasksAutomation()
        
        test_cases = [
            ("Re: Meeting tomorrow", "Meeting tomorrow"),
            ("RE: Important task", "Important task"),
            ("Fwd: Action required", "Action required"),
            ("FW: Review needed", "Review needed"),
        ]
        
        for input_subject, expected_content in test_cases:
            result = automation._extract_task_content(input_subject, "", "test@example.com")
            assert result['content'] == expected_content

    def test_get_existing_task_contents(self):
        """Test fetching existing task contents for duplicate detection."""
        automation = GmailTasksAutomation()
        
        # Mock database and projects
        mock_db = Mock()
        mock_task1 = Mock()
        mock_task1.task_entry.content = "Buy milk"
        mock_task2 = Mock()
        mock_task2.task_entry.content = "Call dentist"
        
        mock_project = Mock()
        mock_project.tasks = [mock_task1, mock_task2]
        
        mock_db.fetch_projects.return_value = [mock_project]
        
        result = automation._get_existing_task_contents(mock_db)
        
        expected = {"buy milk", "call dentist"}
        assert result == expected

    def test_get_existing_task_contents_error_handling(self):
        """Test error handling in getting existing task contents."""
        automation = GmailTasksAutomation()
        
        # Mock database that raises an exception
        mock_db = Mock()
        mock_db.fetch_projects.side_effect = RuntimeError("Database error")
        
        result = automation._get_existing_task_contents(mock_db)
        
        # Should return empty set on error
        assert result == set()

    @patch('todoist.automations.gmail_tasks.build')
    @patch('todoist.automations.gmail_tasks.Credentials')
    @patch('os.path.exists')
    def test_authenticate_gmail_existing_token(self, mock_exists, mock_credentials, mock_build):
        """Test Gmail authentication with existing valid token."""
        automation = GmailTasksAutomation()
        
        # Mock existing valid token
        mock_exists.return_value = True
        mock_creds = Mock()
        mock_creds.valid = True
        mock_credentials.from_authorized_user_file.return_value = mock_creds
        mock_service = Mock()
        mock_build.return_value = mock_service
        
        result = automation._authenticate_gmail()
        
        assert result == mock_service
        mock_credentials.from_authorized_user_file.assert_called_once_with('gmail_token.json', automation.SCOPES)
        mock_build.assert_called_once_with('gmail', 'v1', credentials=mock_creds)

    @patch('os.path.exists')
    def test_authenticate_gmail_no_credentials(self, mock_exists):
        """Test Gmail authentication without credentials file."""
        automation = GmailTasksAutomation()
        
        # Mock no existing files
        mock_exists.return_value = False
        
        result = automation._authenticate_gmail()
        
        assert result is None

    def test_task_keywords_coverage(self):
        """Test that task keywords cover common actionable terms."""
        automation = GmailTasksAutomation()
        
        # Check that important keywords are included
        important_keywords = ['todo', 'urgent', 'deadline', 'follow up', 'action required']
        
        for keyword in important_keywords:
            assert keyword in automation.TASK_KEYWORDS, f"Missing important keyword: {keyword}"

    def test_automation_inheritance(self):
        """Test that GmailTasksAutomation properly inherits from Automation base class."""
        automation = GmailTasksAutomation()
        
        # Check that it has the required methods from base class
        assert hasattr(automation, 'tick')
        assert hasattr(automation, '_tick')
        assert hasattr(automation, 'name')
        assert hasattr(automation, 'frequency')

    def test_query_uses_correct_date_format(self):
        """Ensure Gmail query uses 'after' and 'before' with YYYY/M/D format."""
        automation = GmailTasksAutomation()

        captured_queries = []

        class FakeMessages:
            def list(self, userId, q):  # noqa: N803 (external API naming)
                captured_queries.append(q)
                class Exec:
                    def execute(self):
                        return {"messages": []}
                return Exec()

        class FakeUsers:
            def messages(self):
                return FakeMessages()

        class FakeService:
            def users(self):
                return FakeUsers()

        # Inject fake Gmail service
        automation.gmail_service = FakeService()

        # Run
        mock_db = Mock()
        automation._tick(mock_db)

        assert captured_queries, "Expected at least one Gmail query to be executed"
        q = captured_queries[0]
        # Must include 'is:unread', 'after:' and 'before:' with YYYY/M/D (no leading zeros required)
        assert 'is:unread' in q
        assert 'after:' in q and 'before:' in q
        m = re.search(r"after:(\d{4}/\d{1,2}/\d{1,2})", q)
        n = re.search(r"before:(\d{4}/\d{1,2}/\d{1,2})", q)
        assert m and n, f"Query doesn't contain properly formatted dates: {q}"

    def test_processed_ids_are_skipped_and_persisted(self):
        """Processed Gmail message IDs should be skipped and saved after run."""
        # Fake cache in memory
        saved_set = set()

        class FakeStorage:
            def __init__(self, initial):
                self._data = set(initial)
            def load(self):
                return set(self._data)
            def save(self, data):
                saved_set.clear()
                saved_set.update(data)

        class FakeCache:
            def __init__(self, path: str = './'):
                self.processed_gmail_messages = FakeStorage({"abc123"})

        # Fake Gmail service producing two messages (one already processed)
        class FakeMessages:
            def list(self, userId, q):  # noqa: N803
                class Exec:
                    def execute(self):
                        return {"messages": [{"id": "abc123"}, {"id": "xyz9"}]}
                return Exec()
            def get(self, userId, id):  # noqa: A002, N803 - external API naming
                class Exec:
                    def execute(self):
                        # Always actionable
                        return {
                            "payload": {"headers": [{"name": "Subject", "value": "TODO: Do X"}, {"name": "From", "value": "me@example.com"}]},
                            "snippet": "Please follow up"
                        }
                return Exec()

        class FakeUsers:
            def messages(self):
                return FakeMessages()

        class FakeService:
            def users(self):
                return FakeUsers()

        automation = GmailTasksAutomation()
        # Patch Cache in the module to our fake
        with patch('todoist.automations.gmail_tasks.Cache', FakeCache):
            # Recreate automation so __init__ picks up FakeCache
            automation = GmailTasksAutomation()
            automation.gmail_service = FakeService()

            mock_db = Mock()
            mock_db.insert_task.return_value = {}
            mock_db.fetch_projects.return_value = []

            automation._tick(mock_db)

        # Should insert only for xyz9 (abc123 skipped)
        assert mock_db.insert_task.call_count == 1
        # Saved set should now include both ids
        assert "abc123" in saved_set and "xyz9" in saved_set

    def test_duplicate_content_is_skipped(self):
        """If existing tasks already contain the same content, skip creation."""
        class FakeMessages:
            def list(self, userId, q):  # noqa: N803
                class Exec:
                    def execute(self):
                        return {"messages": [{"id": "dup1"}]}
                return Exec()
            def get(self, userId, id):  # noqa: A002, N803
                class Exec:
                    def execute(self):
                        return {
                            "payload": {"headers": [{"name": "Subject", "value": "Re: Review plan"}, {"name": "From", "value": "boss@example.com"}]},
                            "snippet": "TODO: Review plan please"
                        }
                return Exec()

        class FakeUsers:
            def messages(self):
                return FakeMessages()

        class FakeService:
            def users(self):
                return FakeUsers()

        # Fake empty cache
        class FakeStorage:
            def load(self):
                return set()
            def save(self, data):
                pass
        class FakeCache:
            def __init__(self, path: str = './'):
                self.processed_gmail_messages = FakeStorage()

        with patch('todoist.automations.gmail_tasks.Cache', FakeCache):
            automation = GmailTasksAutomation()
            automation.gmail_service = FakeService()

            # Existing task with same normalized content after prefix removal
            mock_task = Mock()
            mock_task.task_entry.content = "Review plan"
            mock_project = Mock()
            mock_project.tasks = [mock_task]

            mock_db = Mock()
            mock_db.fetch_projects.return_value = [mock_project]

            automation._tick(mock_db)

        # Should not insert any task
        assert not mock_db.insert_task.called