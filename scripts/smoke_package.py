"""Build a wheel and smoke-test the installed files in an isolated directory."""

from email.parser import Parser
from configparser import ConfigParser
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    with (ROOT / "pyproject.toml").open("rb") as stream:
        project = tomllib.load(stream)["project"]
    with tempfile.TemporaryDirectory(prefix="todoist-wheel-smoke-") as temporary:
        root = Path(temporary)
        dist = root / "dist"
        subprocess.run(["uv", "build", "--out-dir", str(dist)], cwd=ROOT, check=True)
        wheels = list(dist.glob("*.whl"))
        if len(wheels) != 1:
            raise RuntimeError(f"Expected one wheel, found {len(wheels)}")
        wheel = wheels[0]
        print(f"Built wheel: {wheel.name}", flush=True)
        extracted = root / "installed"
        with ZipFile(wheel) as archive:
            metadata_file = next(
                n for n in archive.namelist() if n.endswith(".dist-info/METADATA")
            )
            metadata = Parser().parsestr(archive.read(metadata_file).decode("utf-8"))
            if (
                metadata["Name"] != project["name"]
                or metadata["Version"] != project["version"]
            ):
                raise RuntimeError("Wheel metadata does not match pyproject.toml")
            entry_points_file = next(
                n for n in archive.namelist() if n.endswith(".dist-info/entry_points.txt")
            )
            entries = ConfigParser()
            entries.read_string(archive.read(entry_points_file).decode("utf-8"))
            if entries["console_scripts"].get("todoist-telemetry") != "todometry.cli:app":
                raise RuntimeError("Wheel console entry point is missing or incorrect")
            archive.extractall(extracted)
        cache = root / "cache"
        cache.mkdir()
        shutil.copyfile(
            ROOT / "tests/fixtures/v040/activity.joblib", cache / "activity.joblib"
        )
        code = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import todometry
from fastapi.testclient import TestClient
from todometry.core.utils import Cache
from todometry.core.version import get_version
from todometry.features.activity import load_activity_cache
from todometry.web.api import app
assert Path(todometry.__file__).resolve().is_relative_to(Path(sys.argv[1]).resolve())
assert get_version() == sys.argv[3]
assert {event.id for event in load_activity_cache(cache=Cache(sys.argv[2]))} == {"event-v040"}
with TestClient(app) as client:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["version"] == sys.argv[3]
print("Wheel import, legacy activity and API health passed")
"""
        subprocess.run(
            [
                sys.executable,
                "-I",
                "-c",
                code,
                str(extracted),
                str(cache),
                project["version"],
            ],
            cwd=root,
            check=True,
        )
        cli = 'import runpy, sys; sys.path.insert(0, sys.argv.pop(1)); sys.argv = ["todometry.cli", *sys.argv[1:]]; runpy.run_module("todometry.cli", run_name="__main__")'
        for option in ("--help", "--version"):
            result = subprocess.run(
                [sys.executable, "-I", "-c", cli, str(extracted), option],
                cwd=root,
                check=True,
                text=True,
                capture_output=True,
            )
            if option == "--version" and result.stdout.strip() != project["version"]:
                raise RuntimeError("Wheel CLI version does not match package metadata")
        print("Wheel CLI help and version passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
