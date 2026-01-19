# -*- mode: python ; coding: utf-8 -*-

from __future__ import annotations

from pathlib import Path
import os
import plistlib

from PyInstaller.utils.hooks import collect_all

plotly = collect_all("plotly")
matplotlib = collect_all("matplotlib")

binaries = plotly.binaries + matplotlib.binaries
datas = plotly.datas + matplotlib.datas
hiddenimports = plotly.hiddenimports + matplotlib.hiddenimports

block_cipher = None

repo_root = Path(__file__).resolve().parents[2]

config_dir = repo_root / "configs"
if config_dir.exists():
    datas.append((str(config_dir), "configs"))

env_example = repo_root / ".env.example"
if env_example.exists():
    datas.append((str(env_example), "."))

readme = repo_root / "README.md"
if readme.exists():
    datas.append((str(readme), "."))

img_dir = repo_root / "img"
if img_dir.exists():
    datas.append((str(img_dir), "img"))

version = os.environ.get("TODOIST_VERSION", "0.0.0")
info_plist_path = repo_root / "packaging" / "macos" / "Info.plist"
if info_plist_path.exists():
    info_plist = plistlib.loads(info_plist_path.read_bytes())
else:
    info_plist = {}

info_plist.update(
    {
        "CFBundleName": info_plist.get("CFBundleName", "TodoistAssistant"),
        "CFBundleDisplayName": info_plist.get("CFBundleDisplayName", "Todoist Assistant"),
        "CFBundleIdentifier": "com.todoist.assistant",
        "CFBundleShortVersionString": version,
        "CFBundleVersion": version,
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": "True",
    }
)

a = Analysis(
    ["todoist/launcher.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TodoistAssistant",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name="TodoistAssistant",
)

icon_path = repo_root / "packaging" / "macos" / "TodoistAssistant.icns"
app = BUNDLE(
    coll,
    name="TodoistAssistant.app",
    icon=str(icon_path) if icon_path.exists() else None,
    bundle_identifier="com.todoist.assistant",
    info_plist=info_plist,
)
