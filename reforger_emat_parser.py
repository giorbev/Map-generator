"""
Parseur .emat pour Arma Reforger
Extrait les paramètres de texture depuis les fichiers .emat (texte)
Suit les références parent (TerrainMaterial) récursivement
"""

from pathlib import Path
from typing import Dict, Optional, Tuple, List
import json
import re


# ══════════════════════════════════════════════════════════════════════════════
# Paramètres par défaut
# ══════════════════════════════════════════════════════════════════════════════

DEFAULT_PARAMS = {
    "BCRMiddleMap": None,
    "BCRMap": None,  # Fallback si pas de middle
    "MiddleScaleUV": "100",  # Taille tuile en mètres
    "MiddleColor": "1 1 1 1",  # RGBA linéaire
    "Color": "1 1 1 1",  # RGBA linéaire
}


# ══════════════════════════════════════════════════════════════════════════════
# Conversion espace couleur
# ══════════════════════════════════════════════════════════════════════════════

def linear_to_srgb_component(c: float) -> float:
    """Convertit une composante linéaire → sRGB (formule standard)"""
    if c <= 0.0031308:
        return 12.92 * c
    else:
        return 1.055 * (c ** (1 / 2.4)) - 0.055


def linear_to_srgb(rgba_linear: Tuple[float, float, float, float]) -> Tuple[float, float, float, float]:
    """Convertit RGBA linéaire → sRGB"""
    return tuple(linear_to_srgb_component(c) for c in rgba_linear)


def parse_rgba_string(rgba_str: str) -> Tuple[float, float, float, float]:
    """Parse 'R G B A' string → tuple float"""
    parts = rgba_str.strip().split()
    if len(parts) != 4:
        return (1.0, 1.0, 1.0, 1.0)
    try:
        return tuple(float(p) for p in parts)
    except ValueError:
        return (1.0, 1.0, 1.0, 1.0)


def compute_tint_srgb(middle_color_str: str, color_str: str) -> Tuple[int, int, int]:
    """
    Calcule la teinte finale sRGB depuis MiddleColor × Color (linéaires)

    Recette exacte du code TilW :
    1. Parser MiddleColor et Color (RGBA linéaire)
    2. Produit composante par composante
    3. Conversion linéaire → sRGB
    4. Clamp [0, 1] → [0, 255]
    """
    middle = parse_rgba_string(middle_color_str)
    color = parse_rgba_string(color_str)

    # Produit linéaire
    linear_product = tuple(m * c for m, c in zip(middle, color))

    # Conversion sRGB
    srgb = linear_to_srgb(linear_product)

    # Clamp et scale RGB (ignore alpha)
    rgb_255 = tuple(max(0, min(255, int(s * 255))) for s in srgb[:3])

    return rgb_255


# ══════════════════════════════════════════════════════════════════════════════
# Parseur .emat (fichier texte)
# ══════════════════════════════════════════════════════════════════════════════

def search_emat_line(emat_path: Path, param_name: str) -> Optional[str]:
    """
    Cherche une ligne contenant ' param_name ' dans le .emat
    Retourne la valeur après le param (tout après le param jusqu'à fin de ligne)
    """
    if not emat_path.exists():
        return None

    try:
        with open(emat_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                # Recherche ' ParamName ' (avec espaces pour éviter faux positifs)
                parts = line.split(f" {param_name} ")
                if len(parts) == 2:
                    # Valeur = tout après le param, sans \n
                    return parts[1].rstrip('\n').strip()
    except Exception:
        return None

    return None


def extract_filename_from_resource_name(resource_name: str) -> str:
    """
    Extrait le nom de fichier depuis un chemin ressource Reforger

    Exemple :
    '{GUID}Textures/Terrain/Grass_01_Middle_BCR.edds' → 'Grass_01_Middle_BCR'
    """
    # Dernier segment avant extension
    # Split par '.' → prendre avant-dernier élément → split par '/' → dernier
    parts = resource_name.split('.')
    if len(parts) < 2:
        return resource_name

    # Avant extension
    path_part = parts[-2]
    # Dernier segment du path
    filename = path_part.split('/')[-1]

    return filename


def find_emat_file(search_dirs: List[Path], emat_name: str) -> Optional[Path]:
    """
    Cherche un fichier .emat dans les dossiers Vanilla/ et Customs/

    Args:
        search_dirs: Liste [Vanilla/, Customs/]
        emat_name: Nom du .emat (avec ou sans extension)

    Returns:
        Path du .emat trouvé, ou None
    """
    if not emat_name.endswith('.emat'):
        emat_name = f"{emat_name}.emat"

    for search_dir in search_dirs:
        # Recherche récursive
        matches = list(search_dir.rglob(emat_name))
        if matches:
            return matches[0]

    return None


def parse_emat_params(
    emat_path: Path,
    search_dirs: List[Path],
    visited: Optional[set] = None
) -> Dict[str, str]:
    """
    Parse un .emat et résout les paramètres avec héritage récursif

    Args:
        emat_path: Chemin du .emat à parser
        search_dirs: Dossiers où chercher les parents [Vanilla/, Customs/]
        visited: Set des .emat déjà visités (évite boucles infinies)

    Returns:
        Dict des paramètres résolus (valeurs finales après héritage)
    """
    if visited is None:
        visited = set()

    # Protection boucle infinie
    emat_key = str(emat_path.resolve())
    if emat_key in visited:
        return DEFAULT_PARAMS.copy()
    visited.add(emat_key)

    # Parser les paramètres directs
    params = {}

    for param_name in DEFAULT_PARAMS.keys():
        value = search_emat_line(emat_path, param_name)
        if value is not None:
            params[param_name] = value

    # Chercher parent
    parent_ref = search_emat_line(emat_path, "TerrainMaterial :")

    if parent_ref:
        # Extraire nom fichier parent
        parent_name = extract_filename_from_resource_name(parent_ref)
        parent_path = find_emat_file(search_dirs, parent_name)

        if parent_path:
            # Résoudre récursivement
            parent_params = parse_emat_params(parent_path, search_dirs, visited)

            # Héritage : parent puis override local
            result = parent_params.copy()
            result.update(params)
            return result

    # Pas de parent : merge avec defaults
    result = DEFAULT_PARAMS.copy()
    result.update(params)
    return result


# ══════════════════════════════════════════════════════════════════════════════
# Enrichissement catalogue
# ══════════════════════════════════════════════════════════════════════════════

def enrich_catalog_with_emat_data(
    catalog_path: Path,
    vanilla_dir: Path,
    customs_dir: Path
) -> Dict:
    """
    Enrichit le catalogue existant avec les données extraites des .emat

    Pour chaque surface du catalogue :
    1. Parse le .emat correspondant
    2. Extrait middle_bcr, tiling_scale, tint (auto)
    3. Met à jour le catalogue
    4. Détecte divergences zi_ (warning si convention ≠ parseur)

    Args:
        catalog_path: Chemin vers catalog.json
        vanilla_dir: Dossier Vanilla/
        customs_dir: Dossier Customs/

    Returns:
        Catalogue enrichi + rapport divergences
    """
    # Charger catalogue existant
    if not catalog_path.exists():
        raise FileNotFoundError(f"Catalogue introuvable : {catalog_path}")

    with open(catalog_path, 'r', encoding='utf-8') as f:
        catalog = json.load(f)

    search_dirs = [vanilla_dir, customs_dir]

    warnings = []
    updated_count = 0

    for emat_name, entry in catalog.items():
        # Chercher le .emat
        emat_path = find_emat_file(search_dirs, emat_name)

        if not emat_path:
            warnings.append(f"⚠️ {emat_name} : fichier .emat introuvable")
            continue

        # Parser paramètres avec héritage
        params = parse_emat_params(emat_path, search_dirs)

        # ── Extraction middle_bcr ────────────────────────────────────────────
        middle_map_ref = params.get("BCRMiddleMap")

        if not middle_map_ref:
            # Fallback sur BCRMap (detail map)
            middle_map_ref = params.get("BCRMap")
            if middle_map_ref:
                warnings.append(f"⚠️ {emat_name} : BCRMiddleMap absent, fallback BCRMap")

        if middle_map_ref:
            middle_filename = extract_filename_from_resource_name(middle_map_ref)

            # Vérifier si différent de l'existant
            existing_middle = entry.get("middle_bcr", "")
            auto_middle_bcr = f"{middle_filename}.jpg"  # Convention PNG → JPG

            # Ne pas écraser les entrées manuelles
            if entry.get("resolved") != "manual":
                entry["middle_bcr"] = auto_middle_bcr
                entry["resolved"] = "auto"
                updated_count += 1

        # ── Extraction tiling_scale ──────────────────────────────────────────
        middle_scale = params.get("MiddleScaleUV", "100")
        try:
            tiling_scale = float(middle_scale)
            entry["tiling_scale"] = tiling_scale
        except ValueError:
            warnings.append(f"⚠️ {emat_name} : MiddleScaleUV invalide '{middle_scale}'")
            entry["tiling_scale"] = 100.0

        # ── Calcul tint (sRGB) ───────────────────────────────────────────────
        middle_color = params.get("MiddleColor", "1 1 1 1")
        color = params.get("Color", "1 1 1 1")

        tint_rgb = compute_tint_srgb(middle_color, color)

        # Ne pas écraser les tints manuels
        if "tint_manual" not in entry:
            entry["tint"] = list(tint_rgb)

    # ── Vérification divergences zi_ convention ─────────────────────────────
    for emat_name, entry in catalog.items():
        if not emat_name.upper().startswith("ZI_"):
            continue

        # Nom parent attendu par convention
        parent_name = emat_name[3:]  # Enlever 'ZI_'

        if parent_name in catalog:
            parent_entry = catalog[parent_name]

            # Comparer middle_bcr
            if entry.get("middle_bcr") != parent_entry.get("middle_bcr"):
                warnings.append(
                    f"🔍 {emat_name} : middle_bcr diverge du parent {parent_name}\n"
                    f"   Convention attendrait : {parent_entry.get('middle_bcr')}\n"
                    f"   Parseur a trouvé : {entry.get('middle_bcr')}"
                )

    # Sauvegarder catalogue enrichi
    with open(catalog_path, 'w', encoding='utf-8') as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)

    return {
        "catalog": catalog,
        "updated_count": updated_count,
        "warnings": warnings,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Test rapide
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    import io

    # Force UTF-8 pour console Windows
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

    # Chemins test
    catalog_root = Path("data/Textures_ArmaReforger")
    catalog_file = catalog_root / "catalog.json"
    vanilla = catalog_root / "Vanilla"
    customs = catalog_root / "Customs"

    if not catalog_file.exists():
        print(f"❌ Catalogue introuvable : {catalog_file}")
        sys.exit(1)

    print("[INFO] Enrichissement catalogue avec parseur .emat...")
    print()

    result = enrich_catalog_with_emat_data(catalog_file, vanilla, customs)

    print(f"[OK] Catalogue enrichi : {result['updated_count']} surfaces mises a jour")
    print()

    if result['warnings']:
        print(f"[WARN] Avertissements ({len(result['warnings'])}) :")
        for w in result['warnings'][:20]:  # Limite 20
            print(f"  {w}")

        if len(result['warnings']) > 20:
            print(f"  ... et {len(result['warnings']) - 20} autres")
    else:
        print("[OK] Aucun avertissement")

    print()
    print(f"[INFO] Catalogue sauvegarde : {catalog_file}")
