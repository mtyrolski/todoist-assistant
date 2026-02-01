"""Lightweight CLI entrypoint for Todoist Assistant."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.error import URLError
from urllib.request import Request, urlopen

import typer

from todoist import telemetry
from todoist.env import EnvVar
from todoist.version import get_version

GITHUB_REPO = "mtyrolski/todoist-assistant"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases/latest"

app = typer.Typer(add_completion=False, no_args_is_help=True, help="Todoist Assistant CLI")


def _fetch_latest_release() -> dict:
    request = Request(
        RELEASES_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "todoist-assistant",
        },
    )
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _extract_version(text: str) -> str | None:
    parts = re.findall(r"\d+", text)
    if not parts:
        return None
    while len(parts) < 3:
        parts.append("0")
    return ".".join(parts[:3])


def _version_tuple(version: str) -> tuple[int, int, int]:
    parts = re.findall(r"\d+", version)
    parts = (parts + ["0", "0", "0"])[:3]
    return tuple(int(p) for p in parts)  # type: ignore[return-value]


def _select_asset(release: dict, suffixes: tuple[str, ...]) -> tuple[str, str] | None:
    for asset in release.get("assets", []):
        name = str(asset.get("name", ""))
        if any(name.endswith(suffix) for suffix in suffixes):
            url = asset.get("browser_download_url")
            if url:
                return name, url
    return None


def _download(url: str, filename: str) -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix="todoist-assistant-"))
    target = temp_dir / filename
    request = Request(url, headers={"User-Agent": "todoist-assistant"})
    with urlopen(request, timeout=30) as response, target.open("wb") as handle:
        handle.write(response.read())
    return target


def _run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        raise typer.Exit(code=result.returncode)


def _print_install_instructions(label: str, url: str, command: str) -> None:
    typer.echo(f"{label} installer download: {url}")
    typer.echo("Run:")
    typer.echo(f"  {command}")


@app.callback()
def main(
    version: bool = typer.Option(False, "--version", help="Show the version and exit"),
    enable_telemetry: bool = typer.Option(
        False,
        "--enable-telemetry",
        help="Enable telemetry (opt-in only).",
    ),
    disable_telemetry: bool = typer.Option(
        False,
        "--disable-telemetry",
        help="Disable telemetry permanently (opt-in only).",
    ),
) -> None:
    if enable_telemetry and disable_telemetry:
        typer.echo("Choose only one of --enable-telemetry or --disable-telemetry.")
        raise typer.Exit(code=2)
    if enable_telemetry:
        config_dir = telemetry.resolve_config_dir()
        telemetry.set_enabled(config_dir, True)
        typer.echo("Telemetry enabled.")
        if not os.getenv(EnvVar.TELEMETRY_ENDPOINT):
            typer.echo(f"NOTE: {EnvVar.TELEMETRY_ENDPOINT} is not set, so no telemetry will be sent.")
        raise typer.Exit()
    if disable_telemetry:
        config_dir = telemetry.resolve_config_dir()
        telemetry.set_enabled(config_dir, False)
        typer.echo("Telemetry disabled.")
        raise typer.Exit()
    if version:
        typer.echo(get_version())
        raise typer.Exit()


@app.command()
def dashboard() -> None:
    """Explain dashboard packaging for Homebrew installs."""
    typer.echo("Dashboard assets are not bundled in the Homebrew formula.")
    typer.echo("Use the source checkout if you need the web dashboard.")


@app.command()
def version(
    check: bool = typer.Option(False, "--check", help="Check for a newer release"),
) -> None:
    """Show the current version, optionally checking for updates."""
    current = get_version()
    typer.echo(current)
    if not check:
        return

    try:
        release = _fetch_latest_release()
    except URLError as exc:
        typer.echo(f"Update check failed: {exc}")
        raise typer.Exit(code=1)

    latest_tag = str(release.get("tag_name", "")) or str(release.get("name", ""))
    latest = _extract_version(latest_tag) or current
    if _version_tuple(latest) > _version_tuple(current):
        typer.echo(f"Update available: {latest}")
        typer.echo(f"Download from {RELEASES_PAGE}")
    else:
        typer.echo("You are up to date.")

    if sys.platform == "darwin":
        typer.echo("If installed via Homebrew, run: brew upgrade todoist-assistant")
    elif os.name == "nt":
        typer.echo("For MSI installs, download the latest installer from the releases page.")


@app.command("install-windows")
def install_windows(
    dry_run: bool = typer.Option(False, "--dry-run", help="Print steps without executing"),
) -> None:
    """Download and run the latest Windows installer."""
    if os.name != "nt":
        _print_install_instructions(
            "Windows",
            RELEASES_PAGE,
            "msiexec /i todoist-assistant-<version>.msi",
        )
        return

    try:
        release = _fetch_latest_release()
    except URLError as exc:
        typer.echo(f"Failed to query releases: {exc}")
        raise typer.Exit(code=1)

    asset = _select_asset(release, (".msi",))
    if not asset:
        typer.echo(f"No MSI asset found. Download manually: {RELEASES_PAGE}")
        raise typer.Exit(code=1)

    name, url = asset
    command = f"msiexec /i {name}"
    if dry_run:
        _print_install_instructions("Windows", url, command)
        return

    installer = _download(url, name)
    typer.echo(f"Downloaded installer to {installer}")
    if not typer.confirm("Run the installer now? This may prompt for admin access."):
        _print_install_instructions("Windows", url, command)
        return

    _run(["msiexec", "/i", str(installer)])


@app.command("install-macos")
def install_macos(
    dry_run: bool = typer.Option(False, "--dry-run", help="Print steps without executing"),
) -> None:
    """Download and run the latest macOS pkg installer."""
    if sys.platform != "darwin":
        _print_install_instructions(
            "macOS",
            RELEASES_PAGE,
            "sudo installer -pkg todoist-assistant-<version>.pkg -target /",
        )
        return

    try:
        release = _fetch_latest_release()
    except URLError as exc:
        typer.echo(f"Failed to query releases: {exc}")
        raise typer.Exit(code=1)

    asset = _select_asset(release, (".pkg",))
    if not asset:
        typer.echo(f"No pkg asset found. Download manually: {RELEASES_PAGE}")
        raise typer.Exit(code=1)

    name, url = asset
    command = f"sudo installer -pkg {name} -target /"
    if dry_run:
        _print_install_instructions("macOS", url, command)
        return

    installer = _download(url, name)
    typer.echo(f"Downloaded installer to {installer}")
    if not typer.confirm("Run the installer now? This requires sudo."):
        _print_install_instructions("macOS", url, command)
        return

    _run(["sudo", "installer", "-pkg", str(installer), "-target", "/"])


if __name__ == "__main__":
    app()
