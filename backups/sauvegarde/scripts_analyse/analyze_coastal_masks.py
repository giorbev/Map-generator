import cv2
import numpy as np
import os

# Charger heightmap pour identifier zone côtière
hm_path = r"h:\logiciel perso\Map generator\data\projects\Zbk_island\sources\temp_ZBK_terrain_modified7.asc"

# Lire ASC
hm = np.loadtxt(hm_path, skiprows=6).astype(np.float32)

# Min/max
min_alt = hm.min()
max_alt = hm.max()
alt_range = max_alt - min_alt

print(f"ANALYSE ZONE COTIERE - ZBK")
print(f"=" * 70)
print(f"\nAltitudes carte :")
print(f"  Min : {min_alt:.2f}m")
print(f"  Max : {max_alt:.2f}m")
print(f"  Range : {alt_range:.2f}m")

# Zone côtière = altitude 0-30m
coastal_min = 0.0
coastal_max = 30.0

# Normaliser
coastal_min_norm = (coastal_min - min_alt) / alt_range
coastal_max_norm = (coastal_max - min_alt) / alt_range

print(f"\nZone cotiere (0-30m) :")
print(f"  Normalise : {coastal_min_norm:.4f} - {coastal_max_norm:.4f}")

# Trouver pixels côtiers dans heightmap
coastal_mask = (hm >= coastal_min) & (hm <= coastal_max)
print(f"  Pixels : {np.sum(coastal_mask):,} ({np.sum(coastal_mask)/hm.size*100:.1f}% carte)")

# Charger masques
base_path = r"h:\logiciel perso\Map generator\data\projects\Zbk_island\generated\terrain_masks"

coastal_textures = {
    'SeaBed_01': 'mask_01_SeaBed_01.png',
    'BeachGrass_01': 'mask_02_BeachGrass_01.png',
    'Pebbles_01': 'mask_04_Pebbles_01.png',
    'Grass_01': 'mask_06_Grass_01.png',
    'Grass_02': None  # Peut ne pas exister
}

masks = {}
for name, fname in coastal_textures.items():
    if fname is None:
        # Chercher
        files = [f for f in os.listdir(base_path) if 'Grass_02' in f]
        if files:
            fname = files[0]
        else:
            continue

    path = os.path.join(base_path, fname)
    if os.path.exists(path):
        # Charger et resize à taille heightmap
        mask = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if mask.shape != hm.shape:
            mask = cv2.resize(mask, (hm.shape[1], hm.shape[0]), interpolation=cv2.INTER_LINEAR)
        masks[name] = mask

print(f"\n{'='*70}")
print(f"MASQUES SUR ZONE COTIERE (0-30m altitude)")
print(f"{'='*70}")

for name, mask in masks.items():
    # Valeurs sur zone côtière
    coastal_values = mask[coastal_mask]

    # Stats
    mean_val = coastal_values.mean()
    max_val = coastal_values.max()
    pct_active = (coastal_values > 1000).sum() / len(coastal_values) * 100

    print(f"\n{name:20} :")
    print(f"  Moyenne : {mean_val:.0f} ({mean_val/65535*100:.1f}%)")
    print(f"  Max     : {max_val} ({max_val/65535*100:.1f}%)")
    print(f"  Actif   : {pct_active:.1f}% pixels (>1000)")

# Vérifier pixels dans l'eau (altitude < 0m)
water_mask = hm < 0.0
print(f"\n{'='*70}")
print(f"MASQUES DANS L'EAU (altitude < 0m)")
print(f"{'='*70}")
print(f"\nPixels sous l'eau : {np.sum(water_mask):,}")

for name, mask in masks.items():
    if name == 'SeaBed_01':
        continue  # Normal qu'il soit dans l'eau

    water_values = mask[water_mask]
    pct_active = (water_values > 1000).sum() / len(water_values) * 100

    if pct_active > 1.0:
        print(f"\n{name:20} : {pct_active:.1f}% actif dans l'eau !!! <- PROBLEME")
    else:
        print(f"{name:20} : OK ({pct_active:.2f}% actif)")
