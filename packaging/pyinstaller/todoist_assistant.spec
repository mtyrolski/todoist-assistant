# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules


def _collect(module_name):
    collected = collect_all(module_name)
    if isinstance(collected, tuple):
        datas, binaries, hiddenimports = collected
    else:
        datas, binaries, hiddenimports = collected.datas, collected.binaries, collected.hiddenimports
    return datas, binaries, hiddenimports


_spec_file = globals().get("__file__")
if _spec_file:
    ROOT = Path(_spec_file).resolve().parents[2]
else:
    ROOT = Path.cwd().resolve()
ENTRYPOINT = ROOT / "todoist" / "launcher.py"

plotly_datas, plotly_binaries, plotly_hiddenimports = _collect("plotly")
matplotlib_datas, matplotlib_binaries, matplotlib_hiddenimports = _collect("matplotlib")

binaries = plotly_binaries + matplotlib_binaries
datas = plotly_datas + matplotlib_datas
hiddenimports = plotly_hiddenimports + matplotlib_hiddenimports

# launcher.py imports the FastAPI app object and calls uvicorn.run(api_app, ...),
# but PyInstaller still needs these as explicit hidden imports to bundle the API modules.
hiddenimports += ["todoist.web", "todoist.web.api"]
# Guard against new submodules added under todoist.web being missed in future builds.
hiddenimports += collect_submodules("todoist.web")

hiddenimports = list(dict.fromkeys(hiddenimports))

block_cipher = None


a = Analysis(
    [str(ENTRYPOINT)],
    pathex=[str(ROOT)],
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
    [],
    exclude_binaries=True,
    name="todoist-assistant",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name="todoist-assistant",
)
