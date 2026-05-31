from pathlib import Path

from scripts import check_versions


def test_read_formula_version_extracts_version(tmp_path: Path) -> None:
    formula = tmp_path / "todoist-assistant.rb"
    formula.write_text(
        "\n".join(
            [
                'class TodoistAssistant < Formula',
                '  version "0.3.3"',
                "end",
            ]
        ),
        encoding="utf-8",
    )

    assert check_versions.read_formula_version(formula) == "0.3.3"


def test_read_formula_version_returns_none_when_missing(tmp_path: Path) -> None:
    formula = tmp_path / "todoist-assistant.rb"
    formula.write_text("class TodoistAssistant < Formula\nend\n", encoding="utf-8")

    assert check_versions.read_formula_version(formula) is None
