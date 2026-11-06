from todoist import __version__
from todoist.core.version import get_version


def test_package_version_export_matches_helper() -> None:
    assert __version__ == "0.4.1"
    assert get_version() == __version__


def test_version_falls_back_to_checkout_metadata(monkeypatch) -> None:
    from importlib.metadata import PackageNotFoundError
    from todoist.core import version

    def unavailable(_distribution):
        raise PackageNotFoundError

    monkeypatch.setattr(version.metadata, "version", unavailable)
    assert version.get_version() == "0.4.1"
