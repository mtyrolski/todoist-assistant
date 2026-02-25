"""Tests for Gmail Tasks Automation."""

# pylint: disable=protected-access

from unittest.mock import Mock, mock_open, patch

from google.auth.exceptions import RefreshError
from todoist.automations.gmail_tasks import GmailTasksAutomation
from todoist.automations.gmail_tasks.automation import ExistingTaskDedupIndex


def _request(payload):
    req = Mock()
    req.execute.return_value = payload
    return req


def test_initialization():
    """Test that the automation initializes correctly."""
    automation = GmailTasksAutomation()
    assert automation.name == "Gmail Tasks"
    assert automation.frequency == 60
    assert automation.SCOPES == ['https://www.googleapis.com/auth/gmail.readonly']
    assert len(automation.TASK_KEYWORDS) > 0


def test_build_gmail_query_default_targets_unread_inbox_with_last_week_window():
    """Default sync query should target unread inbox email with date bounds."""
    automation = GmailTasksAutomation()
    query = automation._build_gmail_query()
    assert "in:inbox" in query
    assert "is:unread" in query
    assert "after:" in query
    assert "before:" in query


def test_build_gmail_query_with_lookback_adds_time_window():
    """When lookback_days is configured, date bounds are included."""
    automation = GmailTasksAutomation(lookback_days=7)
    query = automation._build_gmail_query()
    assert "in:inbox" in query
    assert "is:unread" in query
    assert "after:" in query
    assert "before:" in query


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

    assert result.content == "TODO: Review the proposal"
    assert "john@example.com" in result.description
    assert snippet in result.description
    assert result.priority == 1  # Normal priority


def test_extract_task_content_urgent():
    """Test task content extraction with urgent priority."""
    automation = GmailTasksAutomation()

    subject = "URGENT: Critical bug fix needed"
    snippet = "This is very important and needs immediate attention"
    sender = "admin@company.com"

    result = automation._extract_task_content(subject, snippet, sender)

    assert result.content == "URGENT: Critical bug fix needed"
    assert result.priority == 3  # High priority due to "urgent"


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
        assert result.content == expected_content


def test_extract_task_content_repeated_prefixes_and_empty_subject_fallback():
    """Repeated prefixes are stripped and empty subjects fall back to snippet text."""
    automation = GmailTasksAutomation()

    repeated = automation._extract_task_content("Re: Fwd: Action required", "", "test@example.com")
    assert repeated.content == "Action required"

    fallback = automation._extract_task_content("Re: ", "   Follow up with vendor tomorrow   ", "test@example.com")
    assert fallback.content == "Follow up with vendor tomorrow"


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


def test_get_existing_task_dedup_index_extracts_gmail_message_ids():
    """Existing Gmail-created tasks are recognized by message-id marker in description."""
    automation = GmailTasksAutomation()
    mock_db = Mock()

    mock_task = Mock()
    mock_task.task_entry.content = "Review invoice"
    mock_task.task_entry.description = (
        "Email from: billing@example.com\n\nSnippet: Invoice attached\n\nGmail Message ID: gmail-123"
    )
    mock_project = Mock()
    mock_project.tasks = [mock_task]
    mock_db.fetch_projects.return_value = [mock_project]

    index = automation._get_existing_task_dedup_index(mock_db)

    assert "review invoice" in index.contents
    assert "gmail-123" in index.gmail_message_ids


@patch('todoist.automations.gmail_tasks.automation.build')
@patch('todoist.automations.gmail_tasks.automation.Credentials')
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


@patch('builtins.open', new_callable=mock_open)
@patch('todoist.automations.gmail_tasks.automation.build')
@patch('todoist.automations.gmail_tasks.automation.InstalledAppFlow')
@patch('todoist.automations.gmail_tasks.automation.Credentials')
@patch('os.path.exists')
def test_authenticate_gmail_refresh_error_falls_back_to_oauth(
    mock_exists,
    mock_credentials,
    mock_flow_cls,
    mock_build,
    _mock_file,
):
    """Invalid refresh token should trigger a fresh OAuth flow when allowed."""
    automation = GmailTasksAutomation()

    mock_exists.side_effect = [True, True]  # token file exists, credentials file exists

    stale_creds = Mock()
    stale_creds.valid = False
    stale_creds.expired = True
    stale_creds.refresh_token = "refresh-token"
    stale_creds.refresh.side_effect = RefreshError("invalid_grant")
    mock_credentials.from_authorized_user_file.return_value = stale_creds

    fresh_creds = Mock()
    fresh_creds.valid = True
    fresh_creds.to_json.return_value = '{"token": "new"}'
    flow = Mock()
    flow.run_local_server.return_value = fresh_creds
    mock_flow_cls.from_client_secrets_file.return_value = flow

    mock_service = Mock()
    mock_build.return_value = mock_service

    result = automation._authenticate_gmail()

    assert result == mock_service
    mock_flow_cls.from_client_secrets_file.assert_called_once_with('gmail_credentials.json', automation.SCOPES)
    flow.run_local_server.assert_called_once_with(port=0)
    mock_build.assert_called_once_with('gmail', 'v1', credentials=fresh_creds)


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


def test_list_matching_messages_paginates_and_respects_cap():
    """Gmail list pagination is followed until cap is reached."""
    automation = GmailTasksAutomation(max_messages_per_tick=3)
    service = Mock()
    messages_api = service.users.return_value.messages.return_value
    messages_api.list.side_effect = [
        _request(
            {
                "messages": [{"id": "m1"}, {"id": "m2"}],
                "nextPageToken": "page-2",
            }
        ),
        _request(
            {
                "messages": [{"id": "m3"}, {"id": "m4"}],
            }
        ),
    ]
    automation.gmail_service = service

    result = automation._list_matching_messages("is:unread")

    assert [msg.get("id") for msg in result] == ["m1", "m2", "m3"]
    assert messages_api.list.call_count == 2
    assert "pageToken" not in messages_api.list.call_args_list[0].kwargs
    assert messages_api.list.call_args_list[1].kwargs["pageToken"] == "page-2"


def test_tick_creates_todoist_task_for_non_actionable_inbox_email_and_marks_processed():
    """All inbox emails (even non-keyword emails) now create Todoist tasks."""
    automation = GmailTasksAutomation()
    automation._processed_message_ids = set()
    automation._cache = Mock()
    automation._cache.processed_gmail_messages.save = Mock()

    service = Mock()
    service.users.return_value.messages.return_value.get.return_value = _request(
        {
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Newsletter: Team updates"},
                    {"name": "From", "value": "Alice <alice@example.com>"},
                ],
            },
            "snippet": "Weekly roundup and release notes.",
        }
    )

    db = Mock()
    db.insert_task.return_value = {"id": "todoist-task-1"}

    with (
        patch.object(automation, "_authenticate_gmail", return_value=service),
        patch.object(automation, "_list_matching_messages", return_value=[{"id": "gmail-msg-1"}]),
        patch.object(
            automation,
            "_get_existing_task_dedup_index",
            return_value=ExistingTaskDedupIndex(contents=set(), gmail_message_ids=set()),
        ),
    ):
        automation._tick(db)

    db.insert_task.assert_called_once()
    insert_kwargs = db.insert_task.call_args.kwargs
    assert insert_kwargs["content"] == "Newsletter: Team updates"
    assert insert_kwargs["labels"] == ["gmail-task"]
    assert "alice@example.com" in insert_kwargs["description"].lower()
    assert "Gmail Message ID: gmail-msg-1" in insert_kwargs["description"]
    assert "gmail-msg-1" in automation._processed_message_ids
    automation._cache.processed_gmail_messages.save.assert_called_once_with(automation._processed_message_ids)
    assert automation.last_sync_stats["created"] == 1
    assert automation.last_sync_stats["would_create"] == 0


def test_tick_dry_run_does_not_create_or_persist_processed_ids():
    """Dry-run mode exercises the sync path without writing to Todoist or cache."""
    automation = GmailTasksAutomation(dry_run=True)
    automation._processed_message_ids = set()
    automation._cache = Mock()
    automation._cache.processed_gmail_messages.save = Mock()

    service = Mock()
    service.users.return_value.messages.return_value.get.return_value = _request(
        {
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "TODO: Review sprint backlog"},
                    {"name": "From", "value": "PM <pm@example.com>"},
                ],
            },
            "snippet": "Please review before the standup.",
        }
    )

    db = Mock()

    with (
        patch.object(automation, "_authenticate_gmail", return_value=service),
        patch.object(automation, "_list_matching_messages", return_value=[{"id": "gmail-msg-2"}]),
        patch.object(
            automation,
            "_get_existing_task_dedup_index",
            return_value=ExistingTaskDedupIndex(contents=set(), gmail_message_ids=set()),
        ),
    ):
        automation._tick(db)

    db.insert_task.assert_not_called()
    automation._cache.processed_gmail_messages.save.assert_not_called()
    assert "gmail-msg-2" not in automation._processed_message_ids
    assert automation.last_sync_stats["dry_run"] is True
    assert automation.last_sync_stats["created"] == 0
    assert automation.last_sync_stats["would_create"] == 1


def test_tick_skips_email_already_added_via_gmail_message_id_marker():
    """If a Gmail message id is already present on an existing task, do not add it again."""
    automation = GmailTasksAutomation()
    automation._processed_message_ids = set()
    automation._cache = Mock()
    automation._cache.processed_gmail_messages.save = Mock()

    service = Mock()
    db = Mock()

    with (
        patch.object(automation, "_authenticate_gmail", return_value=service),
        patch.object(automation, "_list_matching_messages", return_value=[{"id": "gmail-msg-9"}]),
        patch.object(
            automation,
            "_get_existing_task_dedup_index",
            return_value=ExistingTaskDedupIndex(contents=set(), gmail_message_ids={"gmail-msg-9"}),
        ),
    ):
        automation._tick(db)

    service.users.return_value.messages.return_value.get.assert_not_called()
    db.insert_task.assert_not_called()
    assert "gmail-msg-9" in automation._processed_message_ids
    automation._cache.processed_gmail_messages.save.assert_called_once_with(automation._processed_message_ids)
    assert automation.last_sync_stats["duplicates"] == 1


def test_tick_creates_email_even_if_same_content_exists_without_gmail_marker():
    """Dedup is based on Gmail message-id marker, not plain content collisions."""
    automation = GmailTasksAutomation()
    automation._processed_message_ids = set()
    automation._cache = Mock()
    automation._cache.processed_gmail_messages.save = Mock()

    service = Mock()
    service.users.return_value.messages.return_value.get.return_value = _request(
        {
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Status update"},
                    {"name": "From", "value": "Ops <ops@example.com>"},
                ],
            },
            "snippet": "Nightly status summary.",
        }
    )
    db = Mock()
    db.insert_task.return_value = {"id": "todoist-task-2"}

    with (
        patch.object(automation, "_authenticate_gmail", return_value=service),
        patch.object(automation, "_list_matching_messages", return_value=[{"id": "gmail-msg-10"}]),
        patch.object(
            automation,
            "_get_existing_task_dedup_index",
            return_value=ExistingTaskDedupIndex(contents={"status update"}, gmail_message_ids=set()),
        ),
    ):
        automation._tick(db)

    db.insert_task.assert_called_once()
    assert "gmail-msg-10" in automation._processed_message_ids
    assert automation.last_sync_stats["created"] == 1
