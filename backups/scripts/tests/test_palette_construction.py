"""
Tester construction palette tuile et mapping slots
"""

from pathlib import Path
from lrs2_parser import load_lrs2_from_ttile
from layer_dds_reader import read_layer_dds, extract_all_weights
import numpy as np

# Tester plusieurs tuiles
test_tiles = [8, 960, 130, 200]  # Tuiles avec différents matériaux

data_dir = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain\.Data")
editordata_dir = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain\.EditorData")

print("="*80)
print("CONSTRUCTION PALETTE PAR TUILE")
print("="*80)
print()

for tile_id in test_tiles:
    print(f"### TUILE {tile_id} ###")

    # Charger LRS2
    ttile_path = data_dir / f"Terrain_{tile_id}.ttile"
    lrs2_blocks = load_lrs2_from_ttile(ttile_path)

    # Collecter tous les mat_ids uniques
    all_ids = set()
    for mat_ids in lrs2_blocks.values():
        all_ids.update(mat_ids)

    # Ajouter 0 (matériau par défaut) s'il n'est pas présent
    if 0 not in all_ids:
        all_ids.add(0)

    # Trier pour obtenir la palette
    palette = sorted(all_ids)

    print(f"  Palette (triée): {palette[:7]}")
    if len(palette) > 7:
        print(f"    WARNING: {len(palette)} matériaux, mais seulement 7 slots !")

    # Charger layer.dds et vérifier quels slots ont des poids non-nuls
    layer_path = editordata_dir / f"Terrain_{tile_id}_layer.dds"
    layer_img = read_layer_dds(layer_path)

    if layer_img is not None:
        weights = extract_all_weights(layer_img)

        # Calculer poids moyens par slot
        slot_means = [np.mean(weights[:, :, i]) for i in range(7)]

        print(f"  Poids moyens par slot:")
        for i, mean in enumerate(slot_means):
            if mean > 0.001:  # Afficher seulement slots non-nuls
                mat_id = palette[i] if i < len(palette) else "???"
                print(f"    w{i} = {mean:.4f} → mat {mat_id}")

    print()

print("="*80)
print("HYPOTHESE: slots w0-w6 correspondent à palette[0] à palette[6]")
print("="*80)
