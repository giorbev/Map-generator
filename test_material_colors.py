"""
Vérifier couleurs matériaux dans catalogue
"""

from pathlib import Path
import json

catalog_path = Path(r"h:\logiciel perso\Map generator\data\Textures_ArmaReforger\catalog.json")
surfaces_path = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain\terrain_materials_list.txt")

# Charger catalogue
with open(catalog_path, 'r') as f:
    catalog = json.load(f)

# Charger liste surfaces
with open(surfaces_path, 'r') as f:
    surfaces = [line.strip() for line in f if line.strip() and not line.startswith('#')]

print("="*80)
print("COULEURS MATÉRIAUX")
print("="*80)
print()

# Tester premiers matériaux
test_ids = [0, 1, 2, 3, 4, 5, 6]

for mat_id in test_ids:
    if mat_id >= len(surfaces):
        print(f"ID {mat_id}: HORS LIMITES")
        continue

    surface_name = surfaces[mat_id]

    if surface_name in catalog:
        entry = catalog[surface_name]
        middle = entry.get('MiddleColor', [255, 255, 255])
        color_tint = entry.get('Color', [255, 255, 255])

        # TilW method: linear_to_srgb(MiddleColor * Color)
        r = (middle[0] / 255.0) * (color_tint[0] / 255.0)
        g = (middle[1] / 255.0) * (color_tint[1] / 255.0)
        b = (middle[2] / 255.0) * (color_tint[2] / 255.0)

        # Linear to sRGB
        def linear_to_srgb(c):
            return int(255 * (c ** (1/2.2)))

        final_r = linear_to_srgb(r)
        final_g = linear_to_srgb(g)
        final_b = linear_to_srgb(b)

        print(f"ID {mat_id} ({surface_name}):")
        print(f"  MiddleColor: {middle}")
        print(f"  Color: {color_tint}")
        print(f"  → Final RGB: ({final_r}, {final_g}, {final_b})")
    else:
        print(f"ID {mat_id} ({surface_name}): PAS DANS CATALOGUE")

    print()

print("="*80)
