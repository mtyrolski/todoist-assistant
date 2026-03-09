"""Gmail Tasks automation: turn inbox emails into Todoist tasks."""

from datetime import date
import os.path
from typing import cast

from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from loguru import logger

from todoist.automations.base import Automation
from todoist.database.base import Database
from todoist.utils import Cache
from . import constants as C
from .contracts import (
    ExistingTaskDedupIndex,
    ExtractedTaskData,
    GmailAuthCredentials,
    GmailHeaderMap,
    GmailHeaderRecord,
    GmailListParams,
    GmailMessageId,
    GmailPayloadRecord,
    GmailMessageRef,
    GmailService,
    GmailSyncStats,
    TodoistInsertTaskResult,
    new_sync_stats,
)
from .helpers import (
    append_gmail_message_id_to_description,
    build_gmail_inbox_query,
    email_matches_keywords,
    extract_gmail_message_id_from_description,
    extract_task_data,
    format_gmail_date,
    gmail_message_id_marker,
    normalize_gmail_headers,
)

GMAIL_CREDENTIALS_FILE = 'gmail_credentials.json'
GMAIL_TOKEN_FILE = 'gmail_token.json'


class GmailTasksAutomation(Automation):
    """
    Automation to fetch Gmail inbox emails and convert them to Todoist tasks.

    This automation:
    1. Fetches inbox emails from Gmail from the lookback window
    2. Creates Todoist tasks from those emails (Todoist Inbox by default)
    3. Avoids creating duplicate tasks using content + Gmail message ID tracking
    """

    # Gmail API scopes
    SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

    # Legacy keyword heuristic retained for optional/manual checks/tests.
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
        lookback_days: int | None = 7,
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
        self.gmail_service: GmailService | None = None
        self.dry_run = dry_run
        self.max_messages_per_tick = (
            int(max_messages_per_tick)
            if max_messages_per_tick is not None and int(max_messages_per_tick) > 0
            else None
        )
        self.lookback_days = None if lookback_days is None else max(1, int(lookback_days))
        self.label_name = label_name
        self.allow_interactive_auth = allow_interactive_auth
        self._cache = Cache()
        # Keep persistent set of processed Gmail message IDs to avoid duplicate tasks across runs
        loaded_processed_ids = self._cache.processed_gmail_messages.load()
        self._processed_message_ids: set[GmailMessageId] = set(loaded_processed_ids or set())
        self.last_sync_stats: GmailSyncStats = new_sync_stats(dry_run=dry_run)

    @staticmethod
    def _format_gmail_date(d: date) -> str:
        return format_gmail_date(d)

    def _authenticate_gmail(self) -> GmailService | None:
        """Authenticate with Gmail API using stored credentials."""
        creds: GmailAuthCredentials | None = None

        # Check for existing token
        if os.path.exists(GMAIL_TOKEN_FILE):
            creds = cast(
                GmailAuthCredentials,
                Credentials.from_authorized_user_file(GMAIL_TOKEN_FILE, self.SCOPES),
            )

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
                    creds = cast(GmailAuthCredentials, flow.run_local_server(port=0))
                else:
                    logger.error(f"Gmail credentials file {GMAIL_CREDENTIALS_FILE} not found. "
                               "Please follow the setup instructions to configure Gmail API access.")
                    return None

            # Save the credentials for the next run
            assert creds is not None
            with open(GMAIL_TOKEN_FILE, 'w') as token:
                token.write(creds.to_json())

        return cast(GmailService, build('gmail', 'v1', credentials=creds))

    def _build_gmail_query(self) -> str:
        return build_gmail_inbox_query(lookback_days=self.lookback_days)

    def _list_matching_messages(self, query_: str) -> list[GmailMessageRef]:
        """List Gmail message refs (with pagination), capped when configured."""
        if self.gmail_service is None:
            raise RuntimeError("Gmail service is not initialized")

        messages: list[GmailMessageRef] = []
        page_token: str | None = None

        while True:
            list_kwargs: GmailListParams = {
                C.GmailKey.USER_ID: 'me',
                C.GmailKey.QUERY: query_,
            }
            if page_token:
                list_kwargs[C.GmailKey.PAGE_TOKEN] = page_token

            results = self.gmail_service.users().messages().list(**list_kwargs).execute()
            batch = results.get(C.GmailKey.MESSAGES, [])
            if batch:
                messages.extend(batch)
                if self.max_messages_per_tick is not None and len(messages) >= self.max_messages_per_tick:
                    return messages[:self.max_messages_per_tick]

            page_token = results.get(C.GmailKey.NEXT_PAGE_TOKEN)
            if not page_token:
                return messages

    @staticmethod
    def _header_map(headers: list[GmailHeaderRecord] | None) -> GmailHeaderMap:
        return normalize_gmail_headers(headers)

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
        is_actionable = email_matches_keywords(subject, snippet, self.TASK_KEYWORDS)
        logger.debug(f"Email {subject} -> actionable? {is_actionable}")
        return is_actionable

    def _extract_task_content(self, subject: str, snippet: str, sender: str) -> ExtractedTaskData:
        return extract_task_data(subject, snippet, sender)

    @staticmethod
    def _gmail_message_id_marker(message_id: GmailMessageId) -> str:
        return gmail_message_id_marker(message_id)

    @classmethod
    def _extract_gmail_message_id_from_description(cls, description: str) -> GmailMessageId | None:
        return extract_gmail_message_id_from_description(description)

    @classmethod
    def _append_gmail_message_id_to_description(cls, description: str, message_id: GmailMessageId) -> str:
        return append_gmail_message_id_to_description(description, message_id)

    def _get_existing_task_dedup_index(self, db: Database) -> ExistingTaskDedupIndex:
        """Return existing task content and tracked Gmail message IDs for deduplication."""
        try:
            projects = db.fetch_projects(include_tasks=True)
            existing_contents: set[str] = set()
            existing_gmail_message_ids: set[GmailMessageId] = set()

            for project in projects:
                for task in getattr(project, 'tasks', []) or []:
                    task_entry = getattr(task, 'task_entry', None)
                    content = getattr(task_entry, 'content', '')
                    if isinstance(content, str) and content.strip():
                        existing_contents.add(content.lower().strip())

                    description = getattr(task_entry, 'description', '')
                    if isinstance(description, str) and description:
                        existing_message_id = self._extract_gmail_message_id_from_description(description)
                        if existing_message_id is not None:
                            existing_gmail_message_ids.add(existing_message_id)

            logger.info(
                "Found {} existing tasks and {} Gmail-linked tasks",
                len(existing_contents),
                len(existing_gmail_message_ids),
            )
            return ExistingTaskDedupIndex(
                contents=existing_contents,
                gmail_message_ids=existing_gmail_message_ids,
            )

        except (AttributeError, KeyError, RuntimeError, TypeError) as e:
            logger.error(f"Error fetching existing tasks: {e}")
            return ExistingTaskDedupIndex(contents=set(), gmail_message_ids=set())

    def _get_existing_task_contents(self, db: Database) -> set[str]:
        """
        Get content of all existing tasks to avoid duplicates.

        Args:
            db: Database instance

        Returns:
            Set of existing task contents (normalized)
        """
        return self._get_existing_task_dedup_index(db).contents

    def _process_messages_batch(
        self,
        *,
        db: Database,
        messages: list[GmailMessageRef],
        stats: GmailSyncStats,
        existing_gmail_message_ids: set[GmailMessageId],
    ) -> bool:
        """Process a batch of Gmail message refs and update sync stats in place."""
        gmail_service = self.gmail_service
        if gmail_service is None:
            raise RuntimeError("Gmail service is not initialized")

        processed_ids_changed = False
        for message in messages:
            try:
                msg_id = message.get(C.GmailKey.ID)
                stats['messages_scanned'] += 1
                logger.debug(f"Processing email id={msg_id}")
                if msg_id and msg_id in self._processed_message_ids:
                    stats['skipped_processed'] += 1
                    logger.debug(f"Skipping already processed email id={msg_id}")
                    continue
                logger.debug(f'Not yet processed email id={msg_id} in bag of {len(messages)} marked mails.')
                if not msg_id:
                    stats['skipped_missing_id'] += 1
                    logger.debug("Skipping email without id")
                    continue
                if msg_id in existing_gmail_message_ids:
                    stats['duplicates'] += 1
                    if not self.dry_run and msg_id not in self._processed_message_ids:
                        self._processed_message_ids.add(msg_id)
                        processed_ids_changed = True
                    logger.debug(f"Skipping already-created Gmail task for email id={msg_id}")
                    continue

                msg = gmail_service.users().messages().get(
                    userId='me',
                    id=msg_id,
                ).execute()

                payload = cast(GmailPayloadRecord | None, msg.get(C.GmailKey.PAYLOAD))
                headers = self._header_map(payload.get(C.GmailKey.HEADERS) if payload is not None else None)
                subject = headers.get(C.GmailKey.SUBJECT, C.GmailText.NO_SUBJECT)
                sender = headers.get(C.GmailKey.FROM, C.GmailText.UNKNOWN_SENDER)
                snippet = str(msg.get(C.GmailKey.SNIPPET, ''))

                # All inbox emails are treated as relevant for task creation.
                stats['actionable_messages'] += 1

                task_data = self._extract_task_content(subject, snippet, sender)

                normalized_content = task_data.content.lower().strip()
                if not normalized_content:
                    stats['skipped_empty_content'] += 1
                    logger.debug(f"Skipping email with empty task content id={msg_id}")
                    continue

                if self.dry_run:
                    stats['would_create'] += 1
                    logger.info(f"[dry-run] Would create task: {task_data.content}")
                    continue

                result: TodoistInsertTaskResult = db.insert_task(
                    content=task_data.content,
                    description=self._append_gmail_message_id_to_description(task_data.description, msg_id),
                    priority=task_data.priority,
                    labels=[self.label_name],
                )

                if C.TodoistKey.ERROR not in result:
                    stats['created'] += 1
                    existing_gmail_message_ids.add(msg_id)
                    logger.info(f"Created task: {task_data.content}")
                    self._processed_message_ids.add(msg_id)
                    processed_ids_changed = True
                else:
                    stats['errors'] += 1
                    logger.error(f"Failed to create task: {result.get(C.TodoistKey.ERROR)}")

            except (HttpError, KeyError, ValueError, AttributeError, TypeError) as e:
                stats['errors'] += 1
                logger.error(f"Error processing email {message.get(C.GmailKey.ID)}: {e}")

        return processed_ids_changed

    def _tick(self, db: Database) -> None:
        """
        Main automation logic - fetch emails and create tasks.

        Args:
            db: Database instance for Todoist operations
        """
        stats = new_sync_stats(dry_run=self.dry_run)
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

            # Fetch inbox emails from the lookback window
            logger.info("Fetching inbox emails from Gmail...")
            query_ = self._build_gmail_query()
            stats['query'] = query_
            logger.debug(f'Gmail query: {query_}')
            messages = self._list_matching_messages(query_)
            stats['messages_found'] = len(messages)
            logger.info(f"Found {len(messages)} inbox emails")

            if not messages:
                logger.info("No inbox emails found")
                return

            # Get existing tasks to avoid duplicates by Gmail message id
            dedup_index = self._get_existing_task_dedup_index(db)
            existing_gmail_message_ids = dedup_index.gmail_message_ids

            processed_ids_changed = self._process_messages_batch(
                db=db,
                messages=messages,
                stats=stats,
                existing_gmail_message_ids=existing_gmail_message_ids,
            )

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
