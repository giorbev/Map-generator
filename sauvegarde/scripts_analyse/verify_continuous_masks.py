"""
Verification Masks Continus
============================

Vérifie qu'un mask est bien continu (pas binaire)
"""

import numpy as np
from PIL import Image
from pathlib import Path
import sys


def verify_mask_continuity(mask_path):
    """
    Vérifie si un mask est continu ou binaire

    Args:
        mask_path: chemin vers le mask PNG 16-bit

    Returns:
        dict: statistiques du mask
    """
    # Charger mask
    mask = np.array(Image.open(mask_path), dtype=np.uint16)

    # Stats
    unique_vals = len(np.unique(mask))
    min_val = np.min(mask)
    max_val = np.max(mask)
    mean_val = np.mean(mask)

    # Pixels en transition (10%-90%)
    mid_range = mask[(mask > 6553) & (mask < 58982)]
    mid_pct = len(mid_range) / mask.size * 100

    # Couverture (moyenne pondérée)
    coverage = np.mean(mask / 65535.0) * 100

    # Déterminer si binaire ou continu
    is_binary = unique_vals <= 3

    return {
        'unique_vals': unique_vals,
        'min': min_val,
        'max': max_val,
        'mean': mean_val,
        'coverage': coverage,
        'mid_pct': mid_pct,
        'is_binary': is_binary
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python verify_continuous_masks.py <folder>")
        sys.exit(1)

    folder = Path(sys.argv[1])

    if not folder.exists():
        print(f"Erreur: dossier introuvable: {folder}")
        sys.exit(1)

    # Lister tous les masks
    masks = sorted(folder.glob("*.png"))

    if not masks:
        print(f"Aucun mask PNG trouve dans: {folder}")
        sys.exit(1)

    print("=" * 100)
    print("VERIFICATION CONTINUITE MASKS")
    print("=" * 100)
    print(f"\nDossier: {folder}")
    print(f"Nombre de masks: {len(masks)}\n")

    print("-" * 100)
    print(f"{'Mask':<35} {'Vals':<8} {'Min':<8} {'Max':<8} {'Couv%':<8} {'Trans%':<8} {'Type':<10}")
    print("-" * 100)

    binary_count = 0
    continuous_count = 0

    for mask_path in masks:
        stats = verify_mask_continuity(mask_path)

        type_str = "[BINAIRE]" if stats['is_binary'] else "[CONTINU]"
        if stats['is_binary']:
            binary_count += 1
        else:
            continuous_count += 1

        print(f"{mask_path.name:<35} "
              f"{stats['unique_vals']:<8} "
              f"{stats['min']:<8} "
              f"{stats['max']:<8} "
              f"{stats['coverage']:<8.2f} "
              f"{stats['mid_pct']:<8.2f} "
              f"{type_str:<10}")

    print("-" * 100)
    print(f"\nRESULTAT:")
    print(f"  Masks continus : {continuous_count}/{len(masks)}")
    print(f"  Masks binaires : {binary_count}/{len(masks)}")

    if binary_count == 0:
        print("\n[OK] Tous les masks sont continus !")
    else:
        print(f"\n[WARNING] {binary_count} mask(s) binaire(s) detecte(s)")

    print("=" * 100)


if __name__ == "__main__":
    main()
