# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all

plotly = collect_all("plotly")
matplotlib = collect_all("matplotlib")

binaries = plotly.binaries + matplotlib.binaries
datas = plotly.datas + matplotlib.datas
hiddenimports = plotly.hiddenimports + matplotlib.hiddenimports

block_cipher = None


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
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="todoist-assistant",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
)
