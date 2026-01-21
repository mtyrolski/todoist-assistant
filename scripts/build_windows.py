import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from urllib.request import urlopen
from xml.etree import ElementTree

SIGNING_CERT_ENV = "WINDOWS_SIGNING_CERTIFICATE"
SIGNING_PASSWORD_ENV = "WINDOWS_SIGNING_CERTIFICATE_PASSWORD"
SIGNING_TIMESTAMP_ENV = "WINDOWS_SIGNING_TIMESTAMP_URL"
SIGNTOOL_ENV = "WINDOWS_SIGNTOOL_PATH"


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
    shasums_url = f"https://nodejs.org/dist/v{node_version}/SHASUMS256.txt"

    if not node_zip.exists():
        print(f"Downloading Node.js {node_version}...")
        with urlopen(node_url) as response, node_zip.open("wb") as handle:
            handle.write(response.read())

    expected = _fetch_node_sha256(shasums_url, node_zip_name)
    _verify_sha256(node_zip, expected)

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


def _fetch_node_sha256(shasums_url: str, node_zip_name: str) -> str:
    with urlopen(shasums_url) as response:
        text = response.read().decode("utf-8")
    for line in text.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[1].endswith(node_zip_name):
            return parts[0]
    raise RuntimeError(f"Checksum for {node_zip_name} not found in SHASUMS256.txt")


def _verify_sha256(path: Path, expected: str) -> None:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual.lower() != expected.lower():
        raise RuntimeError(f"Checksum mismatch for {path.name}: expected {expected}, got {actual}")


def _stage_node_runtime(app_root: Path, node_version: str) -> None:
    node_target = app_root / "node"
    node_exe = shutil.which("node")
    if node_exe:
        dest_name = "node.exe" if os.name == "nt" else "node"
        print(f"Bundling Node runtime from {node_exe}")
        _copy_file(Path(node_exe), node_target / dest_name)
        return

    _download_node(Path(app_root).parent, node_version, target_dir=node_target)


def _find_wix_tool(tool: str) -> str:
    candidates: list[Path] = []
    wix_bin = os.getenv("WIX_BIN")
    if wix_bin:
        candidates.append(Path(wix_bin))
    wix_root = os.getenv("WIX")
    if wix_root:
        candidates.append(Path(wix_root) / "bin")

    for base in (Path(r"C:\\Program Files (x86)"), Path(r"C:\\Program Files")):
        for wix_dir in sorted(base.glob("WiX Toolset v3.*")):
            candidates.append(wix_dir / "bin")

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


def _find_signtool() -> str:
    candidate = os.getenv(SIGNTOOL_ENV)
    if candidate:
        path = Path(candidate)
        if path.exists():
            return str(path)
        raise RuntimeError(f"{SIGNTOOL_ENV} is set but {path} does not exist.")

    for exe_name in ("signtool.exe", "signtool"):
        resolved = shutil.which(exe_name)
        if resolved:
            return resolved

    raise RuntimeError(
        "signtool.exe not found. Install the Windows SDK (signtool) and add it to PATH, or set "
        f"{SIGNTOOL_ENV} to the explicit path."
    )


def _require_command(name: str, hint: str | None = None) -> str:
    resolved = shutil.which(name)
    if resolved:
        return resolved
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


def _resolve_signing_config() -> tuple[Path, str, str] | None:
    cert_path_str = os.getenv(SIGNING_CERT_ENV)
    cert_password = os.getenv(SIGNING_PASSWORD_ENV)
    if not cert_path_str or not cert_password:
        return None

    cert_path = Path(cert_path_str)
    if not cert_path.exists():
        raise RuntimeError(f"Signing certificate not found: {cert_path}")

    timestamp_url = os.getenv(SIGNING_TIMESTAMP_ENV, "http://timestamp.digicert.com")
    return cert_path, cert_password, timestamp_url


def _sign_with_signtool(
    signtool: str,
    target: Path,
    cert_path: Path,
    cert_password: str,
    timestamp_url: str,
) -> None:
    print(f"Signing {target.name} with signtool...")
    _run(
        [
            signtool,
            "sign",
            "/fd",
            "SHA256",
            "/td",
            "SHA256",
            "/tr",
            timestamp_url,
            "/f",
            str(cert_path),
            "/p",
            cert_password,
            "/a",
            "/as",
            str(target),
        ]
    )


def _python_has_module(python_path: Path, module: str) -> bool:
    if not python_path.exists():
        return False
    probe = (
        "import importlib.util, sys;"
        f"sys.exit(0 if importlib.util.find_spec('{module}') else 1)"
    )
    try:
        result = subprocess.run([str(python_path), "-c", probe], capture_output=True)
    except FileNotFoundError:
        return False
    return result.returncode == 0


def _resolve_pyinstaller_python(repo_root: Path) -> str:
    candidates: list[Path] = []
    venv = os.getenv("VIRTUAL_ENV")
    if venv:
        candidates.append(Path(venv) / "Scripts" / "python.exe")
    candidates.append(repo_root / ".venv" / "Scripts" / "python.exe")
    candidates.append(Path(sys.executable))

    for candidate in candidates:
        if _python_has_module(candidate, "PyInstaller"):
            return str(candidate)

    raise RuntimeError(
        "PyInstaller is not available in the active environment. "
        "Run `uv sync --group build` and invoke the build with `uv run python -m scripts.build_windows` "
        "(or ensure the uv venv is active)."
    )


def _build_dashboard(frontend_dir: Path, *, npm_path: str) -> None:
    if not frontend_dir.exists():
        raise RuntimeError(f"Dashboard directory not found: {frontend_dir}")

    env = os.environ.copy()
    env["NEXT_TELEMETRY_DISABLED"] = "1"

    _run([npm_path, "ci"], cwd=frontend_dir, env=env)
    _run([npm_path, "run", "build"], cwd=frontend_dir, env=env)


def _stage_dashboard(frontend_dir: Path, target_dir: Path) -> None:
    standalone_dir = frontend_dir / ".next" / "standalone"
    static_dir = frontend_dir / ".next" / "static"
    public_dir = frontend_dir / "public"

    if not standalone_dir.exists():
        raise RuntimeError("Next.js standalone output not found. Ensure next.config.js sets output=standalone.")

    target_dir.mkdir(parents=True, exist_ok=True)
    frontend_target = target_dir
    _copy_tree_merge(standalone_dir, frontend_target)

    nested_dir = frontend_target / frontend_dir.name
    server_js = frontend_target / "server.js"
    if not server_js.exists() and (nested_dir / "server.js").exists():
        for item in nested_dir.iterdir():
            dest = frontend_target / item.name
            if dest.exists():
                if item.is_dir():
                    _copy_tree_merge(item, dest)
                else:
                    _copy_file(item, dest)
            else:
                shutil.move(str(item), str(dest))
        shutil.rmtree(nested_dir)

    if static_dir.exists():
        _copy_tree_merge(static_dir, frontend_target / ".next" / "static")
    if public_dir.exists():
        _copy_tree_merge(public_dir, frontend_target / "public")

    if not server_js.exists():
        raise RuntimeError("Next.js standalone server.js missing from packaged frontend.")


def _zip_frontend(frontend_root: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in frontend_root.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(frontend_root))


def _force_win64_components(wxs_path: Path) -> None:
    tree = ElementTree.parse(wxs_path)
    root = tree.getroot()
    ns = {"wix": "http://schemas.microsoft.com/wix/2006/wi"}
    updated = False
    for component in root.findall(".//wix:Component", ns):
        if component.get("Win64") != "yes":
            component.set("Win64", "yes")
            updated = True
    if updated:
        tree.write(wxs_path, encoding="utf-8", xml_declaration=True)


def _check_install_path_lengths(app_root: Path, install_root: Path) -> None:
    max_len = 0
    max_path: Path | None = None
    for path in app_root.rglob("*"):
        if not path.is_file():
            continue
        rel_path = path.relative_to(app_root)
        abs_len = len(str(install_root / rel_path))
        if abs_len > max_len:
            max_len = abs_len
            max_path = rel_path
    if max_len >= 240 and max_path is not None:
        raise RuntimeError(
            f"Installer payload path length {max_len} exceeds safe limit for Windows: {max_path}"
        )


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
        frontend_stage = app_root / "_frontend"
        _stage_dashboard(frontend_dir, frontend_stage)
        _stage_node_runtime(app_root, node_version)
        _zip_frontend(frontend_stage, app_root / "frontend.zip")
        shutil.rmtree(frontend_stage)
        if (app_root / "_frontend").exists() or (app_root / "frontend").exists():
            raise RuntimeError("Frontend staging left an unpacked directory; aborting MSI build.")
        if not (app_root / "frontend.zip").exists():
            raise RuntimeError("frontend.zip missing after staging dashboard.")
        node_exe = app_root / "node" / ("node.exe" if os.name == "nt" else "node")
        if not node_exe.exists():
            raise RuntimeError("Bundled Node runtime missing; expected node executable under app_root/node.")


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
            "-sreg",
            "-out",
            str(app_wxs),
        ]
    )
    _force_win64_components(app_wxs)
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
            "-gg",
            "-srd",
            "-sfrag",
            "-sreg",
            "-out",
            str(config_wxs),
        ]
    )
    _force_win64_components(config_wxs)

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
            "-arch",
            "x64",
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

    signing_config = _resolve_signing_config()
    signtool_path: str | None = None
    if signing_config:
        signtool_path = _find_signtool()
        print("Code signing enabled for MSI build.")

    dist_root = repo_root / "dist" / "windows"
    if dist_root.exists():
        shutil.rmtree(dist_root)
    dist_root.mkdir(parents=True, exist_ok=True)

    build_root = dist_root / "build"
    build_root.mkdir(parents=True, exist_ok=True)

    include_dashboard = (not args.no_dashboard) and (repo_root / "frontend").exists()
    wix_tools = _resolve_wix_tools()

    if include_dashboard:
        _require_command("node", "Install Node.js 20+ (includes npm), or pass --no-dashboard.")
        npm_path = _require_command("npm", "Install Node.js 20+ (includes npm), or pass --no-dashboard.")
        print("Building dashboard...")
        _build_dashboard(repo_root / "frontend", npm_path=npm_path)
    elif not args.no_dashboard:
        print("Dashboard directory not found; skipping frontend packaging.")

    spec_path = repo_root / "packaging" / "pyinstaller" / "todoist_assistant.spec"
    if not spec_path.exists():
        raise RuntimeError(f"PyInstaller spec file not found: {spec_path}")

    pyinstaller_dist = dist_root / "pyinstaller"
    pyinstaller_work = build_root / "pyinstaller"
    pyinstaller_dist.mkdir(parents=True, exist_ok=True)
    pyinstaller_work.mkdir(parents=True, exist_ok=True)

    pyinstaller_python = _resolve_pyinstaller_python(repo_root)
    print(f"Running PyInstaller with {pyinstaller_python}...")
    _run(
        [
            pyinstaller_python,
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

    if signtool_path and signing_config:
        cert_path, cert_password, timestamp_url = signing_config
        payload_exe = app_root / "todoist-assistant.exe"
        if not payload_exe.exists():
            raise RuntimeError(f"Expected PyInstaller executable not found for signing: {payload_exe}")
        _sign_with_signtool(signtool_path, payload_exe, cert_path, cert_password, timestamp_url)

    print("Staging runtime assets...")
    _stage_assets(
        repo_root,
        app_root,
        dist_root / "config",
        include_dashboard=include_dashboard,
        node_version=args.node_version,
    )
    _check_install_path_lengths(app_root, Path(r"C:\Program Files\TodoistAssistant"))

    print("Building MSI...")
    msi_path = _build_msi(repo_root, dist_root, app_root, dist_root / "config", msi_version, wix_tools)
    if signtool_path and signing_config:
        cert_path, cert_password, timestamp_url = signing_config
        _sign_with_signtool(signtool_path, msi_path, cert_path, cert_password, timestamp_url)
    print(f"MSI created: {msi_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
