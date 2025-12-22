"""Shared LLM message and prompt tokens."""


from enum import StrEnum


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class PromptToken(StrEnum):
    INST_OPEN = "[INST]"
    INST_CLOSE = "[/INST]"
    BOS_FALLBACK = "<s>"
    EOS_FALLBACK = "</s>"
