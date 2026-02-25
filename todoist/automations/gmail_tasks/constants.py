from enum import StrEnum


class GmailKey(StrEnum):
    ID = "id"
    PAYLOAD = "payload"
    HEADERS = "headers"
    SNIPPET = "snippet"
    MESSAGES = "messages"
    NEXT_PAGE_TOKEN = "nextPageToken"
    PAGE_TOKEN = "pageToken"
    USER_ID = "userId"
    QUERY = "q"
    NAME = "name"
    VALUE = "value"
    SUBJECT = "subject"
    FROM = "from"


class GmailText(StrEnum):
    MESSAGE_ID_PREFIX = "Gmail Message ID: "
    NO_SUBJECT = "No Subject"
    UNKNOWN_SENDER = "Unknown Sender"
    EMAIL_FOLLOW_UP = "Email follow-up"


class TodoistKey(StrEnum):
    ERROR = "error"
