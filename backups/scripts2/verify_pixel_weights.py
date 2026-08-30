"""
Vérification poids d'un pixel spécifique
Pour comparer avec "Pixel Under Cursor" de Reforger
"""

import numpy as np
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from terrain_terr_reader import read_mats_from_terr
from scripts.edds_decoder import decode_edds_layer, extract_all_weights
from scripts.clean_weights import read_lrs2_from_ttile

# Configuration
TILE_X = 2
TILE_Y = 12
TILE_ID = TILE_Y * 32 + TILE_X

print("=" * 80)
print(f"VÉRIFICATION PIXEL - Tile ({TILE_X},{TILE_Y})")
print("=" * 80)
print()

# Chemins
TERRAIN_ROOT = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain")
DATA_DIR = TERRAIN_ROOT / ".Data"
EDITOR_DATA_DIR = TERRAIN_ROOT / ".EditorData"
TERR_PATH = TERRAIN_ROOT / "terrain.terr"

ttile_path = DATA_DIR / f"Terrain_{TILE_ID}.ttile"
layer_path = EDITOR_DATA_DIR / f"Terrain_{TILE_ID}_layer.dds"

# Charger surfaces
surfaces_data = read_mats_from_terr(TERR_PATH)
surfaces = [e["name"] for e in surfaces_data]

# Lire LRS2
lrs2_blocks = read_lrs2_from_ttile(ttile_path)

# Lire layer.dds
decoded = decode_edds_layer(layer_path)
pixels = extract_all_weights(decoded)

print("Entrez les coordonnées du pixel à vérifier :")
print()
print("Format 1 : Coordonnées LOCALES dans la tile (0-511)")
print("  Exemple : 64,64 pour pixel local (64,64)")
print()
print("Format 2 : Coordonnées GLOBALES Surface Mask")
print("  Exemple : 1143,10160 (format Reforger)")
print()

coord_input = input("Coordonnées (x,y) : ").strip()

try:
    x_str, y_str = coord_input.split(',')
    x = int(x_str.strip())
    y = int(y_str.strip())

    # Déterminer si ce sont des coordonnées globales (Surface Mask)
    if x > 511 or y > 511:
        # Coordonnées globales → convertir en locales
        tile_x_from_coord = x // 512
        tile_y_from_coord = y // 512

        if tile_x_from_coord != TILE_X or tile_y_from_coord != TILE_Y:
            print(f"[WARN] Ces coordonnées correspondent à la tile ({tile_x_from_coord},{tile_y_from_coord}), pas ({TILE_X},{TILE_Y})")
            print(f"       Je vais quand même continuer...")

        x_local = x % 512
        y_local = y % 512

        print()
        print(f"Coordonnées globales: ({x},{y})")
        print(f"Coordonnées locales:  ({x_local},{y_local})")
    else:
        # Coordonnées locales
        x_local = x
        y_local = y

        x_global = TILE_X * 512 + x_local
        y_global = TILE_Y * 512 + y_local

        print()
        print(f"Coordonnées locales:  ({x_local},{y_local})")
        print(f"Coordonnées globales: ({x_global},{y_global})")

    # Déterminer le bloc
    bx = x_local // 128
    by = y_local // 128

    bx_global = TILE_X * 4 + bx
    by_global = TILE_Y * 4 + by

    print()
    print(f"Bloc local:  ({bx},{by})")
    print(f"Bloc global: ({bx_global},{by_global})")
    print()

    # Récupérer les matériaux du bloc
    if (bx, by) not in lrs2_blocks:
        print(f"[ERR] Bloc ({bx},{by}) introuvable dans LRS2")
        sys.exit(1)

    mat_ids = lrs2_blocks[(bx, by)]
    mat_names = [surfaces[mid] if mid < len(surfaces) else f"MAT_{mid}" for mid in mat_ids]

    print(f"Matériaux du bloc ({len(mat_ids)}) :")
    for i, (mat_id, mat_name) in enumerate(zip(mat_ids, mat_names)):
        print(f"  slot[{i}]: ID {mat_id:3d} = {mat_name}")
    print()

    # Récupérer les poids du pixel
    pixel_weights = pixels[y_local, x_local, :len(mat_ids)]

    print("=" * 80)
    print("POIDS DU PIXEL")
    print("=" * 80)
    print()
    print("  Slot | Matériau               | Valeur brute | Échelle 0-31 | Pourcentage")
    print("  " + "-" * 76)

    for i, (mat_name, w_01) in enumerate(zip(mat_names, pixel_weights)):
        w_31 = w_01 * 31.0
        w_pct = w_01 * 100.0

        print(f"  [{i}]   | {mat_name:22s} | {w_01:12.6f} | {w_31:12.3f} | {w_pct:11.2f}%")

    print()
    print(f"  Somme (échelle 0-31): {(pixel_weights * 31).sum():.3f}")
    print()

    print("=" * 80)
    print("COMPARAISON AVEC REFORGER")
    print("=" * 80)
    print()
    print("Reforger affiche probablement la colonne 'Pourcentage' ci-dessus.")
    print("Vérifie que les valeurs correspondent !")
    print()

except Exception as e:
    print(f"[ERR] {e}")
    sys.exit(1)
