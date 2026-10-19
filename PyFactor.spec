# -*- mode: python ; coding: utf-8 -*-
# Сборка: pyinstaller PyFactor.spec  (пути относительные — работает из любой папки; основной способ: python scripts/build_exe.py)
import os
import importlib.util
from PyInstaller.utils.hooks import collect_submodules, copy_metadata


def have(mod):
    return importlib.util.find_spec(mod) is not None


ROOT = os.path.abspath(SPECPATH)
ASSETS = os.path.join(ROOT, 'pyfactor', 'assets')

a = Analysis(
    [os.path.join(ROOT, 'pyfactor', '__main__.py')],
    pathex=[ROOT],
    binaries=[],
    datas=[(ASSETS, 'pyfactor/assets'), (os.path.join(ROOT, 'pyfactor', 'pg2'), 'pyfactor/pg2'),
           (os.path.join(ROOT, 'pyfactor', 'core', 'languages', 'funrun.py'), 'pyfactor/core/languages')]
          + (copy_metadata('keyring') if have('keyring') else []),
    hiddenimports=(collect_submodules('keyring.backends') if have('keyring') else []) + (collect_submodules('pygments.lexers') + collect_submodules('pygments.styles') if have('pygments') else []),
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False, optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name='PyFactor', debug=False, bootloader_ignore_signals=False, strip=False,
    upx=False,  # UPX часто вызывает ложные срабатывания антивирусов
    upx_exclude=[], runtime_tmpdir=None, console=False, disable_windowed_traceback=False,
    argv_emulation=False, target_arch=None, codesign_identity=None, entitlements_file=None,
    icon=[os.path.join(ASSETS, 'icon.ico')],
)
