# -*- coding: utf-8 -*-
"""
catalog_config.py — Configuration centralisée des chemins de textures
Compatible : mode dev, mode exe (PyInstaller).

Chaque projet a ses propres textures dans <projet>/textures/ (emat/, texture_Middle/,
catalog.json). Le dossier global TEXTURES_USER_DIR sert de modèle : il est copié dans
un projet qui n'a pas encore de dossier textures/.

Ce module est importé par main.py et tous les scripts nécessitant le catalog.
"""

import shutil
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

# Dossier modèle (vanilla), copié dans chaque projet
TEXTURES_USER_DIR = USER_DIR / "data" / "Textures_ArmaReforger" / "Textures"

# Contenu du dossier de textures d'un projet
PROJECT_TEXTURES_SUBDIR = "textures"
EMAT_SUBDIR = "emat"
MIDDLES_SUBDIR = "texture_Middle"
CATALOG_NAME = "catalog.json"


# ----------------------------------------------------------------------
# Chemins des textures d'un projet
# ----------------------------------------------------------------------
def get_project_textures_dir(project_dir) -> Path:
    """Dossier des textures du projet : <projet>/textures/."""
    return Path(project_dir) / PROJECT_TEXTURES_SUBDIR


def get_catalog_path(project_dir) -> Path:
    """Chemin du catalog.json du projet."""
    return get_project_textures_dir(project_dir) / CATALOG_NAME


def get_emat_dir(project_dir) -> Path:
    """Dossier des .emat du projet."""
    return get_project_textures_dir(project_dir) / EMAT_SUBDIR


def get_middles_dir(project_dir) -> Path:
    """Dossier des middles (PNG) du projet."""
    return get_project_textures_dir(project_dir) / MIDDLES_SUBDIR


def ensure_project_textures(project_dir) -> dict:
    """
    Copie le dossier modèle (emat/, texture_Middle/, catalog.json) dans <projet>/textures/
    si ce dossier n'existe pas encore. Ne touche jamais à un dossier textures/ existant.

    Returns:
        {"ok": True, "copied": bool, "textures_dir": str} ou {"ok": False, "error": str}
    """
    dst = get_project_textures_dir(project_dir)
    if dst.exists():
        return {"ok": True, "copied": False, "textures_dir": str(dst)}
    if not (TEXTURES_USER_DIR / CATALOG_NAME).exists():
        return {"ok": False, "error": f"Dossier de textures modèle incomplet : {TEXTURES_USER_DIR}"}

    # Copie dans un dossier temporaire puis renommage : pas de textures/ à moitié copié
    tmp = dst.with_name(PROJECT_TEXTURES_SUBDIR + ".tmp")
    try:
        if tmp.exists():
            shutil.rmtree(tmp)
        tmp.mkdir(parents=True)
        for sub in (EMAT_SUBDIR, MIDDLES_SUBDIR):
            src = TEXTURES_USER_DIR / sub
            if src.exists():
                shutil.copytree(src, tmp / sub)
            else:
                (tmp / sub).mkdir()
        shutil.copy2(TEXTURES_USER_DIR / CATALOG_NAME, tmp / CATALOG_NAME)
        tmp.rename(dst)
    except Exception as e:
        shutil.rmtree(tmp, ignore_errors=True)
        return {"ok": False, "error": f"Copie des textures impossible : {e}"}
    return {"ok": True, "copied": True, "textures_dir": str(dst)}
