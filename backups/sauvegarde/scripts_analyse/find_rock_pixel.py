import cv2
import numpy as np
import os

base_path = r"h:\logiciel perso\Map generator\data\projects\Zbk_island\generated\terrain_masks"

# Charger Rock
rock = cv2.imread(os.path.join(base_path, "mask_16_Rock_01.png"), cv2.IMREAD_UNCHANGED)

# Trouver pixels avec Rock > 50%
high_rock = np.where(rock > 32767)  # > 50%

if len(high_rock[0]) > 0:
    # Prendre un pixel au hasard
    idx = len(high_rock[0]) // 2
    r, c = high_rock[0][idx], high_rock[1][idx]

    print(f"Pixel montagne trouve: ({r}, {c})")
    print(f"Rock value: {rock[r,c]} ({rock[r,c]/65535*100:.1f}%)")

    # Charger tous les masques
    stems = ['SeaBed_01', 'BeachGrass_01', 'Grass_03_coastal', 'Pebbles_01',
             'Grass_01', 'MountainGrass_01', 'Heather_01', 'Dirt_03',
             'Debris_Rock_01', 'Rock_01']

    masks = {}
    for stem in stems:
        files = [f for f in os.listdir(base_path) if stem in f and f.endswith('.png')]
        if files:
            masks[stem] = cv2.imread(os.path.join(base_path, files[0]), cv2.IMREAD_UNCHANGED)

    print(f"\n{'='*50}")
    print(f"VALEURS MASQUES PIXEL ({r}, {c})")
    print(f"{'='*50}")

    total = 0
    for stem, mask in masks.items():
        val = int(mask[r, c])
        if val > 0:
            pct = val / 65535 * 100
            print(f"{stem:20} : {val:5d} ({pct:5.2f}%)")
            total += val

    print(f"{'-'*50}")
    print(f"{'TOTAL':20} : {total:5d} ({total/65535*100:5.2f}%)")
    print(f"{'MANQUANT':20} : {65535-total:5d} ({(65535-total)/65535*100:5.2f}%)")

    if abs(total - 65535) > 100:
        print(f"\nPROBLEME: {(65535-total)/65535*100:.1f}% manquants")
    else:
        print(f"\nOK: Total = 100%")
else:
    print("Aucun pixel avec Rock > 50%")
