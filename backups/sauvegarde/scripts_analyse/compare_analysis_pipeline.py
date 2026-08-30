"""
Compare les stats calculées par :
1. L'onglet Analyse (naturemap_biomes_generator.py)
2. Le pipeline (pipeline_core.py)
"""

import numpy as np
import cv2
import json
from pathlib import Path

# ============================================================================
# PROJET À TESTER
# ============================================================================

PROJECT_PATH = Path(r"h:\logiciel perso\Map generator\data\projects\Zbk_island")

# ============================================================================
# MÉTHODE 1 : COMME L'ONGLET ANALYSE (naturemap_biomes_generator.py)
# ============================================================================

print("=" * 80)
print("MÉTHODE 1 : ONGLET ANALYSE (naturemap_biomes_generator.py)")
print("=" * 80)

# Charger heightmap
hm_path = PROJECT_PATH / "sources" / "temp_ZBK_terrain_modified7.asc"
hm_analyse = np.loadtxt(hm_path, skiprows=6).astype(np.float32)

print(f"\nHeightmap :")
print(f"  Shape : {hm_analyse.shape}")
print(f"  Min   : {hm_analyse.min():.2f}m")
print(f"  Max   : {hm_analyse.max():.2f}m")
print(f"  Mean  : {hm_analyse.mean():.2f}m")

# Charger slope
slope_path = PROJECT_PATH / "sources" / "slope.png"
if slope_path.exists():
    slope_analyse = cv2.imread(str(slope_path), cv2.IMREAD_UNCHANGED)
    if slope_analyse.shape != hm_analyse.shape:
        slope_analyse = cv2.resize(slope_analyse, (hm_analyse.shape[1], hm_analyse.shape[0]),
                                   interpolation=cv2.INTER_LINEAR)
    # Normaliser 16-bit -> 0-90°
    slope_deg_analyse = slope_analyse.astype(np.float32) / 65535.0 * 90.0
else:
    print("⚠️ slope.png non trouvé, calcul depuis heightmap...")
    # Calcul gradient (simplifié)
    gy, gx = np.gradient(hm_analyse)
    slope_rad = np.arctan(np.sqrt(gx**2 + gy**2))
    slope_deg_analyse = np.degrees(slope_rad)

print(f"\nSlope :")
print(f"  Mean  : {slope_deg_analyse.mean():.2f}°")
print(f"  P75   : {np.percentile(slope_deg_analyse, 75):.2f}°")
print(f"  P90   : {np.percentile(slope_deg_analyse, 90):.2f}°")
print(f"  P95   : {np.percentile(slope_deg_analyse, 95):.2f}°")

# Stats altitude
alt_p20 = np.percentile(hm_analyse, 20)
alt_p50 = np.percentile(hm_analyse, 50)
alt_p75 = np.percentile(hm_analyse, 75)

print(f"\nAltitude percentiles :")
print(f"  P20   : {alt_p20:.2f}m")
print(f"  P50   : {alt_p50:.2f}m")
print(f"  P75   : {alt_p75:.2f}m")

# ============================================================================
# MÉTHODE 2 : COMME LE PIPELINE (pipeline_core.py)
# ============================================================================

print("\n" + "=" * 80)
print("MÉTHODE 2 : PIPELINE (pipeline_core.py)")
print("=" * 80)

# Le pipeline charge pareil
hm_pipeline = np.loadtxt(hm_path, skiprows=6).astype(np.float32)

print(f"\nHeightmap :")
print(f"  Shape : {hm_pipeline.shape}")
print(f"  Min   : {hm_pipeline.min():.2f}m")
print(f"  Max   : {hm_pipeline.max():.2f}m")
print(f"  Mean  : {hm_pipeline.mean():.2f}m")

# Le pipeline calcule min/max/range
min_alt = hm_pipeline.min()
max_alt = hm_pipeline.max()
alt_range = max_alt - min_alt

print(f"\nPipeline range :")
print(f"  Range : {alt_range:.2f}m")

# Le pipeline charge slope pareil
if slope_path.exists():
    slope_pipeline = cv2.imread(str(slope_path), cv2.IMREAD_UNCHANGED)
    if slope_pipeline.shape != hm_pipeline.shape:
        slope_pipeline = cv2.resize(slope_pipeline, (hm_pipeline.shape[1], hm_pipeline.shape[0]),
                                    interpolation=cv2.INTER_LINEAR)
    slope_deg_pipeline = slope_pipeline.astype(np.float32) / 65535.0 * 90.0
else:
    gy, gx = np.gradient(hm_pipeline)
    slope_rad = np.arctan(np.sqrt(gx**2 + gy**2))
    slope_deg_pipeline = np.degrees(slope_rad)

# Le pipeline calcule slope_p90 pour seuils adaptatifs
slope_p90 = np.percentile(slope_deg_pipeline, 90)

print(f"\nSlope :")
print(f"  Mean  : {slope_deg_pipeline.mean():.2f}°")
print(f"  P75   : {np.percentile(slope_deg_pipeline, 75):.2f}°")
print(f"  P90   : {slope_p90:.2f}°")
print(f"  P95   : {np.percentile(slope_deg_pipeline, 95):.2f}°")

# Seuils slope hybrides (comme dans pipeline ligne 161-196)
flat_thresh = min(slope_p90 * 0.36, 12.0)
gentle_end = 20.0
moderate_end = 35.0

print(f"\nSeuils slope hybrides (pipeline) :")
print(f"  flat      : 0 - {flat_thresh:.1f}°")
print(f"  gentle    : {flat_thresh:.1f} - {gentle_end:.1f}°")
print(f"  moderate  : {gentle_end:.1f} - {moderate_end:.1f}°")
print(f"  steep     : >= {moderate_end:.1f}°")

# ============================================================================
# COMPARAISON
# ============================================================================

print("\n" + "=" * 80)
print("COMPARAISON")
print("=" * 80)

# Heightmap
hm_diff = np.abs(hm_analyse - hm_pipeline).max()
print(f"\nHeightmap :")
print(f"  Différence max : {hm_diff:.6f}m")
print(f"  IDENTIQUE : {'OK' if hm_diff < 0.001 else 'ERREUR'}")

# Slope
slope_diff = np.abs(slope_deg_analyse - slope_deg_pipeline).max()
print(f"\nSlope :")
print(f"  Différence max : {slope_diff:.6f}°")
print(f"  IDENTIQUE : {'OK' if slope_diff < 0.001 else 'ERREUR'}")

# Percentiles
p90_analyse = np.percentile(slope_deg_analyse, 90)
p90_pipeline = slope_p90
p90_diff = abs(p90_analyse - p90_pipeline)

print(f"\nSlope P90 :")
print(f"  Analyse  : {p90_analyse:.2f}°")
print(f"  Pipeline : {p90_pipeline:.2f}°")
print(f"  Diff     : {p90_diff:.4f}°")
print(f"  IDENTIQUE : {'OK' if p90_diff < 0.01 else 'ERREUR'}")

# ============================================================================
# CONCLUSION
# ============================================================================

print("\n" + "=" * 80)
print("CONCLUSION")
print("=" * 80)

if hm_diff < 0.001 and slope_diff < 0.001 and p90_diff < 0.01:
    print("\n>>> LES DEUX METHODES CALCULENT LES MEMES DONNEES <<<")
    print("   -> Le pipeline RECALCULE mais obtient les MEMES resultats")
    print("   -> Pas de probleme de coherence")
else:
    print("\n>>> LES DEUX METHODES DONNENT DES RESULTATS DIFFERENTS <<<")
    print("   -> Probleme potentiel de source de donnees differente")
    print("   -> Verifier quelle heightmap/slope est utilisee")

print("\n" + "=" * 80)
