"""
Réinterpréter layer.dds D32_FLOAT comme UINT32
"""

from pathlib import Path
import numpy as np

tile_id = 960
layer_path = Path(rf"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain\.EditorData\Terrain_{tile_id}_layer.dds")

print("="*80)
print(f"REINTERPRETATION LAYER.DDS COMME UINT32 - TUILE {tile_id}")
print("="*80)
print()

with open(layer_path, 'rb') as f:
    # Skip header (148 bytes)
    f.seek(148)

    # Lire données (512x512 * 4 bytes)
    data_size = 512 * 512 * 4
    raw_data = f.read(data_size)

# Convertir en UINT32
layer_uint = np.frombuffer(raw_data, dtype=np.uint32).reshape((512, 512))

print("### STATISTIQUES (UINT32) ###")
print(f"Min: {layer_uint.min()}")
print(f"Max: {layer_uint.max()}")
print(f"Valeurs uniques: {len(np.unique(layer_uint))}")
print()

# Premiers pixels
print("### PREMIERS PIXELS (HEX) ###")
for i in range(16):
    y = i // 512
    x = i % 512
    val = layer_uint[y, x]
    print(f"Pixel {i:2d}: 0x{val:08X}")

print()

# Analyser par bloc et extraire poids
print("### EXTRACTION POIDS PAR BLOC (128x128) ###")
print("Bloc | Poids moyens (w0 w1 w2 w3 w4 w5 w6)")
print("-" * 70)

for by in range(4):
    for bx in range(4):
        y0 = by * 128
        x0 = bx * 128
        y1 = y0 + 128
        x1 = x0 + 128

        bloc = layer_uint[y0:y1, x0:x1]

        # Extraire poids
        w1 = ((bloc >> 0) & 0x1F).astype(np.float32) / 31.0
        w2 = ((bloc >> 5) & 0x1F).astype(np.float32) / 31.0
        w3 = ((bloc >> 10) & 0x1F).astype(np.float32) / 31.0
        w4 = ((bloc >> 15) & 0x1F).astype(np.float32) / 31.0
        w5 = ((bloc >> 20) & 0x1F).astype(np.float32) / 31.0
        w6 = ((bloc >> 25) & 0x1F).astype(np.float32) / 31.0
        w0 = (31 - (w1*31 + w2*31 + w3*31 + w4*31 + w5*31 + w6*31)) / 31.0

        moyennes = f"({bx},{by}) | {w0.mean():.3f} {w1.mean():.3f} {w2.mean():.3f} {w3.mean():.3f} {w4.mean():.3f} {w5.mean():.3f} {w6.mean():.3f}"
        print(moyennes)

print()
print("="*80)
print("Si les poids sont coherents (somme proche de 1), le format est bon !")
print("="*80)
