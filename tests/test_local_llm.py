# pyright: reportPrivateImportUsage=false

from typing import cast
from unittest.mock import patch

import torch
from pydantic import BaseModel
from transformers import PreTrainedTokenizerBase

from todoist.env import EnvVar
from todoist.llm import LocalChatConfig, MessageRole, PromptToken, TransformersMistral3ChatModel
from todoist.llm.local_llm import _render_chat_prompt
from todoist.llm.usage import load_llm_usage_summary


class FakeTokenizer:
    bos_token = PromptToken.BOS_FALLBACK
    eos_token = PromptToken.EOS_FALLBACK
    pad_token = None
    pad_token_id = 0

    def __init__(self, outputs: list[str]) -> None:
        self._outputs = outputs

    @classmethod
    def from_pretrained(cls, *_args, **_kwargs):
        return cls(outputs=["OK", '```json\n{\"value\": \"ok\"}\n```'])

    def __call__(self, _prompt: str, *, return_tensors: str):
        assert return_tensors == "pt"
        return {
            "input_ids": torch.tensor([[1, 2, 3]]),
            "attention_mask": torch.tensor([[1, 1, 1]]),
            "token_type_ids": torch.tensor([[0, 0, 0]]),
        }

    def decode(self, _ids, *, skip_special_tokens: bool):
        assert skip_special_tokens is True
        return self._outputs.pop(0)


class FakeConfig:
    model_type = "mistral3"


class FakeChatTemplateTokenizer:
    bos_token = PromptToken.BOS_FALLBACK
    eos_token = PromptToken.EOS_FALLBACK

    def apply_chat_template(self, messages, *, tokenize, add_generation_prompt, enable_thinking):
        assert tokenize is False
        assert add_generation_prompt is True
        assert enable_thinking is False
        return "PROMPT:" + " | ".join(f"{item['role']}={item['content']}" for item in messages)


class FakeModel:
    def __init__(self) -> None:
        self.device = torch.device("cpu")

    @classmethod
    def from_pretrained(cls, *_args, **_kwargs):
        return cls()

    def to(self, _device):
        return self

    def eval(self):
        return self

    def parameters(self):
        return []

    def buffers(self):
        return []

    def generate(self, **_kwargs):
        assert "token_type_ids" not in _kwargs
        return torch.tensor([[1, 2, 3, 4]])


class DummySchema(BaseModel):
    value: str


def test_local_llm_initializes_and_generates(monkeypatch, tmp_path):
    monkeypatch.setenv(str(EnvVar.CACHE_DIR), str(tmp_path))
    cfg = LocalChatConfig(model_id="fake/model", max_new_tokens=4)
    with patch("todoist.llm.local_llm.AutoTokenizer", new=FakeTokenizer), \
         patch("todoist.llm.local_llm.AutoConfig.from_pretrained", new=lambda *_a, **_k: FakeConfig()), \
         patch("todoist.llm.local_llm.Mistral3ForConditionalGeneration", new=FakeModel):
        llm = TransformersMistral3ChatModel(cfg)
        assert llm.chat([{"role": MessageRole.USER, "content": "hi"}]) == "OK"
        parsed = llm.structured_chat([{"role": MessageRole.USER, "content": "hi"}], DummySchema)
        assert parsed.value == "ok"
    usage = load_llm_usage_summary(selected_backend="transformers_local", selected_model_id="fake/model")
    assert usage["totals"]["inferenceCount"] == 2
    assert usage["totals"]["chatCount"] == 1
    assert usage["totals"]["structuredCount"] == 1
    assert usage["totals"]["inputTokens"] == 6
    assert usage["totals"]["outputTokens"] == 2


def test_local_chat_prompt_uses_tokenizer_template_when_available():
    prompt = _render_chat_prompt(
        [{"role": MessageRole.USER, "content": "Break this down"}],
        cast(PreTrainedTokenizerBase, FakeChatTemplateTokenizer()),
    )

    assert prompt == "PROMPT:user=Break this down"
