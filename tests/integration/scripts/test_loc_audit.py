from pathlib import Path

from scripts import loc_audit


def _write(path: Path, lines: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x\n" * lines, encoding="utf-8")


def test_audit_paths_counts_selected_tracked_source(tmp_path: Path) -> None:
    _write(tmp_path / "todoist" / "app.py", 3)
    _write(tmp_path / "frontend" / "app.tsx", 5)
    _write(tmp_path / "README.md", 2)
    _write(tmp_path / "uv.lock", 100)
    _write(tmp_path / ".venv" / "ignored.py", 100)
    _write(tmp_path / "frontend" / "node_modules" / "ignored.ts", 100)

    audit = loc_audit.audit_paths(
        tmp_path,
        [
            Path("todoist/app.py"),
            Path("frontend/app.tsx"),
            Path("README.md"),
            Path("uv.lock"),
            Path(".venv/ignored.py"),
            Path("frontend/node_modules/ignored.ts"),
        ],
    )

    assert audit.python_lines == 3
    assert audit.source_lines == 10
    assert audit.total_files == 3
    assert [(item.extension, item.files, item.lines) for item in audit.by_extension] == [
        (".tsx", 1, 5),
        (".py", 1, 3),
        (".md", 1, 2),
    ]


def test_is_counted_path_accepts_extensions_without_leading_dot() -> None:
    assert loc_audit.is_counted_path(Path("scripts/tool.py"), extensions=("py",))
    assert not loc_audit.is_counted_path(Path("uv.lock"), extensions=("lock",))
