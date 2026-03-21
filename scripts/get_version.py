from pathlib import Path
import sys

try:
    from todoist.version import get_version as _get_version
except ModuleNotFoundError:
    _get_version = None


def _read_pyproject_version(pyproject: Path) -> str:
    if not pyproject.exists():
        return "0.0.0"
    if sys.version_info < (3, 11):
        return "0.0.0"

    import tomllib

    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    version = data.get("project", {}).get("version")
    return version or "0.0.0"


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    if _get_version is not None:
        print(_get_version())
        return 0

    print(_read_pyproject_version(repo_root / "pyproject.toml"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
