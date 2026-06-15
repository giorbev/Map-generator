"""
Diagnostic PRÉCIS : Où sont les trous Grass_02 sur la côte et POURQUOI ?
"""

import cv2
import numpy as np

# Charger heightmap
hm = np.loadtxt(r"h:\logiciel perso\Map generator\data\projects\Zbk_island\sources\temp_ZBK_terrain_modified7.asc", skiprows=6).astype(np.float32)

# Charger slope
slope_path = r"h:\logiciel perso\Map generator\data\projects\Zbk_island\sources\slope.png"
slope = cv2.imread(slope_path, cv2.IMREAD_UNCHANGED)
if slope.shape != hm.shape:
    slope = cv2.resize(slope, (hm.shape[1], hm.shape[0]), interpolation=cv2.INTER_LINEAR)
slope_deg = slope.astype(np.float32) / 65535.0 * 90.0

min_alt = hm.min()
max_alt = hm.max()
alt_range = max_alt - min_alt

print("=" * 80)
print("DIAGNOSTIC TROUS GRASS_02 SUR ZONE COTIERE")
print("=" * 80)

# Zone côtière 0-30m
coastal_mask = (hm >= 0.0) & (hm <= 30.0)
print(f"\nZone cotiere (0-30m) : {np.sum(coastal_mask):,} pixels")

# Charger masques
base_path = r"h:\logiciel perso\Map generator\data\projects\Zbk_island\generated\terrain_masks"

def load_mask(name_pattern):
    import os
    files = [f for f in os.listdir(base_path) if name_pattern in f and f.endswith('.png')]
    if not files:
        return None
    path = os.path.join(base_path, files[0])
    mask = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if mask.shape != hm.shape:
        mask = cv2.resize(mask, (hm.shape[1], hm.shape[0]), interpolation=cv2.INTER_LINEAR)
    return mask

beachgrass = load_mask('BeachGrass')
pebbles = load_mask('Pebbles')
grass03 = load_mask('Grass_03')
seabed = load_mask('SeaBed')

# Calculer somme sur zone côtière
all_masks = []
names = []

for pattern, name in [('BeachGrass', 'BeachGrass'), ('Pebbles', 'Pebbles'),
                       ('Grass_03', 'Grass_03_coastal'), ('SeaBed', 'SeaBed')]:
    m = load_mask(pattern)
    if m is not None:
        all_masks.append(m[coastal_mask])
        names.append(name)
        print(f"{name:20} charge")

if not all_masks:
    print("ERREUR : Aucun masque trouve")
    exit(1)

total = np.sum(all_masks, axis=0)

# Identifier TROUS (somme < 90%)
threshold = 58982  # 90% de 65535
holes_mask = total < threshold
n_holes = np.sum(holes_mask)
holes_pct = n_holes / len(total) * 100

print(f"\n{'='*80}")
print(f"RESULTATS")
print(f"{'='*80}")
print(f"\nSomme totale moyenne : {total.mean():.0f} ({total.mean()/65535*100:.1f}%)")
print(f"Pixels avec somme < 90% : {n_holes:,} ({holes_pct:.1f}% de la cote)")

if n_holes == 0:
    print("\n>>> AUCUN TROU ! Tout est OK <<<")
    exit(0)

# Analyser les TROUS : altitude et slope
coastal_indices = np.where(coastal_mask)
coastal_alt = hm[coastal_indices]
coastal_slope = slope_deg[coastal_indices]

holes_alt = coastal_alt[holes_mask]
holes_slope = coastal_slope[holes_mask]

print(f"\n{'='*80}")
print(f"ANALYSE DES TROUS (pixels avec somme < 90%)")
print(f"{'='*80}")

print(f"\nAltitude des trous :")
print(f"  Min     : {holes_alt.min():.1f}m")
print(f"  Max     : {holes_alt.max():.1f}m")
print(f"  Moyenne : {holes_alt.mean():.1f}m")
print(f"  P25     : {np.percentile(holes_alt, 25):.1f}m")
print(f"  P50     : {np.percentile(holes_alt, 50):.1f}m")
print(f"  P75     : {np.percentile(holes_alt, 75):.1f}m")

print(f"\nSlope des trous :")
print(f"  Min     : {holes_slope.min():.1f}°")
print(f"  Max     : {holes_slope.max():.1f}°")
print(f"  Moyenne : {holes_slope.mean():.1f}°")
print(f"  P25     : {np.percentile(holes_slope, 25):.1f}°")
print(f"  P50     : {np.percentile(holes_slope, 50):.1f}°")
print(f"  P75     : {np.percentile(holes_slope, 75):.1f}°")

# Distribution des trous par tranches
print(f"\n{'='*80}")
print(f"DISTRIBUTION DES TROUS")
print(f"{'='*80}")

print(f"\nPar altitude :")
alt_ranges = [(0, 10), (10, 20), (20, 30)]
for alt_min, alt_max in alt_ranges:
    count = np.sum((holes_alt >= alt_min) & (holes_alt < alt_max))
    pct = count / n_holes * 100 if n_holes > 0 else 0
    bar = "#" * int(pct / 2)
    print(f"  {alt_min:2d}-{alt_max:2d}m : {count:8,} ({pct:5.1f}%) {bar}")

print(f"\nPar slope :")
slope_ranges = [(0, 10), (10, 15), (15, 20), (20, 25), (25, 30), (30, 90)]
for slope_min, slope_max in slope_ranges:
    count = np.sum((holes_slope >= slope_min) & (holes_slope < slope_max))
    pct = count / n_holes * 100 if n_holes > 0 else 0
    bar = "#" * int(pct / 2)
    print(f"  {slope_min:2d}-{slope_max:2d}° : {count:8,} ({pct:5.1f}%) {bar}")

# Identifier les zones critiques (altitude × slope)
print(f"\n{'='*80}")
print(f"ZONES CRITIQUES (altitude × slope)")
print(f"{'='*80}")

print(f"\nOu sont concentres les trous ?")
for alt_min, alt_max in [(0, 10), (10, 20), (20, 30)]:
    for slope_min, slope_max in [(0, 15), (15, 20), (20, 25), (25, 30)]:
        count = np.sum((holes_alt >= alt_min) & (holes_alt < alt_max) &
                       (holes_slope >= slope_min) & (holes_slope < slope_max))
        if count > n_holes * 0.05:  # Afficher si > 5% des trous
            pct = count / n_holes * 100
            print(f"  {alt_min:2d}-{alt_max:2d}m × {slope_min:2d}-{slope_max:2d}° : {count:8,} ({pct:5.1f}%)")

print(f"\n{'='*80}")
print(f"RECOMMANDATIONS")
print(f"{'='*80}")

# Trouver la zone dominante
dominant_alt = "0-10m" if np.sum((holes_alt >= 0) & (holes_alt < 10)) > n_holes * 0.4 else \
               "10-20m" if np.sum((holes_alt >= 10) & (holes_alt < 20)) > n_holes * 0.4 else "20-30m"

dominant_slope = "0-15°" if np.sum((holes_slope >= 0) & (holes_slope < 15)) > n_holes * 0.4 else \
                 "15-20°" if np.sum((holes_slope >= 15) & (holes_slope < 20)) > n_holes * 0.4 else \
                 "20-30°" if np.sum((holes_slope >= 20) & (holes_slope < 30)) > n_holes * 0.4 else ">30°"

print(f"\nZone dominante des trous : {dominant_alt} × {dominant_slope}")
print(f"\nPour combler les trous, elargir une texture pour couvrir cette zone.")

print(f"\n{'='*80}")
