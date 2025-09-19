# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Todoist Assistant Windows executable.
"""

import os
import sys
from pathlib import Path

# Get the current directory
current_dir = Path(os.getcwd())
app_name = 'TodoistAssistant'

# Define data files to include
datas = [
    ('configs', 'configs'),
    ('.env.example', '.'),
    ('README.md', '.'),
    ('LICENSE', '.'),
    ('img', 'img'),
]

# Hidden imports - modules that PyInstaller might miss
hiddenimports = [
    'streamlit',
    'streamlit.web.cli',
    'streamlit.runtime.scriptrunner.script_runner',
    'streamlit.runtime.state',
    'streamlit.components.v1.components',
    'altair',
    'plotly',
    'plotly.graph_objs',
    'plotly.express',
    'pandas',
    'numpy',
    'matplotlib',
    'matplotlib.pyplot',
    'PIL',
    'PIL.Image',
    'joblib',
    'loguru',
    'hydra',
    'hydra.core.config_store',
    'hydra.core.global_hydra',
    'omegaconf',
    'dotenv',
    'requests',
    'tqdm',
    'pathlib',
    'webbrowser',
    'subprocess',
    'psutil',  # Often needed by streamlit
    'click',   # Used by streamlit
    'tornado', # Used by streamlit
    'watchdog', # Used by streamlit
    'pyarrow', # Used by streamlit/pandas
]

# Exclude unnecessary modules to reduce size
excludes = [
    'tkinter',
    'matplotlib.tests',
    'numpy.tests',
    'pandas.tests',
    'PIL.tests',
    'test',
    'tests',
    'unittest',
    'doctest',
    'pdb',
    'pydoc',
]

a = Analysis(
    ['main.py'],
    pathex=[str(current_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name=app_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Keep console for now for debugging
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='img/icon.ico' if (current_dir / 'img' / 'icon.ico').exists() else None,
)