"""Gmail Tasks Automation for Todoist Assistant.

This module provides automation to fetch emails from Gmail and create Todoist tasks
from emails that appear to contain actionable items, while avoiding duplicates.
"""

import datetime
import os.path
import re
from typing import List, Set

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from loguru import logger

from todoist.automations.base import Automation
from todoist.database.base import Database


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
    
    def __init__(self, name: str = "Gmail Tasks", frequency_in_minutes: float = 60):
        """
        Initialize the Gmail Tasks automation.
        
        Args:
            name: Name of the automation
            frequency_in_minutes: How often to run the automation (in minutes)
        """
        super().__init__(name, frequency_in_minutes)
        self.gmail_service = None
        
    def _authenticate_gmail(self):
        """Authenticate with Gmail API using stored credentials."""
        creds = None
        
        # Check for existing token
        if os.path.exists('gmail_token.json'):
            creds = Credentials.from_authorized_user_file('gmail_token.json', self.SCOPES)
            
        # If there are no (valid) credentials available, let the user log in
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if os.path.exists('gmail_credentials.json'):
                    flow = InstalledAppFlow.from_client_secrets_file('gmail_credentials.json', self.SCOPES)
                    creds = flow.run_local_server(port=0)
                else:
                    logger.error("Gmail credentials file 'gmail_credentials.json' not found. "
                               "Please follow the setup instructions to configure Gmail API access.")
                    return None
                    
            # Save the credentials for the next run
            with open('gmail_token.json', 'w') as token:
                token.write(creds.to_json())
                
        return build('gmail', 'v1', credentials=creds)
    
    def _is_actionable_email(self, subject: str, snippet: str) -> bool:
        """
        Determine if an email contains actionable content based on keywords.
        
        Args:
            subject: Email subject line
            snippet: Email snippet/preview text
            
        Returns:
            True if the email appears to contain actionable items
        """
        text_to_check = f"{subject} {snippet}".lower()
        return any(keyword in text_to_check for keyword in self.TASK_KEYWORDS)
    
    def _extract_task_content(self, subject: str, snippet: str, sender: str) -> dict:
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
        
        # Remove common email prefixes
        content = re.sub(r'^(re:|fwd?:|fw:)\s*', '', content, flags=re.IGNORECASE)
        
        # Create description with context
        description = f"Email from: {sender}\n\nSnippet: {snippet}"
        
        # Determine priority based on urgency keywords
        priority = 1  # Normal priority
        urgent_keywords = ['urgent', 'asap', 'important', 'deadline', 'critical']
        if any(keyword in content.lower() or keyword in snippet.lower() for keyword in urgent_keywords):
            priority = 3  # High priority
            
        return {
            'content': content,
            'description': description,
            'priority': priority
        }
    
    def _get_existing_task_contents(self, db: Database) -> Set[str]:
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
                for task in project.tasks:
                    # Normalize content for comparison (lowercase, stripped)
                    normalized_content = task.task_entry.content.lower().strip()
                    existing_contents.add(normalized_content)
                    
            logger.info(f"Found {len(existing_contents)} existing tasks")
            return existing_contents
            
        except Exception as e:
            logger.error(f"Error fetching existing tasks: {e}")
            return set()
    
    def _tick(self, db: Database):
        """
        Main automation logic - fetch emails and create tasks.
        
        Args:
            db: Database instance for Todoist operations
        """
        try:
            # Authenticate with Gmail
            self.gmail_service = self._authenticate_gmail()
            if not self.gmail_service:
                logger.error("Failed to authenticate with Gmail API")
                return
                
            logger.info("Successfully authenticated with Gmail API")
            
            # Get timeframe - last week
            now = datetime.datetime.utcnow()
            one_week_ago = (now - datetime.timedelta(weeks=1)).isoformat() + 'Z'
            
            # Fetch unread emails from the last week
            logger.info("Fetching unread emails from the last week...")
            results = self.gmail_service.users().messages().list(
                userId='me',
                q=f'is:unread after:{one_week_ago}'
            ).execute()
            
            messages = results.get('messages', [])
            logger.info(f"Found {len(messages)} unread emails")
            
            if not messages:
                logger.info("No unread emails found")
                return
                
            # Get existing tasks to avoid duplicates
            existing_task_contents = self._get_existing_task_contents(db)
            
            # Process each email
            tasks_created = 0
            for message in messages:
                try:
                    # Get email details
                    msg = self.gmail_service.users().messages().get(
                        userId='me', 
                        id=message['id']
                    ).execute()
                    
                    # Extract email data
                    headers = {h['name']: h['value'] for h in msg['payload']['headers']}
                    subject = headers.get('Subject', 'No Subject')
                    sender = headers.get('From', 'Unknown Sender')
                    snippet = msg.get('snippet', '')
                    
                    # Check if email is actionable
                    if not self._is_actionable_email(subject, snippet):
                        continue
                        
                    # Extract task content
                    task_data = self._extract_task_content(subject, snippet, sender)
                    
                    # Check for duplicates
                    normalized_content = task_data['content'].lower().strip()
                    if normalized_content in existing_task_contents:
                        logger.debug(f"Skipping duplicate task: {task_data['content']}")
                        continue
                        
                    # Create task in Todoist
                    result = db.insert_task(
                        content=task_data['content'],
                        description=task_data['description'],
                        priority=task_data['priority'],
                        labels=['gmail-task']  # Add label to identify Gmail-generated tasks
                    )
                    
                    if 'error' not in result:
                        tasks_created += 1
                        existing_task_contents.add(normalized_content)  # Prevent duplicates in this run
                        logger.info(f"Created task: {task_data['content']}")
                    else:
                        logger.error(f"Failed to create task: {result.get('error')}")
                        
                except Exception as e:
                    logger.error(f"Error processing email {message['id']}: {e}")
                    
            logger.info(f"Gmail Tasks automation completed. Created {tasks_created} new tasks.")
            
        except Exception as e:
            logger.error(f"Gmail Tasks automation failed: {e}")