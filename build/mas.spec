# -*- mode: python ; coding: utf-8 -*-
"""onedir build. Remember to add new interface files to datas."""
import re
from pathlib import Path

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct,
    VSVersionInfo,
)

SRC = Path(SPECPATH).parent / "src"

# The version is read out of the package rather than written here again: an exe
# whose properties disagree with the program's own About tab is worse than one
# with no version at all. Parsed, not imported — importing the package here
# would drag in Windows audio bindings during the build.
VERSION = re.search(r'__version__ = "([^"]+)"',
                    (SRC / "mas" / "__init__.py").read_text(encoding="utf-8")).group(1)
NUMERIC = tuple(int(p) for p in VERSION.split(".")) + (0,) * (4 - VERSION.count(".") - 1)

# Without this resource the exe has no name, no author and no version in its
# properties. For a person that looks unfinished; for antivirus heuristics an
# anonymous PyInstaller binary is one more reason to be suspicious, and this one
# already synthesises keystrokes, reads HID and enumerates other processes.
VERSION_RESOURCE = VSVersionInfo(
    ffi=FixedFileInfo(filevers=NUMERIC, prodvers=NUMERIC, mask=0x3F, flags=0x0,
                      OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
    kids=[
        # 0409 is US English, 04B0 is Unicode.
        StringFileInfo([StringTable("040904B0", [
            StringStruct("CompanyName", "electronic-mars"),
            StringStruct("FileDescription", "Master Audio Switcher"),
            StringStruct("FileVersion", VERSION),
            StringStruct("InternalName", "MasterAudioSwitcher"),
            StringStruct("LegalCopyright",
                         "Copyright (C) 2026 Master Audio Switcher contributors. "
                         "GPL-3.0-or-later"),
            StringStruct("OriginalFilename", "MasterAudioSwitcher.exe"),
            StringStruct("ProductName", "Master Audio Switcher"),
            StringStruct("ProductVersion", VERSION),
        ])]),
        VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
    ],
)

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
    version=VERSION_RESOURCE,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="MasterAudioSwitcher",
)
