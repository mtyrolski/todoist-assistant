"""Tests for model catalog pre-download helpers."""

import threading
import time

from scripts import download_models
from todoist.llm.model_catalog import downloadable_model_ids

# pylint: disable=protected-access


def test_downloadable_model_ids_deduplicates_local_and_triton_catalogs() -> None:
    model_ids = downloadable_model_ids(("local", "triton"))

    assert len(model_ids) == len(set(model_ids))
    assert model_ids == ["Qwen/Qwen2.5-3B-Instruct"]


def test_selected_model_ids_prefers_explicit_ids() -> None:
    args = download_models._parse_args(
        [
            "--backend",
            "local",
            "--model-id",
            "Qwen/Qwen2.5-7B-Instruct",
            "--model-id",
            "Qwen/Qwen2.5-7B-Instruct",
            "--model-id",
            "mistralai/Mistral-7B-Instruct-v0.3",
        ]
    )

    assert download_models._selected_model_ids(args) == [
        "Qwen/Qwen2.5-7B-Instruct",
        "mistralai/Mistral-7B-Instruct-v0.3",
    ]


def test_download_models_calls_snapshot_download(monkeypatch) -> None:
    calls: list[tuple[str, str | None, str | None]] = []

    def _fake_snapshot_download(
        *,
        repo_id: str,
        cache_dir: str | None = None,
        revision: str | None = None,
    ) -> str:
        calls.append((repo_id, cache_dir, revision))
        return f"/cache/{repo_id}"

    monkeypatch.setattr(download_models, "snapshot_download", _fake_snapshot_download)
    exit_code = download_models.download_models(
        ["Qwen/Qwen2.5-7B-Instruct"],
        cache_dir="/tmp/hf",
        revision="main",
    )

    assert exit_code == 0
    assert calls == [("Qwen/Qwen2.5-7B-Instruct", "/tmp/hf", "main")]


def test_download_models_downloads_in_parallel(monkeypatch) -> None:
    active = 0
    max_active = 0
    lock = threading.Lock()

    def _fake_snapshot_download(
        *,
        repo_id: str,
        cache_dir: str | None = None,
        revision: str | None = None,
    ) -> str:
        del cache_dir, revision
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        return f"/cache/{repo_id}"

    monkeypatch.setattr(download_models, "snapshot_download", _fake_snapshot_download)
    exit_code = download_models.download_models(
        ["Qwen/Qwen2.5-7B-Instruct", "Qwen/Qwen2.5-3B-Instruct"],
        workers=2,
    )

    assert exit_code == 0
    assert max_active == 2
