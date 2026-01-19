from __future__ import annotations

from pathlib import Path
import sys


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    pyproject = repo_root / "pyproject.toml"
    if not pyproject.exists():
        print("0.0.0")
        return 0

    if sys.version_info < (3, 11):
        print("0.0.0")
        return 0

    import tomllib

    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    version = data.get("project", {}).get("version")
    print(version or "0.0.0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
