# -*- coding: utf-8 -*-
"""
catalog_config.py — Configuration centralisée du chemin du catalog.json
Compatible : mode dev, mode exe (PyInstaller), usage standalone des scripts.

Ce module est importé par main.py et tous les scripts nécessitant le catalog.
"""

import sys
from pathlib import Path

# ============================================================================
# DÉFINITION UNIQUE DES CHEMINS (DEV + EXE)
# ============================================================================

if getattr(sys, 'frozen', False):
    # Mode EXE (PyInstaller)
    USER_DIR = Path.home() / "Documents" / "MapGeneratorPro"
else:
    # Mode DEV : racine du dépôt (parent de app/)
    USER_DIR = Path(__file__).resolve().parent.parent

TEXTURES_USER_DIR = USER_DIR / "data" / "Textures_ArmaReforger" / "Textures"

# ----------------------------------------------------------------------
# Fonction utilitaire pour obtenir le chemin du catalog.json
# ----------------------------------------------------------------------
def get_catalog_path() -> Path:
    """
    Retourne le chemin absolu du catalog.json global.

    Résolution centralisée :
    - Mode EXE : Documents/MapGeneratorPro/data/Textures_ArmaReforger/Textures/catalog.json
    - Mode DEV : <racine_projet>/data/Textures_ArmaReforger/Textures/catalog.json

    Returns:
        Path: Chemin absolu vers catalog.json
    """
    return TEXTURES_USER_DIR / "catalog.json"


# Constante pour usage direct
CATALOG_PATH = get_catalog_path()

# ----------------------------------------------------------------------
# Test du module
# ----------------------------------------------------------------------
if __name__ == "__main__":
    # Test du module
    print(f"Mode exe : {getattr(sys, 'frozen', False)}")
    print(f"USER_DIR : {USER_DIR}")
    print(f"TEXTURES_USER_DIR : {TEXTURES_USER_DIR}")
    print(f"Chemin catalog : {get_catalog_path()}")
    print(f"Catalogue existe : {get_catalog_path().exists()}")
