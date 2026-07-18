"""
Identifier les tuiles noires dans la satmap
"""

from pathlib import Path
import numpy as np
from PIL import Image

satmap_path = Path(r"h:\logiciel perso\Map generator\output\satmap_debug.png")

print("="*80)
print("IDENTIFICATION TUILES NOIRES")
print("="*80)
print()

# Charger satmap
img = Image.open(satmap_path)
arr = np.array(img)

print(f"Satmap : {img.size} pixels")
print()

# Grille 32x32 tuiles
grid_size = 32
tile_px = arr.shape[0] // grid_size

print(f"Taille tuile : {tile_px}x{tile_px} pixels")
print()

# Analyser chaque tuile
black_tiles = []

for ty in range(grid_size):
    for tx in range(grid_size):
        # Extraire tuile
        y0 = ty * tile_px
        x0 = tx * tile_px
        y1 = min(y0 + tile_px, arr.shape[0])
        x1 = min(x0 + tile_px, arr.shape[1])

        tile = arr[y0:y1, x0:x1]

        # Calculer luminosité moyenne
        lum = tile.mean()

        # Calculer tile_id (origine bas-gauche Reforger)
        tile_id = tx + (grid_size - 1 - ty) * grid_size

        # Si sombre (< 60)
        if lum < 60:
            black_tiles.append((tile_id, tx, ty, lum))

print(f"Tuiles sombres trouvées (< 60) : {len(black_tiles)}")
print()

if black_tiles:
    print("### LISTE TUILES SOMBRES ###")
    print("Tile ID | Pos (x,y) | Luminosité")
    print("-" * 40)
    for tile_id, tx, ty, lum in sorted(black_tiles):
        print(f"{tile_id:7d} | ({tx:2d},{ty:2d})   | {lum:5.1f}")

# Afficher zone autour de tuile 84
print()
print("="*80)
print("ZONE AUTOUR TUILE 84 (Sud)")
print("="*80)
print()

# Tuile 84 : tx=20, ty=29 (en coordonnées image, ty inversé)
tile_84_tx = 84 % grid_size
tile_84_ty_reforger = 84 // grid_size
tile_84_ty_image = grid_size - 1 - tile_84_ty_reforger

print(f"Tuile 84 : position image ({tile_84_tx}, {tile_84_ty_image}), Reforger ({tile_84_tx}, {tile_84_ty_reforger})")
print()

# Afficher 5x5 autour
print("Luminosité 5x5 autour tuile 84:")
for dy in range(-2, 3):
    row = []
    for dx in range(-2, 3):
        tx_local = tile_84_tx + dx
        ty_local = tile_84_ty_image + dy

        if 0 <= tx_local < grid_size and 0 <= ty_local < grid_size:
            y0 = ty_local * tile_px
            x0 = tx_local * tile_px
            y1 = min(y0 + tile_px, arr.shape[0])
            x1 = min(x0 + tile_px, arr.shape[1])

            tile_local = arr[y0:y1, x0:x1]
            lum_local = tile_local.mean()

            tile_id_local = tx_local + (grid_size - 1 - ty_local) * grid_size
            row.append(f"{tile_id_local:4d}:{lum_local:3.0f}")
        else:
            row.append("    :   ")

    print("  ".join(row))

print()
print("="*80)
