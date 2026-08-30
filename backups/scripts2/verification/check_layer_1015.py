"""Vérifier le layer.dds de la tuile 1015"""

from pathlib import Path
from layer_dds_reader import read_layer_dds, extract_all_weights
import numpy as np

layer_path = Path(r'I:\reforger_travail\Zimnitrita_map_test\World\Zimnitrita\Terrain\.EditorData\Terrain_1015_layer.dds')

print('='*80)
print('LAYER.DDS TUILE 1015')
print('='*80)
print()

if not layer_path.exists():
    print('ERREUR Layer.dds introuvable')
    exit(1)

print('OK Fichier existe')

# Lire layer
layer_img = read_layer_dds(layer_path)

if layer_img is None:
    print('ERREUR Impossible de lire layer.dds')
    exit(1)

print(f'OK Layer lu : {layer_img.shape}')
print()

# Extraire poids
weights = extract_all_weights(layer_img)

print(f'Poids extraits : {weights.shape}')
print()

# Analyser poids
for i in range(7):
    w = weights[:, :, i]
    print(f'Poids {i} : min={w.min():.3f}, max={w.max():.3f}, moyenne={w.mean():.3f}')

print()

# Vérifier si tous les poids sont à 0 (sauf w0)
all_zero = True
for i in range(1, 7):
    if weights[:, :, i].max() > 0.01:
        all_zero = False
        break

if all_zero:
    print('ATTENTION TOUS LES POIDS (w1-w6) SONT À ZÉRO !')
    print('   → Seul w0 (mat ID 0) est utilisé')
else:
    print('OK Poids normaux (variation détectée)')
