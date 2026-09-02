# -*- mode: python ; coding: utf-8 -*-
# MapGeneratorPro.spec — Configuration PyInstaller
# Usage : pyinstaller MapGeneratorPro.spec

import sys, os
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
        # Dossier web (HTML/JS)
        ('web', 'web'),
        # Données textures et biomes
        ('data/Textures_ArmaReforger', 'data/Textures_ArmaReforger'),
        # Config
        ('config.json', '.'),
        ('requirements.txt', '.'),
        # Scripts Python locaux
        ('clean_weights.py', '.'),
        ('tile_inspector.py', '.'),
        ('lrs2_parser.py', '.'),
        ('edds_decoder.py', '.'),
        ('terrain_terr_reader.py', '.'),
        ('reforger_emat_parser.py', '.'),
    ],
    hiddenimports=[
        # PyWebView
        'webview',
        'webview.platforms.winforms',
        'webview.js',
        'clr',
        # NumPy / OpenCV / Pillow
        'numpy',
        'cv2',
        'PIL',
        'PIL.Image',
        # Pipeline
        'pipeline_v5',
        'terrain_algorithms',
        'terrain_analysis',
        'hypsometric_colormap',
        'base_map',
        'app_config',
        'project_manager',
        'satmap_v2_generator',
        'satmap_v2_textured',
        'satmap_classifier',
        'pipeline_validation',
        'lrs2_parser',
        'layer_dds_reader',
        'edds_decoder',
        'terrain_terr_reader',
        'reforger_emat_parser',
        'clean_weights',
        # Stdlib
        'json',
        'pathlib',
        'threading',
        'subprocess',
        'shutil',
        'struct',
        'io',
        'contextlib',
        'importlib',
        'sklearn',
        'sklearn.cluster',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'streamlit',
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
