"""Check Android build prerequisites before any dependency installation."""

import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

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


def test_android_manifest_limits_network_and_backup_access() -> None:
    root = Path(__file__).resolve().parents[3] / "android" / "app" / "src" / "main"
    manifest = ET.parse(root / "AndroidManifest.xml").getroot()
    android = "{http://schemas.android.com/apk/res/android}"
    application = manifest.find("application")
    assert application is not None
    assert application.get(android + "allowBackup") == "false"
    assert application.get(android + "fullBackupContent") == "false"
    assert application.get(android + "usesCleartextTraffic") == "false"
    assert application.get(android + "dataExtractionRules") == "@xml/data_extraction_rules"
    assert {permission.get(android + "name") for permission in manifest.findall("uses-permission")} == {
        "android.permission.INTERNET",
        "android.permission.ACCESS_NETWORK_STATE",
    }
    rules = ET.parse(root / "res" / "xml" / "data_extraction_rules.xml").getroot()
    for mode in ("cloud-backup", "device-transfer"):
        section = rules.find(mode)
        assert section is not None
        assert {item.get("domain") for item in section.findall("exclude") if item.get("path") == "."} >= {
            "root", "sharedpref", "file", "database", "external"
        }
