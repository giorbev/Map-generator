"""
Analyse zones d'erreur Workbench
Compare avec masques generes pour trouver cause
"""
import numpy as np
from PIL import Image
from pathlib import Path
from scipy.ndimage import zoom

mask_dir = Path(r"H:\logiciel perso\Map generator\data\projects\Zbk_island\generated\terrain_masks")

# Charger masques generes (4096x4096)
masks = {}
for p in mask_dir.glob("*.png"):
    if "error" not in p.name and "CONFLICT" not in p.name and "DENSITY" not in p.name:
        img = Image.open(p)
        masks[p.stem] = (np.array(img) > 32768).astype(bool)

print(f"Masques charges: {len(masks)}")

# Charger masques erreur (256x256) et upscale
error_masks = {}
for p in mask_dir.glob("error*.png"):
    img = Image.open(p)
    arr = np.array(img)
    # Upscale 256 -> 4096 (x16)
    arr_upscaled = zoom(arr, 16, order=0) > 128
    error_masks[p.stem] = arr_upscaled
    print(f"\nErreur: {p.name}")
    print(f"  Pixels erreur: {np.sum(arr_upscaled)}")

    # Trouver quels masques sont actifs dans zones erreur
    active_in_error = {}
    for name, mask in masks.items():
        overlap = mask & arr_upscaled
        count = np.sum(overlap)
        if count > 0:
            pct = count / np.sum(arr_upscaled) * 100
            active_in_error[name] = (count, pct)

    # Trier par couverture
    sorted_active = sorted(active_in_error.items(), key=lambda x: x[1][1], reverse=True)

    print(f"  Masques actifs dans zone erreur:")
    for name, (count, pct) in sorted_active:
        print(f"    - {name}: {pct:.1f}% ({count} px)")

    # Compter combien de textures par pixel dans zone erreur
    sum_in_error = np.zeros_like(arr_upscaled, dtype=int)
    for name, mask in masks.items():
        sum_in_error += (mask & arr_upscaled).astype(int)

    unique, counts = np.unique(sum_in_error[arr_upscaled], return_counts=True)
    print(f"  Distribution textures/pixel dans zone erreur:")
    for val, cnt in zip(unique, counts):
        print(f"    {val} texture(s): {cnt} pixels")

print("\n" + "="*60)
print("RESUME: Masques presents dans TOUTES les zones erreur")
print("="*60)

# Trouver masques communs a toutes les erreurs
if error_masks:
    common_masks = set(masks.keys())
    for err_name, err_mask in error_masks.items():
        active_in_this_error = set()
        for name, mask in masks.items():
            if np.sum(mask & err_mask) > 0:
                active_in_this_error.add(name)
        common_masks &= active_in_this_error

    print(f"Masques presents partout: {common_masks if common_masks else 'Aucun'}")
