# -*- mode: python ; coding: utf-8 -*-
"""onedir build. Remember to add new interface files to datas."""
from pathlib import Path

SRC = Path(SPECPATH).parent / "src"

a = Analysis(
    [str(SRC / "run_mas.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=[(str(SRC / "mas" / "ui"), "ui")],  # in the build the resources sit next to _MEIPASS, outside the package
    hiddenimports=["clr_loader", "pythonnet"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "unittest", "pydoc_data"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MasterAudioSwitcher",
    debug=False,
    strip=False,
    upx=False,
    console=False,  # a tray utility: a console is scary and looks like a fault
    icon=str(SRC / "mas" / "ui" / "icons" / "app" / "icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="MasterAudioSwitcher",
)
