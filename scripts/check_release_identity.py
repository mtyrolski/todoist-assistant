"""Block publication while release identity or known web debt remains unfinished."""

import ast
import re
import tomllib
from pathlib import Path

from scripts.check_architecture import check_tree

ROOT = Path(__file__).resolve().parents[1]
# SHA-256 of the literal GitHub 404 response, not a release archive.
NOT_FOUND_SHA256 = "d5558cd419c8d46bdc958064cb97f963d1ea793866414c025906ec15033512ed"


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
    formula = root / "Formula" / "todometry.rb"
    if formula.is_file():
        # Examine only the formula's own archive, not the resource checksums.
        definition = formula.read_text(encoding="utf-8").split("  resource ", 1)[0]
        matches = re.findall(r'^\s*sha256\s+"([0-9a-f]{64})"', definition, re.MULTILINE)
        if len(matches) != 1 or matches[0] == NOT_FOUND_SHA256:
            errors.append("Homebrew release archive needs its verified SHA-256")
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
