"""Block publication while release identity or known web debt remains unfinished."""

import ast
import re
import tomllib
from pathlib import Path

from scripts.check_architecture import check_tree

ROOT = Path(__file__).resolve().parents[1]


def identity_errors(root: Path) -> list[str]:
    with (root / "pyproject.toml").open("rb") as stream:
        project = tomllib.load(stream)["project"]
    errors = []
    if project.get("name") != "todometry":
        errors.append("distribution must be todometry")
    if project.get("version") != "0.4.1":
        errors.append("release version must be 0.4.1")
    if not (root / "todometry" / "__init__.py").is_file():
        errors.append("todometry package is missing")
    entry = project.get("scripts", {}).get("todometry", "")
    if not entry.startswith("todometry."):
        errors.append("todometry entry point must use todometry")
    errors.extend(check_tree(root, strict=True))
    for namespace in ("todoist", "todometry"):
        web = root / namespace / "web"
        for path in sorted(web.rglob("*.py")):
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
