"""
Analyse layer.dds comme D32_FLOAT
"""

from pathlib import Path
import struct
import numpy as np

tile_id = 960
layer_path = Path(rf"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain\.EditorData\Terrain_{tile_id}_layer.dds")

print("="*80)
print(f"ANALYSE LAYER.DDS COMME D32_FLOAT - TUILE {tile_id}")
print("="*80)
print()

with open(layer_path, 'rb') as f:
    # Skip header (148 bytes)
    f.seek(148)

    # Lire premiers pixels comme FLOAT
    print("### PREMIERS PIXELS (FLOAT) ###")
    for i in range(32):
        pixel_val = struct.unpack('<f', f.read(4))[0]
        print(f"Pixel {i:2d}: {pixel_val:12.6f}")

    print()

    # Lire toutes les données (512x512)
    f.seek(148)
    data_size = 512 * 512 * 4
    raw_data = f.read(data_size)

    # Convertir en array numpy
    layer_data = np.frombuffer(raw_data, dtype=np.float32).reshape((512, 512))

    print("### STATISTIQUES GLOBALES ###")
    print(f"Min: {layer_data.min():.6f}")
    print(f"Max: {layer_data.max():.6f}")
    print(f"Moyenne: {layer_data.mean():.6f}")
    print(f"Std: {layer_data.std():.6f}")
    print()

    # Compter valeurs uniques
    unique_vals = np.unique(layer_data)
    print(f"Valeurs uniques: {len(unique_vals)}")
    print(f"Premières valeurs: {unique_vals[:20]}")
    print()

    # Analyser par bloc (128x128)
    print("### ANALYSE PAR BLOC (128x128) ###")
    print("Bloc (x,y) | Min      | Max      | Moyenne  | Valeurs uniques")
    print("-" * 70)

    for by in range(4):
        for bx in range(4):
            y0 = by * 128
            x0 = bx * 128
            y1 = y0 + 128
            x1 = x0 + 128

            bloc = layer_data[y0:y1, x0:x1]
            unique_b = len(np.unique(bloc))

            print(f"({bx},{by})      | {bloc.min():8.4f} | {bloc.max():8.4f} | {bloc.mean():8.4f} | {unique_b}")

print()
print("="*80)
print("HYPOTHESE: Les valeurs FLOAT sont des indices/IDs de materiaux ?")
print("="*80)
