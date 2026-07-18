"""Analyser la tuile 1015"""

from pathlib import Path
from lrs2_parser import load_lrs2_from_ttile

# Charger LRS2 de la tuile 1015
ttile = Path(r'I:\reforger_travail\Zimnitrita_map_test\World\Zimnitrita\Terrain\.Data\Terrain_1015.ttile')
editor_data = Path(r'I:\reforger_travail\Zimnitrita_map_test\World\Zimnitrita\Terrain\.EditorData')

# Vérifier fichiers
print('='*80)
print('ANALYSE TUILE 1015')
print('='*80)
print()
print('Fichiers:')
print(f'  ttile: {ttile.exists()}')
print(f'  layer.dds: {(editor_data / "Terrain_1015_layer.dds").exists()}')
print(f'  supertexture.dds: {(editor_data / "Terrain_1015_supertexture.dds").exists()}')
print()

if not ttile.exists():
    print('ERREUR: fichier ttile introuvable')
    exit(1)

lrs2 = load_lrs2_from_ttile(ttile)

# Collecter tous les matériaux
all_mats = set()
for mat_ids in lrs2.values():
    all_mats.update(mat_ids)

print(f'Matériaux trouvés: {len(all_mats)}')
print(f'IDs: {sorted(all_mats)}')
print()

# Charger liste surfaces
mat_list = Path(r'I:\reforger_travail\Zimnitrita_map_test\World\Zimnitrita\Terrain\terrain_materials_list.txt')
with open(mat_list) as f:
    surfaces = [line.strip() for line in f]

print('Noms matériaux:')
for mid in sorted(all_mats):
    if mid < len(surfaces):
        print(f'  ID {mid:2d} : {surfaces[mid]}')
    else:
        print(f'  ID {mid:2d} : HORS LIMITES (max={len(surfaces)-1})')
