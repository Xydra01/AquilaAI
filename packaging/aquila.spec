# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Aquila OS desktop (onedir).

Build:
  pip install -r requirements-core.txt -r requirements-packaging.txt
  pyinstaller packaging/aquila.spec
"""
import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent

block_cipher = None

aquila_datas = [
    (str(ROOT / "modelfiles"), "modelfiles"),
    (str(ROOT / "docker-compose.yml"), "search"),
    (str(ROOT / "searxng-settings.yml"), "search"),
]

hiddenimports = [
    "PySide6",
    "qfluentwidgets",
    "agent.core",
    "agent.gui",
    "agent.gui.gui_pages",
    "agent.aquila_runtime",
    "agent.remote",
    "agent.storage",
    "agent.research",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
]

a = Analysis(
    [str(ROOT / "agent" / "gui" / "gui.py")],
    pathex=[str(ROOT), str(ROOT / "agent")],
    binaries=[],
    datas=aquila_datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["torch", "tensorflow"],
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
    name="Aquila",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Aquila",
)
