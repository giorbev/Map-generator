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

    Structure attendue :
    addon_path/
    └── World/
        └── [nom_monde]/
            └── Terrain/
                ├── .Data/          (Terrain_N.ttile, Terrain_N_layer.edds)
                └── .EditorData/    (Terrain_N.bterr, Terrain_N_layer.dds)

    Args:
        addon_path: Chemin vers le dossier addon

    Returns:
        Dictionnaire avec les chemins validés ou erreur
    """
    base = Path(addon_path)

    if not base.exists():
        return {"valid": False, "error": f"Dossier introuvable : {addon_path}"}

    # Chercher Terrain/ sous World/[nom_monde]/
    terrain_dir = None
    for candidate in base.glob("World/*/Terrain"):
        if candidate.is_dir():
            terrain_dir = candidate
            break

    # Fallback : chercher Terrain/ récursivement
    if terrain_dir is None:
        for candidate in base.rglob("Terrain"):
            if candidate.is_dir() and (candidate / ".Data").exists():
                terrain_dir = candidate
                break

    if terrain_dir is None:
        return {"valid": False, "error": "Dossier Terrain/ introuvable"}

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
    terr_files = list(terrain_dir.glob("*.terr"))
    terr_file = str(terr_files[0]) if terr_files else None

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
        "world_name": terrain_dir.parent.name,
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
