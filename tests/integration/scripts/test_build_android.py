"""Check Android build prerequisites before any dependency installation."""

import os
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.skipif(os.name != "posix" or not shutil.which("bash"), reason="requires bash")
@pytest.mark.parametrize(
    ("version", "npm_runs"),
    [("1.8.0_452", False), ("11.0.27", False), ("17.0.13", True), ("21.0.5", True)],
)
def test_build_checks_java_before_running_npm(
    tmp_path: Path, version: str, npm_runs: bool
) -> None:
    root = Path(__file__).resolve().parents[3]
    java = tmp_path / "jdk" / "bin" / "java"
    java.parent.mkdir(parents=True)
    java.write_text(f'#!/bin/sh\necho \'openjdk version "{version}"\' >&2\n', encoding="utf-8")
    java.chmod(0o755)
    commands = tmp_path / "bin"
    commands.mkdir()
    npm = commands / "npm"
    npm.write_text('#!/bin/sh\ntouch "$TODOMETRY_NPM_MARKER"\nexit 90\n', encoding="utf-8")
    npm.chmod(0o755)
    marker = tmp_path / "npm-ran"
    env = {
        **os.environ,
        "JAVA_HOME": str(java.parent.parent),
        "ANDROID_HOME": str(tmp_path),
        "PATH": str(commands) + os.pathsep + os.environ.get("PATH", ""),
        "TODOMETRY_NPM_MARKER": str(marker),
    }
    result = subprocess.run(
        ["bash", str(root / "scripts/build_android.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert marker.exists() == npm_runs
    if not npm_runs:
        assert "JDK 17" in result.stderr
