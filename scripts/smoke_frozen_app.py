"""Start a frozen app with synthetic legacy activity and verify its API."""

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

from joblib import dump, load

from todometry.core.env import EnvVar
from todometry.database.dataframe import load_activity_data
from todometry.web.api import _DASHBOARD_STATE_SCHEMA_VERSION


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "v040"


def _seed_state(data: Path) -> None:
    cache = data / "cache"
    personal = data / "personal"
    cache.mkdir(parents=True)
    personal.mkdir()
    shutil.copyfile(FIXTURE / "activity.joblib", cache / "activity.joblib")
    snapshot = load(FIXTURE / "dashboard_state.joblib")
    project = snapshot["archived_projects"][0]

    class FixtureDatabase:
        def fetch_mapping_project_id_to_root(self):
            return {project.id: project}

        def fetch_mapping_project_id_to_name(self):
            return {project.id: project.project_entry.name}

        def fetch_projects(self, include_tasks=False):
            return []

        def fetch_archived_projects(self):
            return [project]

    saved_env = {
        key: os.environ.get(key)
        for key in (str(EnvVar.CACHE_DIR), str(EnvVar.PERSONAL_DIR))
    }
    try:
        os.environ[str(EnvVar.CACHE_DIR)] = str(cache)
        os.environ[str(EnvVar.PERSONAL_DIR)] = str(personal)
        frame = load_activity_data(FixtureDatabase())
    finally:
        for key, value in saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    stat = (cache / "activity.joblib").stat()
    snapshot.update(
        {
            "version": _DASHBOARD_STATE_SCHEMA_VERSION,
            "last_refresh_s": time.time(),
            "activity_cache_signature": {
                "mtime_ns": stat.st_mtime_ns,
                "size": stat.st_size,
            },
            "adjustments_cache_signature": [],
            "df_activity": frame,
        }
    )
    dump(snapshot, cache / "dashboard_state.joblib")


def _request(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    executable = args.executable.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="telemetry-frozen-smoke-") as temp:
        root = Path(temp)
        data = root / "data"
        _seed_state(data)
        with closing(socket.socket()) as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("TODOIST_") and key != "API_KEY"
        }
        log = root / "app.log"
        with log.open("w+", encoding="utf-8") as output:
            process = subprocess.Popen(
                [
                    str(executable),
                    "--no-browser",
                    "--no-frontend",
                    "--data-dir",
                    str(data),
                    "--config-dir",
                    str(data / "config"),
                    "--api-port",
                    str(port),
                ],
                cwd=root,
                env=env,
                stdout=output,
                stderr=subprocess.STDOUT,
            )
            try:
                url = f"http://127.0.0.1:{port}"
                deadline = time.monotonic() + 90
                while True:
                    if process.poll() is not None:
                        raise RuntimeError(
                            f"App exited with status {process.returncode}"
                        )
                    try:
                        health = _request(url + "/api/health")
                        break
                    except (OSError, urllib.error.URLError):
                        if time.monotonic() >= deadline:
                            raise RuntimeError("API startup timed out") from None
                        time.sleep(0.25)
                if health.get("version") != args.version:
                    raise RuntimeError(f"Unexpected API version: {health}")
                home = _request(
                    url + "/api/dashboard/home?beg=2024-01-01&end=2024-01-31"
                )
                if home.get("error") or home.get("noData"):
                    raise RuntimeError(
                        f"Legacy activity not visible: {home.get('error')}"
                    )
                timeline = _request(
                    url
                    + "/api/dashboard/project-timeline?beg=2024-01-01&end=2024-01-31"
                )
                if not any(
                    parent.get("name") == "Legacy project"
                    for parent in timeline.get("parents", [])
                ):
                    raise RuntimeError("Legacy archived project missing from timeline")
                print(
                    f"Frozen API {args.version}: legacy activity and archived project verified"
                )
            except Exception:
                output.flush()
                print(log.read_text(encoding="utf-8", errors="replace")[-6000:])
                raise
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
