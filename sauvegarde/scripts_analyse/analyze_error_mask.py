"""
Analyse Error Rock - Trouve EXACTEMENT quels masques sont en conflit
"""

import numpy as np
from PIL import Image
from pathlib import Path


def analyze_error_mask(masks_dir):
    """Analyse error rock.png pour trouver les conflits EXACTS"""

    masks_dir = Path(masks_dir)

    # Charger error mask
    error_path = masks_dir / "error rock.png"
    if not error_path.exists():
        print(f"ERROR: {error_path} introuvable !")
        return

    print(f"Chargement {error_path.name}...")
    error_img = Image.open(error_path)
    error_arr = np.array(error_img, dtype=np.uint16)

    # Pixels avec erreur
    error_pixels = error_arr > 1000
    error_count = np.sum(error_pixels)

    print(f"Pixels avec erreur : {error_count}")

    if error_count == 0:
        print("Aucune erreur dans le masque !")
        return

    # Trouver coordonnées erreurs (échantillon)
    error_coords = np.argwhere(error_pixels)
    sample_size = min(100, len(error_coords))

    print(f"\nAnalyse {sample_size} pixels d'erreur...")

    # Charger TOUS les masques
    mask_files = {
        '01_seabed': masks_dir / '01_seabed.png',
        '02_coastal': masks_dir / '02_coastal.png',
        '03_grass_lowland': masks_dir / '03_grass_lowland.png',
        '04_grass_midland': masks_dir / '04_grass_midland.png',
        '05_grass_highland': masks_dir / '05_grass_highland.png',
        '06_debris': masks_dir / '06_debris.png',
        '07_rock': masks_dir / '07_rock.png',
    }

    masks = {}
    for name, path in mask_files.items():
        if path.exists():
            img = Image.open(path)
            arr = np.array(img, dtype=np.uint16)
            masks[name] = arr
            print(f"  Chargé : {name}")

    print("\n" + "="*60)
    print("ANALYSE CONFLITS SUR PIXELS ERREUR")
    print("="*60)

    # Pour chaque pixel erreur, voir quels masques sont actifs
    conflicts_detail = {}

    for i in range(sample_size):
        y, x = error_coords[i]

        # Vérifier TOUTES les valeurs (pas juste > seuil)
        active = []
        for name, arr in masks.items():
            val = arr[y, x]
            if val > 1000:  # Seuil activité
                active.append(f"{name}({val})")

        if len(active) > 1:
            combo_key = tuple(sorted(active))
            if combo_key not in conflicts_detail:
                conflicts_detail[combo_key] = []
            conflicts_detail[combo_key].append((x, y))

    print(f"\nConflits détectés : {len(conflicts_detail)} combinaisons\n")

    for combo, coords in sorted(conflicts_detail.items(), key=lambda x: -len(x[1])):
        print(f"{len(coords):5d} pixels : {' + '.join(combo)}")
        # Montrer 3 exemples coordonnées
        for j in range(min(3, len(coords))):
            x, y = coords[j]
            print(f"         Exemple pixel ({x}, {y})")

    # Compter combien de fois chaque masque apparaît dans les conflits
    print("\n" + "="*60)
    print("MASQUES IMPLIQUÉS DANS CONFLITS")
    print("="*60)

    mask_conflict_count = {}
    for combo in conflicts_detail.keys():
        for item in combo:
            mask_name = item.split('(')[0]
            if mask_name not in mask_conflict_count:
                mask_conflict_count[mask_name] = 0
            mask_conflict_count[mask_name] += len(conflicts_detail[combo])

    for mask_name, count in sorted(mask_conflict_count.items(), key=lambda x: -x[1]):
        print(f"{mask_name:20s} : {count:6d} pixels en conflit")

    print("\n" + "="*60)
    print("CONCLUSION")
    print("="*60)

    if len(conflicts_detail) > 0:
        top_conflict = sorted(conflicts_detail.items(), key=lambda x: -len(x[1]))[0]
        print(f"\nConflit principal : {' + '.join(top_conflict[0])}")
        print(f"Nombre pixels : {len(top_conflict[1])}")
    else:
        print("\nAUCUN CONFLIT DÉTECTÉ (bizarre...)")


if __name__ == '__main__':
    import sys

    masks_dir = sys.argv[1] if len(sys.argv) > 1 else "data/projects/Zbk_island/generated/terrain_masks"

    analyze_error_mask(masks_dir)
