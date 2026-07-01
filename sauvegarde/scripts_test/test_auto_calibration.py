"""
Test auto-calibration : vérifie que la conversion mètres -> normalisé fonctionne
"""

import json
from pathlib import Path

# Charger project.json ZBK
with open('data/projects/Zbk_island/project.json', 'r', encoding='utf-8') as f:
    project = json.load(f)

min_alt = project['assets']['heightmap']['alt_min']
max_alt = project['assets']['heightmap']['alt_max']
alt_range = max_alt - min_alt

print("=" * 80)
print("VÉRIFICATION CONVERSION ALTITUDE")
print("=" * 80)
print(f"\nZBK :")
print(f"  min_alt   : {min_alt:.2f}m")
print(f"  max_alt   : {max_alt:.2f}m")
print(f"  alt_range : {alt_range:.2f}m")

# Charger biome auto
with open('data/biomes/temperate_auto.json', 'r', encoding='utf-8') as f:
    biome = json.load(f)

print(f"\n{'='*80}")
print(f"CONVERSION METRES > NORMALISE")
print(f"{'='*80}")

for tex_name, tex_config in biome['textures'].items():
    print(f"\n{tex_name} :")

    if 'altitude_min_meters' in tex_config:
        meters = tex_config['altitude_min_meters']
        norm = (meters - min_alt) / alt_range
        print(f"  altitude_min_meters : {meters:.0f}m > {norm:.3f} norm")

    if 'altitude_max_meters' in tex_config:
        meters = tex_config['altitude_max_meters']
        norm = (meters - min_alt) / alt_range
        print(f"  altitude_max_meters : {meters:.0f}m > {norm:.3f} norm")

    if 'slope_min' in tex_config:
        print(f"  slope_min           : {tex_config['slope_min']:.0f} deg (garde degres)")

    if 'slope_max' in tex_config:
        print(f"  slope_max           : {tex_config['slope_max']:.0f} deg (garde degres)")

print(f"\n{'='*80}")
print(f"VALEURS ATTENDUES (ancien système)")
print(f"{'='*80}")
print(f"\nSeaBed  : altitude_max = 0.075 (0m)")
print(f"Pebbles : altitude 0.075-0.121 (0-20m)")
print(f"Beach   : altitude 0.075-0.121 (0-20m)")

print(f"\n{'='*80}")
print(f"Si valeurs normalisees = 0.075 / 0.121 > SUCCES !")
print(f"{'='*80}")
