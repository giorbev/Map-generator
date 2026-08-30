"""
validation_zone_b.py — Validation Zone B (Grass_03 propre)
===========================================================
Script lecture seule — génère une carte PNG de validation.

Entrées:
  --mask : chemin vers le masque Grass_03 PNG (16257×16257 ou 4096×4096)
  --output : chemin du PNG de sortie (défaut: validation_zone_b.png)
  --threshold : seuil de coverage pour considérer un matériau comme présent (défaut: 0.01 = 1%)

Sortie:
  PNG 512×512 (1 pixel par bloc) avec code couleur:
    VERT   (0, 200, 0)   : Zone B propre, prêt pour masques
    ROUGE  (200, 0, 0)   : Zone B avec résidus → à nettoyer
    JAUNE  (200, 200, 0) : Bloc limitrophe Zone A/B
    GRIS   (80, 80, 80)  : Zone A, ignoré
    NOIR   (0, 0, 0)     : .edds manquant
    ORANGE (200, 100, 0) : Zone B sans Grass_03 (anomalie)

Usage:
  python validation_zone_b.py --mask data/projects/Zimnitrita/exports_mask/mask_Grass_03.png
"""

import argparse
import sys
import numpy as np
import cv2
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# Import modules depuis clean_weights.py
from clean_weights import (
    find_layer_path,
    read_layer_dds,
    read_lrs2_from_ttile,
)

# ============================================================================
# CONSTANTES
# ============================================================================

# Chemins
DATA_DIR = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain\.Data")
EDITOR_DATA_DIR = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain\.EditorData")
TTILE_DIR = DATA_DIR

# IDs matériaux (depuis terrain.terr Zimnitrita)
GRASS03_FAMILY = [0, 3, 28, 36, 40, 56]  # Grass_03_default, Grass_03, Grass_03_coastal, MountainGrass_03_aut, Grass_03_aut, MountainGrass_03
SEABED_ID = 1

# Couleurs de sortie
COLOR_VERT = (0, 200, 0)      # Zone B propre
COLOR_ROUGE = (200, 0, 0)     # Zone B avec résidus
COLOR_JAUNE = (200, 200, 0)   # Limitrophe
COLOR_GRIS = (80, 80, 80)     # Zone A
COLOR_NOIR = (0, 0, 0)        # Manquant
COLOR_ORANGE = (200, 100, 0)  # Zone B sans Grass_03


# ============================================================================
# UTILITAIRES
# ============================================================================

def detect_mask_resolution(img: np.ndarray) -> Tuple[int, int]:
    """
    Détecte la résolution du masque et calcule px_per_tile et px_per_bloc.

    Returns:
        (px_per_tile, px_per_bloc)
    """
    h, w = img.shape[:2]

    if h == 16257 and w == 16257:
        # 1 tuile = 508px, 1 bloc = 127px (508/4)
        px_per_tile = 508
        px_per_bloc = 127
    elif h == 4096 and w == 4096:
        # 1 tuile = 128px, 1 bloc = 32px (128/4)
        px_per_tile = 128
        px_per_bloc = 32
    else:
        raise ValueError(f"Résolution masque non supportée: {w}×{h} (attendu 16257×16257 ou 4096×4096)")

    return px_per_tile, px_per_bloc


def extract_tile_zone(img: np.ndarray, tx: int, ty: int, px_per_tile: int) -> np.ndarray:
    """Extrait la zone masque d'une tuile."""
    y0 = ty * px_per_tile
    x0 = tx * px_per_tile
    y1 = y0 + px_per_tile
    x1 = x0 + px_per_tile

    # Clamp pour éviter les débordements
    y1 = min(y1, img.shape[0])
    x1 = min(x1, img.shape[1])

    return img[y0:y1, x0:x1]


def extract_block_zone(tile_zone: np.ndarray, bx: int, by: int, px_per_bloc: int) -> np.ndarray:
    """Extrait la zone masque d'un bloc depuis la zone tuile."""
    y0 = by * px_per_bloc
    x0 = bx * px_per_bloc
    y1 = y0 + px_per_bloc
    x1 = x0 + px_per_bloc

    # Clamp
    y1 = min(y1, tile_zone.shape[0])
    x1 = min(x1, tile_zone.shape[1])

    return tile_zone[y0:y1, x0:x1]


def classify_block_zone(block_zone: np.ndarray) -> str:
    """
    Classifie une zone bloc depuis le masque.

    Returns:
        "zone_a" : 0 pixels blancs
        "limitrophe" : pixels blancs ET pixels noirs
        "zone_b" : 100% blancs
    """
    # Convertir en grayscale si nécessaire
    if len(block_zone.shape) == 3:
        block_zone = cv2.cvtColor(block_zone, cv2.COLOR_BGR2GRAY)

    white_count = np.sum(block_zone > 200)
    black_count = np.sum(block_zone < 50)

    if white_count == 0:
        return "zone_a"
    elif white_count > 0 and black_count > 0:
        return "limitrophe"
    else:
        return "zone_b"


def calculate_material_coverage(
    weights: np.ndarray,
    lrs2_blocks: Dict,
    bx: int,
    by: int,
    mat_ids: List[int]
) -> Dict[int, float]:
    """
    Calcule la coverage de chaque matériau dans un bloc.

    Args:
        weights: (512, 512, 7) array normalisé [0..1]
        lrs2_blocks: dict des blocs LRS2
        bx, by: coordonnées locales du bloc
        mat_ids: liste des mat_ids du bloc

    Returns:
        dict {mat_id: coverage}
    """
    x0 = bx * 128
    y0 = by * 128
    block_weights = weights[y0:y0+128, x0:x0+128, :]

    pixel_count = 128 * 128
    coverages = {}

    for slot_idx, mat_id in enumerate(mat_ids):
        # slot 0 = w0 implicite, slot 1 = mat_ids[0], etc.
        layer_slot = slot_idx + 1

        if layer_slot >= block_weights.shape[2]:
            coverages[mat_id] = 0.0
            continue

        # Coverage = % de pixels où weight > 0
        coverage = (block_weights[:, :, layer_slot] > 0).sum() / pixel_count
        coverages[mat_id] = coverage

    return coverages


def classify_zone_b_block(
    mat_ids: List[int],
    coverages: Dict[int, float],
    threshold: float
) -> Tuple[str, List[str]]:
    """
    Classifie un bloc Zone B.

    Returns:
        (status, residues)
        status: "vert" | "rouge" | "orange"
        residues: liste des matériaux résidus
    """
    # Vérifier présence Grass_03
    has_grass03 = any(mid in GRASS03_FAMILY for mid in mat_ids)

    if not has_grass03:
        return "orange", []

    # Vérifier résidus (matériaux autres que Grass_03 avec coverage > threshold)
    residues = []
    for mat_id in mat_ids:
        if mat_id not in GRASS03_FAMILY:
            cov = coverages.get(mat_id, 0.0)
            if cov > threshold:
                residues.append(mat_id)

    if residues:
        return "rouge", residues
    else:
        return "vert", []


# ============================================================================
# VALIDATION
# ============================================================================

def validate_zone_b(
    mask_path: Path,
    output_path: Path,
    threshold: float,
    surfaces: List[str]
):
    """
    Génère la carte de validation Zone B.
    """
    print("=" * 80)
    print("VALIDATION ZONE B")
    print("=" * 80)
    print(f"Masque      : {mask_path}")
    print(f"Output      : {output_path}")
    print(f"Threshold   : {threshold*100:.1f}%")
    print()

    # Charger masque
    if not mask_path.exists():
        print(f"[ERR] Masque introuvable: {mask_path}")
        return 1

    mask = cv2.imread(str(mask_path))
    if mask is None:
        print(f"[ERR] Impossible de lire le masque")
        return 1

    print(f"Résolution masque: {mask.shape[1]}×{mask.shape[0]}")

    # Détecter résolution
    try:
        px_per_tile, px_per_bloc = detect_mask_resolution(mask)
        print(f"px_per_tile={px_per_tile}, px_per_bloc={px_per_bloc}")
        print()
    except ValueError as e:
        print(f"[ERR] {e}")
        return 1

    # Image de sortie 512×512
    output_img = np.zeros((512, 512, 3), dtype=np.uint8)

    # Compteurs
    stats = {
        "vert": 0,
        "rouge": 0,
        "jaune": 0,
        "gris": 0,
        "noir": 0,
        "orange": 0,
    }

    red_blocks = []  # Liste des blocs rouges avec détails

    # Parcourir toutes les tuiles
    for ty in range(32):
        for tx in range(32):
            tile_id = ty * 32 + tx

            # Extraire zone masque de la tuile
            tile_zone = extract_tile_zone(mask, tx, ty, px_per_tile)

            # Vérifier si tuile entièrement Zone A (aucun pixel blanc)
            tile_gray = cv2.cvtColor(tile_zone, cv2.COLOR_BGR2GRAY)
            if np.sum(tile_gray > 200) == 0:
                # Tuile entièrement Zone A → tous blocs = GRIS
                for by in range(4):
                    for bx in range(4):
                        out_x = tx * 4 + bx
                        out_y = ty * 4 + by
                        output_img[out_y, out_x] = COLOR_GRIS
                        stats["gris"] += 1
                continue

            # Trouver .edds
            layer_path = find_layer_path(tile_id, DATA_DIR, EDITOR_DATA_DIR)
            if layer_path is None:
                # .edds manquant → tous blocs = NOIR
                for by in range(4):
                    for bx in range(4):
                        out_x = tx * 4 + bx
                        out_y = ty * 4 + by
                        output_img[out_y, out_x] = COLOR_NOIR
                        stats["noir"] += 1
                continue

            # Lire weights
            weights = read_layer_dds(layer_path)
            if weights is None:
                for by in range(4):
                    for bx in range(4):
                        out_x = tx * 4 + bx
                        out_y = ty * 4 + by
                        output_img[out_y, out_x] = COLOR_NOIR
                        stats["noir"] += 1
                continue

            # Lire LRS2
            ttile_path = TTILE_DIR / f"Terrain_{tile_id}.ttile"
            lrs2_blocks = read_lrs2_from_ttile(ttile_path)
            if lrs2_blocks is None:
                for by in range(4):
                    for bx in range(4):
                        out_x = tx * 4 + bx
                        out_y = ty * 4 + by
                        output_img[out_y, out_x] = COLOR_NOIR
                        stats["noir"] += 1
                continue

            # Analyser chaque bloc
            for by in range(4):
                for bx in range(4):
                    out_x = tx * 4 + bx
                    out_y = ty * 4 + by

                    # Extraire zone masque du bloc
                    block_zone = extract_block_zone(tile_zone, bx, by, px_per_bloc)
                    zone_type = classify_block_zone(block_zone)

                    if zone_type == "zone_a":
                        output_img[out_y, out_x] = COLOR_GRIS
                        stats["gris"] += 1
                        continue

                    if zone_type == "limitrophe":
                        output_img[out_y, out_x] = COLOR_JAUNE
                        stats["jaune"] += 1
                        continue

                    # zone_type == "zone_b" → analyser matériaux
                    block_data = lrs2_blocks.get((bx, by))
                    if block_data is None:
                        # Pas de LRS2 pour ce bloc ?
                        output_img[out_y, out_x] = COLOR_NOIR
                        stats["noir"] += 1
                        continue

                    mat_ids, orig_index = block_data

                    # Calculer coverage
                    coverages = calculate_material_coverage(weights, lrs2_blocks, bx, by, mat_ids)

                    # Classifier
                    status, residues = classify_zone_b_block(mat_ids, coverages, threshold)

                    if status == "vert":
                        output_img[out_y, out_x] = COLOR_VERT
                        stats["vert"] += 1
                    elif status == "rouge":
                        output_img[out_y, out_x] = COLOR_ROUGE
                        stats["rouge"] += 1

                        # Enregistrer détails
                        lrs_x = tx * 4 + bx
                        lrs_y = ty * 4 + by
                        residue_names = [
                            surfaces[mid] if mid < len(surfaces) else f"MAT_{mid}"
                            for mid in residues
                        ]
                        red_blocks.append({
                            "lrs": (lrs_x, lrs_y),
                            "tile": (tx, ty),
                            "residues": residue_names,
                            "coverages": {surfaces[mid] if mid < len(surfaces) else f"MAT_{mid}": coverages.get(mid, 0.0)
                                          for mid in residues}
                        })
                    else:  # orange
                        output_img[out_y, out_x] = COLOR_ORANGE
                        stats["orange"] += 1

    # Sauvegarder image
    cv2.imwrite(str(output_path), cv2.cvtColor(output_img, cv2.COLOR_RGB2BGR))

    # Afficher résultats
    print("=" * 80)
    print("RÉSULTATS")
    print("=" * 80)
    print(f"Blocs VERTS   : {stats['vert']:4d} (Zone B propre)")
    print(f"Blocs ROUGES  : {stats['rouge']:4d} (Zone B avec résidus)")
    print(f"Blocs JAUNES  : {stats['jaune']:4d} (Limitrophes)")
    print(f"Blocs GRIS    : {stats['gris']:4d} (Zone A)")
    print(f"Blocs NOIRS   : {stats['noir']:4d} (.edds manquant)")
    print(f"Blocs ORANGES : {stats['orange']:4d} (Zone B sans Grass_03)")
    print()

    if red_blocks:
        print(f"DÉTAILS BLOCS ROUGES ({len(red_blocks)} blocs):")
        print("-" * 80)
        for block in red_blocks[:20]:  # Limiter à 20 premiers
            lrs_x, lrs_y = block["lrs"]
            tx, ty = block["tile"]
            residues_str = ", ".join([f"{name} ({block['coverages'][name]*100:.1f}%)"
                                      for name in block["residues"]])
            print(f"LRS2=({lrs_x:3d},{lrs_y:3d}) Tile({tx:2d},{ty:2d}) : {residues_str}")

        if len(red_blocks) > 20:
            print(f"... et {len(red_blocks)-20} autres blocs rouges")
        print()

    print(f"[OK] Carte sauvegardée: {output_path}")
    return 0


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Validation Zone B — Carte de diagnostic',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  python validation_zone_b.py --mask data/projects/Zimnitrita/exports_mask/mask_Grass_03.png
  python validation_zone_b.py --mask mask.png --output validation.png --threshold 0.02
        """
    )

    parser.add_argument('--mask', type=str, required=True,
                       help='Chemin vers le masque Grass_03 PNG')
    parser.add_argument('--output', type=str, default='validation_zone_b.png',
                       help='Chemin du PNG de sortie (défaut: validation_zone_b.png)')
    parser.add_argument('--threshold', type=float, default=0.01,
                       help='Seuil de coverage (défaut: 0.01 soit 1%%)')

    args = parser.parse_args()

    # Charger surfaces depuis terrain.terr
    try:
        from terrain_terr_reader import read_mats_from_terr
        TERR_PATH = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain\terrain.terr")
        surfaces_data = read_mats_from_terr(TERR_PATH)
        surfaces = [e["name"] for e in surfaces_data]
    except Exception as e:
        print(f"[ERR] Impossible de charger surfaces: {e}")
        return 1

    mask_path = Path(args.mask)
    output_path = Path(args.output)

    return validate_zone_b(mask_path, output_path, args.threshold, surfaces)


if __name__ == '__main__':
    sys.exit(main())
