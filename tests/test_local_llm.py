from unittest.mock import patch

import torch
from pydantic import BaseModel

from todoist.agent.local_llm import LocalChatConfig, TransformersMistral3ChatModel


class FakeTokenizer:
    bos_token = "<s>"
    eos_token = "</s>"
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


def test_local_llm_initializes_and_generates():
    cfg = LocalChatConfig(model_id="fake/model", max_new_tokens=4)
    with patch("todoist.agent.local_llm.AutoTokenizer", new=FakeTokenizer), \
         patch("todoist.agent.local_llm.AutoConfig.from_pretrained", new=lambda *_a, **_k: FakeConfig()), \
         patch("todoist.agent.local_llm.Mistral3ForConditionalGeneration", new=FakeModel):
        llm = TransformersMistral3ChatModel(cfg)
        assert llm.chat([{"role": "user", "content": "hi"}]) == "OK"
        parsed = llm.structured_chat([{"role": "user", "content": "hi"}], DummySchema)
        assert parsed.value == "ok"
