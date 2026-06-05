"""Codex CLI flag constants."""

from enum import StrEnum
from typing import Final


class CodexDangerousFlag(StrEnum):
    BYPASS_APPROVALS_AND_SANDBOX = "--dangerously-bypass-approvals-and-sandbox"
    BYPASS_HOOK_TRUST = "--dangerously-bypass-hook-trust"


DANGEROUS_CODEX_FLAGS: Final[frozenset[CodexDangerousFlag]] = frozenset(
    CodexDangerousFlag
)
