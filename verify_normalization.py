import cv2
import numpy as np
import os

base_path = r"h:\logiciel perso\Map generator\data\projects\Zbk_island\generated\terrain_masks"

# Charger TOUS les masques avec noms EXACTS
masks = {
    'SeaBed_01': 'mask_01_SeaBed_01.png',
    'BeachGrass_01': 'mask_02_BeachGrass_01.png',
    'Grass_03_coastal': 'mask_03_Grass_03_coastal.png',
    'Pebbles_01': 'mask_04_Pebbles_01.png',
    'Grass_01': 'mask_06_Grass_01.png',
    'MountainGrass_01': 'mask_08_MountainGrass_01.png',
    'Heather_01': 'mask_11_Heather_01.png',
    'Dirt_03': 'mask_14_Dirt_03.png',
    'Debris_Rock_01': 'mask_15_Debris_Rock_01.png',
    'Rock_01': 'mask_16_Rock_01.png',
}

data = {}
for name, fname in masks.items():
    path = os.path.join(base_path, fname)
    if os.path.exists(path):
        data[name] = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        print(f"Charge: {fname}")

# Tester plusieurs pixels aléatoires
H, W = data['Rock_01'].shape
np.random.seed(42)
pixels_test = [(np.random.randint(0, H), np.random.randint(0, W)) for _ in range(10)]

print(f"\n{'='*70}")
print(f"VERIFICATION NORMALISATION (10 pixels aleatoires)")
print(f"{'='*70}\n")

for i, (r, c) in enumerate(pixels_test):
    total = sum(int(mask[r, c]) for mask in data.values())
    pct = total / 65535 * 100

    # Afficher seulement si total != 100%
    if abs(pct - 100.0) > 1.0:  # Tolérance 1%
        print(f"Pixel {i+1} ({r:4d}, {c:4d}):")
        for name, mask in data.items():
            val = int(mask[r, c])
            if val > 0:
                print(f"  {name:20} : {val:5d} ({val/65535*100:5.2f}%)")
        print(f"  {'TOTAL':20} : {total:5d} ({pct:5.2f}%)")
        print(f"  {'MANQUANT':20} : {65535-total:5d} ({(65535-total)/65535*100:5.2f}%)")
        print()

# Stats globales
totals = []
for r in range(0, H, 100):  # Échantillon tous les 100px
    for c in range(0, W, 100):
        total = sum(int(mask[r, c]) for mask in data.values())
        totals.append(total)

totals = np.array(totals)
print(f"\n{'='*70}")
print(f"STATS GLOBALES ({len(totals)} pixels echantillon)")
print(f"{'='*70}")
print(f"Total moyen   : {totals.mean():.0f} ({totals.mean()/65535*100:.1f}%)")
print(f"Total min     : {totals.min()} ({totals.min()/65535*100:.1f}%)")
print(f"Total max     : {totals.max()} ({totals.max()/65535*100:.1f}%)")
print(f"Ecart-type    : {totals.std():.0f}")
print(f"\nPixels < 90%  : {(totals < 58981).sum()} ({(totals < 58981).sum()/len(totals)*100:.1f}%)")
print(f"Pixels < 80%  : {(totals < 52428).sum()} ({(totals < 52428).sum()/len(totals)*100:.1f}%)")
print(f"Pixels > 110% : {(totals > 72088).sum()} ({(totals > 72088).sum()/len(totals)*100:.1f}%)")
