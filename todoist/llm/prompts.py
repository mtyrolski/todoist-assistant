"""Prompt rendering helpers for tokenizer-backed LLM backends."""

from collections.abc import Callable, Sequence
from typing import cast

from transformers import PreTrainedTokenizerBase

from .types import MessageRole, PromptToken


def _render_chat_prompt(messages: Sequence[dict[str, str]], tokenizer: PreTrainedTokenizerBase) -> str:
    apply_chat_template = getattr(tokenizer, "apply_chat_template", None)
    if callable(apply_chat_template):
        template_fn = cast(Callable[..., object], apply_chat_template)
        payload = [
            {
                "role": str(message.get("role") or "").strip().lower(),
                "content": str(message.get("content") or "").strip(),
            }
            for message in messages
            if str(message.get("content") or "").strip()
        ]
        try:
            rendered = template_fn(  # pylint: disable=not-callable
                payload,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=False,
            )
            if isinstance(rendered, str) and rendered.strip():
                return rendered.strip()
        except (TypeError, ValueError, NotImplementedError):
            try:
                rendered = template_fn(  # pylint: disable=not-callable
                    payload,
                    tokenize=False,
                    add_generation_prompt=True,
                )
                if isinstance(rendered, str) and rendered.strip():
                    return rendered.strip()
            except (TypeError, ValueError, NotImplementedError):
                pass
    return _render_mistral_instruct_prompt(messages, tokenizer)


def _render_mistral_instruct_prompt(messages: Sequence[dict[str, str]], tokenizer: PreTrainedTokenizerBase) -> str:
    system_parts: list[str] = []
    turns: list[tuple[str, str | None]] = []

    current_user: str | None = None
    current_assistant: str | None = None

    for msg in messages:
        role = (msg.get("role") or "").lower()
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        if role == MessageRole.SYSTEM:
            system_parts.append(content)
            continue
        if role == MessageRole.USER:
            if current_user is not None:
                turns.append((current_user, current_assistant))
            current_user = content
            current_assistant = None
            continue
        if role == MessageRole.ASSISTANT:
            current_assistant = content
            continue

    if current_user is not None:
        turns.append((current_user, current_assistant))

    if not turns:
        raise ValueError("At least one user message is required")
    if turns[-1][1] is not None:
        raise ValueError("Last user message must be unanswered (append user message before generating)")

    bos = tokenizer.bos_token or PromptToken.BOS_FALLBACK
    eos = tokenizer.eos_token or PromptToken.EOS_FALLBACK
    system_prefix = "\n\n".join(system_parts).strip()
    if system_prefix:
        system_prefix += "\n\n"

    parts: list[str] = []
    for i, (user_text, assistant_text) in enumerate(turns):
        prefix = system_prefix if i == 0 else ""
        inst = f"{bos}{PromptToken.INST_OPEN} {prefix}{user_text} {PromptToken.INST_CLOSE}"
        if assistant_text is None:
            parts.append(inst)
        else:
            parts.append(f"{inst} {assistant_text} {eos}")
    return "".join(parts).strip()
