"""
Scan Exclusion Zone - Vérifie que Zone B ne contient que Grass_03 et seabed

Scanne tous les blocs dans la zone d'exclusion (masque PNG grass03 blanc)
et vérifie que seuls Grass_03 (ID=3) et SeaBed_01 sont présents.

Usage:
    python scan_exclusion_zone.py --mask chemin/vers/grass03_mask.png
"""

import sys
import json
import numpy as np
import cv2
from pathlib import Path
from typing import Dict, List, Tuple, Set
import argparse

# Import modules terrain
sys.path.insert(0, str(Path(__file__).parent.parent))
from terrain_terr_reader import read_mats_from_terr
from clean_weights import find_layer_path, read_layer_dds, read_lrs2_from_ttile

# ============================================================================
# CONSTANTES
# ============================================================================

TERRAIN_ROOT = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain")
DATA_DIR = TERRAIN_ROOT / ".Data"
EDITOR_DATA_DIR = TERRAIN_ROOT / ".EditorData"
TERR_PATH = TERRAIN_ROOT / "terrain.terr"
CATALOG_PATH = Path(__file__).parent / "data" / "Textures_ArmaReforger" / "catalog.json"

TILE_GRID = 32          # tuiles par côté
TILE_SIZE_PX = 127      # pixels par tuile dans le masque (16257/128 ≈ 127)
BLOC_SIZE_PX = 8        # pixels par bloc LRS2 dans le masque (32m/4m)
ALLOWED_MATS = {0, 3}   # Grass_03_defaut (w0=0), Grass_03 vanilla (ID=3)


# ============================================================================
# FONCTIONS
# ============================================================================

def find_seabed_id(surfaces: List[str]) -> int:
    """Trouve l'ID de SeaBed_01.emat dans la liste des surfaces."""
    for i, name in enumerate(surfaces):
        if "seabed" in name.lower():
            return i
    return -1


def load_exclusion_mask(mask_path: Path) -> np.ndarray:
    """
    Charge le masque PNG 16-bit et retourne un array binaire uint8.
    Blanc (>0) = Zone B, Noir (0) = hors zone.
    """
    mask = cv2.imread(str(mask_path), cv2.IMREAD_UNCHANGED)
    if mask is None:
        raise ValueError(f"Impossible de charger le masque : {mask_path}")

    # Convertir en binaire : tout ce qui est > 0 → 1
    binary = (mask > 0).astype(np.uint8)
    return binary


def is_in_exclusion_zone(mask: np.ndarray, x0: int, y0: int, x1: int, y1: int) -> bool:
    """Vérifie si la région contient au moins un pixel blanc (Zone B)."""
    roi = mask[y0:y1, x0:x1]
    return np.any(roi > 0)


def scan_tile(tx: int, ty: int, mask: np.ndarray, data_dir: Path,
              editor_data_dir: Path, allowed_set: Set[int],
              surfaces: List[str]) -> List[Tuple[int, int, int, int, List[int]]]:
    """
    Scanne une tuile et retourne la liste des blocs avec résidus.

    Returns:
        Liste de (tx, ty, bx, by, mat_ids_interdits)
    """
    tile_id = ty * TILE_GRID + tx
    x0_tile = tx * TILE_SIZE_PX
    y0_tile = ty * TILE_SIZE_PX
    x1_tile = x0_tile + TILE_SIZE_PX
    y1_tile = y0_tile + TILE_SIZE_PX

    # Vérifier si la tuile intersecte la Zone B
    if not is_in_exclusion_zone(mask, x0_tile, y0_tile, x1_tile, y1_tile):
        return []

    # Charger le .edds
    layer_path = find_layer_path(tile_id, data_dir, editor_data_dir)
    if layer_path is None:
        print(f"  [WARN] Tile ({tx},{ty}) T{tile_id} : .edds introuvable")
        return []

    # Lire LRS2
    ttile_path = layer_path.with_suffix('.ttile')
    lrs2 = read_lrs2_from_ttile(ttile_path)
    if lrs2 is None:
        print(f"  [WARN] Tile ({tx},{ty}) T{tile_id} : LRS2 introuvable")
        return []

    # Scanner les blocs
    residues = []
    for by in range(64):
        for bx in range(64):
            x0_bloc = x0_tile + bx * BLOC_SIZE_PX
            y0_bloc = y0_tile + by * BLOC_SIZE_PX
            x1_bloc = x0_bloc + BLOC_SIZE_PX
            y1_bloc = y0_bloc + BLOC_SIZE_PX

            # Clip pour éviter dépassement
            x1_bloc = min(x1_bloc, mask.shape[1])
            y1_bloc = min(y1_bloc, mask.shape[0])

            # Vérifier si le bloc intersecte la Zone B
            if not is_in_exclusion_zone(mask, x0_bloc, y0_bloc, x1_bloc, y1_bloc):
                continue

            # Lire mat_ids depuis LRS2
            mat_ids = lrs2.get((bx, by), [])
            if not mat_ids:
                continue

            # Vérifier les matériaux
            forbidden = [mid for mid in mat_ids if mid not in allowed_set]
            if forbidden:
                residues.append((tx, ty, bx, by, forbidden))

    return residues


def main():
    parser = argparse.ArgumentParser(description="Scan Zone B pour résidus matériaux")
    parser.add_argument("--mask", required=True, help="Chemin vers le masque PNG grass03")
    parser.add_argument("--threshold", type=float, default=0.01, help="Seuil négligeable (défaut 0.01)")
    args = parser.parse_args()

    mask_path = Path(args.mask)
    if not mask_path.exists():
        print(f"[ERR] Masque introuvable : {mask_path}")
        return 1

    # Vérifier chemins terrain
    if not all([DATA_DIR.exists(), EDITOR_DATA_DIR.exists(), TERR_PATH.exists()]):
        print(f"[ERR] Chemins terrain introuvables")
        return 1

    # Charger surfaces
    surfaces_data = read_mats_from_terr(TERR_PATH)
    surfaces = [e["name"] for e in surfaces_data]

    # Trouver SeaBed_01 ID
    seabed_id = find_seabed_id(surfaces)
    if seabed_id == -1:
        print("[WARN] SeaBed_01 introuvable dans terrain.terr — sera considéré comme résidu")

    allowed_set = ALLOWED_MATS.copy()
    if seabed_id != -1:
        allowed_set.add(seabed_id)

    print(f"[INFO] Matériaux autorisés en Zone B : {sorted(allowed_set)}")
    if seabed_id != -1:
        print(f"       0=Grass_03_defaut, 3=Grass_03, {seabed_id}=SeaBed_01")
    else:
        print(f"       0=Grass_03_defaut, 3=Grass_03")

    # Charger masque
    print(f"[INFO] Chargement masque : {mask_path}")
    mask = load_exclusion_mask(mask_path)
    print(f"       Dimensions : {mask.shape[1]}×{mask.shape[0]} px")

    # Scanner toutes les tuiles
    all_residues = []
    tiles_scanned = 0
    blocks_scanned = 0

    print(f"\n[SCAN] Démarrage scan {TILE_GRID}×{TILE_GRID} tuiles...")

    for ty in range(TILE_GRID):
        for tx in range(TILE_GRID):
            tile_residues = scan_tile(tx, ty, mask, DATA_DIR, EDITOR_DATA_DIR,
                                      allowed_set, surfaces)
            if tile_residues:
                tiles_scanned += 1
                blocks_scanned += len(tile_residues)
                all_residues.extend(tile_residues)

    # Affichage résultats
    print(f"\n{'='*80}")
    print(f"RÉSULTATS SCAN")
    print(f"{'='*80}")
    print(f"Tuiles avec résidus : {tiles_scanned}")
    print(f"Blocs avec résidus  : {blocks_scanned}")
    print()

    if all_residues:
        print("BLOCS AVEC RÉSIDUS :")
        print("-" * 80)

        tiles_to_clean = set()
        for tx, ty, bx, by, forbidden in all_residues:
            tile_id = ty * TILE_GRID + tx
            lx = bx // 8  # Bloc LRS2 8×8
            ly = by // 8

            # Noms des matériaux interdits
            mat_names = [surfaces[mid] if mid < len(surfaces) else f"MAT_{mid}"
                         for mid in forbidden]

            print(f"Tile ({tx},{ty}) T{tile_id:03d} Bloc ({bx:02d},{by:02d}) "
                  f"LRS2=({lx},{ly}) : résidus {mat_names}")

            tiles_to_clean.add((tx, ty))

        print()
        print("-" * 80)
        print(f"RÉSUMÉ : {len(tiles_to_clean)} tuiles à cleaner")
        print()
        print("Commandes à lancer :")
        for tx, ty in sorted(tiles_to_clean):
            print(f"  python clean_weights.py --clean {tx},{ty}")

        print()
        print("Liste tuiles (copier-coller) :")
        coords = " ".join([f"{tx},{ty}" for tx, ty in sorted(tiles_to_clean)])
        print(f"  {coords}")

    else:
        print("[OK] Aucun résidu détecté — Zone B est propre !")

    return 0


if __name__ == "__main__":
    sys.exit(main())
