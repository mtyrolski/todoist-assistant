"""Tests for the Triton Python backend model entrypoint."""

# pylint: disable=protected-access

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest


def _load_triton_backend_module() -> Any:
    module_path = (
        Path(__file__).resolve().parents[3]
        / "deploy"
        / "triton"
        / "model_repository"
        / "todoist_llm"
        / "1"
        / "model.py"
    )
    stub = ModuleType("triton_python_backend_utils")
    setattr(stub, "get_input_tensor_by_name", lambda *_args, **_kwargs: None)
    setattr(stub, "TritonError", RuntimeError)
    setattr(stub, "InferenceResponse", object)
    setattr(stub, "Tensor", object)
    sys.modules.setdefault("triton_python_backend_utils", stub)
    spec = importlib.util.spec_from_file_location(
        "todoist_triton_backend_model", module_path
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_triton_backend_load_tokenizer_falls_back_for_tokenizers_backend(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_triton_backend_module()
    monkeypatch.setattr(
        module.AutoTokenizer,
        "from_pretrained",
        Mock(
            side_effect=ValueError("Tokenizer class TokenizersBackend does not exist")
        ),
    )
    monkeypatch.setattr(module, "snapshot_download", lambda **_kwargs: str(tmp_path))
    tokenizer_ctor = Mock(return_value=object())
    monkeypatch.setattr(module, "PreTrainedTokenizerFast", tokenizer_ctor)

    (tmp_path / "tokenizer.json").write_text("{}", encoding="utf-8")
    (tmp_path / "tokenizer_config.json").write_text(
        json.dumps(
            {
                "bos_token": "<s>",
                "eos_token": "</s>",
                "unk_token": "<unk>",
                "additional_special_tokens": ["<extra>", 1],
            }
        ),
        encoding="utf-8",
    )

    result = module._load_tokenizer(
        "mistralai/Ministral-3-3B-Instruct-2512", trust_remote_code=False
    )

    assert result is tokenizer_ctor.return_value
    tokenizer_ctor.assert_called_once_with(
        tokenizer_file=str(tmp_path / "tokenizer.json"),
        bos_token="<s>",
        eos_token="</s>",
        unk_token="<unk>",
        additional_special_tokens=["<extra>"],
    )


def test_triton_backend_load_tokenizer_reraises_unrelated_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_triton_backend_module()
    monkeypatch.setattr(
        module.AutoTokenizer,
        "from_pretrained",
        Mock(side_effect=ValueError("some other tokenizer error")),
    )

    with pytest.raises(ValueError, match="some other tokenizer error"):
        module._load_tokenizer("some/model", trust_remote_code=False)


def test_triton_backend_load_config_normalizes_ministral3(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_triton_backend_module()
    monkeypatch.setattr(
        module.AutoConfig,
        "from_pretrained",
        Mock(side_effect=KeyError("'ministral3'")),
    )
    monkeypatch.setattr(module, "snapshot_download", lambda **_kwargs: str(tmp_path))
    normalized_config = object()
    for_model = Mock(return_value=normalized_config)
    monkeypatch.setattr(module.AutoConfig, "for_model", for_model)

    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "model_type": "mistral3",
                "text_config": {"model_type": "ministral3"},
                "hidden_size": 42,
            }
        ),
        encoding="utf-8",
    )

    result = module._load_config("mistralai/Ministral-3-3B-Instruct-2512")

    assert result is normalized_config
    for_model.assert_called_once_with(
        "mistral3",
        text_config={"model_type": "mistral"},
        hidden_size=42,
    )


def test_triton_backend_initialize_uses_mistral3_loader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_triton_backend_module()

    class FakeTokenizer:
        pad_token = None
        eos_token = "</s>"
        pad_token_id = None
        eos_token_id = 7
        padding_side = "right"

    class FakeModel:
        def __init__(self) -> None:
            self.moved_to = None
            self.moved_dtype = None
            self.eval_called = False

        def to(
            self, device: Any = None, dtype: Any = None, **_kwargs: Any
        ) -> "FakeModel":
            self.moved_to = device
            self.moved_dtype = dtype
            return self

        def eval(self) -> None:
            self.eval_called = True

    fake_tokenizer = FakeTokenizer()
    fake_model = FakeModel()
    fake_config = SimpleNamespace(model_type="mistral3")
    mistral_loader = Mock(return_value=fake_model)
    auto_loader = Mock()

    monkeypatch.setattr(
        module, "_load_tokenizer", lambda *_args, **_kwargs: fake_tokenizer
    )
    monkeypatch.setattr(module, "_load_config", lambda *_args, **_kwargs: fake_config)
    monkeypatch.setattr(
        module, "_strip_quantization_config", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        module.Mistral3ForConditionalGeneration, "from_pretrained", mistral_loader
    )
    monkeypatch.setattr(module.AutoModelForCausalLM, "from_pretrained", auto_loader)

    backend = module.TritonPythonModel()
    backend.initialize({"model_config": "{}"})

    mistral_loader.assert_called_once()
    auto_loader.assert_not_called()
    assert fake_model.moved_to is not None
    assert fake_model.moved_dtype is None
    assert fake_model.eval_called is True
    assert fake_tokenizer.pad_token == "</s>"
    assert fake_tokenizer.padding_side == "left"


def test_resolve_torch_dtype_auto_does_not_force_cpu_float32() -> None:
    module = _load_triton_backend_module()

    assert (
        module._resolve_torch_dtype("auto", device=module.torch.device("cpu")) is None
    )


def test_move_model_to_runtime_passes_dtype_when_requested() -> None:
    module = _load_triton_backend_module()

    calls: list[dict[str, Any]] = []

    class FakeModel:
        def to(self, *args: Any, **kwargs: Any) -> "FakeModel":
            calls.append({"args": args, "kwargs": kwargs})
            return self

    model = FakeModel()
    result = module._move_model_to_runtime(
        model,
        device=module.torch.device("cpu"),
        dtype=module.torch.float16,
    )

    assert result is model
    assert calls == [
        {
            "args": (),
            "kwargs": {
                "device": module.torch.device("cpu"),
                "dtype": module.torch.float16,
            },
        }
    ]


def test_move_model_to_runtime_skips_dtype_when_not_requested() -> None:
    module = _load_triton_backend_module()

    calls: list[dict[str, Any]] = []

    class FakeModel:
        def to(self, *args: Any, **kwargs: Any) -> "FakeModel":
            calls.append({"args": args, "kwargs": kwargs})
            return self

    model = FakeModel()
    result = module._move_model_to_runtime(
        model,
        device=module.torch.device("cpu"),
        dtype=None,
    )

    assert result is model
    assert calls == [{"args": (module.torch.device("cpu"),), "kwargs": {}}]


def test_split_execution_items_respects_batch_size_limit() -> None:
    module = _load_triton_backend_module()
    backend = module.TritonPythonModel()
    backend._max_batch_size = 2
    backend._max_batch_input_tokens = 999
    backend._prompt_token_lengths = lambda prompts: [10 for _ in prompts]

    items = [
        (0, 0, "a"),
        (0, 1, "b"),
        (1, 0, "c"),
    ]

    batches = backend._split_execution_items(items)

    assert batches == [
        [(0, 0, "a"), (0, 1, "b")],
        [(1, 0, "c")],
    ]


def test_split_execution_items_respects_token_budget() -> None:
    module = _load_triton_backend_module()
    backend = module.TritonPythonModel()
    backend._max_batch_size = 10
    backend._max_batch_input_tokens = 12
    backend._prompt_token_lengths = lambda prompts: [5, 5, 5]

    items = [
        (0, 0, "a"),
        (0, 1, "b"),
        (1, 0, "c"),
    ]

    batches = backend._split_execution_items(items)

    assert batches == [
        [(0, 0, "a"), (0, 1, "b")],
        [(1, 0, "c")],
    ]
