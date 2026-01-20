import json
from pathlib import Path
import re
import sys


def read_pyproject_version(repo_root: Path) -> str:
    pyproject = repo_root / "pyproject.toml"
    if not pyproject.exists():
        raise FileNotFoundError("pyproject.toml not found")
    if sys.version_info < (3, 11):
        raise RuntimeError("Python 3.11+ is required to parse pyproject.toml")
    import tomllib

    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    version = data.get("project", {}).get("version")
    if not isinstance(version, str) or not version.strip():
        raise RuntimeError("pyproject.toml is missing project.version")
    return version.strip()


def read_package_json_version(path: Path) -> str | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    version = data.get("version")
    if isinstance(version, str) and version.strip():
        return version.strip()
    return None


def read_formula_version(path: Path) -> str | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    match = re.search(r'^\s*version\s+"([0-9]+\.[0-9]+\.[0-9]+)"', text, re.MULTILINE)
    if match:
        return match.group(1)
    match = re.search(r"todoist-assistant-v([0-9]+\.[0-9]+\.[0-9]+)", text)
    if match:
        return match.group(1)
    return None


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    version = read_pyproject_version(repo_root)

    mismatches: list[str] = []

    frontend_version = read_package_json_version(repo_root / "frontend" / "package.json")
    if frontend_version and frontend_version != version:
        mismatches.append(f"frontend/package.json version {frontend_version} != pyproject {version}")

    root_package_version = read_package_json_version(repo_root / "package.json")
    if root_package_version and root_package_version != version:
        mismatches.append(f"package.json version {root_package_version} != pyproject {version}")

    formula_version = read_formula_version(repo_root / "Formula" / "todoist-assistant.rb")
    if formula_version and formula_version != version:
        mismatches.append(f"Formula/todoist-assistant.rb version {formula_version} != pyproject {version}")

    if mismatches:
        print("Version mismatch detected:")
        for item in mismatches:
            print(f" - {item}")
        return 1

    print(f"Version check OK: {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
