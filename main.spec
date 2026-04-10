# -*- mode: python -*-

block_cipher = None

import os
import sys
from PyInstaller.utils.hooks import collect_data_files

# Helper to include all files inside the tools/ folder, preserving structure
def collect_folder(folder_name):
    collected = []
    for root, _, files in os.walk(folder_name):
        for file in files:
            src_path = os.path.join(root, file)
            # Keep relative path from folder_name
            rel_dest = os.path.relpath(src_path, folder_name)
            collected.append((src_path, os.path.join(folder_name, os.path.dirname(rel_dest))))
    return collected


a = Analysis(
    ['main.py'],
    pathex=['C:\\Users\\ABC-RnD\\Documents\\GitHub\\WHAT_Tools_Control_Center'],
    datas=[
        ('inno_setup_script_for_making_installer.iss', '.'),
    ] + collect_folder('assets') + collect_folder('cache') + collect_folder('ui'),
    hiddenimports=['pkg_resources', 'pkg_resources.extern'],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='WHATControlCenter',
    debug=False,
    strip=False,
    onefile=False,
    upx=False,
    console=False,
    icon='assets/WHAT.ico'
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='WHATControlCenter'
)
