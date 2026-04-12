# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec: AM4OpsCenter.exe + AM4OpsCenter-Stop.exe (onedir, not onefile).

Build from repo root:
  pyinstaller --clean --noconfirm packaging/launcher/launcher.spec

Output:
  dist/launcher/AM4OpsCenter/AM4OpsCenter.exe
  dist/launcher/AM4OpsCenter-Stop/AM4OpsCenter-Stop.exe
"""
import os

from PyInstaller.building.api import COLLECT, EXE, PYZ
from PyInstaller.building.build_main import Analysis
from PyInstaller.config import CONF

# Match Inno Setup layout: ../../dist/launcher/<name>/
_REPO_ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))
CONF["distpath"] = os.path.join(_REPO_ROOT, "dist", "launcher")
CONF["workpath"] = os.path.join(_REPO_ROOT, "build", "pyinstaller-launcher")
os.makedirs(CONF["distpath"], exist_ok=True)
os.makedirs(CONF["workpath"], exist_ok=True)

_SPECDIR = SPECPATH
_LAUNCHER = os.path.join(_SPECDIR, "am4opscenter_launcher.py")
_STOP = os.path.join(_SPECDIR, "am4opscenter_stop.py")
_ICON = os.path.join(_SPECDIR, "icon.ico")

block_cipher = None

launcher_a = Analysis(
    [_LAUNCHER],
    pathex=[_SPECDIR],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

stop_a = Analysis(
    [_STOP],
    pathex=[_SPECDIR],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

launcher_pyz = PYZ(launcher_a.pure, launcher_a.zipped_data, cipher=block_cipher)
stop_pyz = PYZ(stop_a.pure, stop_a.zipped_data, cipher=block_cipher)

launcher_exe = EXE(
    launcher_pyz,
    launcher_a.scripts,
    [],
    exclude_binaries=True,
    name="AM4OpsCenter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_ICON,
)

stop_exe = EXE(
    stop_pyz,
    stop_a.scripts,
    [],
    exclude_binaries=True,
    name="AM4OpsCenter-Stop",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_ICON,
)

COLLECT(
    launcher_exe,
    launcher_a.binaries,
    launcher_a.zipfiles,
    launcher_a.datas,
    strip=False,
    upx=False,
    name="AM4OpsCenter",
)

COLLECT(
    stop_exe,
    stop_a.binaries,
    stop_a.zipfiles,
    stop_a.datas,
    strip=False,
    upx=False,
    name="AM4OpsCenter-Stop",
)
