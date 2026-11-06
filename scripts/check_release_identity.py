"""Block publication while the promised distribution identity is unfinished."""

from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def identity_errors(root: Path) -> list[str]:
    with (root / "pyproject.toml").open("rb") as stream:
        project = tomllib.load(stream)["project"]
    errors = []
    if project.get("name") != "telemetry-for-todoist":
        errors.append("distribution must be telemetry-for-todoist")
    if project.get("version") != "0.4.1":
        errors.append("release version must be 0.4.1")
    if not (root / "todometry" / "__init__.py").is_file():
        errors.append("todometry package is missing")
    entry = project.get("scripts", {}).get("todoist-telemetry", "")
    if not entry.startswith("todometry."):
        errors.append("todoist-telemetry entry point must use todometry")
    return errors


def main() -> int:
    errors = identity_errors(ROOT)
    if errors:
        print("Release publication blocked:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(
        "Release identity check passed; verify migration and native artifacts separately."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
