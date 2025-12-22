from __future__ import annotations

from importlib import metadata
from pathlib import Path


def get_version() -> str:
    try:
        return metadata.version("todoist-assistant")
    except metadata.PackageNotFoundError:
        pass

    # Fallback to reading the local pyproject when running from a repo checkout.
    try:
        import tomllib  # py311+

        repo_root = Path(__file__).resolve().parents[1]
        pyproject = repo_root / "pyproject.toml"
        if pyproject.exists():
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            version = data.get("project", {}).get("version")
            if isinstance(version, str) and version:
                return version
    except Exception:
        pass

    return "0.0.0"
