"""
simulate_masks.py — Simulation budget slots par bloc (lecture seule)
=====================================================================
Génère une image PNG 4096×4096 montrant le budget de slots
par bloc après simulation de l'empilement des masques.

Usage:
    python simulate_masks.py --masks-dir path/to/masks
    python simulate_masks.py --masks-dir path/to/masks --output budget.png
"""

import argparse
import sys
import numpy as np
import cv2
from pathlib import Path
from collections import defaultdict

# Import fonctions depuis clean_weights.py
from clean_weights import (
    find_layer_path,
    read_layer_dds,
    read_lrs2_from_ttile,
)

# Chemins
DATA_DIR = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain\.Data")
EDITOR_DATA_DIR = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain\.EditorData")
TTILE_DIR = DATA_DIR

# Constantes
TILE_GRID = 32
BLOC_PER_TILE = 4
TOTAL_BLOCS = 128
BUDGET_MAX = 7
CELL = 32
OUT_SIZE = TOTAL_BLOCS * CELL  # 4096

# Couleurs
COLOR_OK = (0, 180, 0)          # Vert (0-5 slots)
COLOR_LIMIT = (255, 160, 0)     # Orange (6 slots)
COLOR_OVER = (220, 0, 0)        # Rouge (7 slots)
COLOR_CRITICAL = (140, 0, 0)    # Rouge foncé (8+ slots)
COLOR_GRID = (60, 60, 60)       # Gris (grille tuiles)


def detect_bloc_px(mask_size: int) -> int:
    """
    Détecte le nombre de pixels par bloc dans le masque.

    Args:
        mask_size: largeur du masque en pixels

    Returns:
        pixels par bloc
    """
    if mask_size >= 8000:
        return 62  # ~62.5px par bloc
    elif mask_size >= 4000:
        return 32  # 4096/128 = 32px par bloc
    else:
        return mask_size // TOTAL_BLOCS


def read_current_slots() -> np.ndarray:
    """
    Lit l'état actuel des .edds pour compter les slots occupés par bloc.

    Returns:
        Array (128, 128) avec le nombre de slots actuels par bloc
    """
    print("[1/4] Lecture état actuel des .edds...")

    slots_actuels = np.zeros((TOTAL_BLOCS, TOTAL_BLOCS), dtype=np.uint8)

    for ty_reforger in range(TILE_GRID):
        for tx in range(TILE_GRID):
            tile_id = ty_reforger * 32 + tx

            # Lire LRS2
            ttile_path = TTILE_DIR / f"Terrain_{tile_id}.ttile"
            lrs2_blocks = read_lrs2_from_ttile(ttile_path)

            if lrs2_blocks is None:
                continue

            # Compter slots par bloc
            for (bx, by), (mat_ids, orig_index) in lrs2_blocks.items():
                bx_global = tx * 4 + bx
                ty_png = 31 - ty_reforger
                by_global = ty_png * 4 + by
                slots_actuels[by_global, bx_global] = len(mat_ids)

    nb_total = np.count_nonzero(slots_actuels)
    print(f"  {nb_total} blocs avec slots actuels (moyenne: {slots_actuels[slots_actuels>0].mean():.1f})")

    return slots_actuels


def simulate_masks_stacking(masks_dir: Path, slots_actuels: np.ndarray, exclude: list = None, threshold: float = 0.10) -> tuple:
    """
    Simule l'empilement des masques PNG.

    Args:
        masks_dir: dossier contenant les masques PNG
        slots_actuels: array (128, 128) avec slots actuels
        exclude: liste de noms de fichiers à ignorer (optionnel)
        threshold: seuil de coverage minimum pour compter +1 slot (défaut: 0.10)

    Returns:
        (total_slots, mask_contributions)
        total_slots: array (128, 128) avec total après empilement
        mask_contributions: dict {mask_name: count_blocs_touched}
    """
    print("[2/4] Simulation empilement masques...")

    # Charger tous les masques dans l'ordre alphabétique
    mask_files = sorted(masks_dir.glob("*.png"))

    # Filtrer les fichiers exclus
    if exclude:
        exclude_set = set(exclude)
        mask_files = [f for f in mask_files if f.name not in exclude_set]
        if exclude_set:
            print(f"  Exclus: {', '.join(sorted(exclude_set))}")

    if not mask_files:
        print(f"[ERR] Aucun masque PNG trouvé dans {masks_dir}")
        sys.exit(1)

    print(f"  {len(mask_files)} masques à empiler")

    slots_masques = np.zeros((TOTAL_BLOCS, TOTAL_BLOCS), dtype=np.uint8)
    mask_contributions = {}

    for mask_file in mask_files:
        # Charger masque
        mask_img = cv2.imread(str(mask_file), cv2.IMREAD_UNCHANGED)
        if mask_img is None:
            print(f"  [WARN] Impossible de lire {mask_file.name}")
            continue

        # Convertir en binaire
        if len(mask_img.shape) == 3:
            mask_img = cv2.cvtColor(mask_img, cv2.COLOR_BGR2GRAY)
        mask_bin = (mask_img > 0).astype(np.uint8)

        h, w = mask_bin.shape
        bloc_px = detect_bloc_px(w)

        # Compter les blocs touchés par ce masque
        blocs_touched = 0

        for by_global in range(TOTAL_BLOCS):
            for bx_global in range(TOTAL_BLOCS):
                y0 = by_global * bloc_px
                x0 = bx_global * bloc_px
                y1 = min(y0 + bloc_px, h)
                x1 = min(x0 + bloc_px, w)

                zone_bloc = mask_bin[y0:y1, x0:x1]

                # Si coverage >= threshold → +1 slot
                coverage = zone_bloc.sum() / zone_bloc.size
                if coverage >= threshold:
                    if slots_masques[by_global, bx_global] == 0:
                        blocs_touched += 1
                    slots_masques[by_global, bx_global] += 1

        mask_contributions[mask_file.name] = blocs_touched
        print(f"  {mask_file.name}: {blocs_touched} blocs touchés")

    # Total = slots actuels + slots masques
    total_slots = slots_actuels + slots_masques

    return total_slots, mask_contributions


def generate_budget_image(total_slots: np.ndarray) -> np.ndarray:
    """
    Génère l'image 4096×4096 avec code couleur par budget.

    Args:
        total_slots: array (128, 128) avec total slots par bloc

    Returns:
        Image BGR (4096, 4096, 3)
    """
    print("[3/4] Génération image budget...")

    img = np.zeros((OUT_SIZE, OUT_SIZE, 3), dtype=np.uint8)

    # Pour chaque bloc
    for by in range(TOTAL_BLOCS):
        for bx in range(TOTAL_BLOCS):
            slots = total_slots[by, bx]

            # Choisir couleur
            if slots <= 5:
                color = COLOR_OK
            elif slots == 6:
                color = COLOR_LIMIT
            elif slots == 7:
                color = COLOR_OVER
            else:
                color = COLOR_CRITICAL

            # Dessiner carré 32×32
            y0 = by * CELL
            x0 = bx * CELL
            img[y0:y0+CELL, x0:x0+CELL] = color

    # Grille tuiles (toutes les 128px = 4 blocs)
    for i in range(1, TILE_GRID):
        pos = i * BLOC_PER_TILE * CELL
        cv2.line(img, (pos, 0), (pos, OUT_SIZE), COLOR_GRID, 1)
        cv2.line(img, (0, pos), (OUT_SIZE, pos), COLOR_GRID, 1)

    return img


def print_statistics(total_slots: np.ndarray, mask_contributions: dict):
    """
    Affiche les statistiques en console.

    Args:
        total_slots: array (128, 128) avec total slots par bloc
        mask_contributions: dict {mask_name: count_blocs_touched}
    """
    print("[4/4] Statistiques budget...")
    print()
    print("=" * 80)
    print("RÉSULTAT SIMULATION")
    print("=" * 80)

    # Comptage par catégorie
    ok = np.sum(total_slots <= 5)
    limit = np.sum(total_slots == 6)
    over = np.sum(total_slots == 7)
    critical = np.sum(total_slots >= 8)

    print()
    print("Budget par bloc :")
    print(f"  0-5 slots (OK)         : {ok:5d} blocs ({ok/TOTAL_BLOCS**2*100:5.1f}%)")
    print(f"  6 slots (Limite)       : {limit:5d} blocs ({limit/TOTAL_BLOCS**2*100:5.1f}%)")
    print(f"  7 slots (Dépassement)  : {over:5d} blocs ({over/TOTAL_BLOCS**2*100:5.1f}%)")
    print(f"  8+ slots (Critique)    : {critical:5d} blocs ({critical/TOTAL_BLOCS**2*100:5.1f}%)")

    # Masques contributeurs
    print()
    print("Contribution par masque (blocs touchés) :")
    for mask_name, count in sorted(mask_contributions.items(), key=lambda x: -x[1]):
        print(f"  {mask_name}: {count} blocs")

    # Tuiles avec le plus de conflits
    print()
    print("Tuiles avec le plus de dépassements (≥7 slots) :")
    tiles_issues = defaultdict(int)

    for by in range(TOTAL_BLOCS):
        for bx in range(TOTAL_BLOCS):
            if total_slots[by, bx] >= 7:
                tx = bx // 4
                ty_reforger = by // 4
                tiles_issues[(tx, ty_reforger)] += 1

    if tiles_issues:
        for (tx, ty_reforger), count in sorted(tiles_issues.items(), key=lambda x: -x[1])[:10]:
            tile_id = ty_reforger * 32 + tx
            print(f"  Tuile ({tx:2d},{ty_reforger:2d}) T{tile_id:3d} : {count} blocs en dépassement")
    else:
        print("  Aucun dépassement détecté !")

    print()


def main():
    parser = argparse.ArgumentParser(
        description='Simulation budget slots par bloc (lecture seule)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  python simulate_masks.py --masks-dir data/projects/Zimnitrita/exports_mask
  python simulate_masks.py --masks-dir masks/ --output budget_slots.png
        """
    )

    parser.add_argument('--masks-dir', type=str, required=True,
                       help='Dossier contenant les masques PNG')
    parser.add_argument('--output', type=str, default='simulate_masks.png',
                       help='Chemin du PNG de sortie (défaut: simulate_masks.png)')
    parser.add_argument('--exclude', nargs='*', default=[],
                       help='Noms de fichiers PNG à exclure de la simulation')
    parser.add_argument('--threshold', type=float, default=0.10,
                       help='Seuil de coverage minimum pour +1 slot (défaut: 0.10)')

    args = parser.parse_args()

    masks_dir = Path(args.masks_dir)
    output_path = Path(args.output)

    if not masks_dir.exists():
        print(f"[ERR] Dossier masques introuvable: {masks_dir}")
        return 1

    print("=" * 80)
    print("SIMULATION BUDGET SLOTS PAR BLOC")
    print("=" * 80)
    print(f"Masques: {masks_dir}")
    print(f"Output:  {output_path}")
    print()

    # 1. Lire état actuel
    slots_actuels = read_current_slots()

    # 2. Simuler empilement
    total_slots, mask_contributions = simulate_masks_stacking(masks_dir, slots_actuels, args.exclude, args.threshold)

    # 3. Générer image
    img = generate_budget_image(total_slots)

    # 4. Sauvegarder
    cv2.imwrite(str(output_path), img)
    print(f"  Image sauvegardée: {output_path}")

    # 5. Statistiques
    print_statistics(total_slots, mask_contributions)

    print("=" * 80)
    print("Simulation terminée")
    print("=" * 80)

    return 0


if __name__ == '__main__':
    sys.exit(main())
