"""Analyser les coordonnées réelles des tuiles depuis LRS2"""

from pathlib import Path
from lrs2_parser import load_lrs2_from_ttile

data_dir = Path(r'I:\reforger_travail\Zimnitrita_map_test\World\Zimnitrita\Terrain\.Data')

# Échantillon de tuiles
sample_tiles = [0, 1, 2, 10, 31, 32, 100, 1000, 1015, 1023]

print('='*80)
print('COORDONNÉES TUILES depuis LRS2')
print('='*80)
print()
print('tile_id  | Coords LRS2 trouvées (bx_global, by_global)')
print('-'*80)

for tile_id in sample_tiles:
    ttile = data_dir / f'Terrain_{tile_id}.ttile'
    if not ttile.exists():
        print(f'{tile_id:4d}     | FICHIER ABSENT')
        continue

    lrs2 = load_lrs2_from_ttile(ttile)

    if not lrs2:
        print(f'{tile_id:4d}     | LRS2 VIDE')
        continue

    # Prendre les coordonnées du premier bloc
    first_block = list(lrs2.keys())[0]
    bx, by = first_block

    # Afficher (bx et by sont locaux 0-3)
    # Il faudrait les coordonnées globales
    print(f'{tile_id:4d}     | Bloc local: ({bx}, {by}) - INCOMPLET')

print()
print('='*80)
print('NOTE: Les coordonnées affichées sont LOCALES (0-3) par tuile.')
print('Il faut lire les coordonnées GLOBALES depuis le chunk LRS2 raw.')
