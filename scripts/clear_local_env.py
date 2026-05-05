#!/usr/bin/env python3

"""Remove local runtime state created by the Todoist Assistant."""

from __future__ import annotations

import os
import shutil
import argparse
from pathlib import Path
from collections.abc import Sequence

from todoist.env import EnvVar
from todoist.utils import RUNTIME_MIGRATABLE_FILENAMES, resolve_cache_dir


def _resolve_data_dir() -> Path:
    override = os.getenv(str(EnvVar.DATA_DIR))
    if override:
        return Path(override).expanduser().resolve()
    return Path.cwd().resolve()


def _remove_path(path: Path) -> bool:
    if not path.exists():
        return False
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()
    return True


def clear_local_env() -> list[Path]:
    """Remove cache directories and legacy runtime files from the local checkout."""

    cache_dir = Path(resolve_cache_dir())
    data_dir = _resolve_data_dir()
    roots = [Path.cwd().resolve(), data_dir]
    cleanup_targets = [
        cache_dir,
        data_dir / "cache",
        Path.cwd() / ".cache-migration-backup",
        data_dir / ".cache-migration-backup",
    ]

    for root in roots:
        for filename in RUNTIME_MIGRATABLE_FILENAMES:
            cleanup_targets.append(root / filename)

    removed: list[Path] = []
    seen: set[str] = set()
    for target in cleanup_targets:
        key = str(target.expanduser().resolve())
        if key in seen:
            continue
        seen.add(key)
        if _remove_path(target):
            removed.append(target)
    return removed


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Remove local Todoist Assistant runtime state.")
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print every removed cache or runtime path.",
    )
    args = parser.parse_args(argv)
    removed = clear_local_env()
    if args.verbose:
        if removed:
            for path in removed:
                print(f"Removed: {path}")
        else:
            print("Nothing to remove.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
