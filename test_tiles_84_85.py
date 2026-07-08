from layer_dds_reader import read_layer_dds
from pathlib import Path

for tile in [84, 85]:
    p = Path(f'I:/Reforger_addons travail/Zimnitrita_map/World/Zimnitrita/Terrain/.EditorData/Terrain_{tile}_layer.dds')
    img = read_layer_dds(p)
    print(f'Tuile {tile}: {"OK" if img is not None else "ERREUR"}')
    if img is not None:
        print(f'  Shape: {img.shape}')
