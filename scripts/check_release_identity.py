"""Block publication while release identity or known web debt remains unfinished."""

import ast
import re
import tomllib
from pathlib import Path

from scripts.check_architecture import inspect_python

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
    for namespace in ("todoist", "todometry"):
        web = root / namespace / "web"
        for path in sorted(web.rglob("*.py")):
            if any(inspect_python(path).values()):
                errors.append(
                    f"runtime namespace injection remains in {path.relative_to(root)}"
                )
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.lstrip().startswith("#") and (
                    re.search(
                        r"pyright:.*report(?:UndefinedVariable|UnboundVariable|PossiblyUnboundVariable)\s*=\s*false",
                        line,
                        re.IGNORECASE,
                    )
                    or re.search(
                        r"pylint:\s*disable\s*=.*(?:undefined-variable|global-variable-undefined|used-before-assignment)",
                        line,
                    )
                ):
                    errors.append(
                        f"undefined-name suppression remains in {path.relative_to(root)}"
                    )
                    break
        stub = web / "api.pyi"
        if stub.is_file() and any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "__getattr__"
            for node in ast.walk(ast.parse(stub.read_text(encoding="utf-8")))
        ):
            errors.append(f"catch-all API stub remains in {stub.relative_to(root)}")
    with (root / "pyproject.toml").open("rb") as stream:
        config = tomllib.load(stream)
    ruff = config.get("tool", {}).get("ruff", {})
    for section in (ruff, ruff.get("lint", {})):
        for key in ("ignore", "extend-ignore"):
            if {"F", "F821", "ALL"}.intersection(section.get(key, [])):
                errors.append("global Ruff undefined-name exemption remains")
        for key in ("per-file-ignores", "extend-per-file-ignores"):
            for pattern, rules in section.get(key, {}).items():
                if ("web" in pattern or pattern in ("*", "**/*.py")) and {
                    "F",
                    "F821",
                    "ALL",
                }.intersection(rules):
                    errors.append(
                        f"web Ruff undefined-name exemption remains: {pattern}"
                    )
    return errors


def main() -> int:
    errors = identity_errors(ROOT)
    if errors:
        print("Release publication blocked:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(
        "Release identity and web debt checks passed; verify product, migration and native artifacts separately."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
