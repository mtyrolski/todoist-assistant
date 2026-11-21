from typer.testing import CliRunner

from todometry.cli import app
from todometry.core.version import get_version


def test_version_option_works_without_a_command():
    result = CliRunner().invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == get_version()
