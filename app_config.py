"""
Configuration persistante de l'application
"""

import json
from pathlib import Path


CONFIG_FILE = Path(__file__).parent / "config.json"


def save_config(addon_path: str) -> None:
    """
    Sauvegarde le chemin addon dans config.json

    Args:
        addon_path: Chemin vers le dossier addon
    """
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"addon_path": addon_path}, f, indent=2)
    except Exception:
        pass


def load_config() -> str:
    """
    Charge le chemin addon depuis config.json

    Returns:
        Chemin addon ou chaîne vide si non trouvé
    """
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f).get("addon_path", "")
    except Exception:
        pass
    return ""


def resolve_paths(addon_path: str) -> dict:
    """
    Depuis le chemin addon, résout automatiquement toute l'arborescence.
    Stocke le résultat dans st.session_state.resolved_paths (si disponible)

    Structures supportées :
    1. Standard :
       addon_path/World/<nom_monde>/Terrain/
           ├── .Data/
           ├── .EditorData/
           └── <nom_monde>.terr

    2. Alternative :
       addon_path/worlds/<nom_monde>/
           ├── .Data/
           ├── .EditorData/
           └── <nom_monde>.terr

    Args:
        addon_path: Chemin vers le dossier addon

    Returns:
        Dictionnaire avec les chemins validés ou erreur
    """
    base = Path(addon_path)

    if not base.exists():
        return {"valid": False, "error": f"Dossier introuvable : {addon_path}"}

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
        return {"valid": False, "error": "Aucun dossier terrain trouvé (recherché : World/*/Terrain/, worlds/*/, ou tout dossier avec .Data/)"}

    data_dir = terrain_dir / ".Data"
    editor_dir = terrain_dir / ".EditorData"
    materials_f = terrain_dir / "terrain_materials_list.txt"

    # Vérifier existence
    if not data_dir.exists():
        return {"valid": False, "error": f".Data/ introuvable dans {terrain_dir}"}

    if not editor_dir.exists():
        return {"valid": False, "error": f".EditorData/ introuvable dans {terrain_dir}"}

    # Compter les tuiles (fichiers .bterr avec numéro)
    bterr_files = [
        f for f in editor_dir.glob("Terrain_*.bterr")
        if f.stem.replace("Terrain_", "").isdigit()
    ]
    num_tiles = len(bterr_files)
    grid_size = int(round(num_tiles ** 0.5))

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

    result = {
        "valid": True,
        "addon_path": str(base),
        "terrain_dir": str(terrain_dir),
        "data_dir": str(data_dir),
        "editor_dir": str(editor_dir),
        "materials_file": str(materials_f) if materials_f.exists() else None,
        "terr_file": terr_file,
        "num_tiles": num_tiles,
        "grid_size": grid_size,
        "world_name": world_name,
        "data_exists": data_dir.exists(),
        "editor_exists": editor_dir.exists(),
    }

    # Sauvegarder automatiquement le chemin
    save_config(addon_path)

    # Stocker dans session_state si disponible (Streamlit)
    try:
        import streamlit as st
        st.session_state.resolved_paths = result
    except:
        pass

    return result
