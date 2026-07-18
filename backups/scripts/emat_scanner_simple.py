"""
Scanner .emat simplifie
Lit tous les .emat depuis UN SEUL dossier (pas de vanilla/customs separe)
"""

from pathlib import Path
from typing import Dict, Optional
import json
import re

# Importer fonctions du parseur original
from reforger_emat_parser import (
    parse_emat_params,
    compute_tint_srgb,
    extract_filename_from_resource_name
)


def scan_emat_directory(emat_dir: Path, catalog_path: Path) -> Dict:
    """
    Scanne un dossier contenant tous les .emat de la map
    Enrichit le catalogue avec les donnees extraites

    Args:
        emat_dir: Dossier contenant tous les .emat (vanilla + custom)
        catalog_path: Chemin vers catalog.json

    Returns:
        {
            'catalog': catalogue enrichi,
            'updated_count': nombre surfaces mises a jour,
            'warnings': liste avertissements
        }
    """
    # Charger catalogue existant
    if not catalog_path.exists():
        raise FileNotFoundError(f"Catalogue introuvable : {catalog_path}")

    with open(catalog_path, 'r', encoding='utf-8') as f:
        catalog = json.load(f)

    # Un seul dossier de recherche
    search_dirs = [emat_dir]

    warnings = []
    updated_count = 0

    # Pour chaque surface du catalogue
    for emat_name, entry in catalog.items():
        # Chercher le fichier .emat directement dans le dossier
        emat_path = emat_dir / emat_name

        if not emat_path.exists():
            warnings.append(f"Attention {emat_name} : fichier .emat absent (OK si herite)")
            # Pas grave si le fichier n'existe pas, il peut heriter d'un autre
            continue

        # Parser parametres avec heritage
        params = parse_emat_params(emat_path, search_dirs)

        # ── Extraction middle_bcr ────────────────────────────────────────────
        middle_map_ref = params.get("BCRMiddleMap")

        if not middle_map_ref:
            # Fallback sur BCRMap (detail map)
            middle_map_ref = params.get("BCRMap")
            if middle_map_ref:
                # Ce n'est plus un warning, c'est normal pour certaines textures
                pass

        if middle_map_ref:
            middle_filename = extract_filename_from_resource_name(middle_map_ref)
            auto_middle_bcr = f"{middle_filename}.jpg"

            # Mettre a jour middle_bcr
            if "middle_bcr_manual" not in entry:
                entry["middle_bcr"] = auto_middle_bcr
                if entry.get("resolved") == "fallback":
                    entry["resolved"] = "auto"

        # ── Extraction tiling_scale ──────────────────────────────────────────
        middle_scale = params.get("MiddleScaleUV", "100")
        try:
            tiling_scale = float(middle_scale)
            entry["tiling_scale"] = tiling_scale
            updated_count += 1
        except ValueError:
            warnings.append(f"Attention {emat_name} : MiddleScaleUV invalide '{middle_scale}'")
            entry["tiling_scale"] = 100.0

        # ── Calcul tint (sRGB) ───────────────────────────────────────────────
        middle_color = params.get("MiddleColor", "1 1 1 1")
        color = params.get("Color", "1 1 1 1")

        tint_rgb = compute_tint_srgb(middle_color, color)
        entry["tint_srgb"] = list(tint_rgb)

    # Sauvegarder catalogue enrichi
    with open(catalog_path, 'w', encoding='utf-8') as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)

    return {
        'catalog': catalog,
        'updated_count': updated_count,
        'warnings': warnings
    }


# Test
if __name__ == "__main__":
    import sys

    emat_dir = Path(r"H:\logiciel perso\Map generator\data\Textures_ArmaReforger\emat")
    catalog_file = Path(r"h:\logiciel perso\Map generator\data\Textures_ArmaReforger\catalog.json")

    if not emat_dir.exists():
        print(f"Dossier .emat introuvable : {emat_dir}")
        sys.exit(1)

    print(f"Scanner simplifie")
    print(f"Dossier .emat : {emat_dir}")
    print(f"Catalogue : {catalog_file}")
    print()

    # Compter fichiers .emat
    emat_files = list(emat_dir.glob("*.emat"))
    print(f"Fichiers .emat trouves : {len(emat_files)}")
    print()

    # Scanner
    result = scan_emat_directory(emat_dir, catalog_file)

    print(f"OK Catalogue enrichi : {result['updated_count']} surfaces")

    if result['warnings']:
        print(f"\nAvertissements ({len(result['warnings'])}) :")
        for w in result['warnings']:
            print(f"  {w}")
    else:
        print("\nAucun avertissement !")
