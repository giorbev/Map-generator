"""
Diagnostic coordonnées LRS2 vs layer.dds pour tuile problématique
"""

from pathlib import Path
import struct
import numpy as np
from layer_dds_reader import read_layer_dds, extract_all_weights

# Tuile problématique : 960
tile_id = 960
data_dir = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain\.Data")
editordata_dir = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain\.EditorData")

ttile_path = data_dir / f"Terrain_{tile_id}.ttile"
layer_path = editordata_dir / f"Terrain_{tile_id}_layer.dds"

print("="*80)
print(f"DIAGNOSTIC TUILE {tile_id}")
print("="*80)
print()

# 1. Lire LRS2 et afficher coordonnées GLOBALES
print("### LRS2 - Coordonnées GLOBALES des blocs ###")
print()

with open(ttile_path, 'rb') as f:
    data = f.read()

# Chercher chunk LRS2
lrs2_marker = b'LRS2'
offset = data.find(lrs2_marker)

if offset == -1:
    print("ERREUR : Chunk LRS2 introuvable")
    exit(1)

# Skip marker + taille
lrs2_data = data[offset + 8:]

# Parser les 16 blocs
print("Bloc | bx_global | by_global | bx_local | by_local | n_mats | mat_ids")
print("-" * 80)

pos = 0
for i in range(16):
    if pos + 6 > len(lrs2_data):
        break

    # Index
    index = struct.unpack_from('<I', lrs2_data, pos)[0]
    bx_global = index & 0x7F
    by_global = (index >> 7) & 0x7F
    bx_local = bx_global % 4
    by_local = by_global % 4
    pos += 4

    # Nombre matériaux
    n = struct.unpack_from('<H', lrs2_data, pos)[0]
    pos += 2

    # IDs
    mat_ids = []
    for j in range(n):
        mat_id = struct.unpack_from('<H', lrs2_data, pos)[0]
        mat_ids.append(mat_id)
        pos += 2

    print(f"{i:4d} | {bx_global:9d} | {by_global:9d} | {bx_local:8d} | {by_local:8d} | {n:6d} | {mat_ids}")

print()

# 2. Analyser layer.dds pour les blocs correspondants
print("### LAYER.DDS - Poids moyens par bloc ###")
print()

layer_img = read_layer_dds(layer_path)
if layer_img is None:
    print("ERREUR : Impossible de lire layer.dds")
    exit(1)

weights = extract_all_weights(layer_img)

print("Bloc (local) | w0 moyen | w1 moyen | w2 moyen | w3 moyen | w4 moyen | w5 moyen | w6 moyen")
print("-" * 90)

for by in range(4):
    for bx in range(4):
        y0 = by * 128
        x0 = bx * 128
        y1 = y0 + 128
        x1 = x0 + 128

        bloc_weights = weights[y0:y1, x0:x1, :]
        moyennes = [np.mean(bloc_weights[:, :, i]) for i in range(7)]

        moy_str = " | ".join([f"{m:8.4f}" for m in moyennes])
        print(f"({bx}, {by})      | {moy_str}")

print()
print("="*80)
print("NOTE : Si bx_global % 4 != bx_local attendu, le modulo est incorrect !")
print("Si w0 moyen très faible pour un bloc avec un seul matériau, incohérence !")
print("="*80)
