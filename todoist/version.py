
from contextlib import suppress
from importlib import metadata
from pathlib import Path


def get_version() -> str:
    with suppress(metadata.PackageNotFoundError):
        return metadata.version("todoist-assistant")

    # Fallback to reading the local pyproject when running from a repo checkout.
    with suppress(Exception):
        import tomllib  # py311+

        repo_root = Path(__file__).resolve().parents[1]
        pyproject = repo_root / "pyproject.toml"
        if pyproject.exists():
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            version = data.get("project", {}).get("version")
            if isinstance(version, str) and version:
                return version

    return "0.0.0"
