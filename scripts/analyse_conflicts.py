"""
analyse_conflicts.py — Analyse des conflits avant import masques dans Workbench

Script lecture seule : aucune écriture .edds ou .ttile.

Analyse l'état actuel des blocs terrain + simule l'empilement des masques
pour identifier les conflits (>7 slots) avant import dans Workbench.

Usage:
    python analyse_conflicts.py --masks-dir OUTPUT_DIR --output-png conflicts.png --output-json conflicts.json
"""

import argparse
import json
import cv2
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Set

# Import fonctions depuis clean_weights.py
from clean_weights import find_layer_path, read_lrs2_from_ttile

# Import lecture terrain.terr
from terrain_terr_reader import read_mats_from_terr


# ============================================================================
# CONFIGURATION
# ============================================================================

# Chemins — même valeurs que dans clean_weights.py
TERRAIN_ROOT = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain")
DATA_DIR = TERRAIN_ROOT / ".Data"
EDITOR_DATA_DIR = TERRAIN_ROOT / ".EditorData"
TERR_PATH = TERRAIN_ROOT / "terrain.terr"

# Grille Reforger
NUM_TILES = 32
BLOCS_PER_TILE = 4
TOTAL_BLOCS = NUM_TILES * BLOCS_PER_TILE  # 128×128 blocs

# Couleurs image
COLOR_OK = (0, 180, 0)           # Vert : 0-5 slots total
COLOR_OK_EXISTING = (0, 180, 180)  # Cyan : OK mais terrain existant
COLOR_LIMIT = (255, 160, 0)      # Orange : 6-7 slots
COLOR_CONFLICT = (220, 0, 0)     # Rouge : >7 slots
COLOR_EMPTY = (60, 60, 60)       # Gris : Hors zone masques


# ============================================================================
# ÉTAPE 1 : LIRE ÉTAT ACTUEL TERRAIN
# ============================================================================

def read_current_state(surfaces: List[Dict]) -> Tuple[np.ndarray, Dict]:
    """
    Lit l'état actuel de tous les blocs terrain depuis les .edds et .ttile.

    Returns:
        slots_actuels : array (128, 128) int — nombre slots utilisés par bloc
        mats_actuels  : dict {(bx_global, by_global): set(mat_ids)}
    """
    print("[INFO] Lecture état actuel terrain...")

    slots_actuels = np.zeros((TOTAL_BLOCS, TOTAL_BLOCS), dtype=np.int32)
    mats_actuels = {}

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

            # Pour chaque bloc de la tuile
            for (bx, by), (mat_ids, orig_index) in lrs2_blocks.items():
                bx_global = tx * BLOCS_PER_TILE + bx
                by_global = ty * BLOCS_PER_TILE + by

                slots_actuels[by_global, bx_global] = len(mat_ids)
                mats_actuels[(bx_global, by_global)] = set(mat_ids)

    total_slots = slots_actuels.sum()
    blocs_utilises = (slots_actuels > 0).sum()

    print(f"[INFO] État actuel : {blocs_utilises}/{TOTAL_BLOCS**2} blocs utilisés, {total_slots} slots totaux")

    return slots_actuels, mats_actuels


# ============================================================================
# ÉTAPE 2 : CHARGER MASQUES
# ============================================================================

def load_masks(masks_dir: Path, exclude: List[str] = None) -> List[Tuple[str, np.ndarray]]:
    """
    Charge tous les masques PNG du dossier, triés par ordre alphabétique.

    Returns:
        Liste de (nom_masque, masque_binaire)
        masque_binaire : (H, W) uint8, 0 ou 1
    """
    print(f"[INFO] Chargement masques depuis {masks_dir}...")

    if exclude is None:
        exclude = []

    mask_files = sorted(masks_dir.glob("*.png"))
    masks = []

    for mask_path in mask_files:
        if mask_path.name in exclude:
            print(f"[SKIP] {mask_path.name} (exclu)")
            continue

        img = cv2.imread(str(mask_path), cv2.IMREAD_UNCHANGED)
        if img is None:
            print(f"[WARN] Impossible de lire {mask_path.name}")
            continue

        # Convertir en binaire (blanc = présent)
        if len(img.shape) == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        mask_bin = (img > 0).astype(np.uint8)

        masks.append((mask_path.stem, mask_bin))
        print(f"[OK] {mask_path.name} ({mask_bin.shape[1]}×{mask_bin.shape[0]})")

    print(f"[INFO] {len(masks)} masques chargés")
    return masks


# ============================================================================
# ÉTAPE 3 : CALCULER SLOTS MASQUES PAR BLOC
# ============================================================================

def compute_masks_slots(masks: List[Tuple[str, np.ndarray]]) -> Tuple[np.ndarray, Dict]:
    """
    Calcule le nombre de slots ajoutés par les masques pour chaque bloc.

    Returns:
        slots_masques : array (128, 128) int — nombre masques s'appliquant au bloc
        masques_per_bloc : dict {(bx, by): [mask_names]} — liste masques par bloc
    """
    print("[INFO] Calcul slots masques par bloc...")

    slots_masques = np.zeros((TOTAL_BLOCS, TOTAL_BLOCS), dtype=np.int32)
    masques_per_bloc = {}

    # Détecter résolution
    if not masks:
        return slots_masques, masques_per_bloc

    h, w = masks[0][1].shape
    px_per_bloc = w // TOTAL_BLOCS

    print(f"[INFO] Résolution masques : {w}×{h}, {px_per_bloc} px/bloc")

    for mask_name, mask_bin in masks:
        for by in range(TOTAL_BLOCS):
            for bx in range(TOTAL_BLOCS):
                # Orientation PNG inversée : ty_png = 31 - ty_reforger
                # Bloc Reforger (bx, by) → (bx, TOTAL_BLOCS - 1 - by) dans PNG
                by_png = TOTAL_BLOCS - 1 - by

                y0 = by_png * px_per_bloc
                x0 = bx * px_per_bloc
                y1 = y0 + px_per_bloc
                x1 = x0 + px_per_bloc

                # Vérifier au moins 1 pixel blanc dans la zone
                zone = mask_bin[y0:y1, x0:x1]
                if zone.sum() > 0:
                    slots_masques[by, bx] += 1

                    if (bx, by) not in masques_per_bloc:
                        masques_per_bloc[(bx, by)] = []
                    masques_per_bloc[(bx, by)].append(mask_name)

    total_slots_masques = slots_masques.sum()
    blocs_masques = (slots_masques > 0).sum()

    print(f"[INFO] Masques : {blocs_masques}/{TOTAL_BLOCS**2} blocs touchés, {total_slots_masques} slots ajoutés")

    return slots_masques, masques_per_bloc


# ============================================================================
# ÉTAPE 4 : ANALYSER CONFLITS
# ============================================================================

def analyze_conflicts(
    slots_actuels: np.ndarray,
    slots_masques: np.ndarray,
    mats_actuels: Dict,
    masques_per_bloc: Dict,
    surfaces: List[Dict]
) -> Dict:
    """
    Analyse les conflits et génère les statistiques.

    Returns:
        dict avec summary et liste détaillée des conflits
    """
    print("[INFO] Analyse des conflits...")

    total_slots = slots_actuels + slots_masques

    # Compteurs
    ok_count = 0
    ok_existing_count = 0
    limit_count = 0
    conflict_count = 0

    conflicts = []

    for by in range(TOTAL_BLOCS):
        for bx in range(TOTAL_BLOCS):
            slots_act = int(slots_actuels[by, bx])
            slots_mask = int(slots_masques[by, bx])
            total = int(total_slots[by, bx])

            # Calculer tuile
            tx = bx // BLOCS_PER_TILE
            ty = by // BLOCS_PER_TILE
            tile_id = ty * NUM_TILES + tx

            # Stratégie
            if total <= 5:
                if slots_act > 0:
                    ok_existing_count += 1
                else:
                    ok_count += 1
            elif total <= 7:
                limit_count += 1
                # Ajouter aux conflits
                conflicts.append({
                    "lrs_x": bx,
                    "lrs_y": by,
                    "tx": tx,
                    "ty": ty,
                    "tile_id": tile_id,
                    "slots_actuels": slots_act,
                    "slots_masques": slots_mask,
                    "total": total,
                    "mats_existants": get_mat_names(mats_actuels.get((bx, by), set()), surfaces),
                    "masques_appliques": masques_per_bloc.get((bx, by), []),
                    "strategie": "limite"
                })
            else:
                conflict_count += 1
                # Stratégie conflit
                if slots_act == 0:
                    strat = "conflit_terrain_vierge"
                else:
                    strat = "conflit_terrain_existant"

                conflicts.append({
                    "lrs_x": bx,
                    "lrs_y": by,
                    "tx": tx,
                    "ty": ty,
                    "tile_id": tile_id,
                    "slots_actuels": slots_act,
                    "slots_masques": slots_mask,
                    "total": total,
                    "mats_existants": get_mat_names(mats_actuels.get((bx, by), set()), surfaces),
                    "masques_appliques": masques_per_bloc.get((bx, by), []),
                    "strategie": strat
                })

    summary = {
        "total_blocs": TOTAL_BLOCS * TOTAL_BLOCS,
        "ok": ok_count,
        "ok_existing": ok_existing_count,
        "limite": limit_count,
        "conflit": conflict_count
    }

    print(f"[RÉSUMÉ] OK: {ok_count}, OK (existant): {ok_existing_count}, "
          f"Limite: {limit_count}, Conflit: {conflict_count}")

    return {
        "summary": summary,
        "conflits": conflicts
    }


def get_mat_names(mat_ids: Set[int], surfaces: List[Dict]) -> List[str]:
    """Convertit les IDs matériaux en noms."""
    names = []
    for mid in sorted(mat_ids):
        if mid < len(surfaces):
            names.append(surfaces[mid]["name"])
        else:
            names.append(f"MAT_{mid}")
    return names


# ============================================================================
# ÉTAPE 5 : GÉNÉRER IMAGE
# ============================================================================

def generate_image(
    slots_actuels: np.ndarray,
    slots_masques: np.ndarray,
    output_path: Path
):
    """
    Génère l'image 4096×4096 avec code couleur par bloc.
    """
    print(f"[INFO] Génération image {output_path}...")

    total_slots = slots_actuels + slots_masques

    # Image 4096×4096 (128 blocs × 32 px)
    img_size = TOTAL_BLOCS * 32
    img = np.zeros((img_size, img_size, 3), dtype=np.uint8)

    for by in range(TOTAL_BLOCS):
        for bx in range(TOTAL_BLOCS):
            slots_act = int(slots_actuels[by, bx])
            slots_mask = int(slots_masques[by, bx])
            total = int(total_slots[by, bx])

            # Orientation PNG inversée
            by_png = TOTAL_BLOCS - 1 - by

            y0 = by_png * 32
            x0 = bx * 32
            y1 = y0 + 32
            x1 = x0 + 32

            # Couleur selon stratégie
            if total == 0:
                color = COLOR_EMPTY
            elif total <= 5:
                if slots_act > 0:
                    color = COLOR_OK_EXISTING
                else:
                    color = COLOR_OK
            elif total <= 7:
                color = COLOR_LIMIT
            else:
                color = COLOR_CONFLICT

            img[y0:y1, x0:x1] = color

    # Grille fine 1px entre tuiles (toutes les 128px)
    for i in range(0, img_size + 1, 128):
        if i < img_size:
            img[i, :] = (100, 100, 100)  # Ligne horizontale
            img[:, i] = (100, 100, 100)  # Ligne verticale

    # Convertir BGR pour cv2
    img_bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    cv2.imwrite(str(output_path), img_bgr)

    print(f"[OK] Image sauvegardée : {output_path}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Analyse des conflits avant import masques dans Workbench',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('--masks-dir', type=str, required=True,
                        help='Dossier contenant les masques PNG')
    parser.add_argument('--output-png', type=str, default='conflicts.png',
                        help='Image de sortie (défaut: conflicts.png)')
    parser.add_argument('--output-json', type=str, default='conflicts.json',
                        help='JSON de sortie (défaut: conflicts.json)')
    parser.add_argument('--exclude', type=str, nargs='*', default=[],
                        help='Masques à exclure (ex: qtre_map.png)')

    args = parser.parse_args()

    masks_dir = Path(args.masks_dir)
    output_png = Path(args.output_png)
    output_json = Path(args.output_json)

    if not masks_dir.exists():
        print(f"[ERR] Dossier masques introuvable : {masks_dir}")
        return 1

    # Charger catalogue surfaces
    if not TERR_PATH.exists():
        print(f"[ERR] Fichier terrain.terr introuvable : {TERR_PATH}")
        return 1

    surfaces = read_mats_from_terr(TERR_PATH)
    print(f"[INFO] {len(surfaces)} surfaces chargées depuis terrain.terr")

    # Étape 1 : État actuel
    slots_actuels, mats_actuels = read_current_state(surfaces)

    # Étape 2 : Charger masques
    masks = load_masks(masks_dir, args.exclude)

    if not masks:
        print("[ERR] Aucun masque chargé")
        return 1

    # Étape 3 : Slots masques
    slots_masques, masques_per_bloc = compute_masks_slots(masks)

    # Étape 4 : Analyser conflits
    analysis = analyze_conflicts(slots_actuels, slots_masques, mats_actuels, masques_per_bloc, surfaces)

    # Étape 5 : Générer image
    generate_image(slots_actuels, slots_masques, output_png)

    # Étape 6 : Écrire JSON
    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(analysis, f, indent=2, ensure_ascii=False)

    print(f"[OK] JSON sauvegardé : {output_json}")

    # Résumé final
    print()
    print("=" * 80)
    print("RÉSUMÉ ANALYSE")
    print("=" * 80)
    print(f"Total blocs       : {analysis['summary']['total_blocs']}")
    print(f"✓ OK              : {analysis['summary']['ok']} blocs")
    print(f"✓ OK (existant)   : {analysis['summary']['ok_existing']} blocs")
    print(f"⚠ Limite (6-7)    : {analysis['summary']['limite']} blocs")
    print(f"✗ Conflit (>7)    : {analysis['summary']['conflit']} blocs")
    print()

    if analysis['summary']['conflit'] > 0:
        print(f"[WARN] {analysis['summary']['conflit']} blocs en conflit détectés !")
        print(f"[INFO] Voir détails dans {output_json}")
        return 1

    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
