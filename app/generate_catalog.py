"""
generate_catalog.py - Entrées du catalog.json depuis les .emat

Fonctions utilisées par textures_sync.py (synchronisation des textures du projet) :
1. Parser un .emat avec gestion de l'héritage (parse_emat_file, resolve_inheritance)
2. Construire son entrée (build_catalog_entry : middle_bcr, tiling_scale, tint_srgb, avg_color)

Le Scan .emat et catalog_generated.json (bascule manuelle) ont été retirés à l'étape 12d.
"""

import re
import cv2
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import date


def parse_emat_file(emat_path: Path) -> Dict[str, str]:
    """
    Parse un fichier .emat et extrait ses paramètres bruts.

    Returns:
        {
            "parent": str | None,
            "BCRMiddleMap": str | "ABSENT",
            "MiddleColor": str | "ABSENT",
            "Color": str | "ABSENT",
            "MiddleScaleUV": str | "ABSENT",
            "MiddleBCRBlend": str | "ABSENT",
            "DebugColor": str | "ABSENT"
        }
    """
    params = {
        "parent": None,
        "BCRMiddleMap": "ABSENT",
        "MiddleColor": "ABSENT",
        "Color": "ABSENT",
        "MiddleScaleUV": "ABSENT",
        "MiddleBCRBlend": "ABSENT",
        "DebugColor": "ABSENT"
    }

    try:
        content = emat_path.read_text(encoding='utf-8', errors='ignore')

        # Parent (héritage)
        # Format: TerrainMaterial : "{GUID}data/Terrains/.../Parent.emat" {
        parent_match = re.search(r'TerrainMaterial\s*:\s*"[^"]*?([^/\\]+\.emat)"\s*\{', content)
        if parent_match:
            params["parent"] = parent_match.group(1)

        # BCRMiddleMap
        bcr_match = re.search(r'BCRMiddleMap\s+"([^"]+)"', content)
        if bcr_match:
            full_path = bcr_match.group(1)
            # Extraire nom de fichier sans GUID ni chemin
            name = full_path.split('/')[-1].split('\\')[-1]
            # Retirer GUID {xxx}
            name = re.sub(r'\{[^}]+\}', '', name)
            # Retirer extension .edds
            name = name.rsplit('.', 1)[0] if '.' in name else name
            params["BCRMiddleMap"] = name.strip()

        # MiddleColor (SANS guillemets, début de ligne après espaces)
        # Format: " MiddleColor 0.144 0.103 0.07 1"
        mc_match = re.search(r'^\s*MiddleColor\s+([\d\s.]+)', content, re.MULTILINE)
        if mc_match:
            params["MiddleColor"] = mc_match.group(1).strip()

        # Color (SANS guillemets, début de ligne, ne pas matcher MiddleColor/DebugColor)
        # Format: " Color 0.913 0.913 0.913 1"
        c_match = re.search(r'^\s*Color\s+([\d\s.]+)', content, re.MULTILINE)
        if c_match:
            params["Color"] = c_match.group(1).strip()

        # MiddleScaleUV (SANS guillemets)
        # Format: " MiddleScaleUV 75"
        scale_match = re.search(r'^\s*MiddleScaleUV\s+([\d.]+)', content, re.MULTILINE)
        if scale_match:
            params["MiddleScaleUV"] = scale_match.group(1).strip()

        # MiddleBCRBlend (SANS guillemets)
        blend_match = re.search(r'^\s*MiddleBCRBlend\s+([\d.]+)', content, re.MULTILINE)
        if blend_match:
            params["MiddleBCRBlend"] = blend_match.group(1).strip()

        # DebugColor (SANS guillemets)
        debug_match = re.search(r'^\s*DebugColor\s+([\d\s.]+)', content, re.MULTILINE)
        if debug_match:
            params["DebugColor"] = debug_match.group(1).strip()

    except Exception as e:
        params["_error"] = str(e)

    return params


def resolve_inheritance(emat_name: str, emat_dir: Path, cache: Dict[str, Dict]) -> Dict[str, str]:
    """
    Résout la chaîne d'héritage d'un .emat.

    Args:
        emat_name: nom du fichier .emat (avec extension)
        emat_dir: dossier contenant les .emat
        cache: {emat_name: params_resolved} pour éviter re-parsing

    Returns:
        Paramètres résolus (enfant écrase parent)
    """
    # Déjà en cache
    if emat_name in cache:
        return cache[emat_name]

    emat_path = emat_dir / emat_name
    if not emat_path.exists():
        # .emat introuvable
        cache[emat_name] = {"_missing": True}
        return cache[emat_name]

    # Parser le fichier
    params = parse_emat_file(emat_path)

    # Si a un parent, résoudre le parent d'abord
    if params["parent"]:
        parent_params = resolve_inheritance(params["parent"], emat_dir, cache)

        # Fusionner : parent puis enfant (enfant écrase)
        resolved = parent_params.copy()
        for key, value in params.items():
            if key != "parent" and value != "ABSENT":
                resolved[key] = value

        # Garder trace du parent
        resolved["_parent_chain"] = parent_params.get("_parent_chain", []) + [params["parent"]]

        cache[emat_name] = resolved
        return resolved

    # Pas de parent
    cache[emat_name] = params
    return params


def parse_color_value(value_str: str) -> np.ndarray:
    """
    Parse une valeur de couleur Enfusion.

    Format: "R G B" | "R G B A" (valeurs linéaires 0-1)

    Returns:
        np.array([R, G, B], dtype=float) en linéaire 0-1
    """
    if value_str == "ABSENT":
        return np.array([1.0, 1.0, 1.0], dtype=float)

    try:
        parts = value_str.split()
        rgb = [float(parts[0]), float(parts[1]), float(parts[2])]
        return np.array(rgb, dtype=float)
    except:
        return np.array([1.0, 1.0, 1.0], dtype=float)


def linear_to_srgb(linear: np.ndarray) -> np.ndarray:
    """
    Convertit linéaire → sRGB (composante par composante).

    Args:
        linear: np.array([R, G, B], dtype=float) en 0-1

    Returns:
        np.array([R, G, B], dtype=uint8) en 0-255
    """
    # Formule sRGB standard
    srgb = np.where(
        linear <= 0.0031308,
        linear * 12.92,
        1.055 * np.power(linear, 1.0 / 2.4) - 0.055
    )

    # Clip et arrondir
    srgb = np.clip(srgb, 0.0, 1.0)
    return np.round(srgb * 255.0).astype(np.uint8)


def compute_tint_srgb(middle_color_str: str, color_str: str) -> List[int]:
    """
    Calcul du tint sRGB depuis MiddleColor × Color.

    Args:
        middle_color_str: valeur MiddleColor du .emat ("R G B" linéaire)
        color_str: valeur Color du .emat ("R G B" linéaire)

    Returns:
        [R, G, B] en sRGB 0-255
    """
    middle_color = parse_color_value(middle_color_str)
    color = parse_color_value(color_str)

    # Produit composante par composante
    tint_linear = middle_color * color

    # Conversion sRGB
    tint_srgb = linear_to_srgb(tint_linear)

    return tint_srgb.tolist()


def compute_avg_color(middle_path: Path, tint_srgb: List[int]) -> List[int]:
    """
    Calcule la couleur moyenne du middle × tint.

    Args:
        middle_path: chemin vers le fichier middle (PNG/JPG)
        tint_srgb: [R, G, B] en sRGB 0-255

    Returns:
        [R, G, B] moyenne en sRGB 0-255
    """
    try:
        # Charger image
        img = cv2.imread(str(middle_path))
        if img is None:
            return [128, 128, 128]  # Gris par défaut

        # Appliquer tint
        tint_bgr = np.array([tint_srgb[2], tint_srgb[1], tint_srgb[0]], dtype=float) / 255.0
        img_tinted = img * tint_bgr

        # Moyenne
        avg_bgr = img_tinted.mean(axis=(0, 1))
        avg_rgb = [int(avg_bgr[2]), int(avg_bgr[1]), int(avg_bgr[0])]

        return avg_rgb

    except Exception:
        return [128, 128, 128]


def find_middle_file(middle_name: str, middles_dir: Path) -> Optional[Path]:
    """
    Cherche le fichier middle avec extensions .jpg ou .png.

    Args:
        middle_name: nom sans extension (ex: "Dirt_01_Middle_BCR")

    Returns:
        Path du fichier trouvé ou None
    """
    if middle_name == "ABSENT":
        return None

    for ext in ['.jpg', '.png', '.jpeg', '.JPG', '.PNG']:
        middle_path = middles_dir / (middle_name + ext)
        if middle_path.exists():
            return middle_path

    return None


def build_catalog_entry(emat_name: str, emat_dir: Path, middles_dir: Path,
                        inheritance_cache: Dict[str, Dict]) -> Tuple[dict, List[str], Optional[str]]:
    """
    Construit l'entrée du catalog d'un .emat (héritage résolu, middle cherché dans middles_dir).

    Returns:
        (entrée, parents introuvables ["emat → parent"], middle manquant "emat → middle" ou None)
    """
    parent_missing = []
    middle_missing = None

    # Résoudre héritage
    params = resolve_inheritance(emat_name, emat_dir, inheritance_cache)

    # Vérifier si parent introuvable
    if "_parent_chain" in params:
        for parent_name in params["_parent_chain"]:
            parent_path = emat_dir / parent_name
            if not parent_path.exists():
                parent_missing.append(f"{emat_name} → {parent_name}")

    # Construire entrée
    entry = {}

    # middle_bcr
    bcr_name = params.get("BCRMiddleMap", "ABSENT")
    if bcr_name != "ABSENT":
        # Remplacer extension .edds par .png
        middle_bcr = bcr_name + ".png"

        # Vérifier existence dans texture_Middle/
        middle_path = find_middle_file(bcr_name, middles_dir)
        if middle_path:
            # Utiliser extension réelle trouvée
            middle_bcr = middle_path.name
        else:
            # Fichier manquant
            middle_missing = f"{emat_name} → {bcr_name}"
    else:
        middle_bcr = None
        middle_path = None

    # tiling_scale
    scale_str = params.get("MiddleScaleUV", "ABSENT")
    if scale_str != "ABSENT":
        try:
            # Prendre premier nombre (format "X Y")
            tiling_scale = float(scale_str.split()[0])
        except:
            tiling_scale = 100.0
    else:
        tiling_scale = 100.0  # Valeur par défaut moteur Workbench

    # tint_srgb
    middle_color_str = params.get("MiddleColor", "ABSENT")
    color_str = params.get("Color", "ABSENT")
    tint_srgb = compute_tint_srgb(middle_color_str, color_str)

    # avg_color
    if middle_path and middle_path.exists():
        avg_color = compute_avg_color(middle_path, tint_srgb)
    else:
        avg_color = [128, 128, 128]

    # Construire entrée avec TOUS les champs du schéma
    entry = {
        "provenance": "vanilla",
        "parent": params.get("_parent_chain", [])[-1] if "_parent_chain" in params else None,
        "middle_bcr": middle_bcr,
        "avg_color": avg_color,
        "tint": tint_srgb,  # Ancien champ (même valeur que tint_srgb)
        "role": "auto_generated",  # Rôle générique
        "resolved": "auto",
        "resolved_date": str(date.today()),
        "tiling_scale": tiling_scale,
        "tint_srgb": tint_srgb
    }

    # Ajouter champs info supplémentaires (source, raw values)
    entry["source"] = "emat"
    entry["middle_color_raw"] = middle_color_str
    entry["color_raw"] = color_str

    return entry, parent_missing, middle_missing
