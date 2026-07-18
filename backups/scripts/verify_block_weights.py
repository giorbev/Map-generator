"""
Vérification détaillée des poids d'un bloc spécifique
Comparaison avec les valeurs Reforger
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

# Bloc en coordonnées locales (0-3)
BX_LOCAL = 0
BY_LOCAL = 0

# Coordonnées globales correspondantes
BX_GLOBAL = TILE_X * 4 + BX_LOCAL  # 2*4+0 = 8
BY_GLOBAL = TILE_Y * 4 + BY_LOCAL  # 12*4+0 = 48

print("=" * 80)
print(f"VÉRIFICATION BLOC - Tile ({TILE_X},{TILE_Y}) bloc local ({BX_LOCAL},{BY_LOCAL})")
print("=" * 80)
print(f"Tile ID: {TILE_ID}")
print(f"Bloc global: ({BX_GLOBAL},{BY_GLOBAL})")
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
    print(f"[ERR] Bloc ({BX_LOCAL},{BY_LOCAL}) introuvable dans LRS2")
    print(f"Blocs disponibles: {list(lrs2_blocks.keys())}")
    sys.exit(1)

mat_ids = lrs2_blocks[(BX_LOCAL, BY_LOCAL)]
mat_names = [surfaces[mid] if mid < len(surfaces) else f"MAT_{mid}" for mid in mat_ids]

print(f"   [OK] {len(mat_ids)} matériaux trouvés")
print()
print("   Matériaux du bloc:")
for i, (mat_id, mat_name) in enumerate(zip(mat_ids, mat_names)):
    print(f"     slot[{i}]: ID {mat_id:3d} = {mat_name}")
print()

# Lire layer.dds
print("[2] Lecture _layer.dds...")
decoded = decode_edds_layer(layer_path)
if decoded is None:
    print("[ERR] Échec décodage")
    sys.exit(1)

pixels = extract_all_weights(decoded)
print(f"   [OK] Shape: {pixels.shape}")
print()

# Extraire le bloc (128×128 pixels)
print("[3] Extraction du bloc...")
x0 = BX_LOCAL * 128
y0 = BY_LOCAL * 128
block_pixels = pixels[y0:y0+128, x0:x0+128, :len(mat_ids)]

print(f"   Bloc pixels: {block_pixels.shape}")
print(f"   Range X: {x0} à {x0+127}")
print(f"   Range Y: {y0} à {y0+127}")
print()

# Calculer statistiques par slot
print("[4] Statistiques par slot (échelle 0..31):")
print()
print("  Slot | Matériau               | Moy    | Min | Max | Std   | Pixels>0")
print("  " + "-" * 74)

for i in range(len(mat_ids)):
    slot_weights = block_pixels[:, :, i] * 31.0  # Convertir en échelle 0-31

    mean_val = slot_weights.mean()
    min_val = slot_weights.min()
    max_val = slot_weights.max()
    std_val = slot_weights.std()
    pixels_nonzero = (slot_weights > 0).sum()

    print(f"  [{i}]   | {mat_names[i]:22s} | {mean_val:6.2f} | {min_val:3.0f} | {max_val:3.0f} | {std_val:5.2f} | {pixels_nonzero:6d}")

print()

# Vérifier la somme des poids
print("[5] Vérification cohérence:")
sum_weights = block_pixels.sum(axis=2) * 31.0  # Somme en échelle 0-31
print(f"   Somme min: {sum_weights.min():.2f}")
print(f"   Somme max: {sum_weights.max():.2f}")
print(f"   Somme moyenne: {sum_weights.mean():.2f}")
print(f"   Pixels avec somme != 31: {(np.abs(sum_weights - 31) > 0.1).sum()}")
print()

# Échantillon de pixels
print("[6] Échantillon pixels (coins + centre):")
print()
positions = [
    (0, 0, "Coin haut-gauche"),
    (127, 0, "Coin haut-droit"),
    (0, 127, "Coin bas-gauche"),
    (127, 127, "Coin bas-droit"),
    (64, 64, "Centre")
]

for px, py, label in positions:
    weights_01 = block_pixels[py, px, :]
    weights_31 = weights_01 * 31.0

    print(f"   {label} ({px},{py}):")
    for i, (mat_name, w) in enumerate(zip(mat_names, weights_31)):
        pct = (w / 31.0) * 100
        print(f"     slot[{i}] {mat_name:22s}: {w:5.2f}/31 ({pct:5.1f}%)")
    print()

# Moyennes finales (pour comparaison Reforger)
print("=" * 80)
print("RÉSUMÉ - MOYENNES PAR SLOT (à comparer avec Reforger)")
print("=" * 80)
for i in range(len(mat_ids)):
    slot_weights = block_pixels[:, :, i] * 31.0
    mean_val = slot_weights.mean()
    pct = (mean_val / 31.0) * 100
    print(f"slot[{i}] {mat_names[i]:22s}: {mean_val:6.3f}/31 ({pct:6.2f}%)")
print()
