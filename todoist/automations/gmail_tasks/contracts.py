from dataclasses import dataclass
from typing import Protocol, TypeAlias, TypedDict

from google.auth.transport.requests import Request

GmailMessageId: TypeAlias = str
GmailHeaderMap: TypeAlias = dict[str, str]
GmailListParams: TypeAlias = dict[str, str]
TodoistInsertTaskResult: TypeAlias = dict[str, object]


class GmailHeaderRecord(TypedDict, total=False):
    name: str
    value: str


class GmailPayloadRecord(TypedDict, total=False):
    headers: list[GmailHeaderRecord]


class GmailMessageRef(TypedDict, total=False):
    id: GmailMessageId


class GmailMessageRecord(TypedDict, total=False):
    id: GmailMessageId
    payload: GmailPayloadRecord
    snippet: str


class GmailMessageListResponse(TypedDict, total=False):
    messages: list[GmailMessageRef]
    nextPageToken: str


class GmailSyncStats(TypedDict):
    dry_run: bool
    auth_failed: bool
    query: str | None
    messages_found: int
    messages_scanned: int
    actionable_messages: int
    duplicates: int
    created: int
    would_create: int
    skipped_processed: int
    skipped_missing_id: int
    skipped_empty_content: int
    errors: int


@dataclass(frozen=True, slots=True)
class ExtractedTaskData:
    content: str
    description: str
    priority: int


@dataclass(frozen=True, slots=True)
class ExistingTaskDedupIndex:
    contents: set[str]
    gmail_message_ids: set[GmailMessageId]


class _GmailListRequest(Protocol):
    def execute(self) -> GmailMessageListResponse: ...


class _GmailGetRequest(Protocol):
    def execute(self) -> GmailMessageRecord: ...


class _GmailMessagesApi(Protocol):
    def list(self, **kwargs: str) -> _GmailListRequest: ...
    def get(self, *, userId: str, **kwargs: str) -> _GmailGetRequest: ...


class _GmailUsersApi(Protocol):
    def messages(self) -> _GmailMessagesApi: ...


class GmailService(Protocol):
    def users(self) -> _GmailUsersApi: ...


class GmailAuthCredentials(Protocol):
    valid: bool
    expired: bool
    refresh_token: str | None

    def refresh(self, request: Request) -> None: ...
    def to_json(self) -> str: ...


def new_sync_stats(*, dry_run: bool) -> GmailSyncStats:
    return {
        'dry_run': dry_run,
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
