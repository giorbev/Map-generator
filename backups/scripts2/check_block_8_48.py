"""
Vérification ciblée : Bloc (8,48) de la tile (2,12)
Affiche les poids moyens du bloc et compare avec Reforger
"""

import numpy as np
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from terrain_terr_reader import read_mats_from_terr
from scripts.edds_decoder import decode_edds_layer, extract_all_weights
from scripts.clean_weights import read_lrs2_from_ttile

# Tile (2,12) = tile ID 386
TILE_X, TILE_Y = 2, 12
TILE_ID = TILE_Y * 32 + TILE_X

# Bloc global (8,48)
BX_GLOBAL, BY_GLOBAL = 8, 48

# Bloc local dans la tile
BX_LOCAL = BX_GLOBAL - TILE_X * 4  # 8 - 2*4 = 0
BY_LOCAL = BY_GLOBAL - TILE_Y * 4  # 48 - 12*4 = 0

print("=" * 80)
print("VÉRIFICATION BLOC (8,48)")
print("=" * 80)
print(f"Tile: ({TILE_X},{TILE_Y}) = ID {TILE_ID}")
print(f"Bloc global: ({BX_GLOBAL},{BY_GLOBAL})")
print(f"Bloc local: ({BX_LOCAL},{BY_LOCAL})")
print()

# Coordonnées pixel dans le _layer.dds (512×512)
x0 = BX_LOCAL * 128
y0 = BY_LOCAL * 128
x1 = x0 + 128
y1 = y0 + 128

print(f"Coordonnées pixel dans _layer.dds:")
print(f"  X: {x0} à {x1-1}")
print(f"  Y: {y0} à {y1-1}")
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
print("[1] Lecture LRS2...")
lrs2_blocks = read_lrs2_from_ttile(ttile_path)

if (BX_LOCAL, BY_LOCAL) not in lrs2_blocks:
    print(f"[ERR] Bloc ({BX_LOCAL},{BY_LOCAL}) introuvable !")
    print(f"Blocs disponibles: {sorted(lrs2_blocks.keys())}")
    sys.exit(1)

mat_ids = lrs2_blocks[(BX_LOCAL, BY_LOCAL)]
mat_names = [surfaces[mid] if mid < len(surfaces) else f"MAT_{mid}" for mid in mat_ids]

print(f"   Matériaux du bloc LRS2 ({len(mat_ids)}):")
for i, (mat_id, mat_name) in enumerate(zip(mat_ids, mat_names)):
    print(f"     slot[{i}]: {mat_name}")
print()

# Lire _layer.dds
print("[2] Lecture _layer.dds...")
decoded = decode_edds_layer(layer_path)
pixels = extract_all_weights(decoded)
print(f"   Shape: {pixels.shape}")
print()

# Extraire le bloc
print(f"[3] Extraction bloc pixels[{y0}:{y1}, {x0}:{x1}, :] ...")
block_pixels = pixels[y0:y1, x0:x1, :len(mat_ids)]
print(f"   Shape bloc: {block_pixels.shape}")
print()

# Calculer moyennes
print("=" * 80)
print("RÉSULTATS")
print("=" * 80)
print()

for i, mat_name in enumerate(mat_names):
    slot_weights = block_pixels[:, :, i] * 31.0
    mean_val = slot_weights.mean()
    pct = (mean_val / 31.0) * 100

    print(f"slot[{i}] {mat_name:22s}: {mean_val:6.3f}/31 ({pct:6.2f}%)")

print()
print("=" * 80)
print("À COMPARER AVEC REFORGER (section Block):")
print("=" * 80)
print()
print("Si les valeurs ne correspondent pas, le problème est ailleurs")
print("(décodage DDS, synchronisation LRS2/_layer.dds, etc.)")
print()
