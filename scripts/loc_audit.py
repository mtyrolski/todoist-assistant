#!/usr/bin/env python3

"""Count tracked source lines for refactor guardrails."""

import argparse
import json
import subprocess
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path


DEFAULT_SOURCE_EXTENSIONS = (
    ".py",
    ".tsx",
    ".css",
    ".sh",
    ".md",
    ".ts",
    ".yml",
    ".ps1",
    ".wxs",
    ".yaml",
    ".spec",
    ".toml",
)
EXCLUDED_DIR_NAMES = {
    ".cache",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}
EXCLUDED_FILENAMES = {
    "package-lock.json",
    "uv.lock",
}


@dataclass(frozen=True)
class ExtensionCount:
    extension: str
    files: int
    lines: int


@dataclass(frozen=True)
class LocAudit:
    python_lines: int
    source_lines: int
    total_files: int
    by_extension: tuple[ExtensionCount, ...]


def _normalize_extensions(raw_extensions: Iterable[str]) -> tuple[str, ...]:
    extensions = []
    for extension in raw_extensions:
        stripped = extension.strip()
        if not stripped:
            continue
        extensions.append(stripped if stripped.startswith(".") else f".{stripped}")
    return tuple(dict.fromkeys(extensions))


def tracked_files(repo_root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=repo_root,
        check=True,
        text=True,
        capture_output=True,
    )
    return [Path(line) for line in result.stdout.splitlines() if line.strip()]


def is_counted_path(
    path: Path,
    *,
    extensions: Sequence[str] = DEFAULT_SOURCE_EXTENSIONS,
) -> bool:
    if path.name in EXCLUDED_FILENAMES:
        return False
    if any(part in EXCLUDED_DIR_NAMES for part in path.parts):
        return False
    return path.suffix in _normalize_extensions(extensions)


def count_file_lines(path: Path) -> int:
    with path.open("rb") as file:
        return sum(1 for _ in file)


def audit_paths(
    repo_root: Path,
    paths: Iterable[Path],
    *,
    extensions: Sequence[str] = DEFAULT_SOURCE_EXTENSIONS,
) -> LocAudit:
    normalized_extensions = _normalize_extensions(extensions)
    line_counts: Counter[str] = Counter()
    file_counts: Counter[str] = Counter()

    for relative_path in paths:
        if not is_counted_path(relative_path, extensions=normalized_extensions):
            continue
        extension = relative_path.suffix
        file_counts[extension] += 1
        line_counts[extension] += count_file_lines(repo_root / relative_path)

    by_extension = tuple(
        ExtensionCount(extension, file_counts[extension], line_counts[extension])
        for extension in sorted(line_counts, key=lambda item: (-line_counts[item], item))
    )
    return LocAudit(
        python_lines=line_counts[".py"],
        source_lines=sum(line_counts.values()),
        total_files=sum(file_counts.values()),
        by_extension=by_extension,
    )


def _format_table(audit: LocAudit) -> str:
    lines = [
        "Tracked source line audit",
        f"Python lines: {audit.python_lines:,}",
        f"Source lines: {audit.source_lines:,}",
        f"Counted files: {audit.total_files:,}",
        "",
        "Extension  Files  Lines",
        "---------  -----  -----",
    ]
    for item in audit.by_extension:
        lines.append(f"{item.extension:<9} {item.files:>5} {item.lines:>6,}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root to audit.",
    )
    parser.add_argument(
        "--extensions",
        nargs="+",
        default=DEFAULT_SOURCE_EXTENSIONS,
        help="File extensions to count. Defaults to the source audit set.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable counts.",
    )
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    audit = audit_paths(
        repo_root,
        tracked_files(repo_root),
        extensions=_normalize_extensions(args.extensions),
    )
    if args.json:
        print(
            json.dumps(
                {
                    "python_lines": audit.python_lines,
                    "source_lines": audit.source_lines,
                    "total_files": audit.total_files,
                    "by_extension": [
                        {
                            "extension": item.extension,
                            "files": item.files,
                            "lines": item.lines,
                        }
                        for item in audit.by_extension
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(_format_table(audit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
