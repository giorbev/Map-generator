#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Analyse masque peint manuellement pour calibrer seuils
=======================================================

Charge un masque peint à la main + données terrain
et affiche les caractéristiques (slope/curvature/TPI)
des zones peintes pour recommander des seuils.

Usage:
    python analyze_manual_mask.py
"""

import numpy as np
import cv2
from pathlib import Path
import sys

# Chemins
PROJECT_DIR = Path("data/projects/Zimnitrita")
MASK_PATH = PROJECT_DIR / "sources/reforger/export curv.png"
HEIGHTMAP_PATH = PROJECT_DIR / "sources/temp_Terrain_modified3.asc"
TERRAIN_CACHE = PROJECT_DIR / "terrain_data.npz"

print("=" * 80)
print("ANALYSE MASQUE MANUEL - CALIBRATION SEUILS")
print("=" * 80)

# 1. Charger masque manuel
print(f"\n[1/4] Chargement masque manuel : {MASK_PATH}")
if not MASK_PATH.exists():
    print(f"ERREUR : Fichier introuvable : {MASK_PATH}")
    sys.exit(1)

mask_img = cv2.imread(str(MASK_PATH), cv2.IMREAD_GRAYSCALE)
print(f"  Resolution : {mask_img.shape[1]}x{mask_img.shape[0]}")

# Binariser (>128 = peint, <=128 = non peint)
mask_painted = mask_img > 128
n_painted = int(np.sum(mask_painted))
n_total = mask_img.size
pct_painted = n_painted / n_total * 100

print(f"  Pixels peints : {n_painted:,} / {n_total:,} ({pct_painted:.2f}%)")

if n_painted == 0:
    print("\nERREUR : Aucun pixel peint detecte !")
    print("Verifiez que le masque exporte contient des zones blanches.")
    sys.exit(1)

# 2. Charger données terrain
print(f"\n[2/4] Chargement donnees terrain...")

if TERRAIN_CACHE.exists():
    print(f"  Cache trouve : {TERRAIN_CACHE}")
    data = np.load(str(TERRAIN_CACHE))
    heightmap = data['heightmap']
    slope = data['slope']
    curvature = data['curvature']
    tpi_local = data['tpi_local']
    cellsize = float(data['cellsize'])
    print(f"  Cellsize : {cellsize}m/px")
else:
    print(f"  Cache non trouve, chargement heightmap : {HEIGHTMAP_PATH}")

    # Charger heightmap ASC
    from pipeline_v2 import load_asc
    heightmap, meta = load_asc(str(HEIGHTMAP_PATH))
    cellsize = meta['cellsize']

    # Calculer signaux
    print("  Calcul slope...")
    from pipeline_v2 import calculate_slope
    slope = calculate_slope(heightmap, cellsize)

    print("  Calcul curvature...")
    from pipeline_v2 import calculate_curvature
    curvature = calculate_curvature(heightmap, cellsize)

    print("  Calcul TPI local...")
    from pipeline_v2 import calculate_tpi
    tpi_local, _ = calculate_tpi(heightmap, cellsize, radius_local_m=100.0, radius_macro_m=500.0)

# Vérifier résolution et redimensionner si nécessaire
if mask_painted.shape != heightmap.shape:
    print(f"  Resolution masque ({mask_painted.shape}) != heightmap ({heightmap.shape})")
    print(f"  Redimensionnement du masque...")

    # Resize avec interpolation NEAREST pour garder valeurs binaires
    mask_painted = cv2.resize(
        mask_painted.astype(np.uint8) * 255,
        (heightmap.shape[1], heightmap.shape[0]),
        interpolation=cv2.INTER_NEAREST
    ) > 128

    n_painted = int(np.sum(mask_painted))
    print(f"  Apres resize : {n_painted:,} pixels peints")

# 3. Extraire valeurs des zones peintes
print(f"\n[3/4] Extraction valeurs zones peintes...")

slope_painted = slope[mask_painted]
curv_painted = curvature[mask_painted]
tpi_painted = tpi_local[mask_painted]

# Filtrer NaN
slope_valid = slope_painted[~np.isnan(slope_painted)]
curv_valid = curv_painted[~np.isnan(curv_painted)]
tpi_valid = tpi_painted[~np.isnan(tpi_painted)]

print(f"  Slope : {len(slope_valid):,} valeurs")
print(f"  Curvature : {len(curv_valid):,} valeurs")
print(f"  TPI : {len(tpi_valid):,} valeurs")

# 4. Statistiques et recommandations
print("\n" + "=" * 80)
print("STATISTIQUES ZONES PEINTES")
print("=" * 80)

def print_stats(name, values, unit=""):
    """Affiche statistiques complètes"""
    print(f"\n{name} {unit}:")
    print(f"  Min    : {np.min(values):>10.2f}")
    print(f"  P10    : {np.percentile(values, 10):>10.2f}")
    print(f"  P25    : {np.percentile(values, 25):>10.2f}")
    print(f"  Median : {np.percentile(values, 50):>10.2f}")
    print(f"  P75    : {np.percentile(values, 75):>10.2f}")
    print(f"  P90    : {np.percentile(values, 90):>10.2f}")
    print(f"  Max    : {np.max(values):>10.2f}")
    print(f"  Moyenne: {np.mean(values):>10.2f}")

print_stats("SLOPE", slope_valid, "(degres)")
print_stats("CURVATURE", curv_valid, "(valeurs brutes DoG)")
print_stats("TPI LOCAL", tpi_valid, "(m)")

# 5. Comparaison avec distribution globale
print("\n" + "=" * 80)
print("COMPARAISON AVEC DISTRIBUTION GLOBALE")
print("=" * 80)

slope_all = slope[~np.isnan(slope)]
curv_all = curvature[~np.isnan(curvature)]
tpi_all = tpi_local[~np.isnan(tpi_local)]

# Trouver percentile des valeurs médianes peintes
median_slope_painted = np.median(slope_valid)
median_curv_painted = np.median(curv_valid)
median_tpi_painted = np.median(tpi_valid)

pct_slope = np.searchsorted(np.sort(slope_all), median_slope_painted) / len(slope_all) * 100
pct_curv = np.searchsorted(np.sort(curv_all), median_curv_painted) / len(curv_all) * 100
pct_tpi = np.searchsorted(np.sort(tpi_all), median_tpi_painted) / len(tpi_all) * 100

print(f"\nVotre peinture mediane correspond a :")
print(f"  Slope      : P{pct_slope:.0f} (median = {median_slope_painted:.1f} degres)")
print(f"  Curvature  : P{pct_curv:.0f} (median = {median_curv_painted:.2f})")
print(f"  TPI        : P{pct_tpi:.0f} (median = {median_tpi_painted:.1f} m)")

# 6. Recommandations
print("\n" + "=" * 80)
print("RECOMMANDATIONS SEUILS")
print("=" * 80)

# Trouver percentile global qui capture 90% des zones peintes
curv_p90_painted = np.percentile(curv_valid, 90)
pct_curv_90 = np.searchsorted(np.sort(curv_all), curv_p90_painted) / len(curv_all) * 100

slope_min_painted = np.percentile(slope_valid, 10)
slope_max_painted = np.percentile(slope_valid, 90)

tpi_max_painted = np.percentile(tpi_valid, 90)
pct_tpi_90 = np.searchsorted(np.sort(tpi_all), tpi_max_painted) / len(tpi_all) * 100

print(f"""
Pour capturer 90% de vos zones peintes :

1. CURVATURE (debris_deep)
   Valeur : < {curv_p90_painted:.3f}
   Percentile global : P{pct_curv_90:.0f}
   --> Ajustez slider Debug "deep" a : {int(pct_curv_90)}

2. SLOPE (debris_min)
   Plage : {slope_min_painted:.1f} - {slope_max_painted:.1f} degres
   --> Votre debris_min actuel : {np.percentile(slope_all, 65):.1f} degres (P65)
   {'OK' if slope_min_painted < np.percentile(slope_all, 65) < slope_max_painted else 'A AJUSTER'}

3. TPI (optionnel pour restriction ravin)
   Maximum : < {tpi_max_painted:.1f} m
   Percentile global : P{pct_tpi_90:.0f}
   --> Si vous voulez restreindre aux ravins uniquement
""")

print("\n" + "=" * 80)
print("PROCHAINES ETAPES")
print("=" * 80)
print("""
1. Onglet Debug -> Ajuster slider "deep" a P{:.0f}
2. Sauvegarder pour Pipeline
3. Regenerer masks
4. Verifier dans Workbench
""".format(pct_curv_90))
