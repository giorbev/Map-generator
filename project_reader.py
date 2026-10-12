# -*- coding: utf-8 -*-
"""
project_reader.py — Module unique de résolution des informations projet

Source de vérité : project.json du projet ouvert
Aucune valeur par défaut en dur, aucun import streamlit, aucune écriture disque.

Décisions :
1. Addon Reforger = paths.addon_reforger UNIQUEMENT
2. Grille = 4 clés à la racine : grid_w, num_blk, tile_size_m, surface_tile_px
3. m_per_px = TOUJOURS calculé (tile_size_m / surface_tile_px)
4. Préfixe = détecté depuis *.ttile dans .Data/, unicité vérifiée
5. Budget = pipeline.reforger_block_limit (5, 7, ou None)
"""

import json
import re
from pathlib import Path
from typing import Dict, Any, Optional


def load_project(project_dir: Path) -> dict:
    """
    Charge le project.json depuis le dossier projet.

    Args:
        project_dir: Chemin vers le dossier du projet

    Returns:
        Dictionnaire du project.json

    Raises:
        FileNotFoundError: Si project.json n'existe pas
        json.JSONDecodeError: Si le fichier est invalide
    """
    project_json = project_dir / "project.json"
    if not project_json.exists():
        raise FileNotFoundError(f"project.json introuvable : {project_json}")

    return json.loads(project_json.read_text(encoding="utf-8"))


def get_addon_path(project_dir: Path) -> Dict[str, Any]:
    """
    Retourne le chemin de l'addon Reforger depuis paths.addon_reforger.

    Args:
        project_dir: Chemin vers le dossier du projet

    Returns:
        {"ok": True, "addon_path": str} ou {"ok": False, "error": str}
    """
    try:
        data = load_project(project_dir)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        return {"ok": False, "error": str(e)}

    addon_path = data.get("paths", {}).get("addon_reforger", "")
    if not addon_path:
        return {"ok": False, "error": f"Chemin addon_reforger non configuré dans {project_dir / 'project.json'}"}

    return {"ok": True, "addon_path": addon_path}


def get_terrain_dirs(project_dir: Path) -> Dict[str, Any]:
    """
    Résout les chemins terrain Reforger depuis addon_reforger.

    Reprend la logique de app_config.resolve_paths() sans import streamlit.

    Args:
        project_dir: Chemin vers le dossier du projet

    Returns:
        {
            "ok": True,
            "terrain_dir": str,
            "data_dir": str,
            "editor_dir": str,
            "terr_file": str ou None,
            "world_name": str
        }
        ou {"ok": False, "error": str}
    """
    addon_result = get_addon_path(project_dir)
    if not addon_result["ok"]:
        return addon_result

    addon_path = addon_result["addon_path"]
    base = Path(addon_path)

    if not base.exists():
        return {"ok": False, "error": f"Dossier addon introuvable : {base}"}

    # Chercher le dossier terrain (avec .Data/ et .EditorData/)
    terrain_dir = None

    # 1. Structure standard : World/<nom_monde>/Terrain/
    for candidate in base.glob("World/*/Terrain"):
        if candidate.is_dir() and (candidate / ".Data").exists():
            terrain_dir = candidate
            break

    # 2. Structure alternative : worlds/<nom_monde>/ (directement)
    if terrain_dir is None:
        for candidate in base.glob("worlds/*"):
            if candidate.is_dir() and (candidate / ".Data").exists():
                terrain_dir = candidate
                break

    # 3. Fallback : chercher récursivement n'importe quel dossier avec .Data/
    if terrain_dir is None:
        for candidate in base.rglob(".Data"):
            if candidate.is_dir():
                terrain_dir = candidate.parent
                break

    if terrain_dir is None:
        return {
            "ok": False,
            "error": f"Aucun dossier terrain trouvé dans {base} (recherché : World/*/Terrain/, worlds/*/, ou tout dossier avec .Data/)"
        }

    data_dir = terrain_dir / ".Data"
    editor_dir = terrain_dir / ".EditorData"

    # Vérifier existence
    if not data_dir.exists():
        return {"ok": False, "error": f".Data/ introuvable dans {terrain_dir}"}

    if not editor_dir.exists():
        return {"ok": False, "error": f".EditorData/ introuvable dans {terrain_dir}"}

    # Fichier .terr
    # 1. Chercher d'abord dans terrain_dir lui-même (structure alternative)
    terr_files = list(terrain_dir.glob("*.terr"))
    terr_files_full = [f for f in terr_files if f.stat().st_size > 1000]

    # 2. Si pas trouvé, chercher dans parent (structure standard)
    if not terr_files_full:
        search_root = terrain_dir.parent
        terr_files = list(search_root.rglob("*.terr"))
        terr_files_full = [f for f in terr_files if f.stat().st_size > 1000]

    # 3. Sélectionner le premier .terr valide trouvé
    if terr_files_full:
        terr_file = str(terr_files_full[0])
    elif terr_files:
        terr_file = str(terr_files[0])  # Fallback même si petit (stub)
    else:
        terr_file = None

    # Détecter la structure pour déterminer world_name
    # Structure standard : .../World/<nom_monde>/Terrain/ → world_name = parent.name
    # Structure alternative : .../worlds/<nom_monde>/ → world_name = terrain_dir.name
    if terrain_dir.name == "Terrain":
        world_name = terrain_dir.parent.name
    else:
        world_name = terrain_dir.name

    return {
        "ok": True,
        "terrain_dir": str(terrain_dir),
        "data_dir": str(data_dir),
        "editor_dir": str(editor_dir),
        "terr_file": terr_file,
        "world_name": world_name,
    }


def get_grid(project_dir: Path) -> Dict[str, Any]:
    """
    Lit la configuration grille depuis les 4 clés à la racine de project.json.

    Args:
        project_dir: Chemin vers le dossier du projet

    Returns:
        {
            "ok": True,
            "grid_w": int,
            "num_blk": int,
            "tile_size_m": int,
            "surface_tile_px": int,
            "m_per_px": float,
            "terrain_size_m": int
        }
        ou {"ok": False, "error": str, "missing": list}
    """
    try:
        data = load_project(project_dir)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        return {"ok": False, "error": str(e)}

    # Vérifier clés obligatoires À LA RACINE
    required = ["grid_w", "num_blk", "tile_size_m", "surface_tile_px"]
    missing = []
    values = {}

    for key in required:
        val = data.get(key)
        if val is None or not isinstance(val, (int, float)) or val <= 0:
            missing.append(key)
        else:
            values[key] = int(val)

    if missing:
        missing_str = ", ".join(missing)
        return {
            "ok": False,
            "missing": missing,
            "error": f"Grille non configurée dans {project_dir / 'project.json'} (manque : {missing_str}) : collez le texte Workbench General Info dans Terrain > Paths & Files puis cliquez sur Apply Reforger grid"
        }

    # Calculs
    m_per_px = values["tile_size_m"] / values["surface_tile_px"]
    terrain_size_m = values["grid_w"] * values["tile_size_m"]

    return {
        "ok": True,
        "grid_w": values["grid_w"],
        "num_blk": values["num_blk"],
        "tile_size_m": values["tile_size_m"],
        "surface_tile_px": values["surface_tile_px"],
        "m_per_px": m_per_px,
        "terrain_size_m": terrain_size_m,
    }


def get_tile_prefix(data_dir: Path) -> Dict[str, Any]:
    """
    Détecte le préfixe des tuiles .ttile dans .Data/ avec vérification d'unicité.

    Args:
        data_dir: Chemin vers le dossier .Data

    Returns:
        {"ok": True, "tile_prefix": str, "num_tiles": int}
        ou {"ok": False, "error": str}
    """
    if not data_dir.exists():
        return {"ok": False, "error": f"Dossier .Data introuvable : {data_dir}"}

    ttile_files = list(data_dir.glob("*.ttile"))

    if not ttile_files:
        return {"ok": False, "error": f"Aucun fichier .ttile trouvé dans {data_dir}"}

    # Extraire préfixe depuis les fichiers (ex: "Terrain_0.ttile" → "Terrain_")
    prefixes = set()
    for f in ttile_files[:10]:  # Vérifier 10 premiers fichiers max
        match = re.match(r'^(.*?)(\d+)\.ttile$', f.name)
        if match:
            prefixes.add(match.group(1))

    if len(prefixes) != 1:
        return {
            "ok": False,
            "error": f"Préfixes multiples détectés dans {data_dir} : {prefixes}. Attendu : un seul préfixe."
        }

    tile_prefix = prefixes.pop()

    # Compter les tuiles avec ce préfixe
    num_tiles = len([f for f in ttile_files if re.match(rf'^{re.escape(tile_prefix)}\d+\.ttile$', f.name)])

    return {
        "ok": True,
        "tile_prefix": tile_prefix,
        "num_tiles": num_tiles,
    }


def get_block_budget(project_dir: Path) -> Optional[int]:
    """
    Retourne le budget QTRE textures/bloc (5 ou 7).

    Args:
        project_dir: Chemin vers le dossier du projet

    Returns:
        5, 7, ou None si non configuré ou invalide
    """
    try:
        data = load_project(project_dir)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

    budget = data.get("pipeline", {}).get("reforger_block_limit")

    if budget in (5, 7):
        return budget

    return None


def get_project_info(project_dir: Path) -> Dict[str, Any]:
    """
    Retourne toutes les informations du projet réunies.

    Args:
        project_dir: Chemin vers le dossier du projet

    Returns:
        {
            "ok": True,
            "project_dir": str,
            "addon_path": str,
            "terrain_dir": str,
            "data_dir": str,
            "editor_dir": str,
            "terr_file": str ou None,
            "world_name": str,
            "grid_w": int,
            "num_blk": int,
            "tile_size_m": int,
            "surface_tile_px": int,
            "m_per_px": float,
            "terrain_size_m": int,
            "tile_prefix": str,
            "num_tiles": int,
            "block_budget": int ou None,
        }
        ou {"ok": False, "error": str}
    """
    # 1. Addon path
    addon = get_addon_path(project_dir)
    if not addon["ok"]:
        return addon
    
    # 2. Terrain dirs
    terrain = get_terrain_dirs(project_dir)
    if not terrain["ok"]:
        return terrain
    
    # 3. Grille
    grid = get_grid(project_dir)
    if not grid["ok"]:
        return grid

    # 4. Préfixe
    prefix = get_tile_prefix(Path(terrain["data_dir"]))
    if not prefix["ok"]:
        return prefix

    # 5. Budget
    budget = get_block_budget(project_dir)

    # Combiner
    return {
        "ok": True,
        "project_dir": str(project_dir),
        "addon_path": addon["addon_path"],
        "terrain_dir": terrain["terrain_dir"],
        "data_dir": terrain["data_dir"],
        "editor_dir": terrain["editor_dir"],
        "terr_file": terrain["terr_file"],
        "world_name": terrain["world_name"],
        "grid_w": grid["grid_w"],
        "num_blk": grid["num_blk"],
        "tile_size_m": grid["tile_size_m"],
        "surface_tile_px": grid["surface_tile_px"],
        "m_per_px": grid["m_per_px"],
        "terrain_size_m": grid["terrain_size_m"],
        "tile_prefix": prefix["tile_prefix"],
        "num_tiles": prefix["num_tiles"],
        "block_budget": budget,
    }
