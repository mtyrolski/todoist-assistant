"""Download configured Hugging Face models into the local cache."""

from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import sys
import time

from dotenv import load_dotenv
from huggingface_hub import snapshot_download
from huggingface_hub.utils.tqdm import enable_progress_bars
from tqdm.auto import tqdm

from todoist.llm.model_catalog import ModelBackend, downloadable_model_ids


def _parse_args(argv: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(
        description=(
            "Pre-download the Hugging Face models exposed by the dashboard local "
            "Transformers and Triton model selectors."
        )
    )
    parser.add_argument(
        "--backend",
        choices=("all", "local", "triton"),
        default="all",
        help="Model catalog to download. Defaults to all local and Triton models.",
    )
    parser.add_argument(
        "--model-id",
        action="append",
        default=[],
        help="Download one explicit Hugging Face model id instead of the catalog. May be repeated.",
    )
    parser.add_argument(
        "--cache-dir",
        help="Optional Hugging Face cache directory passed to snapshot_download.",
    )
    parser.add_argument(
        "--revision",
        help="Optional revision, branch, or commit to download for every selected model.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        help="Number of models to download in parallel. Defaults to min(4, selected models).",
    )
    parser.add_argument(
        "--skip-errors",
        action="store_true",
        help="Continue and exit successfully even if a model cannot be downloaded.",
    )
    return parser.parse_args(argv)


def _selected_model_ids(args: Namespace) -> list[str]:
    explicit_ids = [str(model_id).strip() for model_id in args.model_id if str(model_id).strip()]
    if explicit_ids:
        return list(dict.fromkeys(explicit_ids))

    backend = str(args.backend)
    backends = _catalog_backends(backend)
    return downloadable_model_ids(backends)


def _catalog_backends(backend: str) -> tuple[ModelBackend, ...]:
    if backend == "local":
        return ("local",)
    if backend == "triton":
        return ("triton",)
    return ("local", "triton")


def _resolve_worker_count(requested_workers: int | None, model_count: int) -> int:
    if model_count <= 0:
        return 1
    if requested_workers is not None:
        return max(1, min(requested_workers, model_count))

    env_workers = os.getenv("TODOIST_DOWNLOAD_MODEL_WORKERS")
    if env_workers:
        try:
            return max(1, min(int(env_workers), model_count))
        except ValueError:
            print(
                f"Ignoring invalid TODOIST_DOWNLOAD_MODEL_WORKERS={env_workers!r}; using default.",
                file=sys.stderr,
            )
    return max(1, min(4, model_count))


def _download_one_model(
    model_id: str,
    *,
    cache_dir: str | None = None,
    revision: str | None = None,
) -> tuple[str, str | None, str | None]:
    try:
        local_path = snapshot_download(repo_id=model_id, cache_dir=cache_dir, revision=revision)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return model_id, None, str(exc)
    return model_id, local_path, None


def download_models(
    model_ids: Sequence[str],
    *,
    cache_dir: str | None = None,
    revision: str | None = None,
    skip_errors: bool = False,
    workers: int | None = None,
) -> int:
    if not model_ids:
        print("No downloadable Hugging Face model ids selected.")
        return 0
    enable_progress_bars()
    worker_count = _resolve_worker_count(workers, len(model_ids))
    print(f"Downloading {len(model_ids)} Hugging Face model(s) with {worker_count} worker(s).")
    cache_hint = cache_dir or os.getenv("HF_HOME") or os.getenv("HUGGINGFACE_HUB_CACHE") or "default HF cache"
    print(f"Cache: {cache_hint}")
    if revision:
        print(f"Revision: {revision}")

    failures: list[tuple[str, str]] = []
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(_download_one_model, model_id, cache_dir=cache_dir, revision=revision): model_id
            for model_id in model_ids
        }
        for index, future in enumerate(tqdm(as_completed(futures), total=len(futures), desc="Models", unit="model"), start=1):
            model_id, local_path, error = future.result()
            if error:
                failures.append((model_id, error))
                tqdm.write(f"[{index}/{len(model_ids)}] Failed: {model_id}: {error}", file=sys.stderr)
                continue
            tqdm.write(f"[{index}/{len(model_ids)}] Cached: {model_id} -> {local_path}")

        if not failures:
            print("All selected models are cached.")

    elapsed = time.monotonic() - started
    print(f"\nModel download pass finished in {elapsed:.1f}s.")
    if failures:
        print("Failures:", file=sys.stderr)
        for model_id, error in failures:
            print(f"  - {model_id}: {error}", file=sys.stderr)
        return 0 if skip_errors else 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    load_dotenv(".env", override=True)
    args = _parse_args(argv)
    return download_models(
        _selected_model_ids(args),
        cache_dir=args.cache_dir,
        revision=args.revision,
        skip_errors=bool(args.skip_errors),
        workers=args.workers,
    )


if __name__ == "__main__":
    raise SystemExit(main())
