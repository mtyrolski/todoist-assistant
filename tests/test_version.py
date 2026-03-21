from todoist import __version__
from todoist.version import get_version


def test_package_version_export_matches_helper() -> None:
    assert __version__ == "0.3.0"
    assert get_version() == __version__
