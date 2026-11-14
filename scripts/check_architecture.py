"""Report source size and prevent growth of known web architecture debt."""

import ast
import tokenize
import tomllib
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Temporary ceilings for code that predates this check. Reduce these as it is removed;
# do not move or increase them to accommodate new injection.
LEGACY = {
    "todometry/web/api.py": {"sync": 1, "globals_subscript": 1},
    "todometry/web/api_components/dashboard_runtime.py": {
        "sync": 1,
        "globals_subscript": 4,
        "api_namespace": 1,
    },
    "todometry/web/routes/admin_settings.py": {"sync": 2},
    "todometry/web/routes/common.py": {"sync": 1, "api_namespace": 1},
    "todometry/web/routes/dashboard.py": {"sync": 6},
}
LEGACY_F821_PATHS = {
    "todometry/web/api_components/*.py",
    "todometry/web/routes/*.py",
}


def _globals_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "globals"
        and not node.args
        and not node.keywords
    )


def inspect_python(path: Path) -> Counter[str]:
    """Count the specific legacy injection mechanisms, ignoring comments and strings."""
    with path.open("rb") as stream:
        counts = Counter(
            {
                "sync": sum(
                    t.type == tokenize.NAME and t.string == "_sync_api_globals"
                    for t in tokenize.tokenize(stream.readline)
                )
            }
        )
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    aliases = {"web_api"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in {
            "todoist.web",
            "todometry.web",
        }:
            aliases.update(a.asname or a.name for a in node.names if a.name == "api")
        if isinstance(node, ast.Import):
            aliases.update(
                a.asname or a.name
                for a in node.names
                if a.name in {"todoist.web.api", "todometry.web.api"}
            )

    def api_module(node: ast.AST) -> bool:
        return (
            isinstance(node, (ast.Name, ast.Attribute)) and ast.unparse(node) in aliases
        )

    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and _globals_call(node.value):
            counts["globals_subscript"] += 1
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "update"
            and _globals_call(node.func.value)
        ):
            counts["globals_update"] += 1
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "vars"
            and len(node.args) == 1
            and api_module(node.args[0])
        ):
            counts["api_namespace"] += 1
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "__dict__"
            and api_module(node.value)
        ):
            counts["api_namespace"] += 1
    return counts


def check_ruff(config: dict, *, strict: bool = False) -> list[str]:
    ruff = config.get("tool", {}).get("ruff", {})
    errors = []
    forbidden = {"F", "F821", "ALL"}
    # Ruff also accepts these keys in its older [tool.ruff] layout.
    for section_name, section in (("ruff", ruff), ("ruff.lint", ruff.get("lint", {}))):
        for key in ("ignore", "extend-ignore"):
            if forbidden.intersection(section.get(key, [])):
                errors.append(f"global {section_name}.{key} suppresses undefined names")
        for key in ("per-file-ignores", "extend-per-file-ignores"):
            for pattern, rules in section.get(key, {}).items():
                for rule in forbidden.intersection(rules):
                    if (
                        strict
                        or section_name != "ruff.lint"
                        or key != "per-file-ignores"
                        or pattern not in LEGACY_F821_PATHS
                        or rule != "F821"
                    ):
                        errors.append(
                            f"new Ruff undefined-name exemption: {pattern}: {rule}"
                        )
    return errors


def check_tree(root: Path, *, strict: bool = False) -> list[str]:
    errors = []
    paths = [
        path
        for namespace in ("todoist", "todometry")
        for path in (root / namespace / "web").rglob("*.py")
    ]
    for path in sorted(paths):
        relative = path.relative_to(root).as_posix()
        for kind, count in inspect_python(path).items():
            allowed = 0 if strict else LEGACY.get(relative, {}).get(kind, 0)
            if count > allowed:
                errors.append(
                    f"runtime namespace injection in {relative}: {kind}: {count} occurrences, allowed {allowed}"
                )
    with (root / "pyproject.toml").open("rb") as stream:
        errors.extend(check_ruff(tomllib.load(stream), strict=strict))
    return errors


def report_size(root: Path) -> None:
    groups = {
        "python": (root / "todometry", {".py"}),
        "frontend": (root / "frontend" / "app", {".ts", ".tsx", ".css"}),
        "android": (root / "android" / "app" / "src" / "main", {".kt", ".java"}),
    }
    total_files = total_lines = 0
    for name, (directory, extensions) in groups.items():
        files = [
            p for p in directory.rglob("*") if p.is_file() and p.suffix in extensions
        ]
        lines = sum(len(p.read_text(encoding="utf-8").splitlines()) for p in files)
        total_files += len(files)
        total_lines += lines
        print(f"{name}: {len(files)} files, {lines} lines")
    with (root / "pyproject.toml").open("rb") as stream:
        dependencies = tomllib.load(stream)["project"]["dependencies"]
    print(
        f"total: {total_files} files, {total_lines} lines; {len(dependencies)} direct runtime dependencies"
    )


def main() -> int:
    report_size(ROOT)
    errors = check_tree(ROOT)
    if errors:
        print("Architecture check failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Architecture check passed (existing injection debt is baselined).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
