from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from urllib.request import urlopen


def _run(cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    try:
        result = subprocess.run(cmd, cwd=cwd, env=env)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Command not found: {cmd[0]}") from exc
    if result.returncode != 0:
        joined = subprocess.list2cmdline(cmd)
        raise RuntimeError(f"Command failed ({result.returncode}): {joined}")


def _read_version(repo_root: Path) -> tuple[str, str]:
    pyproject = repo_root / "pyproject.toml"
    if pyproject.exists():
        try:
            import tomllib
        except ModuleNotFoundError as exc:
            raise RuntimeError("Python 3.11+ is required to parse pyproject.toml") from exc
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        version = data.get("project", {}).get("version")
        if isinstance(version, str) and version.strip():
            return version.strip(), "pyproject.toml"

    package_json = repo_root / "package.json"
    frontend_pkg = repo_root / "frontend" / "package.json"
    for pkg in (package_json, frontend_pkg):
        if pkg.exists():
            payload = json.loads(pkg.read_text(encoding="utf-8"))
            version = payload.get("version")
            if isinstance(version, str) and version.strip():
                return version.strip(), str(pkg.relative_to(repo_root))

    raise RuntimeError("Unable to determine version from pyproject.toml or package.json")


def _normalize_msi_version(version: str) -> str:
    parts = re.findall(r"\d+", version)
    if not parts:
        raise RuntimeError(f"Invalid version string: {version}")
    while len(parts) < 3:
        parts.append("0")
    return ".".join(parts[:3])


def _copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def _copy_tree_merge(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, dirs_exist_ok=True)


def _download_node(dist_root: Path, node_version: str, *, target_dir: Path) -> None:
    node_zip_name = f"node-v{node_version}-win-x64.zip"
    node_zip = dist_root / node_zip_name
    node_url = f"https://nodejs.org/dist/v{node_version}/{node_zip_name}"

    if not node_zip.exists():
        print(f"Downloading Node.js {node_version}...")
        with urlopen(node_url) as response, node_zip.open("wb") as handle:
            handle.write(response.read())

    extract_dir = dist_root / f"node-v{node_version}-win-x64"
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    with zipfile.ZipFile(node_zip, "r") as archive:
        archive.extractall(dist_root)

    if not extract_dir.exists():
        raise RuntimeError("Failed to extract Node.js archive")

    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(extract_dir, target_dir)


def _find_wix_tool(tool: str) -> str:
    candidates: list[Path] = []
    wix_bin = os.getenv("WIX_BIN")
    if wix_bin:
        candidates.append(Path(wix_bin))
    wix_root = os.getenv("WIX")
    if wix_root:
        candidates.append(Path(wix_root) / "bin")

    for base in (
        Path(r"C:\\Program Files (x86)\\WiX Toolset v3.11\\bin"),
        Path(r"C:\\Program Files\\WiX Toolset v3.11\\bin"),
    ):
        candidates.append(base)

    for base in candidates:
        candidate = base / tool
        if candidate.exists():
            return str(candidate)

    which = shutil.which(tool)
    if which:
        return which

    raise RuntimeError(
        "WiX Toolset not found. Install WiX v3.11+ and ensure candle.exe, light.exe, and heat.exe are on PATH."
    )


def _require_command(name: str, hint: str | None = None) -> None:
    if shutil.which(name) is None:
        message = f"Required command not found: {name}"
        if hint:
            message = f"{message}. {hint}"
        raise RuntimeError(message)


def _resolve_wix_tools() -> dict[str, str]:
    return {
        "heat": _find_wix_tool("heat.exe"),
        "candle": _find_wix_tool("candle.exe"),
        "light": _find_wix_tool("light.exe"),
    }


def _build_dashboard(frontend_dir: Path) -> None:
    if not frontend_dir.exists():
        raise RuntimeError(f"Dashboard directory not found: {frontend_dir}")

    env = os.environ.copy()
    env["NEXT_TELEMETRY_DISABLED"] = "1"

    _run(["npm", "ci"], cwd=frontend_dir, env=env)
    _run(["npm", "run", "build"], cwd=frontend_dir, env=env)


def _stage_dashboard(frontend_dir: Path, app_root: Path) -> None:
    standalone_dir = frontend_dir / ".next" / "standalone"
    static_dir = frontend_dir / ".next" / "static"
    public_dir = frontend_dir / "public"

    if not standalone_dir.exists():
        raise RuntimeError("Next.js standalone output not found. Ensure next.config.js sets output=standalone.")

    frontend_target = app_root / "frontend"
    _copy_tree(standalone_dir, frontend_target)

    if static_dir.exists():
        _copy_tree_merge(static_dir, frontend_target / ".next" / "static")
    if public_dir.exists():
        _copy_tree_merge(public_dir, frontend_target / "public")

    server_js = frontend_target / "server.js"
    if not server_js.exists():
        raise RuntimeError("Next.js standalone server.js missing from packaged frontend.")


def _stage_assets(repo_root: Path, app_root: Path, config_stage: Path, *, include_dashboard: bool, node_version: str) -> None:
    configs_src = repo_root / "configs"
    if not configs_src.exists():
        raise RuntimeError("configs/ directory not found; required for runtime config")

    env_template_src = repo_root / ".env.example"
    if not env_template_src.exists():
        raise RuntimeError(".env.example not found; required to create .env.template")

    readme_src = repo_root / "README.md"
    if not readme_src.exists():
        raise RuntimeError("README.md not found; required asset")

    config_stage.mkdir(parents=True, exist_ok=True)
    _copy_tree_merge(configs_src, config_stage)
    _copy_file(env_template_src, config_stage / ".env.template")

    _copy_file(env_template_src, app_root / ".env.template")
    _copy_file(readme_src, app_root / "README.md")

    pyproject = repo_root / "pyproject.toml"
    if pyproject.exists():
        _copy_file(pyproject, app_root / "pyproject.toml")

    img_src = repo_root / "img"
    if img_src.exists():
        _copy_tree(img_src, app_root / "img")

    if include_dashboard:
        frontend_dir = repo_root / "frontend"
        _stage_dashboard(frontend_dir, app_root)
        _download_node(Path(app_root).parent, node_version, target_dir=app_root / "node")


def _build_msi(
    repo_root: Path,
    dist_root: Path,
    app_root: Path,
    config_stage: Path,
    msi_version: str,
    wix_tools: dict[str, str],
) -> Path:
    wixobj_dir = dist_root / "wixobj"
    wixobj_dir.mkdir(parents=True, exist_ok=True)

    heat = wix_tools["heat"]
    candle = wix_tools["candle"]
    light = wix_tools["light"]

    app_wxs = dist_root / "app_files.wxs"
    config_wxs = dist_root / "config_files.wxs"

    _run(
        [
            heat,
            "dir",
            str(app_root),
            "-cg",
            "AppFiles",
            "-dr",
            "INSTALLFOLDER",
            "-var",
            "var.AppSource",
            "-ag",
            "-srd",
            "-sfrag",
            "-out",
            str(app_wxs),
        ]
    )
    _run(
        [
            heat,
            "dir",
            str(config_stage),
            "-cg",
            "ConfigFiles",
            "-dr",
            "CONFIGDIR",
            "-var",
            "var.ConfigSource",
            "-ag",
            "-srd",
            "-sfrag",
            "-out",
            str(config_wxs),
        ]
    )

    installer_dir = repo_root / "windows" / "installer"
    product_wxs = installer_dir / "product.wxs"
    components_wxs = installer_dir / "components.wxs"
    ui_wxs = installer_dir / "ui.wxs"
    missing = [path for path in (product_wxs, components_wxs, ui_wxs) if not path.exists()]
    if missing:
        missing_str = ", ".join(str(path) for path in missing)
        raise RuntimeError(f"WiX installer files missing: {missing_str}")

    wix_out_dir = str(wixobj_dir) + os.sep
    _run(
        [
            candle,
            "-nologo",
            "-ext",
            "WixUtilExtension",
            "-ext",
            "WixUIExtension",
            f"-dProductVersion={msi_version}",
            f"-dAppSource={app_root}",
            f"-dConfigSource={config_stage}",
            "-out",
            wix_out_dir,
            str(product_wxs),
            str(components_wxs),
            str(ui_wxs),
            str(app_wxs),
            str(config_wxs),
        ]
    )

    wixobjs = sorted(str(path) for path in wixobj_dir.glob("*.wixobj"))
    if not wixobjs:
        raise RuntimeError("No WiX object files generated; candle.exe did not produce outputs")

    msi_path = dist_root / f"todoist-assistant-{msi_version}.msi"
    _run(
        [
            light,
            "-nologo",
            "-ext",
            "WixUtilExtension",
            "-ext",
            "WixUIExtension",
            "-out",
            str(msi_path),
            *wixobjs,
        ]
    )

    return msi_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Todoist Assistant Windows MSI installer.")
    parser.add_argument("--no-dashboard", action="store_true", help="Skip building/packaging the dashboard frontend.")
    parser.add_argument("--node-version", default="20.11.1", help="Node.js version to bundle for the dashboard.")
    args = parser.parse_args()

    if os.name != "nt":
        raise RuntimeError("This build script must be run on Windows.")

    repo_root = Path(__file__).resolve().parents[1]
    version, source = _read_version(repo_root)
    msi_version = _normalize_msi_version(version)
    print(f"Using version {version} (MSI {msi_version}) from {source}")

    dist_root = repo_root / "dist" / "windows"
    if dist_root.exists():
        shutil.rmtree(dist_root)
    dist_root.mkdir(parents=True, exist_ok=True)

    build_root = dist_root / "build"
    build_root.mkdir(parents=True, exist_ok=True)

    include_dashboard = (not args.no_dashboard) and (repo_root / "frontend").exists()
    wix_tools = _resolve_wix_tools()

    if include_dashboard:
        _require_command("node", "Install Node.js 20+ (includes npm).")
        _require_command("npm", "Install Node.js 20+ (includes npm).")
    if include_dashboard:
        print("Building dashboard...")
        _build_dashboard(repo_root / "frontend")
    elif not args.no_dashboard:
        print("Dashboard directory not found; skipping frontend packaging.")

    spec_path = repo_root / "packaging" / "pyinstaller" / "todoist_assistant.spec"
    if not spec_path.exists():
        raise RuntimeError(f"PyInstaller spec file not found: {spec_path}")

    pyinstaller_dist = dist_root / "pyinstaller"
    pyinstaller_work = build_root / "pyinstaller"
    pyinstaller_dist.mkdir(parents=True, exist_ok=True)
    pyinstaller_work.mkdir(parents=True, exist_ok=True)

    print("Running PyInstaller...")
    _run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--distpath",
            str(pyinstaller_dist),
            "--workpath",
            str(pyinstaller_work),
            str(spec_path),
        ],
        cwd=repo_root,
    )

    app_root = pyinstaller_dist / "todoist-assistant"
    if not app_root.exists():
        raise RuntimeError("PyInstaller output not found; expected onedir build under dist/windows/pyinstaller")

    print("Staging runtime assets...")
    _stage_assets(
        repo_root,
        app_root,
        dist_root / "config",
        include_dashboard=include_dashboard,
        node_version=args.node_version,
    )

    print("Building MSI...")
    msi_path = _build_msi(repo_root, dist_root, app_root, dist_root / "config", msi_version, wix_tools)
    print(f"MSI created: {msi_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
