"""Fail on explicit ``: Any =`` variable annotations in first-party code.

This keeps us from silencing type issues with throwaway variable annotations while
still allowing ``Any`` where it is part of a function signature or a structured type.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = ("todoist", "tests", "scripts")
SKIP_PARTS = {
    ".git",
    ".venv",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
}


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    name: str


def _is_explicit_any(annotation: ast.expr) -> bool:
    if isinstance(annotation, ast.Name):
        return annotation.id == "Any"
    if isinstance(annotation, ast.Attribute):
        return (
            isinstance(annotation.value, ast.Name)
            and annotation.value.id == "typing"
            and annotation.attr == "Any"
        )
    return False


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for dirname in SCAN_DIRS:
        base = ROOT / dirname
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if any(part in SKIP_PARTS for part in path.parts):
                continue
            files.append(path)
    return sorted(files)


def _find_violations(path: Path) -> list[Violation]:
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"Failed reading {path}: {exc}") from exc

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        raise RuntimeError(f"Failed parsing {path}: {exc}") from exc

    violations: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.AnnAssign):
            continue
        if node.value is None or not _is_explicit_any(node.annotation):
            continue
        if isinstance(node.target, ast.Name):
            name = node.target.id
        else:
            name = ast.unparse(node.target)
        violations.append(Violation(path=path, line=node.lineno, name=name))
    return violations


def main() -> int:
    violations: list[Violation] = []
    for path in _iter_python_files():
        violations.extend(_find_violations(path))

    if not violations:
        print("No explicit ': Any =' variable annotations found.")
        return 0

    print("Explicit ': Any =' variable annotations are not allowed:")
    for violation in violations:
        relative = violation.path.relative_to(ROOT)
        print(f" - {relative}:{violation.line} ({violation.name})")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
