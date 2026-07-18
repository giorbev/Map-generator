"""
Identifier blocs noirs restants (haut-gauche = tuiles 0-31)
"""

from pathlib import Path
from lrs2_parser import load_lrs2_from_ttile
from layer_dds_reader import read_layer_dds, extract_all_weights
import numpy as np

# Tuiles haut-gauche (0-31)
test_tiles = list(range(32))

data_dir = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain\.Data")
editordata_dir = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain\.EditorData")

print("="*80)
print("DIAGNOSTIC BLOCS NOIRS (tuiles haut-gauche)")
print("="*80)
print()

problematic_blocks = []

for tile_id in test_tiles:
    ttile_path = data_dir / f"Terrain_{tile_id}.ttile"
    layer_path = editordata_dir / f"Terrain_{tile_id}_layer.dds"

    if not ttile_path.exists() or not layer_path.exists():
        continue

    # Charger LRS2
    lrs2_blocks = load_lrs2_from_ttile(ttile_path)
    if not lrs2_blocks:
        continue

    # Charger layer
    layer_img = read_layer_dds(layer_path)
    if layer_img is None:
        continue

    weights = extract_all_weights(layer_img)

    # Vérifier chaque bloc
    for by in range(4):
        for bx in range(4):
            mat_ids = lrs2_blocks.get((bx, by), [])

            if len(mat_ids) == 0:
                continue

            # Vérifier si TOUS les poids sont quasi-nuls
            y0 = by * 128
            x0 = bx * 128
            y1 = y0 + 128
            x1 = x0 + 128

            all_zero = True
            for slot_idx in range(min(len(mat_ids), 7)):
                w = weights[y0:y1, x0:x1, slot_idx]
                if np.max(w) >= 0.001:
                    all_zero = False
                    break

            if all_zero:
                problematic_blocks.append({
                    'tile': tile_id,
                    'bloc': (bx, by),
                    'mat_ids': mat_ids,
                    'poids_max': [np.max(weights[y0:y1, x0:x1, i]) for i in range(7)]
                })

print(f"Blocs problématiques trouvés: {len(problematic_blocks)}")
print()

if problematic_blocks:
    print("### DÉTAILS PREMIERS BLOCS ###")
    for p in problematic_blocks[:10]:
        print(f"Tuile {p['tile']} bloc {p['bloc']}: mat_ids={p['mat_ids']}")
        print(f"  Poids max slots: {[f'{w:.4f}' for w in p['poids_max']]}")

print()
print("="*80)
