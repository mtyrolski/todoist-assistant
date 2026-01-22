"""Local launcher for the Todoist Assistant dashboard stack."""

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import time
import traceback
import webbrowser
import zipfile

import uvicorn

from todoist import telemetry


def _default_data_dir() -> Path:
    override = os.getenv("TODOIST_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        base = os.getenv("PROGRAMDATA") or os.getenv("LOCALAPPDATA") or str(Path.home())
        return Path(base) / "TodoistAssistant"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "TodoistAssistant"
    return Path.home() / ".local" / "share" / "todoist-assistant"


def _resolve_config_dir(data_dir: Path, install_dir: Path, override: str | None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    candidate = data_dir / "config"
    if getattr(sys, "frozen", False):
        return candidate
    if candidate.exists():
        return candidate
    repo_candidate = install_dir / "configs"
    if repo_candidate.exists():
        return repo_candidate
    return candidate


def _seed_config_dir(config_dir: Path, install_dir: Path) -> None:
    templates_dir = install_dir / "configs"
    if templates_dir.exists() and not any(config_dir.iterdir()):
        shutil.copytree(templates_dir, config_dir, dirs_exist_ok=True)

    template_src: Path | None = None
    for name in (".env.template", ".env.example"):
        candidate = install_dir / name
        if candidate.exists():
            template_src = candidate
            break

    if template_src:
        dest = config_dir / ".env.template"
        if not dest.exists():
            shutil.copyfile(template_src, dest)


def _ensure_env_and_files(data_dir: Path, config_dir: Path, install_dir: Path | None = None) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)

    if install_dir and getattr(sys, "frozen", False):
        _seed_config_dir(config_dir, install_dir)

    env_path = data_dir / ".env"
    template_candidates = [config_dir / ".env.template", config_dir / ".env.example"]
    if not env_path.exists():
        for template_path in template_candidates:
            if template_path.exists():
                shutil.copyfile(template_path, env_path)
                break

    os.environ["TODOIST_CONFIG_DIR"] = str(config_dir)
    os.environ["TODOIST_CACHE_DIR"] = str(data_dir)
    os.environ["TODOIST_AGENT_CACHE_PATH"] = str(data_dir)
    os.environ["TODOIST_AGENT_INSTRUCTIONS_DIR"] = str(config_dir / "agent_instructions")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch the Todoist Assistant dashboard.")
    parser.add_argument("--api-host", default=os.getenv("TODOIST_API_HOST", "127.0.0.1"))
    parser.add_argument("--api-port", type=int, default=int(os.getenv("TODOIST_API_PORT", "8000")))
    parser.add_argument("--frontend-host", default=os.getenv("TODOIST_FRONTEND_HOST", "127.0.0.1"))
    parser.add_argument("--frontend-port", type=int, default=int(os.getenv("TODOIST_FRONTEND_PORT", "3000")))
    parser.add_argument("--data-dir", default=os.getenv("TODOIST_DATA_DIR"))
    parser.add_argument("--config-dir", default=os.getenv("TODOIST_CONFIG_DIR"))
    parser.add_argument("--no-frontend", action="store_true", help="Start only the API server.")
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser window.")
    return parser.parse_args()


def _frontend_manifest_info(zip_path: Path) -> dict[str, int]:
    stat = zip_path.stat()
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def _frontend_manifest_path(data_dir: Path) -> Path:
    return data_dir / ".frontend_manifest.json"


def _load_frontend_manifest(path: Path) -> dict[str, int] | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    size = payload.get("size")
    mtime_ns = payload.get("mtime_ns")
    if isinstance(size, int) and isinstance(mtime_ns, int):
        return {"size": size, "mtime_ns": mtime_ns}
    return None


def _write_frontend_manifest(path: Path, info: dict[str, int]) -> None:
    path.write_text(json.dumps(info, sort_keys=True), encoding="utf-8")


def _frontend_ready(frontend_dir: Path) -> bool:
    server_js = frontend_dir / "server.js"
    if not server_js.exists():
        return False
    static_dir = frontend_dir / ".next" / "static"
    public_dir = frontend_dir / "public"
    return static_dir.exists() or public_dir.exists()


def _prepare_frontend_dir(install_dir: Path, data_dir: Path) -> Path:
    frontend_zip = install_dir / "frontend.zip"
    extracted_dir = data_dir / "frontend"
    if frontend_zip.exists():
        manifest_path = _frontend_manifest_path(data_dir)
        current = _frontend_manifest_info(frontend_zip)
        cached = _load_frontend_manifest(manifest_path)
        needs_extract = (cached != current) or (not _frontend_ready(extracted_dir))
        server_js = extracted_dir / "server.js"
        if needs_extract:
            temp_dir = data_dir / f"frontend.tmp-{os.getpid()}"
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
            temp_dir.mkdir(parents=True, exist_ok=True)
            try:
                _extract_zip(frontend_zip, temp_dir)
                if not _frontend_ready(temp_dir):
                    raise RuntimeError("Extracted frontend is missing server.js or assets")
                if extracted_dir.exists():
                    shutil.rmtree(extracted_dir)
                shutil.move(str(temp_dir), str(extracted_dir))
                _write_frontend_manifest(manifest_path, current)
            finally:
                if temp_dir.exists():
                    shutil.rmtree(temp_dir)
        return extracted_dir
    if (install_dir / "frontend" / "server.js").exists():
        return install_dir / "frontend"
    return install_dir


def _start_frontend(install_dir: Path, data_dir: Path, host: str, port: int) -> subprocess.Popen[bytes]:
    frontend_dir = _prepare_frontend_dir(install_dir, data_dir)
    node_exe = install_dir / "node" / ("node.exe" if os.name == "nt" else "node")
    if os.name != "nt" and not node_exe.exists():
        fallback = install_dir / "node" / "bin" / "node"
        if fallback.exists():
            node_exe = fallback
    node_cmd = str(node_exe) if node_exe.exists() else ("node.exe" if os.name == "nt" else "node")
    server_js = frontend_dir / "server.js"
    if not server_js.exists():
        raise FileNotFoundError(f"Next.js server not found at {server_js}")

    env = os.environ.copy()
    env["PORT"] = str(port)
    env["HOSTNAME"] = host

    return subprocess.Popen([node_cmd, str(server_js)], cwd=str(frontend_dir), env=env)


def _win_long_path(path: Path) -> str:
    if os.name != "nt":
        return str(path)
    resolved = os.path.abspath(str(path))
    if resolved.startswith("\\\\?\\"):
        return resolved
    if resolved.startswith("\\\\"):
        return f"\\\\?\\UNC\\{resolved[2:]}"
    return f"\\\\?\\{resolved}"


def _extract_zip(zip_path: Path, dest: Path) -> None:
    with zipfile.ZipFile(zip_path, "r") as archive:
        for member in archive.infolist():
            if not member.filename:
                continue
            normalized = member.filename.replace("\\", "/")
            member_path = PurePosixPath(normalized)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise RuntimeError(f"Refusing to extract unsafe path: {member.filename}")
            if member_path.parts and ":" in member_path.parts[0]:
                raise RuntimeError(f"Refusing to extract unsafe path: {member.filename}")
            target = dest / Path(*member_path.parts)
            if member.is_dir():
                os.makedirs(_win_long_path(target), exist_ok=True)
                continue
            os.makedirs(_win_long_path(target.parent), exist_ok=True)
            with archive.open(member, "r") as src, open(_win_long_path(target), "wb") as dst:
                shutil.copyfileobj(src, dst)


def main() -> int:
    args = _parse_args()

    if getattr(sys, "frozen", False):
        install_dir = Path(sys.executable).resolve().parent
        if sys.platform == "darwin":
            resources_dir = install_dir.parent / "Resources"
            if resources_dir.exists():
                install_dir = resources_dir
    else:
        install_dir = Path(__file__).resolve().parents[1]
    data_dir = Path(args.data_dir).expanduser().resolve() if args.data_dir else _default_data_dir()
    config_dir = _resolve_config_dir(data_dir, install_dir, args.config_dir)
    _ensure_env_and_files(data_dir, config_dir, install_dir=install_dir)
    try:
        telemetry.bootstrap_config(config_dir)
    except Exception:
        # Telemetry is best-effort; avoid blocking launch.
        pass

    try:
        telemetry.maybe_send_install_success(config_dir, data_dir)
    except Exception:
        # Telemetry is best-effort; avoid blocking launch.
        pass

    os.chdir(data_dir)

    frontend_proc: subprocess.Popen[bytes] | None = None
    try:
        if not args.no_frontend:
            frontend_proc = _start_frontend(install_dir, data_dir, args.frontend_host, args.frontend_port)
            time.sleep(1.0)
        if not args.no_browser:
            target = f"http://{args.frontend_host}:{args.frontend_port}" if not args.no_frontend else None
            if target:
                webbrowser.open(target)

        uvicorn.run(
            "todoist.web.api:app",
            host=args.api_host,
            port=args.api_port,
            log_level="info",
        )
    except Exception:
        traceback.print_exc()
        try:
            telemetry.maybe_send_install_failure(config_dir, data_dir)
        except Exception:
            # Telemetry is best-effort; avoid masking the original error.
            pass
        if getattr(sys, "frozen", False) and os.name == "nt":
            print("\nApplication failed to start or crashed.")
            print("Press Enter to exit...")
            try:
                input()
            except Exception:
                # Ignore any stdin errors; this pause is best-effort and should not block exit.
                pass
        sys.exit(1)
    finally:
        if frontend_proc and frontend_proc.poll() is None:
            frontend_proc.terminate()
            try:
                frontend_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                frontend_proc.kill()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
