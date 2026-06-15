import cv2
import numpy as np

# Charger TOUS les masques
masks = {}
stems = ['SeaBed_01', 'BeachGrass_01', 'Grass_03_coastal', 'Pebbles_01',
         'Grass_01', 'MountainGrass_01', 'Heather_01', 'Dirt_03',
         'Debris_Rock_01', 'Rock_01']

base_path = r"h:\logiciel perso\Map generator\data\projects\Zbk_island\generated\terrain_masks"

for stem in stems:
    # Trouver le fichier correspondant
    import os
    files = [f for f in os.listdir(base_path) if stem in f and f.endswith('.png')]
    if files:
        path = os.path.join(base_path, files[0])
        masks[stem] = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        print(f"Chargé : {stem}")

# Pixel test (pente raide d'après check_mask_values.py)
r, c = 1132, 5540

print(f"\n{'='*60}")
print(f"PIXEL ({r}, {c})")
print(f"{'='*60}")

# Valeurs masques
total = 0
for stem, mask in masks.items():
    val = int(mask[r, c])
    pct = val / 65535 * 100
    if val > 0:
        print(f"{stem:20} : {val:5d} ({pct:5.2f}%)")
        total += val

print(f"{'-'*60}")
print(f"{'TOTAL':20} : {total:5d} ({total/65535*100:5.2f}%)")
print(f"{'MANQUANT':20} : {65535-total:5d} ({(65535-total)/65535*100:5.2f}%)")

# Vérifier si somme = 65535 (100%)
if abs(total - 65535) > 100:
    print(f"\n❌ PROBLÈME : Total ≠ 65535 (100%)")
    print(f"   -> {(65535-total)/65535*100:.1f}% manquants = BASE Grass_02 visible")
else:
    print(f"\n✅ OK : Total ≈ 65535 (100%)")
