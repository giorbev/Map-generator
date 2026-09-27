"""
diag_middles.py - Diagnostic complet de résolution des textures middle_bcr
Reproduit EXACTEMENT la logique de satmap_v2_textured_v2.py (get_material_middle)
+ Analyse de couverture + Diagnostic MISS + Diagnostic EMAT
"""

import json
import cv2
import numpy as np
import difflib
from pathlib import Path
from typing import Dict, Optional, List, Tuple
from collections import defaultdict

from catalog_config import get_catalog_path, TEXTURES_USER_DIR
from reforger_emat_parser import parse_emat_params, compute_tint_srgb
from terrain_terr_reader import read_mats_from_terr
from layer_dds_reader import read_layer_dds, extract_all_weights
from lrs2_parser import load_lrs2_from_ttile


def resolve_catalog_entry(surface_name: str, catalog: dict) -> dict | None:
    """Cherche surface_name dans catalog (copie de satmap_v2_textured_v2.py)."""
    entry = catalog.get(surface_name) or catalog.get(surface_name + ".emat")
    return entry


def get_avg_color_from_middle(middle_path: Path) -> Optional[Tuple[int, int, int]]:
    """Calcule la couleur moyenne d'une texture middle."""
    try:
        img = cv2.imread(str(middle_path))
        if img is None:
            return None
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        avg = img_rgb.mean(axis=(0, 1))
        return tuple(int(c) for c in avg)
    except:
        return None


def find_similar_files(target: str, files_list: List[str], n: int = 3) -> List[str]:
    """Trouve les n fichiers les plus proches du nom cible (difflib)."""
    matches = difflib.get_close_matches(target, files_list, n=n, cutoff=0.3)
    return matches


def analyze_material(
    surface_name: str,
    catalog: Dict,
    middles_dir: Path,
    emat_dir: Path,
    all_middle_files: List[str]
) -> Dict:
    """
    Analyse la résolution d'un matériau (reproduit get_material_middle).

    Returns:
        {
            "surface": str,
            "middle_found": bool,
            "miss_reason": Optional[str],  # NO_CATALOG_ENTRY | NO_MIDDLE_BCR | FILE_NOT_FOUND
            "expected_file": Optional[str],
            "similar_files": List[str],
            "middle_path": Optional[Path],
            "tint_source": str,
            "tint_value": Optional[List[int]],
            "middle_avg_raw": Optional[Tuple[int,int,int]],
            "middle_avg_tinted": Optional[Tuple[int,int,int]],
            "fallback_color": Optional[Tuple[int,int,int]]
        }
    """
    result = {
        "surface": surface_name,
        "middle_found": False,
        "miss_reason": None,
        "expected_file": None,
        "similar_files": [],
        "middle_path": None,
        "tint_source": "NONE",
        "tint_value": None,
        "middle_avg_raw": None,
        "middle_avg_tinted": None,
        "fallback_color": None
    }

    # Chercher dans catalogue
    entry = resolve_catalog_entry(surface_name, catalog)

    if entry is None:
        result["miss_reason"] = "NO_CATALOG_ENTRY"
        result["fallback_color"] = (75, 110, 48)
        return result

    # Récupérer middle_bcr
    middle_bcr = entry.get("middle_bcr")

    if not middle_bcr:
        result["miss_reason"] = "NO_MIDDLE_BCR"
        # Chercher fichiers similaires au nom de la surface
        base_name = surface_name.replace(".emat", "")
        result["similar_files"] = find_similar_files(base_name, all_middle_files)

        avg = entry.get("avg_color")
        if avg and avg != [0, 0, 0]:
            result["fallback_color"] = tuple(avg[:3])
        else:
            tint = entry.get("tint_srgb") or entry.get("tint")
            if tint and tint != [0, 0, 0]:
                result["fallback_color"] = tuple(tint[:3])
            else:
                result["fallback_color"] = (75, 110, 48)
        return result

    # Chercher le fichier middle
    result["expected_file"] = middle_bcr
    middle_path = middles_dir / middle_bcr

    if not middle_path.exists():
        result["miss_reason"] = "FILE_NOT_FOUND"
        result["similar_files"] = find_similar_files(middle_bcr, all_middle_files)

        avg = entry.get("avg_color")
        if avg and avg != [0, 0, 0]:
            result["fallback_color"] = tuple(avg[:3])
        else:
            result["fallback_color"] = (75, 110, 48)
        return result

    # Middle trouvé !
    result["middle_found"] = True
    result["middle_path"] = middle_path

    # Calculer couleur moyenne brute
    result["middle_avg_raw"] = get_avg_color_from_middle(middle_path)

    # Déterminer tint
    tint_rgb = None

    # 1. Essayer depuis .emat (prioritaire)
    emat_path = emat_dir / surface_name
    if emat_path.exists():
        try:
            params = parse_emat_params(emat_path, [emat_dir])
            middle_color = params.get("MiddleColor", "1 1 1 1")
            color = params.get("Color", "1 1 1 1")
            tint_rgb = compute_tint_srgb(middle_color, color)

            if tint_rgb and tint_rgb != [0, 0, 0]:
                result["tint_source"] = "EMAT"
                result["tint_value"] = tint_rgb[:3]
        except:
            pass

    # 2. Fallback sur tint_srgb du catalog
    if tint_rgb is None:
        tint_srgb = entry.get("tint_srgb")
        if tint_srgb and tint_srgb != [0, 0, 0]:
            tint_rgb = tint_srgb[:3]
            result["tint_source"] = "CATALOG"
            result["tint_value"] = tint_rgb[:3]

    # Calculer couleur moyenne après tint
    if result["middle_avg_raw"] and tint_rgb:
        raw = np.array(result["middle_avg_raw"], dtype=np.float32) / 255.0
        tint = np.array(tint_rgb, dtype=np.float32) / 255.0

        if not np.allclose(tint, [1.0, 1.0, 1.0], atol=0.02):
            tinted = raw * tint
            tinted = np.clip(tinted * 255.0, 0, 255)
            result["middle_avg_tinted"] = tuple(int(c) for c in tinted)
        else:
            result["middle_avg_tinted"] = result["middle_avg_raw"]
    else:
        result["middle_avg_tinted"] = result["middle_avg_raw"]

    return result


def calculate_surface_coverage(
    surfaces: List[str],
    terrain_dir: Path
) -> Dict[str, float]:
    """
    Calcule le % de couverture de chaque surface sur toute la carte.

    Returns:
        {surface_name: coverage_percent}
    """
    coverage = defaultdict(float)
    total_pixels = 0

    data_dir = terrain_dir / ".Data"

    if not data_dir.exists():
        print(f"⚠️  .Data introuvable : {data_dir}")
        return {}

    # Parcourir toutes les tuiles
    ttile_files = sorted(data_dir.glob("Terrain_*.ttile"))

    for ttile_path in ttile_files:
        tile_id = int(ttile_path.stem.split("_")[1])
        layer_path = data_dir / f"Terrain_{tile_id}_layer.edds"

        if not layer_path.exists():
            continue

        try:
            # Charger LRS2
            lrs2_blocks = load_lrs2_from_ttile(ttile_path)
            if not lrs2_blocks:
                continue

            # Charger layer
            layer_img = read_layer_dds(layer_path)
            if layer_img is None:
                continue

            # Extraire poids (512, 512, 7)
            weights = extract_all_weights(layer_img)

            # Pour chaque bloc
            for (bx, by), mat_ids in lrs2_blocks.items():
                # Zone du bloc (128×128)
                x0 = bx * 128
                y0 = by * 128
                x1 = x0 + 128
                y1 = y0 + 128

                # Pour chaque matériau du bloc
                for i, mat_id in enumerate(mat_ids):
                    if i >= 7 or mat_id >= len(surfaces):
                        continue

                    surface_name = surfaces[mat_id]

                    # Somme des poids pour ce matériau dans ce bloc
                    w = weights[y0:y1, x0:x1, i]
                    coverage[surface_name] += w.sum()

            total_pixels += weights.shape[0] * weights.shape[1]

        except Exception as e:
            continue

    # Convertir en pourcentages
    if total_pixels > 0:
        for surface in coverage:
            coverage[surface] = (coverage[surface] / total_pixels) * 100.0

    return dict(coverage)


def main():
    print("=" * 80)
    print("DIAGNOSTIC COMPLET RÉSOLUTION TEXTURES MIDDLE_BCR")
    print("Reproduit satmap_v2_textured_v2.py + Couverture + MISS + EMAT")
    print("=" * 80)
    print()

    # Chemins (DEV)
    catalog_path = get_catalog_path()
    middles_dir = TEXTURES_USER_DIR / "texture_Middle"
    emat_dir = TEXTURES_USER_DIR / "emat"
    terrain_dir = Path(r"I:\Reforger_addons travail\normandie_map\world\Terrain")
    terr_path = terrain_dir / "terrain.terr"

    print(f"📂 CHEMINS UTILISÉS (via catalog_config) :")
    print(f"  Catalogue     : {catalog_path}")
    print(f"  middles_dir   : {middles_dir}")
    print(f"  emat_dir      : {emat_dir}")
    print()

    # Vérifier correspondance
    expected_catalog = Path(r"H:\logiciel perso\Map generator\data\Textures_ArmaReforger\Textures\catalog.json")
    expected_middles = Path(r"H:\logiciel perso\Map generator\data\Textures_ArmaReforger\Textures\texture_Middle")
    expected_emat = Path(r"H:\logiciel perso\Map generator\data\Textures_ArmaReforger\Textures\emat")

    print(f"✅ VÉRIFICATION CHEMINS :")
    print(f"  catalog == attendu : {catalog_path == expected_catalog}")
    print(f"  middles == attendu : {middles_dir == expected_middles}")
    print(f"  emat    == attendu : {emat_dir == expected_emat}")
    print()

    # Vérifications existence
    if not catalog_path.exists():
        print(f"❌ Catalogue introuvable")
        return 1

    if not terr_path.exists():
        print(f"❌ terrain.terr introuvable : {terr_path}")
        return 1

    print(f"✅ middles_dir existe : {middles_dir.exists()}")
    print(f"✅ emat_dir existe    : {emat_dir.exists()}")
    print()

    # Charger surfaces
    try:
        mat_entries = read_mats_from_terr(terr_path)
        surfaces = [e["name"] for e in mat_entries]
        print(f"✅ {len(surfaces)} surfaces chargées depuis terrain.terr")
    except Exception as e:
        print(f"❌ Erreur lecture terrain.terr : {e}")
        return 1

    # Charger catalogue
    with open(catalog_path, 'r', encoding='utf-8') as f:
        catalog = json.load(f)
    print(f"✅ {len(catalog)} entrées dans le catalogue")
    print()

    # Lister fichiers middles
    all_middle_files = []
    if middles_dir.exists():
        all_middle_files = [f.name for f in middles_dir.iterdir() if f.is_file()]

    # Calculer couvertures (désactivé - fichiers 1024x1024)
    print("⚠️  Calcul couvertures désactivé (fichiers layer incompatibles)")
    print("   → Utilisation couverture uniforme (ordre alphabétique)")
    coverage = {s: float(len(surfaces) - i) for i, s in enumerate(sorted(surfaces))}
    print()

    # Analyser chaque surface
    results = []

    for surface_name in surfaces:
        result = analyze_material(surface_name, catalog, middles_dir, emat_dir, all_middle_files)
        result["coverage"] = coverage.get(surface_name, 0.0)
        results.append(result)

    # Ajouter Grass_03_default si absent
    if "Grass_03_default.emat" not in [r["surface"] for r in results]:
        if "Grass_03_default.emat" in catalog:
            result = analyze_material("Grass_03_default.emat", catalog, middles_dir, emat_dir, all_middle_files)
            result["coverage"] = coverage.get("Grass_03_default.emat", 0.0)
            results.append(result)

    # Trier par couverture décroissante
    results.sort(key=lambda r: r["coverage"], reverse=True)

    # Statistiques
    found_count = sum(1 for r in results if r["middle_found"])
    miss_count = len(results) - found_count

    tint_emat = sum(1 for r in results if r["tint_source"] == "EMAT")
    tint_catalog = sum(1 for r in results if r["tint_source"] == "CATALOG")
    tint_none = sum(1 for r in results if r["tint_source"] == "NONE")

    print("=" * 80)
    print(f"📊 RÉCAPITULATIF ({len(results)} surfaces)")
    print("=" * 80)
    print(f"✅ FOUND (middle trouvé)     : {found_count:3d} / {len(results)}")
    print(f"❌ MISS (middle absent)      : {miss_count:3d} / {len(results)}")
    print()
    print("SOURCE DU TINT (pour les FOUND) :")
    print(f"  EMAT (prioritaire)         : {tint_emat:3d}")
    print(f"  CATALOG (fallback)         : {tint_catalog:3d}")
    print(f"  NONE (pas de tint)         : {tint_none:3d}")
    print()

    # ANALYSE EMAT (point 3)
    print("=" * 80)
    print("🔍 ANALYSE EMAT (0/53 trouvés)")
    print("=" * 80)

    # Exemples de surface_name
    sample_surfaces = surfaces[:3] if len(surfaces) >= 3 else surfaces
    print(f"\nExemples surface_name (repr) :")
    for s in sample_surfaces:
        print(f"  {repr(s)}")

    # Chemins testés
    print(f"\nChemins testés :")
    for s in sample_surfaces:
        emat_test = emat_dir / s
        print(f"  {emat_test}  →  existe={emat_test.exists()}")

    # Contenu emat_dir
    if emat_dir.exists():
        emat_files = list(emat_dir.iterdir())
        emat_file_count = sum(1 for f in emat_files if f.is_file())
        emat_dir_count = sum(1 for f in emat_files if f.is_dir())

        print(f"\nContenu de {emat_dir} :")
        print(f"  Fichiers      : {emat_file_count}")
        print(f"  Sous-dossiers : {emat_dir_count}")

        print(f"\n5 exemples de noms (fichiers) :")
        for i, f in enumerate(sorted(emat_files)[:5]):
            if f.is_file():
                print(f"  {repr(f.name)}")

        # Diagnostic non-appariement
        print(f"\n❌ CAUSE DU NON-APPARIEMENT :")
        if emat_file_count == 0:
            print(f"   Le dossier emat/ ne contient AUCUN fichier .emat")
        else:
            print(f"   Les noms de fichiers .emat ne correspondent PAS aux surface_name")
            print(f"   Surface recherchée : sans extension (ex: 'ForestDeciduous_01_Base')")
            print(f"   Fichiers présents  : vérifier si l'extension .emat est incluse")
    else:
        print(f"\n❌ Le dossier emat/ n'existe pas !")
    print()

    # DÉTAILS MISS (point 2)
    miss_results = [r for r in results if not r["middle_found"]]

    if miss_results:
        print("=" * 80)
        print(f"❌ DÉTAILS DES MISS ({len(miss_results)} surfaces)")
        print("=" * 80)

        for r in miss_results[:10]:  # Limiter à 10 pour lisibilité
            print(f"\n{r['surface']:50s}  Couverture: {r['coverage']:5.2f}%")
            print(f"  Raison        : {r['miss_reason']}")

            if r['expected_file']:
                print(f"  Fichier attendu: {r['expected_file']}")

            if r['similar_files']:
                print(f"  Fichiers proches :")
                for sim in r['similar_files']:
                    print(f"    - {sim}")

            if r['fallback_color']:
                print(f"  Fallback      : RGB{r['fallback_color']}")

        if len(miss_results) > 10:
            print(f"\n... et {len(miss_results) - 10} autres MISS")
        print()

    # TOUTES LES SURFACES FOREST (point 4)
    forest_results = [r for r in results if "forest" in r["surface"].lower()]

    # Fichiers candidats Forest dans middles
    forest_files = [f for f in all_middle_files if "forest" in f.lower()]

    if forest_results:
        print("=" * 80)
        print(f"🌲 TOUTES LES SURFACES 'Forest' ({len(forest_results)} entrées)")
        print("=" * 80)

        print(f"\nFichiers candidats 'Forest*' dans texture_Middle/ :")
        if forest_files:
            for f in forest_files:
                print(f"  - {f}")
        else:
            print(f"  Aucun fichier *Forest* trouvé")
        print()

        for r in forest_results:
            print(f"\n{r['surface']:50s}")
            print(f"  Couverture    : {r['coverage']:5.2f}%")
            print(f"  Middle        : {'FOUND' if r['middle_found'] else 'MISS':5s}")

            if r['middle_found']:
                entry = resolve_catalog_entry(r['surface'], catalog)
                if entry:
                    print(f"  middle_bcr    : {entry.get('middle_bcr', 'N/A')}")
                print(f"  Tint source   : {r['tint_source']:8s}")
                print(f"  Tint value    : {r['tint_value'] or 'N/A'}")
                if r['middle_avg_raw']:
                    print(f"  Avg RAW       : RGB{r['middle_avg_raw']}")
                if r['middle_avg_tinted']:
                    print(f"  Avg TINTED    : RGB{r['middle_avg_tinted']}")
            else:
                entry = resolve_catalog_entry(r['surface'], catalog)
                if entry:
                    print(f"  middle_bcr    : {entry.get('middle_bcr', 'N/A')}")
                print(f"  Raison MISS   : {r['miss_reason']}")
                if r['similar_files']:
                    print(f"  Candidats     : {', '.join(r['similar_files'][:3])}")
        print()

    # RAPPORT COMPLET TRIÉ PAR COUVERTURE
    print("=" * 80)
    print("📊 RAPPORT COMPLET (trié par couverture décroissante)")
    print("=" * 80)
    print()
    print(f"{'Surface':50s}  {'Cov%':>6s}  {'Mid':5s}  {'Tint':8s}  {'Couleur finale':15s}")
    print("-" * 100)

    for r in results[:20]:  # Top 20
        status = "FOUND" if r['middle_found'] else "MISS"

        if r['middle_avg_tinted']:
            color_str = f"RGB{r['middle_avg_tinted']}"
        elif r['fallback_color']:
            color_str = f"RGB{r['fallback_color']} (fb)"
        else:
            color_str = "N/A"

        print(f"{r['surface']:50s}  {r['coverage']:6.2f}  {status:5s}  {r['tint_source']:8s}  {color_str:15s}")

    if len(results) > 20:
        print(f"\n... et {len(results) - 20} autres surfaces")

    print()
    print("=" * 80)
    print("FIN DU DIAGNOSTIC")
    print("=" * 80)

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
