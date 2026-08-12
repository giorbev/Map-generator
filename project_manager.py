"""
project_manager.py — Gestion surfaces.json par projet

Charge ou génère surfaces.json depuis le .terr du projet.
Source unique de vérité pour les matériaux terrain.
"""

from pathlib import Path
from datetime import datetime
import json
from terrain_terr_reader import read_mats_from_terr


def load_or_update_surfaces(project_path: str | Path, terr_path: str | Path) -> tuple[dict, dict]:
    """
    Charge ou met à jour surfaces.json pour un projet.

    Vérifie si le fichier surfaces.json existe et si le .terr a changé.
    Si le .terr est différent (chemin ou taille), régénère surfaces.json.

    Args:
        project_path: Chemin vers data/projects/<projet>
        terr_path: Chemin vers le .terr du projet

    Returns:
        (name_to_id, id_to_name): Deux dicts pour résolution bidirectionnelle
        - name_to_id: {"Grass_01": 0, "Dirt_02": 1, ...}
        - id_to_name: {0: "Grass_01", 1: "Dirt_02", ...}

    Raises:
        FileNotFoundError: Si le .terr n'existe pas
    """
    project_path = Path(project_path)
    terr_path = Path(terr_path)
    surfaces_json_path = project_path / "surfaces.json"

    # Lire métadonnées .terr
    if not terr_path.exists():
        raise FileNotFoundError(f"Fichier .terr introuvable: {terr_path}")

    terr_size = terr_path.stat().st_size
    terr_path_str = str(terr_path)

    # Vérifier si mise à jour nécessaire
    need_update = True
    materials = {}

    if surfaces_json_path.exists():
        try:
            data = json.loads(surfaces_json_path.read_text(encoding='utf-8'))
            if (data.get("terr_path") == terr_path_str and
                data.get("terr_size") == terr_size):
                print("[SURFACES] OK, pas de changement")
                need_update = False
                materials = data.get("materials", {})
            else:
                print("[SURFACES] Mise à jour détectée")
        except Exception as e:
            print(f"[SURFACES] Fichier corrompu ({e}), régénération")

    # Générer/mettre à jour si nécessaire
    if need_update:
        # Lire matériaux depuis .terr
        mats = read_mats_from_terr(terr_path)
        materials = {m['name']: m['id'] for m in mats}

        # Sauvegarder surfaces.json
        data = {
            "terr_path": terr_path_str,
            "terr_size": terr_size,
            "generated": datetime.now().isoformat(),
            "count": len(materials),
            "materials": materials
        }

        project_path.mkdir(parents=True, exist_ok=True)
        surfaces_json_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )
        print(f"[SURFACES] Généré: {len(materials)} matériaux")

    # Retourner dicts bidirectionnels
    name_to_id = materials
    id_to_name = {v: k for k, v in materials.items()}

    return name_to_id, id_to_name


def resolve_mask_config(name_to_id: dict, mask_config: list) -> list:
    """
    Résout une config de masques en remplaçant noms texture → IDs.

    Args:
        name_to_id: Dict {nom_texture: id} depuis surfaces.json
        mask_config: Liste [(nom_masque, texture_name, color), ...]

    Returns:
        Liste [(nom_masque, mat_id, color), ...] avec IDs résolus

    Si une texture n'existe pas dans le .terr, utilise fallback "default" (ID 0).
    """
    resolved = []

    for name, texture_name, color in mask_config:
        mat_id = name_to_id.get(texture_name)

        if mat_id is None:
            # Fallback sur "default" ou index 0
            mat_id = name_to_id.get("default", 0)
            print(f"[WARN] Texture '{texture_name}' absente du .terr, fallback index {mat_id}")

        resolved.append((name, mat_id, color))

    return resolved


def load_mask_config(project_dir: str | Path) -> dict:
    """
    Charge la configuration masque→texture du projet.

    Args:
        project_dir: Chemin vers data/projects/<projet>

    Returns:
        Dict {nom_masque: nom_texture}
        Ex: {"mask_seabed": "SeaBed_01", "mask_coastal": "BeachGrass_01", ...}

    Ordre de priorité:
    1. Charge project_mask_config.json si existe
    2. Sinon : matching par nom depuis DEFAULT_MASK_CONFIG
    3. Fallback : "default" pour chaque masque
    """
    project_dir = Path(project_dir)
    config_path = project_dir / "project_mask_config.json"

    # Charger depuis fichier si existe
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text(encoding='utf-8'))
            return data.get("mask_config", {})
        except Exception as e:
            print(f"[MASK_CONFIG] Erreur lecture {config_path}: {e}")

    # Fallback : matching depuis DEFAULT_MASK_CONFIG
    try:
        import pipeline_v5 as pv5
        config = {}
        for name, texture_name, _ in pv5.DEFAULT_MASK_CONFIG:
            config[name] = texture_name
        return config
    except Exception as e:
        print(f"[MASK_CONFIG] Erreur chargement DEFAULT_MASK_CONFIG: {e}")
        # Fallback ultime : dict vide
        return {}


def save_mask_config(project_dir: str | Path, config: dict) -> None:
    """
    Sauvegarde la configuration masque→texture du projet.

    Args:
        project_dir: Chemin vers data/projects/<projet>
        config: Dict {nom_masque: nom_texture}
    """
    project_dir = Path(project_dir)
    config_path = project_dir / "project_mask_config.json"

    print(f"[MASK_CONFIG] Tentative sauvegarde : {config_path}")

    data = {
        "updated": datetime.now().isoformat(),
        "mask_config": config
    }

    # Créer le dossier si absent
    project_dir.mkdir(parents=True, exist_ok=True)
    print(f"[MASK_CONFIG] Dossier vérifié/créé : {project_dir}")

    config_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding='utf-8'
    )

    print(f"[MASK_CONFIG] Sauvegardé avec succès : {config_path}")


def parse_workbench_info(text: str) -> dict | None:
    """
    Parse les informations terrain depuis General Info de Workbench.

    Extrait les valeurs clés depuis le texte brut copié depuis
    Workbench → Terrain → General Info.

    Format attendu (valeur sur ligne suivante) :
        Tiles:
        64 x 64
        Blocks per tile:
        4 x 4
        Planar resolution:
        1 m

    Args:
        text: Texte brut copié depuis Workbench General Info

    Returns:
        dict {grid_w, num_blk, cell_size} ou None si parsing échoué

    Example:
        >>> text = "Tiles:\\n64 x 64\\nBlocks per tile:\\n4 x 4\\nPlanar resolution:\\n1 m"
        >>> result = parse_workbench_info(text)
        >>> result
        {'grid_w': 64, 'num_blk': 4, 'cell_size': 1.0}
    """
    import re

    if not text or not text.strip():
        return None

    result = {}

    # Pattern Tiles:\n64 x 64
    # Cherche "Tiles:" suivi d'un saut de ligne puis "X x Y"
    tiles_match = re.search(r'Tiles:?\s*\n\s*(\d+)\s*x\s*(\d+)', text, re.IGNORECASE | re.MULTILINE)
    if tiles_match:
        result['grid_w'] = int(tiles_match.group(1))
    else:
        return None  # Obligatoire

    # Pattern Blocks per tile:\n4 x 4
    blocks_match = re.search(r'Blocks\s+per\s+tile:?\s*\n\s*(\d+)\s*x\s*(\d+)', text, re.IGNORECASE | re.MULTILINE)
    if blocks_match:
        result['num_blk'] = int(blocks_match.group(1))
    else:
        return None  # Obligatoire

    # Pattern Planar resolution:\n1 m ou 1.0 m
    resolution_match = re.search(r'Planar\s+resolution:?\s*\n\s*(\d+(?:\.\d+)?)\s*m', text, re.IGNORECASE | re.MULTILINE)
    if resolution_match:
        result['cell_size'] = float(resolution_match.group(1))
    else:
        return None  # Obligatoire

    return result


def save_project_calibration(project_dir: str | Path, calibration: dict) -> None:
    """Sauvegarde la calibration active dans project.json"""
    import json
    from datetime import datetime
    p = Path(project_dir) / "project.json"
    if not p.exists():
        return
    data = json.loads(p.read_text(encoding='utf-8'))
    data["pipeline_calibration"] = {
        "updated": datetime.now().isoformat(),
        "values": calibration
    }
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"[CALIB] Sauvegardé dans {p}")


def load_project_calibration(project_dir: str | Path) -> dict:
    """Charge la calibration depuis project.json"""
    import json
    p = Path(project_dir) / "project.json"
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding='utf-8'))
    return data.get("pipeline_calibration", {}).get("values", {})
