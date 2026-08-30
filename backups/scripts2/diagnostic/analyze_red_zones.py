"""
Analyser les zones rouges tuile par tuile
"""

from pathlib import Path
from lrs2_parser import load_lrs2_from_ttile
from terrain_materials_parser import load_surfaces_list_from_world
from reforger_emat_parser import parse_emat_params, compute_tint_srgb, find_emat_file
import json

terrain_dir = Path(r'I:\reforger_travail\Zimnitrita_map_test\World\Zimnitrita\Terrain')
data_dir = terrain_dir / '.Data'
emat_dir = Path(r'h:\logiciel perso\Map generator\data\Textures_ArmaReforger\emat')

# Charger liste surfaces
surfaces_list = load_surfaces_list_from_world(terrain_dir)

print("="*80)
print("ANALYSE ZONES ROUGES - TUILE PAR TUILE")
print("="*80)
print()

# Tuiles suspectes avec rouge (d'après l'image)
suspect_tiles = [101, 102, 121, 122, 133, 134, 153]

for tile_id in suspect_tiles:
    ttile_path = data_dir / f'Terrain_{tile_id}.ttile'
    if not ttile_path.exists():
        continue

    print(f"TUILE {tile_id}")
    print("-"*80)

    # Charger LRS2
    lrs2_blocks = load_lrs2_from_ttile(ttile_path)

    # Collecter tous les matériaux uniques de cette tuile
    all_mats = set()
    for mat_ids in lrs2_blocks.values():
        all_mats.update(mat_ids)

    # Pour chaque matériau, calculer son tint
    red_surfaces = []

    for mat_id in sorted(all_mats):
        if mat_id >= len(surfaces_list):
            continue

        surface_name = surfaces_list[mat_id]

        # Calculer tint à la volée
        emat_path = find_emat_file([emat_dir], surface_name)
        if not emat_path:
            continue

        params = parse_emat_params(emat_path, [emat_dir])
        middle_color = params.get('MiddleColor', '1 1 1 1')
        color = params.get('Color', '1 1 1 1')

        tint_rgb = compute_tint_srgb(middle_color, color)
        r, g, b = tint_rgb

        # Détecter rouge : R > 100 ET R > G+30 ET R > B+30
        if r > 100 and r > g + 30 and r > b + 30:
            red_surfaces.append((mat_id, surface_name, tint_rgb))

    if red_surfaces:
        print(f"  SURFACES ROUGES trouvees : {len(red_surfaces)}")
        for mat_id, surf_name, (r, g, b) in red_surfaces:
            print(f"    ID {mat_id:2d} : {surf_name:40s} RGB({r:3d}, {g:3d}, {b:3d})")
    else:
        print(f"  Aucune surface rouge detectee")

    print()
