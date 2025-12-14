"""Tests for Gmail Tasks Automation."""

from unittest.mock import Mock, patch
from todoist.automations.gmail_tasks import GmailTasksAutomation


def test_initialization():
    """Test that the automation initializes correctly."""
    automation = GmailTasksAutomation()
    assert automation.name == "Gmail Tasks"
    assert automation.frequency == 60
    assert automation.SCOPES == ['https://www.googleapis.com/auth/gmail.readonly']
    assert len(automation.TASK_KEYWORDS) > 0


def test_is_actionable_email_positive():
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


def test_is_actionable_email_negative():
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


def test_extract_task_content_basic():
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


def test_extract_task_content_urgent():
    """Test task content extraction with urgent priority."""
    automation = GmailTasksAutomation()
    
    subject = "URGENT: Critical bug fix needed"
    snippet = "This is very important and needs immediate attention"
    sender = "admin@company.com"
    
    result = automation._extract_task_content(subject, snippet, sender)
    
    assert result['content'] == "URGENT: Critical bug fix needed"
    assert result['priority'] == 3  # High priority due to "urgent"


def test_extract_task_content_email_prefix_removal():
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


def test_get_existing_task_contents():
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


@patch('todoist.automations.gmail_tasks.build')
@patch('todoist.automations.gmail_tasks.Credentials')
@patch('os.path.exists')
def test_authenticate_gmail_existing_token(mock_exists, mock_credentials, mock_build):
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
def test_authenticate_gmail_no_credentials(mock_exists):
    """Test Gmail authentication without credentials file."""
    automation = GmailTasksAutomation()
    
    # Mock no existing files
    mock_exists.return_value = False
    
    result = automation._authenticate_gmail()
    
    assert result is None


def test_task_keywords_coverage():
    """Test that task keywords cover common actionable terms."""
    automation = GmailTasksAutomation()
    
    # Check that important keywords are included
    important_keywords = ['todo', 'urgent', 'deadline', 'follow up', 'action required']
    
    for keyword in important_keywords:
        assert keyword in automation.TASK_KEYWORDS, f"Missing important keyword: {keyword}"


def test_automation_inheritance():
    """Test that GmailTasksAutomation properly inherits from Automation base class."""
    automation = GmailTasksAutomation()
    
    # Check that it has the required methods from base class
    assert hasattr(automation, 'tick')
    assert hasattr(automation, '_tick')
    assert hasattr(automation, 'name')
    assert hasattr(automation, 'frequency')