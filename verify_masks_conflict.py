"""
Vérification Superposition Masques
===================================

Détecte les pixels où plusieurs masques sont actifs simultanément
-> Cause erreur "+5 textures" Workbench

"""

import numpy as np
from PIL import Image
from pathlib import Path


def load_mask(mask_path):
    """Charge masque PNG 16-bit et retourne array booléen"""
    img = Image.open(mask_path)
    arr = np.array(img, dtype=np.uint16)

    # Masque actif si valeur > seuil (ex: 65535 = blanc = actif)
    threshold = 1000  # Seuil QTRE ≈ 128/65535 * 65535 ≈ 128
    mask_active = arr > threshold

    return mask_active


def verify_masks(masks_dir):
    """
    Vérifie superposition masques

    Returns:
        dict: {
            'conflicts': list[(x, y, masks_actives)],
            'max_textures_per_pixel': int,
            'conflict_count': int
        }
    """
    masks_dir = Path(masks_dir)

    # Charger tous les masques
    mask_files = sorted(masks_dir.glob("0*_*.png"))

    print(f"Masques trouvés : {len(mask_files)}")
    for mf in mask_files:
        print(f"  - {mf.name}")

    if not mask_files:
        print("Aucun masque trouvé !")
        return None

    # Charger premier masque pour obtenir dimensions
    first_mask = load_mask(mask_files[0])
    H, W = first_mask.shape

    print(f"\nDimensions : {W}×{H} pixels")

    # Stack tous les masques (N_masks, H, W)
    masks = {}
    for mf in mask_files:
        mask_name = mf.stem
        masks[mask_name] = load_mask(mf)

    # Compter nombre textures actives par pixel
    stack = np.stack(list(masks.values()), axis=0)  # (N, H, W)
    textures_per_pixel = np.sum(stack, axis=0)  # (H, W)

    max_textures = int(np.max(textures_per_pixel))

    print(f"\n=== RÉSULTATS ===")
    print(f"Max textures/pixel : {max_textures}")

    # Distribution
    for n in range(max_textures + 1):
        count = np.sum(textures_per_pixel == n)
        pct = (count / (H * W)) * 100
        print(f"  {n} texture(s) : {count:8d} pixels ({pct:5.2f}%)")

    # Détecter conflits (> 1 texture)
    conflicts_mask = textures_per_pixel > 1
    conflict_count = int(np.sum(conflicts_mask))

    if conflict_count > 0:
        print(f"\n⚠️ CONFLITS DÉTECTÉS : {conflict_count} pixels avec superposition")

        # Trouver quels masques se superposent
        conflict_coords = np.argwhere(conflicts_mask)

        # Analyser premiers conflits (max 100 pour ne pas saturer)
        sample_size = min(100, len(conflict_coords))

        conflicts_detail = {}

        for i in range(sample_size):
            y, x = conflict_coords[i]
            active_masks = [name for name, mask in masks.items() if mask[y, x]]

            # Grouper par combinaison
            combo_key = tuple(sorted(active_masks))
            if combo_key not in conflicts_detail:
                conflicts_detail[combo_key] = 0
            conflicts_detail[combo_key] += 1

        print("\nCombinaisons masques superposés (échantillon 100 pixels) :")
        for combo, count in sorted(conflicts_detail.items(), key=lambda x: -x[1]):
            print(f"  {count:3d}× : {' + '.join(combo)}")

        # Générer masque erreur
        error_mask = conflicts_mask.astype(np.uint16) * 65535
        error_img = Image.fromarray(error_mask)
        error_path = masks_dir / "conflict_detected.png"
        error_img.save(error_path)
        print(f"\n✅ Masque conflits sauvegardé : {error_path.name}")

    else:
        print("\n✅ AUCUN CONFLIT : Chaque pixel = 1 texture max")

    return {
        'max_textures_per_pixel': max_textures,
        'conflict_count': conflict_count,
        'total_pixels': H * W
    }


if __name__ == '__main__':
    import sys

    masks_dir = sys.argv[1] if len(sys.argv) > 1 else "data/projects/Zbk_island/generated/terrain_masks"

    print("="*60)
    print("VÉRIFICATION SUPERPOSITION MASQUES")
    print("="*60)
    print(f"Dossier : {masks_dir}\n")

    result = verify_masks(masks_dir)

    print("\n" + "="*60)
    if result and result['conflict_count'] == 0:
        print("✅ VALIDATION : Masques OK pour Workbench")
    else:
        print("❌ ERREUR : Conflits détectés - impossible Workbench")
    print("="*60)
