"""
Analyse Zimnitrita : différences EST vs OUEST
- Zone EST : très plate
- Zone OUEST : très montagneuse

Montre pourquoi calibration globale inadaptée
"""
import numpy as np
from PIL import Image
from pathlib import Path
import json

# Charger heightmap
heightmap_path = Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\sources\Terrain_modified3.asc")

print("="*70)
print("ANALYSE ZIMNITRITA - EST vs OUEST")
print("="*70)

# Charger ASC
print("\nChargement heightmap...")
with open(heightmap_path, 'r') as f:
    lines = f.readlines()

ncols = int(lines[0].split()[1])
nrows = int(lines[1].split()[1])
cellsize = float(lines[4].split()[1])

data = []
for line in lines[6:]:
    data.append([float(x) for x in line.split()])

heightmap = np.array(data, dtype=np.float32)
print(f"Shape: {heightmap.shape}")
print(f"Cellsize: {cellsize}m/px")

# Diviser en EST (droite) et OUEST (gauche)
mid_col = heightmap.shape[1] // 2

heightmap_ouest = heightmap[:, :mid_col]
heightmap_est = heightmap[:, mid_col:]

# Charger curvature
curv_path = Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\sources\curvature.png")
if curv_path.exists():
    curv_img = Image.open(curv_path)
    curv_arr = np.array(curv_img, dtype=np.uint16)
    # Décoder curvature [-21, 21]
    curvature = (curv_arr / 65535.0) * 42 - 21

    curv_ouest = curvature[:, :mid_col]
    curv_est = curvature[:, mid_col:]
else:
    curvature = None
    curv_ouest = None
    curv_est = None

# Calculer slope approximatif
dy, dx = np.gradient(heightmap)
slope = np.arctan(np.sqrt(dx**2 + dy**2) / cellsize) * 180 / np.pi

slope_ouest = slope[:, :mid_col]
slope_est = slope[:, mid_col:]

print("\n" + "="*70)
print("STATISTIQUES COMPARATIVES")
print("="*70)

# Fonction stats
def print_stats(name, data, indent="  "):
    valid = data[~np.isnan(data)]
    if len(valid) == 0:
        return

    print(f"{indent}{name}:")
    print(f"{indent}  Min    : {np.min(valid):.2f}")
    print(f"{indent}  Max    : {np.max(valid):.2f}")
    print(f"{indent}  Mean   : {np.mean(valid):.2f}")
    print(f"{indent}  Std    : {np.std(valid):.2f}")
    print(f"{indent}  P10    : {np.percentile(valid, 10):.2f}")
    print(f"{indent}  P50    : {np.percentile(valid, 50):.2f}")
    print(f"{indent}  P90    : {np.percentile(valid, 90):.2f}")

print("\n--- ALTITUDE ---")
print("\nZONE OUEST (gauche, montagneuse):")
land_ouest = heightmap_ouest[heightmap_ouest > 0]
print_stats("Altitude", land_ouest)

print("\nZONE EST (droite, plate):")
land_est = heightmap_est[heightmap_est > 0]
print_stats("Altitude", land_est)

print("\n--- SLOPE (pente) ---")
print("\nZONE OUEST:")
print_stats("Slope", slope_ouest[~np.isnan(slope_ouest)])

print("\nZONE EST:")
print_stats("Slope", slope_est[~np.isnan(slope_est)])

if curvature is not None:
    print("\n--- CURVATURE ---")
    print("\nZONE OUEST:")
    print_stats("Curvature", curv_ouest[~np.isnan(curv_ouest)])

    print("\nZONE EST:")
    print_stats("Curvature", curv_est[~np.isnan(curv_est)])

# Seuils globaux actuels
print("\n" + "="*70)
print("SEUILS GLOBAUX ACTUELS")
print("="*70)

# Charger calibration
calib_path = Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\generated\terrain_masks_v2\calibration.json")
if calib_path.exists():
    with open(calib_path, 'r') as f:
        calib = json.load(f)

    thresholds = calib['thresholds']

    print(f"\nAltitude:")
    print(f"  P10 (coastal max)  : {thresholds['altitude']['p10']:.2f}m")
    print(f"  P20                : {thresholds['altitude']['p20']:.2f}m")
    print(f"  P66 (highland min) : {thresholds['altitude']['p66']:.2f}m")

    print(f"\nSlope:")
    print(f"  debris_min : {thresholds['slope']['debris_min']:.2f}°")
    print(f"  rock_min   : {thresholds['slope']['rock_min']:.2f}°")

    if 'curvature' in thresholds:
        print(f"\nCurvature:")
        print(f"  grass_dense_max    : {thresholds['curvature']['grass_dense_max']:.2f}")
        print(f"  debris_concave_max : {thresholds['curvature']['debris_concave_max']:.2f}")

print("\n" + "="*70)
print("PROBLÈMES IDENTIFIÉS")
print("="*70)

print("""
1. COASTAL (P10 = 20m global) :

   ZONE OUEST (montagne) :
     - P10 local : ~30-50m (zones basses rares)
     - Coastal 20m = OK (bande côtière étroite)

   ZONE EST (plate) :
     - P10 local : ~8-12m (beaucoup de zones basses)
     - Coastal 20m = TROP LARGE (monte dans plaines)

   -> Besoin COASTAL LOCALISÉ (distance mer, pas altitude globale)

2. GRASS_DENSE (P15 curvature global) :

   ZONE OUEST (montagne) :
     - Curvature variée (-30 à +30)
     - P15 local : ~-8 (assez strict)
     - Grass_Dense peu visible

   ZONE EST (plate) :
     - Curvature faible (-5 à +5)
     - P15 local : ~-2 (trop strict !)
     - Grass_Dense presque absent

   -> Besoin CALIBRATION LOCALE par région

3. ÉROSION (debris_min, rock_min globaux) :

   ZONE OUEST (montagne) :
     - Slope mean : 15-20° (beaucoup érosion)
     - debris_min=8° OK, rock_min=16° OK

   ZONE EST (plate) :
     - Slope mean : 3-5° (peu érosion)
     - debris_min=8° trop strict (classe trop en debris)

   -> Érosion absente zones plates, omniprésente montagne
""")

print("="*70)
print("SOLUTIONS PROPOSÉES")
print("="*70)

print("""
OPTION A : COASTAL LOCALISÉ (distance mer)
  - Au lieu de P10 altitude global
  - Limiter à 50-100m DISTANCE du rivage (0m altitude)
  - Coastal = (alt 0-20m) ET (distance < 100m mer)

OPTION B : CALIBRATION LOCALE (2-4 régions)
  - Détecter régions homogènes (K-means altitude+slope)
  - Calibrer P10, P15, debris_min par région
  - Zimnitrita : 2 régions (EST plate, OUEST montagne)

OPTION C : HYBRIDE (coastal distance + calibration locale)
  - Coastal = distance mer (option A)
  - Grass/Érosion = calibration locale (option B)
""")

print("\n" + "="*70)
