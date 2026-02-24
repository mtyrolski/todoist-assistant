"""Gmail Tasks automation: turn actionable unread emails into Todoist tasks."""

import datetime
import os.path
import re
from typing import Any

from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from loguru import logger

from todoist.automations.base import Automation
from todoist.constants import TaskField
from todoist.database.base import Database
from todoist.utils import Cache

GMAIL_CREDENTIALS_FILE = 'gmail_credentials.json'
GMAIL_TOKEN_FILE = 'gmail_token.json'


class GmailTasksAutomation(Automation):
    """
    Automation to fetch Gmail emails and convert them to Todoist tasks.

    This automation:
    1. Fetches unread emails from Gmail from the last week
    2. Identifies emails that contain actionable items based on keywords
    3. Creates Todoist tasks from those emails
    4. Avoids creating duplicate tasks
    """

    # Gmail API scopes
    SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

    # Keywords that indicate an email might contain actionable items
    TASK_KEYWORDS = [
        'todo', 'to do', 'action required', 'follow up', 'deadline', 'urgent',
        'reminder', 'task', 'complete', 'finish', 'review', 'approve',
        'respond', 'reply', 'meeting', 'call', 'schedule', 'due'
    ]

    def __init__(
        self,
        name: str = "Gmail Tasks",
        frequency_in_minutes: float = 60,
        *,
        dry_run: bool = False,
        max_messages_per_tick: int | None = None,
        lookback_days: int = 7,
        label_name: str = "gmail-task",
        allow_interactive_auth: bool = True,
    ):
        """
        Initialize the Gmail Tasks automation.

        Args:
            name: Name of the automation
            frequency_in_minutes: How often to run the automation (in minutes)
        """
        super().__init__(name, frequency_in_minutes)
        self.gmail_service: Any | None = None
        self.dry_run = dry_run
        self.max_messages_per_tick = (
            int(max_messages_per_tick)
            if max_messages_per_tick is not None and int(max_messages_per_tick) > 0
            else None
        )
        self.lookback_days = max(1, int(lookback_days))
        self.label_name = label_name
        self.allow_interactive_auth = allow_interactive_auth
        self._cache = Cache()
        # Keep persistent set of processed Gmail message IDs to avoid duplicate tasks across runs
        loaded_processed_ids = self._cache.processed_gmail_messages.load()
        self._processed_message_ids = set(loaded_processed_ids or set())
        self.last_sync_stats: dict[str, Any] = {}

    @staticmethod
    def _format_gmail_date(d: datetime.date) -> str:
        """Return Gmail-compatible date string: YYYY/M/D (no leading zeros)."""
        return f"{d.year}/{d.month}/{d.day}"

    def _authenticate_gmail(self):
        """Authenticate with Gmail API using stored credentials."""
        creds = None

        # Check for existing token
        if os.path.exists(GMAIL_TOKEN_FILE):
            creds = Credentials.from_authorized_user_file(GMAIL_TOKEN_FILE, self.SCOPES)

        # If there are no (valid) credentials available, let the user log in
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except RefreshError as exc:
                    logger.warning(f"Gmail token refresh failed ({exc}); falling back to interactive OAuth.")
                    creds = None

            if not creds or not creds.valid:
                if not self.allow_interactive_auth:
                    logger.error(
                        "Gmail credentials require interactive OAuth, but interactive auth is disabled."
                    )
                    return None

                if os.path.exists(GMAIL_CREDENTIALS_FILE):
                    flow = InstalledAppFlow.from_client_secrets_file(GMAIL_CREDENTIALS_FILE, self.SCOPES)
                    creds = flow.run_local_server(port=0)
                else:
                    logger.error(f"Gmail credentials file {GMAIL_CREDENTIALS_FILE} not found. "
                               "Please follow the setup instructions to configure Gmail API access.")
                    return None

            # Save the credentials for the next run
            with open(GMAIL_TOKEN_FILE, 'w') as token:
                token.write(creds.to_json())

        return build('gmail', 'v1', credentials=creds)

    def _build_gmail_query(self) -> str:
        """Build the Gmail search query for unread messages in the lookback window."""
        today = datetime.date.today()
        start_date = today - datetime.timedelta(days=self.lookback_days)
        tomorrow = today + datetime.timedelta(days=1)  # `before:` is exclusive
        after_str = self._format_gmail_date(start_date)
        before_str = self._format_gmail_date(tomorrow)
        return f'is:unread after:{after_str} before:{before_str}'

    def _list_matching_messages(self, query_: str) -> list[dict[str, Any]]:
        """List Gmail message refs (with pagination), capped when configured."""
        if self.gmail_service is None:
            raise RuntimeError("Gmail service is not initialized")

        messages: list[dict[str, Any]] = []
        page_token: str | None = None

        while True:
            list_kwargs: dict[str, Any] = {'userId': 'me', 'q': query_}
            if page_token:
                list_kwargs['pageToken'] = page_token

            results = self.gmail_service.users().messages().list(**list_kwargs).execute()
            batch = results.get('messages', [])
            if batch:
                messages.extend(batch)
                if self.max_messages_per_tick is not None and len(messages) >= self.max_messages_per_tick:
                    return messages[:self.max_messages_per_tick]

            page_token = results.get('nextPageToken')
            if not page_token:
                return messages

    @staticmethod
    def _header_map(headers: list[dict[str, Any]] | None) -> dict[str, str]:
        """Normalize Gmail headers into a lowercase name->value map."""
        normalized: dict[str, str] = {}
        for header in headers or []:
            name = str(header.get('name', '')).strip().lower()
            if not name:
                continue
            normalized[name] = str(header.get('value', ''))
        return normalized

    def _is_actionable_email(self, subject: str, snippet: str) -> bool:
        """
        Determine if an email contains actionable content based on keywords.

        Args:
            subject: Email subject line
            snippet: Email snippet/preview text

        Returns:
            True if the email appears to contain actionable items
        """
        logger.debug(f"Checking if email is actionable: {subject}")
        text_to_check = f"{subject} {snippet}".lower()
        is_actionable = any(keyword in text_to_check for keyword in self.TASK_KEYWORDS)
        logger.debug(f"Email {subject} -> actionable? {is_actionable}")
        return is_actionable

    def _extract_task_content(self, subject: str, snippet: str, sender: str) -> dict[str, Any]:
        """
        Extract task content from email data.

        Args:
            subject: Email subject line
            snippet: Email snippet/preview text
            sender: Email sender

        Returns:
            Dictionary with task content, description, and priority
        """
        # Use subject as task content, with some cleanup
        content = subject.strip()

        # Remove repeated email prefixes like "Re: Fwd: ..."
        content = re.sub(r'^(?:(?:re|fwd?):\s*)+', '', content, flags=re.IGNORECASE).strip()

        if not content:
            fallback = re.sub(r'\s+', ' ', snippet).strip()
            content = fallback[:120] if fallback else "Email follow-up"

        # Create description with context
        description = f"Email from: {sender}\n\nSnippet: {snippet}"

        # Determine priority based on urgency keywords
        priority = 1  # Normal priority
        urgent_keywords = ['urgent', 'asap', 'important', 'deadline', 'critical']
        content_lower = content.lower()
        snippet_lower = snippet.lower()
        if any(keyword in content_lower or keyword in snippet_lower for keyword in urgent_keywords):
            priority = 3  # High priority

        return {
            TaskField.CONTENT.value: content,
            TaskField.DESCRIPTION.value: description,
            TaskField.PRIORITY.value: priority,
        }

    def _get_existing_task_contents(self, db: Database) -> set[str]:
        """
        Get content of all existing tasks to avoid duplicates.

        Args:
            db: Database instance

        Returns:
            Set of existing task contents (normalized)
        """
        try:
            projects = db.fetch_projects(include_tasks=True)
            existing_contents = set()

            for project in projects:
                for task in getattr(project, 'tasks', []) or []:
                    # Normalize content for comparison (lowercase, stripped)
                    content = getattr(getattr(task, 'task_entry', None), 'content', '')
                    if not isinstance(content, str) or not content.strip():
                        continue
                    normalized_content = content.lower().strip()
                    existing_contents.add(normalized_content)

            logger.info(f"Found {len(existing_contents)} existing tasks")
            return existing_contents

        except (AttributeError, KeyError, RuntimeError, TypeError) as e:
            logger.error(f"Error fetching existing tasks: {e}")
            return set()

    def _tick(self, db: Database):
        """
        Main automation logic - fetch emails and create tasks.

        Args:
            db: Database instance for Todoist operations
        """
        stats: dict[str, Any] = {
            'dry_run': self.dry_run,
            'auth_failed': False,
            'query': None,
            'messages_found': 0,
            'messages_scanned': 0,
            'actionable_messages': 0,
            'duplicates': 0,
            'created': 0,
            'would_create': 0,
            'skipped_processed': 0,
            'skipped_missing_id': 0,
            'skipped_empty_content': 0,
            'errors': 0,
        }
        self.last_sync_stats = stats
        try:
            # Authenticate with Gmail
            self.gmail_service = self._authenticate_gmail()
            if not self.gmail_service:
                stats['auth_failed'] = True
                stats['errors'] += 1
                logger.error("Failed to authenticate with Gmail API")
                return

            logger.info("Successfully authenticated with Gmail API")

            # Fetch unread emails from the lookback window
            logger.info("Fetching unread emails from Gmail...")
            query_ = self._build_gmail_query()
            stats['query'] = query_
            logger.debug(f'Gmail query: {query_}')
            messages = self._list_matching_messages(query_)
            stats['messages_found'] = len(messages)
            logger.info(f"Found {len(messages)} unread emails")

            if not messages:
                logger.info("No unread emails found")
                return

            # Get existing tasks to avoid duplicates by content
            existing_task_contents = self._get_existing_task_contents(db)

            # Process each email
            processed_ids_changed = False
            for message in messages:
                try:
                    msg_id = message.get('id')
                    stats['messages_scanned'] += 1
                    logger.debug(f"Processing email id={msg_id}")
                    if msg_id and msg_id in self._processed_message_ids:
                        stats['skipped_processed'] += 1
                        logger.debug(f"Skipping already processed email id={msg_id}")
                        continue
                    logger.debug(f'Not yet processed email id={msg_id} in bag of {len(messages)} marked mails.')
                    # Get email details
                    if not msg_id:
                        stats['skipped_missing_id'] += 1
                        logger.debug("Skipping email without id")
                        continue

                    msg = self.gmail_service.users().messages().get(
                        userId='me',
                        id=msg_id
                    ).execute()

                    # Extract email data
                    payload = msg.get('payload', {})
                    headers = self._header_map(payload.get('headers'))
                    subject = headers.get('subject', 'No Subject')
                    sender = headers.get('from', 'Unknown Sender')
                    snippet = msg.get('snippet', '')

                    # Check if email is actionable
                    if not self._is_actionable_email(subject, snippet):
                        continue
                    stats['actionable_messages'] += 1

                    # Extract task content
                    task_data = self._extract_task_content(subject, snippet, sender)

                    # Check for duplicates
                    normalized_content = task_data[TaskField.CONTENT.value].lower().strip()
                    if not normalized_content:
                        stats['skipped_empty_content'] += 1
                        logger.debug(f"Skipping email with empty task content id={msg_id}")
                        continue
                    if normalized_content in existing_task_contents:
                        stats['duplicates'] += 1
                        logger.debug(f"Skipping duplicate task: {task_data[TaskField.CONTENT.value]}")
                        continue

                    if self.dry_run:
                        stats['would_create'] += 1
                        existing_task_contents.add(normalized_content)
                        logger.info(f"[dry-run] Would create task: {task_data[TaskField.CONTENT.value]}")
                        continue

                    # Create task in Todoist
                    result = db.insert_task(
                        content=task_data[TaskField.CONTENT.value],
                        description=task_data[TaskField.DESCRIPTION.value],
                        priority=task_data[TaskField.PRIORITY.value],
                        labels=[self.label_name],
                    )

                    if 'error' not in result:
                        stats['created'] += 1
                        existing_task_contents.add(normalized_content)  # Prevent duplicates in this run
                        logger.info(f"Created task: {task_data[TaskField.CONTENT.value]}")
                        # Mark this message as processed
                        if msg_id:
                            logger.debug(f"Marking email as processed: {msg_id}")
                            self._processed_message_ids.add(msg_id)
                            processed_ids_changed = True
                    else:
                        stats['errors'] += 1
                        logger.error(f"Failed to create task: {result.get('error')}")

                except (HttpError, KeyError, ValueError, AttributeError, TypeError) as e:
                    stats['errors'] += 1
                    logger.error(f"Error processing email {message.get('id')}: {e}")

            # Persist processed IDs if updated
            if not self.dry_run and processed_ids_changed:
                try:
                    self._cache.processed_gmail_messages.save(self._processed_message_ids)
                except (OSError, TypeError, ValueError) as e:
                    logger.error(f"Failed to save processed Gmail message IDs: {e}")

            logger.info(
                "Gmail Tasks automation completed. "
                f"created={stats['created']}, would_create={stats['would_create']}, "
                f"duplicates={stats['duplicates']}, errors={stats['errors']}"
            )

        except (HttpError, OSError, ValueError, TypeError) as e:
            stats['errors'] += 1
            logger.error(f"Gmail Tasks automation failed: {e}")
