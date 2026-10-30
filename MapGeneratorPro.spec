# -*- mode: python ; coding: utf-8 -*-
# MapGeneratorPro.spec — Configuration PyInstaller
# Usage : .venv\Scripts\python.exe -m PyInstaller MapGeneratorPro.spec

import sys
from pathlib import Path

APP_DIR = Path(SPECPATH)
# Utiliser sys.base_prefix pour avoir le Python global (pas le venv)
PYTHON_DIR = Path(sys.base_prefix)
PYTHON_DLL = PYTHON_DIR / 'python313.dll'

a = Analysis(
    ['main.py'],
    pathex=[str(APP_DIR)],
    binaries=[
        (str(PYTHON_DLL), '.'),  # Copie python313.dll à la racine du dist
    ],
    datas=[
        # Interface (HTML/JS)
        ('web', 'web'),
        # Base vanilla copiée dans Documents/MapGeneratorPro au premier lancement
        # (régénérée par tools/build_vanilla_base.py)
        ('data/Textures_ArmaReforger/vanilla_base', 'data/Textures_ArmaReforger/vanilla_base'),
    ],
    hiddenimports=[
        # PyWebView
        'webview',
        'webview.platforms.winforms',
        'webview.js',
        'clr',
        # Modules de l'app (importés à l'intérieur des fonctions de main.py)
        'catalog_config',
        'clean_weights',
        'edds_decoder',
        'generate_catalog',
        'hypsometric_colormap',
        'layer_dds_reader',
        'lrs2_parser',
        'pipeline_v5',
        'project_reader',
        'reforger_emat_parser',
        'satmap_v2_textured_v2',
        'satmap_verifiers',
        'terrain_algorithms',
        'terrain_analysis',
        'terrain_terr_reader',
        'tile_inspector',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'streamlit',
        'sklearn',
        'tkinter',
        'PyQt5',
        'PyQt6',
        'wx',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='MapGeneratorPro',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # Pas de console noire au lancement
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,              # Ajouter 'img/icon.ico' si disponible
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='MapGeneratorPro',
)
