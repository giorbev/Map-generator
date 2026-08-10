"""
pipeline_v4.py — Génération masques PNG corrigés sans conflit de budget

Script lecture seule qui génère des masques PNG 16 bits corrigés
sans conflit de budget, en respectant les textures existantes.

Principe :
- Pour chaque pixel : fusion textures existantes + masques selon MASK_PRIORITY
- Budget max 6 slots par bloc automatiquement respecté
- Export masques PNG 16 bits prêts pour import Workbench

Usage:
    python pipeline_v4.py --masks-dir OUTPUT_DIR --output-dir OUTPUT_CORRECTED --exclusion zone_b.png
"""

import argparse
import cv2
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple

# Import modules terrain
from edds_decoder import decode_edds_layer, extract_all_weights
from clean_weights import find_layer_path, read_lrs2_from_ttile
from terrain_terr_reader import read_mats_from_terr


# ============================================================================
# CONFIGURATION
# ============================================================================

# Chemins
TERRAIN_ROOT = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain")
DATA_DIR = TERRAIN_ROOT / ".Data"
EDITOR_DATA_DIR = TERRAIN_ROOT / ".EditorData"
TERR_PATH = TERRAIN_ROOT / "terrain.terr"

# Grille Reforger
NUM_TILES = 32
BLOCS_PER_TILE = 4
TOTAL_BLOCS = NUM_TILES * BLOCS_PER_TILE  # 128×128 blocs

# Ordre de priorité masques (du plus prioritaire au moins prioritaire)
MASK_PRIORITY = [
    "01_mask_seabed",
    "02_mask_flow",
    "03_mask_deposit",
    "04_mask_coastal_flat",
    "05_mask_coastal_slope",
    "06_mask_landes_rocheuses",
    "07_mask_rock",
    "08_mask_prairie_humide",
    "09_mask_prairie_seche",
    "10_mask_landes_plateau",
    "11_mask_maquis_landes",
    "12_mask_alpages",
    "13_mask_foret_feuillue",
    "14_mask_foret_coniferes",
]

# Budget max par bloc (Reforger QTRE limite)
BUDGET_MAX = 6


# ============================================================================
# ÉTAPE 1 : CHARGER MASQUES
# ============================================================================

def load_masks(masks_dir: Path, exclude: List[str] = None) -> Dict[str, np.ndarray]:
    """
    Charge tous les masques PNG 16 bits, triés par ordre alphabétique.

    Returns:
        dict {nom_masque: array_normalisé_0_1}
    """
    print(f"[INFO] Chargement masques depuis {masks_dir}...")

    if exclude is None:
        exclude = []

    mask_files = sorted(masks_dir.glob("*.png"))
    masks = {}

    for mask_path in mask_files:
        if mask_path.name in exclude:
            print(f"[SKIP] {mask_path.name} (exclu)")
            continue

        # Lire PNG 16 bits
        img = cv2.imread(str(mask_path), cv2.IMREAD_UNCHANGED)
        if img is None:
            print(f"[WARN] Impossible de lire {mask_path.name}")
            continue

        # Convertir grayscale si nécessaire
        if len(img.shape) == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Normaliser 0-1
        if img.dtype == np.uint16:
            mask_norm = img.astype(np.float32) / 65535.0
        else:
            mask_norm = img.astype(np.float32) / 255.0

        # Seuillage des parasites (1% du max)
        mask_max = mask_norm.max()
        if mask_max > 0:
            threshold = mask_max * 0.01
            mask_norm[mask_norm < threshold] = 0

        masks[mask_path.stem] = mask_norm
        print(f"[OK] {mask_path.name} ({mask_norm.shape[1]}×{mask_norm.shape[0]})")

    print(f"[INFO] {len(masks)} masques chargés")
    return masks


def load_exclusion_mask(exclusion_path: Path, target_shape: Tuple[int, int]) -> np.ndarray:
    """
    Charge le masque d'exclusion (Zone B).

    Returns:
        array (H, W) bool — True = Zone B (exclusion)
    """
    if not exclusion_path or not exclusion_path.exists():
        print("[INFO] Pas de masque d'exclusion")
        return np.zeros(target_shape, dtype=bool)

    print(f"[INFO] Chargement masque exclusion {exclusion_path}...")

    img = cv2.imread(str(exclusion_path), cv2.IMREAD_UNCHANGED)
    if img is None:
        print(f"[WARN] Impossible de lire {exclusion_path}")
        return np.zeros(target_shape, dtype=bool)

    if len(img.shape) == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Resize si nécessaire
    if img.shape != target_shape:
        img = cv2.resize(img, (target_shape[1], target_shape[0]), interpolation=cv2.INTER_NEAREST)

    # Binaire : blanc = Zone B
    exclusion = (img > 0)

    excluded_pixels = exclusion.sum()
    total_pixels = exclusion.size
    pct = excluded_pixels / total_pixels * 100

    print(f"[INFO] Zone B : {excluded_pixels}/{total_pixels} pixels ({pct:.1f}%)")

    return exclusion


# ============================================================================
# ÉTAPE 2 : LIRE ÉTAT TERRAIN EXISTANT
# ============================================================================

def read_terrain_state(surfaces: List[Dict]) -> Tuple[Dict, Dict]:
    """
    Lit l'état actuel terrain (textures + poids) pour toutes les tuiles.

    Returns:
        textures_existantes : dict {(tx, ty): {(bx, by): [mat_ids]}}
        poids_existants     : dict {(tx, ty): weights_array (512, 512, 7)}
    """
    print("[INFO] Lecture état terrain existant...")

    textures_existantes = {}
    poids_existants = {}

    for ty in range(NUM_TILES):
        for tx in range(NUM_TILES):
            tile_id = ty * NUM_TILES + tx
            ttile_path = DATA_DIR / f"Terrain_{tile_id}.ttile"

            if not ttile_path.exists():
                continue

            # Lire LRS2
            lrs2_blocks = read_lrs2_from_ttile(ttile_path)
            if lrs2_blocks is None:
                continue

            textures_existantes[(tx, ty)] = {}
            for (bx, by), (mat_ids, orig_index) in lrs2_blocks.items():
                textures_existantes[(tx, ty)][(bx, by)] = mat_ids

            # Lire layer.edds
            layer_path = find_layer_path(tile_id, DATA_DIR, EDITOR_DATA_DIR)
            if layer_path is None:
                continue

            pixels = decode_edds_layer(layer_path)
            if pixels is None:
                continue

            weights = extract_all_weights(pixels)
            poids_existants[(tx, ty)] = weights

    print(f"[INFO] {len(poids_existants)} tuiles avec données existantes")

    return textures_existantes, poids_existants


# ============================================================================
# ÉTAPE 3 : FUSION INTELLIGENTE
# ============================================================================

def fusion_masques_par_bloc(
    masks: Dict[str, np.ndarray],
    textures_existantes: Dict,
    poids_existants: Dict,
    exclusion: np.ndarray,
    surfaces: List[Dict]
) -> Dict[str, np.ndarray]:
    """
    Fusionne masques + textures existantes en respectant le budget par bloc.

    Returns:
        dict {nom_masque: array_corrigé (H, W) float32}
    """
    print("[INFO] Fusion masques + terrain existant...")

    # Résolution masques
    if not masks:
        print("[ERR] Aucun masque chargé")
        return {}

    first_mask = next(iter(masks.values()))
    h, w = first_mask.shape
    px_per_bloc = w // TOTAL_BLOCS

    print(f"[INFO] Résolution : {w}×{h}, {px_per_bloc} px/bloc")

    # Initialiser masques corrigés (tous à zéro)
    masques_corriges = {name: np.zeros((h, w), dtype=np.float32) for name in masks.keys()}

    # Traiter bloc par bloc
    blocs_ok = 0
    blocs_corriges = 0
    blocs_total = TOTAL_BLOCS * TOTAL_BLOCS

    for by_global in range(TOTAL_BLOCS):
        for bx_global in range(TOTAL_BLOCS):
            # Orientation PNG inversée
            by_png = TOTAL_BLOCS - 1 - by_global

            y0 = by_png * px_per_bloc
            x0 = bx_global * px_per_bloc
            y1 = y0 + px_per_bloc
            x1 = x0 + px_per_bloc

            # Zone bloc dans masques
            zone_exclusion = exclusion[y0:y1, x0:x1]

            # Si bloc entièrement en Zone B, skip terrain existant
            if zone_exclusion.all():
                # Appliquer masques directement (Zone B vierge)
                slots_bloc = process_bloc_vierge(
                    masks, masques_corriges, y0, y1, x0, x1, bx_global, by_global, px_per_bloc
                )
            else:
                # Fusionner terrain existant + masques
                tx = bx_global // BLOCS_PER_TILE
                ty = by_global // BLOCS_PER_TILE
                bx = bx_global % BLOCS_PER_TILE
                by = by_global % BLOCS_PER_TILE

                slots_bloc = process_bloc_fusion(
                    masks, masques_corriges, textures_existantes, poids_existants,
                    tx, ty, bx, by, y0, y1, x0, x1, bx_global, by_global, px_per_bloc, surfaces
                )

            if slots_bloc <= BUDGET_MAX:
                blocs_ok += 1
            else:
                blocs_corriges += 1

    print(f"[INFO] Blocs OK: {blocs_ok}/{blocs_total}, Blocs corrigés: {blocs_corriges}/{blocs_total}")

    return masques_corriges


def process_bloc_vierge(
    masks: Dict[str, np.ndarray],
    masques_corriges: Dict[str, np.ndarray],
    y0: int, y1: int, x0: int, x1: int,
    bx_global: int, by_global: int,
    px_per_bloc: int
) -> int:
    """
    Traite un bloc vierge (Zone B) : applique les masques dans l'ordre de priorité.

    Returns:
        nombre de slots utilisés
    """
    # Collecter tous les masques applicables
    masques_actifs = []

    for mask_name in MASK_PRIORITY:
        if mask_name not in masks:
            continue

        zone = masks[mask_name][y0:y1, x0:x1]
        if zone.max() > 0:
            masques_actifs.append(mask_name)

    # Limiter au budget
    if len(masques_actifs) > BUDGET_MAX:
        masques_actifs = masques_actifs[:BUDGET_MAX]

    # Copier les poids
    for mask_name in masques_actifs:
        masques_corriges[mask_name][y0:y1, x0:x1] = masks[mask_name][y0:y1, x0:x1]

    return len(masques_actifs)


def process_bloc_fusion(
    masks: Dict[str, np.ndarray],
    masques_corriges: Dict[str, np.ndarray],
    textures_existantes: Dict,
    poids_existants: Dict,
    tx: int, ty: int, bx: int, by: int,
    y0: int, y1: int, x0: int, x1: int,
    bx_global: int, by_global: int,
    px_per_bloc: int,
    surfaces: List[Dict]
) -> int:
    """
    Fusionne terrain existant + masques en respectant le budget.

    Returns:
        nombre de slots utilisés
    """
    # Textures existantes du bloc
    mat_ids_existants = []
    if (tx, ty) in textures_existantes:
        mat_ids_existants = textures_existantes[(tx, ty)].get((bx, by), [])

    # Masques applicables
    masques_actifs = []
    for mask_name in MASK_PRIORITY:
        if mask_name not in masks:
            continue
        zone = masks[mask_name][y0:y1, x0:x1]
        if zone.max() > 0:
            masques_actifs.append(mask_name)

    # Total slots = existants + masques
    total_slots = len(mat_ids_existants) + len(masques_actifs)

    # Si budget OK, copier tout
    if total_slots <= BUDGET_MAX:
        for mask_name in masques_actifs:
            masques_corriges[mask_name][y0:y1, x0:x1] = masks[mask_name][y0:y1, x0:x1]
        return total_slots

    # Sinon, limiter les masques (garder textures existantes)
    slots_disponibles = BUDGET_MAX - len(mat_ids_existants)
    masques_retenus = masques_actifs[:slots_disponibles]

    for mask_name in masques_retenus:
        masques_corriges[mask_name][y0:y1, x0:x1] = masks[mask_name][y0:y1, x0:x1]

    return BUDGET_MAX


# ============================================================================
# ÉTAPE 4 : EXPORT MASQUES CORRIGÉS
# ============================================================================

def export_masques(masques_corriges: Dict[str, np.ndarray], output_dir: Path):
    """
    Exporte les masques corrigés en PNG 16 bits.
    """
    print(f"[INFO] Export masques dans {output_dir}...")

    output_dir.mkdir(parents=True, exist_ok=True)

    for mask_name, mask_array in masques_corriges.items():
        # Convertir 0-1 → 0-65535
        mask_uint16 = (mask_array * 65535).astype(np.uint16)

        output_path = output_dir / f"{mask_name}.png"
        cv2.imwrite(str(output_path), mask_uint16)

        print(f"[OK] {output_path.name}")

    print(f"[INFO] {len(masques_corriges)} masques exportés")


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Génération masques corrigés sans conflit de budget',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('--masks-dir', type=str, required=True,
                        help='Dossier des masques PNG 16 bits')
    parser.add_argument('--output-dir', type=str, required=True,
                        help='Dossier de sortie pour les masques corrigés')
    parser.add_argument('--exclusion', type=str, default=None,
                        help='Masque d\'exclusion PNG (Zone B)')
    parser.add_argument('--exclude', type=str, nargs='*', default=[],
                        help='Fichiers à ignorer (ex: qtre_map.png)')

    args = parser.parse_args()

    masks_dir = Path(args.masks_dir)
    output_dir = Path(args.output_dir)
    exclusion_path = Path(args.exclusion) if args.exclusion else None

    if not masks_dir.exists():
        print(f"[ERR] Dossier masques introuvable : {masks_dir}")
        return 1

    # Charger catalogue surfaces
    if not TERR_PATH.exists():
        print(f"[ERR] Fichier terrain.terr introuvable : {TERR_PATH}")
        return 1

    surfaces = read_mats_from_terr(TERR_PATH)
    print(f"[INFO] {len(surfaces)} surfaces chargées")

    # Étape 1 : Charger masques
    masks = load_masks(masks_dir, args.exclude)

    if not masks:
        print("[ERR] Aucun masque chargé")
        return 1

    # Résolution cible
    first_mask = next(iter(masks.values()))
    target_shape = first_mask.shape

    # Charger masque exclusion
    exclusion = load_exclusion_mask(exclusion_path, target_shape)

    # Étape 2 : Lire terrain existant
    textures_existantes, poids_existants = read_terrain_state(surfaces)

    # Étape 3 : Fusion intelligente
    masques_corriges = fusion_masques_par_bloc(
        masks, textures_existantes, poids_existants, exclusion, surfaces
    )

    # Étape 4 : Export
    export_masques(masques_corriges, output_dir)

    print()
    print("=" * 80)
    print("PIPELINE V4 TERMINÉ")
    print("=" * 80)
    print(f"Masques corrigés exportés dans : {output_dir}")

    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
