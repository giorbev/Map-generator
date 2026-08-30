"""
Analyse les masques EXPORTÉS depuis Reforger pour trouver les trous Grass_02
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

print("=" * 80)
print("ANALYSE MASQUES EXPORTES DEPUIS REFORGER")
print("=" * 80)

# Zone côtière 0-30m
coastal_mask = (hm >= 0.0) & (hm <= 30.0)
n_coastal = np.sum(coastal_mask)
print(f"\nZone cotiere (0-30m) : {n_coastal:,} pixels")

# Charger exports
base_path = r"h:\logiciel perso\Map generator\data\projects\Zbk_island\generated\terrain_masks"

exports = {
    'SeaBed': 'export _seabed.png',
    'BeachGrass': 'export_beachgrass.png',
    'Grass_03_coastal': 'export_grass3coastal.png',
    'Pebbles': 'export_pebbles.png'
}

masks = {}
for name, filename in exports.items():
    path = f"{base_path}/{filename}"
    try:
        mask = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if mask is None:
            print(f"ERREUR : {filename} non trouve")
            continue
        # Resize si nécessaire
        if mask.shape != hm.shape:
            mask = cv2.resize(mask, (hm.shape[1], hm.shape[0]), interpolation=cv2.INTER_LINEAR)

        # Convertir en 16-bit si 8-bit
        if mask.dtype == np.uint8:
            mask = mask.astype(np.uint16) * 257  # 0-255 -> 0-65535

        masks[name] = mask
        print(f"{name:20} : charge ({mask.dtype}, shape {mask.shape})")
    except Exception as e:
        print(f"ERREUR {name} : {e}")

if len(masks) == 0:
    print("\nERREUR : Aucun export charge")
    exit(1)

# Analyser zone côtière
print(f"\n{'='*80}")
print(f"COUVERTURE SUR ZONE COTIERE")
print(f"{'='*80}")

coastal_masks = {}
for name, mask in masks.items():
    coastal_masks[name] = mask[coastal_mask]
    mean_val = coastal_masks[name].mean()
    active_pct = (coastal_masks[name] > 1000).sum() / n_coastal * 100
    print(f"\n{name:20} :")
    print(f"  Moyenne  : {mean_val:.0f} ({mean_val/65535*100:.1f}%)")
    print(f"  Actif    : {active_pct:.1f}% pixels (>1000)")

# Somme totale
print(f"\n{'='*80}")
print(f"SOMME TOTALE")
print(f"{'='*80}")

total = np.sum(list(coastal_masks.values()), axis=0)
total_mean = total.mean()
total_min = total.min()
total_max = total.max()

print(f"\nSomme sur zone cotiere :")
print(f"  Moyenne : {total_mean:.0f} ({total_mean/65535*100:.1f}%)")
print(f"  Min     : {total_min} ({total_min/65535*100:.1f}%)")
print(f"  Max     : {total_max} ({total_max/65535*100:.1f}%)")

# Trous
threshold_90 = 58982  # 90% de 65535
holes = total < threshold_90
n_holes = np.sum(holes)
holes_pct = n_holes / n_coastal * 100

print(f"\n  Pixels < 90% : {n_holes:,} ({holes_pct:.1f}% de la cote)")

if n_holes > 0:
    print(f"\n  >>> {holes_pct:.1f}% de la cote a des TROUS (Grass_02 visible)")

    # Analyser les trous
    coastal_indices = np.where(coastal_mask)
    holes_alt = hm[coastal_indices][holes]
    holes_slope = slope_deg[coastal_indices][holes]

    print(f"\n{'='*80}")
    print(f"ANALYSE DES TROUS")
    print(f"{'='*80}")

    print(f"\nAltitude des trous :")
    print(f"  Min     : {holes_alt.min():.1f}m")
    print(f"  Moyenne : {holes_alt.mean():.1f}m")
    print(f"  Max     : {holes_alt.max():.1f}m")

    print(f"\nSlope des trous :")
    print(f"  Min     : {holes_slope.min():.1f}°")
    print(f"  Moyenne : {holes_slope.mean():.1f}°")
    print(f"  Max     : {holes_slope.max():.1f}°")

    # Distribution
    print(f"\nDistribution par altitude :")
    for alt_min, alt_max in [(0, 10), (10, 20), (20, 30)]:
        count = np.sum((holes_alt >= alt_min) & (holes_alt < alt_max))
        pct = count / n_holes * 100
        bar = "#" * int(pct / 2)
        print(f"  {alt_min:2d}-{alt_max:2d}m : {pct:5.1f}% {bar}")

    print(f"\nDistribution par slope :")
    for slope_min, slope_max in [(0, 10), (10, 15), (15, 20), (20, 25), (25, 30), (30, 90)]:
        count = np.sum((holes_slope >= slope_min) & (holes_slope < slope_max))
        pct = count / n_holes * 100
        bar = "#" * int(pct / 2)
        print(f"  {slope_min:2d}-{slope_max:2d}° : {pct:5.1f}% {bar}")

    # Zone critique
    print(f"\n{'='*80}")
    print(f"ZONE CRITIQUE (ou sont concentres les trous ?)")
    print(f"{'='*80}")

    for alt_min, alt_max in [(0, 10), (10, 20), (20, 30)]:
        for slope_min, slope_max in [(0, 15), (15, 20), (20, 25), (25, 30), (30, 90)]:
            count = np.sum((holes_alt >= alt_min) & (holes_alt < alt_max) &
                          (holes_slope >= slope_min) & (holes_slope < slope_max))
            if count > n_holes * 0.05:  # Afficher si > 5%
                pct = count / n_holes * 100
                print(f"  {alt_min:2d}-{alt_max:2d}m × {slope_min:2d}-{slope_max:2d}° : {pct:5.1f}%")

else:
    print(f"\n  >>> AUCUN TROU ! Somme = 100% partout <<<")

print(f"\n{'='*80}")
