import datetime as dt
import re
from collections.abc import Sequence

from . import constants as C
from .contracts import (
    ExtractedTaskData,
    GmailHeaderMap,
    GmailHeaderRecord,
    GmailMessageId,
)


def format_gmail_date(value: dt.date) -> str:
    """Return Gmail-compatible date string: YYYY/M/D (no leading zeros)."""
    return f"{value.year}/{value.month}/{value.day}"


def build_gmail_inbox_query(*, lookback_days: int | None, today: dt.date | None = None) -> str:
    """Build Gmail query targeting unread inbox messages, optionally time-bounded."""
    query_parts = ["in:inbox", "is:unread"]
    if lookback_days is None:
        return " ".join(query_parts)

    current_day = today or dt.date.today()
    start_date = current_day - dt.timedelta(days=lookback_days)
    tomorrow = current_day + dt.timedelta(days=1)  # `before:` is exclusive
    after_str = format_gmail_date(start_date)
    before_str = format_gmail_date(tomorrow)
    query_parts.extend([f"after:{after_str}", f"before:{before_str}"])
    return " ".join(query_parts)


def normalize_gmail_headers(headers: list[GmailHeaderRecord] | None) -> GmailHeaderMap:
    """Normalize Gmail headers into a lowercase name->value map."""
    normalized: GmailHeaderMap = {}
    for header in headers or []:
        name = str(header.get(C.GmailKey.NAME, '')).strip().lower()
        if not name:
            continue
        normalized[name] = str(header.get(C.GmailKey.VALUE, ''))
    return normalized


def email_matches_keywords(subject: str, snippet: str, keywords: Sequence[str]) -> bool:
    text_to_check = f"{subject} {snippet}".lower()
    return any(keyword in text_to_check for keyword in keywords)


def extract_task_data(subject: str, snippet: str, sender: str) -> ExtractedTaskData:
    """Create Todoist task fields from Gmail subject/snippet/sender."""
    content = subject.strip()
    content = re.sub(r'^(?:(?:re|fwd?):\s*)+', '', content, flags=re.IGNORECASE).strip()

    if not content:
        fallback = re.sub(r'\s+', ' ', snippet).strip()
        content = fallback[:120] if fallback else C.GmailText.EMAIL_FOLLOW_UP

    description = f"Email from: {sender}\n\nSnippet: {snippet}"

    priority = 1
    urgent_keywords = ['urgent', 'asap', 'important', 'deadline', 'critical']
    content_lower = content.lower()
    snippet_lower = snippet.lower()
    if any(keyword in content_lower or keyword in snippet_lower for keyword in urgent_keywords):
        priority = 3

    return ExtractedTaskData(content=content, description=description, priority=priority)


def gmail_message_id_marker(message_id: GmailMessageId) -> str:
    return f"{C.GmailText.MESSAGE_ID_PREFIX}{message_id}"


def extract_gmail_message_id_from_description(description: str) -> GmailMessageId | None:
    for line in description.splitlines():
        line_stripped = line.strip()
        if line_stripped.startswith(C.GmailText.MESSAGE_ID_PREFIX):
            value = line_stripped.removeprefix(C.GmailText.MESSAGE_ID_PREFIX).strip()
            return value or None
    return None


def append_gmail_message_id_to_description(description: str, message_id: GmailMessageId) -> str:
    marker_line = gmail_message_id_marker(message_id)
    if marker_line in description:
        return description
    return f"{description}\n\n{marker_line}"
