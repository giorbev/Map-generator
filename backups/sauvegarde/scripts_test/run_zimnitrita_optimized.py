"""
Pipeline Zimnitrita Optimisé QTRE
==================================

Paramètres ajustés :
- debris_min_deg : 18.0° (↑ de 10.4°)
- rock_min_deg : 28.0° (↑ de 19.9°)
- feather_grass_m : 20.0m (↓ de 40m)

Objectif :
- dirt_erosion < 20%
- blocs critiques < 1%
"""

import sys
sys.path.insert(0, r'h:\logiciel perso\Map generator')

from pipeline_phases import run_pipeline_continuous
from pathlib import Path

# Chemins
heightmap_path = "data/projects/Zimnitrita/sources/temp_Terrain_modified3.asc"
curvature_path = "data/projects/Zimnitrita/sources/curvature.png"
curvature_range = (-17, 17)
output_dir = "data/projects/Zimnitrita/pipeline_11masks_optimized_20260611_174609"

# Paramètres optimisés
user_params = {
    "coastal_distance_max_m": 100.0,
    "coastal_alt_max_m": None,  # Auto P10
    "grass_low_max_m": None,    # Auto P30
    "grass_mid_max_m": None,    # Auto P66
    "grass_high_max_m": None,   # Auto P80
    "debris_min_deg": 18.0,     # Augmenté (était 10.4° auto)
    "rock_min_deg": 28.0,       # Augmenté (était 19.9° auto)
    "curvature_radius_m": None,
    "concave_threshold": None,
    "feather_coastal_m": 20.0,
    "feather_grass_m": 20.0,    # Réduit (était 40m)
    "feather_rock_m": 10.0,
}

print("="*80)
print("PIPELINE ZIMNITRITA OPTIMISE QTRE")
print("="*80)
print("\nParametres ajustes:")
print(f"  debris_min_deg: {user_params['debris_min_deg']} (augmente depuis auto)")
print(f"  rock_min_deg: {user_params['rock_min_deg']} (augmente depuis auto)")
print(f"  feather_grass_m: {user_params['feather_grass_m']} (reduit de 40m)")
print("\nObjectifs:")
print("  - dirt_erosion < 20%")
print("  - blocs critiques < 1%")
print("")

# Lancer pipeline
results = run_pipeline_continuous(
    heightmap_path=heightmap_path,
    curvature_path=curvature_path,
    curvature_range=curvature_range,
    output_dir=output_dir,
    user_params=user_params
)

print("\n" + "="*80)
print("RESULTATS COVERAGE")
print("="*80)

# Afficher couverture par mask
for name in sorted(results['masks'].keys()):
    mask = results['masks'][name]
    coverage = results['masks'][name].mean() * 100
    print(f"  {name:<35}: {coverage:5.2f}%")

print(f"\nTexture de base: {results['base_texture']}")
print("="*80)
