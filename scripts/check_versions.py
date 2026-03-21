import json
from pathlib import Path
import sys


def read_pyproject_version(path: Path) -> str | None:
    if not path.exists():
        return None
    if sys.version_info < (3, 11):
        raise RuntimeError("Python 3.11+ is required to parse pyproject.toml")
    import tomllib

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    version = data.get("project", {}).get("version")
    if isinstance(version, str) and version.strip():
        return version.strip()
    return None


def read_package_json_version(path: Path) -> str | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    version = data.get("version")
    if isinstance(version, str) and version.strip():
        return version.strip()
    return None


def read_package_lock_versions(path: Path) -> tuple[str | None, str | None]:
    if not path.exists():
        return None, None
    data = json.loads(path.read_text(encoding="utf-8"))
    top_level = data.get("version")
    if not isinstance(top_level, str) or not top_level.strip():
        top_level = None
    else:
        top_level = top_level.strip()

    packages = data.get("packages")
    root_package_version: str | None = None
    if isinstance(packages, dict):
        root_package = packages.get("")
        if isinstance(root_package, dict):
            version = root_package.get("version")
            if isinstance(version, str) and version.strip():
                root_package_version = version.strip()

    return top_level, root_package_version


def read_uv_lock_version(path: Path) -> str | None:
    if not path.exists():
        return None
    if sys.version_info < (3, 11):
        raise RuntimeError("Python 3.11+ is required to parse uv.lock")
    import tomllib

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    for package in data.get("package", []):
        if isinstance(package, dict) and package.get("name") == "todoist-assistant":
            version = package.get("version")
            if isinstance(version, str) and version.strip():
                return version.strip()
            return None
    return None


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    root_pyproject = repo_root / "pyproject.toml"
    version = read_pyproject_version(root_pyproject)
    if version is None:
        raise RuntimeError("pyproject.toml is missing project.version")

    mismatches: list[str] = []

    core_pyproject = repo_root / "core" / "pyproject.toml"
    core_version = read_pyproject_version(core_pyproject)
    if core_pyproject.exists() and core_version is None:
        mismatches.append("core/pyproject.toml is missing project.version")
    elif core_version and core_version != version:
        mismatches.append(f"core/pyproject.toml version {core_version} != pyproject {version}")

    frontend_package = repo_root / "frontend" / "package.json"
    frontend_version = read_package_json_version(frontend_package)
    if frontend_package.exists() and frontend_version is None:
        mismatches.append("frontend/package.json is missing version")
    elif frontend_version and frontend_version != version:
        mismatches.append(f"frontend/package.json version {frontend_version} != pyproject {version}")

    frontend_lock = repo_root / "frontend" / "package-lock.json"
    lock_version, lock_package_version = read_package_lock_versions(
        frontend_lock
    )
    if frontend_lock.exists() and lock_version is None:
        mismatches.append("frontend/package-lock.json is missing top-level version")
    elif lock_version and lock_version != version:
        mismatches.append(f"frontend/package-lock.json version {lock_version} != pyproject {version}")
    if frontend_lock.exists() and lock_package_version is None:
        mismatches.append("frontend/package-lock.json is missing packages[''].version")
    elif lock_package_version and lock_package_version != version:
        mismatches.append(
            f"frontend/package-lock.json packages[''].version {lock_package_version} != pyproject {version}"
        )

    uv_lock = repo_root / "uv.lock"
    uv_lock_version = read_uv_lock_version(uv_lock)
    if uv_lock.exists() and uv_lock_version is None:
        mismatches.append("uv.lock is missing todoist-assistant version")
    elif uv_lock_version and uv_lock_version != version:
        mismatches.append(f"uv.lock todoist-assistant version {uv_lock_version} != pyproject {version}")

    if mismatches:
        print("Version mismatch detected:")
        for item in mismatches:
            print(f" - {item}")
        return 1

    print(f"Version check OK: {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
