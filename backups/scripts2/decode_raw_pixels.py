"""
Lecture binaire brute du _layer.dds
Décodage manuel bit par bit des 4 premiers pixels du bloc (8,48)
"""

import struct
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from terrain_terr_reader import read_mats_from_terr
from scripts.clean_weights import read_lrs2_from_ttile

# Configuration
TILE_X, TILE_Y = 2, 12
TILE_ID = TILE_Y * 32 + TILE_X
BX_LOCAL, BY_LOCAL = 0, 0

print("=" * 80)
print("DÉCODAGE BRUT PIXELS - Bloc (8,48)")
print("=" * 80)
print()

# Chemins
TERRAIN_ROOT = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain")
DATA_DIR = TERRAIN_ROOT / ".Data"
EDITOR_DATA_DIR = TERRAIN_ROOT / ".EditorData"
TERR_PATH = TERRAIN_ROOT / "terrain.terr"

layer_path = EDITOR_DATA_DIR / f"Terrain_{TILE_ID}_layer.dds"
ttile_path = DATA_DIR / f"Terrain_{TILE_ID}.ttile"

# Charger LRS2 pour les noms de matériaux
surfaces_data = read_mats_from_terr(TERR_PATH)
surfaces = [e["name"] for e in surfaces_data]

lrs2_blocks = read_lrs2_from_ttile(ttile_path)
mat_ids = lrs2_blocks[(BX_LOCAL, BY_LOCAL)]
mat_names = [surfaces[mid] if mid < len(surfaces) else f"MAT_{mid}" for mid in mat_ids]

print("Matériaux du bloc (LRS2):")
for i, name in enumerate(mat_names):
    print(f"  slot[{i}]: {name}")
print()

# Lire le fichier DDS en binaire
print(f"Lecture fichier: {layer_path.name}")
with open(layer_path, 'rb') as f:
    # Sauter le header DDS (148 bytes)
    f.seek(148)

    # Lire toutes les données pixel (512×512 uint32 = 1048576 bytes)
    pixel_data = f.read(512 * 512 * 4)

print(f"Données lues: {len(pixel_data)} bytes")
print()

# Coordonnées pixel du bloc (0,0)
x0, y0 = 0, 0

print("=" * 80)
print("4 PREMIERS PIXELS DU BLOC")
print("=" * 80)
print()

for i in range(4):
    # Coordonnées pixel
    x = x0 + i
    y = y0

    # Offset dans les données (row-major: y*512 + x)
    offset = (y * 512 + x) * 4

    # Lire le pixel uint32 (little-endian)
    pixel = struct.unpack_from('<I', pixel_data, offset)[0]

    # Décoder bit par bit
    w1 = (pixel >> 0) & 0x1F
    w2 = (pixel >> 5) & 0x1F
    w3 = (pixel >> 10) & 0x1F
    w4 = (pixel >> 15) & 0x1F
    w5 = (pixel >> 20) & 0x1F
    w6 = (pixel >> 25) & 0x1F
    w0 = 31 - (w1 + w2 + w3 + w4 + w5 + w6)

    print(f"Pixel ({x},{y}):")
    print(f"  Valeur hex: 0x{pixel:08X}")
    print(f"  Décodage:")
    print(f"    w0 = {w0:2d}  (31 - sum)")
    print(f"    w1 = {w1:2d}  bits[0:4]")
    print(f"    w2 = {w2:2d}  bits[5:9]")
    print(f"    w3 = {w3:2d}  bits[10:14]")
    print(f"    w4 = {w4:2d}  bits[15:19]")
    print(f"    w5 = {w5:2d}  bits[20:24]")
    print(f"    w6 = {w6:2d}  bits[25:29]")
    print(f"  Somme: {w0+w1+w2+w3+w4+w5+w6}")
    print()

    # Mapper aux matériaux (seulement les slots présents dans le LRS2)
    print(f"  Poids par matériau:")
    weights = [w0, w1, w2, w3, w4, w5, w6]
    for slot_idx, mat_name in enumerate(mat_names):
        if slot_idx < len(weights):
            w = weights[slot_idx]
            pct = (w / 31.0) * 100
            print(f"    slot[{slot_idx}] {mat_name:22s}: {w:2d}/31 ({pct:5.1f}%)")
    print()
    print("-" * 80)
    print()
