"""
Vérifier si .bterr contient heightmap ou QTRE
"""

import sys
import io
import struct
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

bterr = Path(r"I:\reforger_travail\Zimnitrita_map_test\World\Zimnitrita\Terrain\.EditorData\Terrain_1000.bterr")
with open(bterr, 'rb') as f:
    data = f.read()

# Chunk DATA à offset 32
chunk_data = data[32:32+66564]
bloc0 = chunk_data[:4160]

print("="*80)
print("ANALYSE CONTENU BLOC 0")
print("="*80 + "\n")

# Hypothèse : 60 bytes header + 4096 bytes heightmap + 4 bytes padding
header = bloc0[:60]
heightmap_data = bloc0[60:60+4096]
padding = bloc0[60+4096:]

print(f"Header (60 bytes)")
print(f"Padding (4 bytes) : {padding.hex()}\n")

# Décoder heightmap comme grille 32×32 de floats
heights = struct.unpack(f'<{1024}f', heightmap_data)
print(f"Heightmap (4096 bytes = 1024 floats = 32×32):")
print(f"  Min height : {min(heights):.2f}m")
print(f"  Max height : {max(heights):.2f}m")
print(f"  Moyenne    : {sum(heights)/len(heights):.2f}m")
print(f"  Écart-type : {(sum((h-sum(heights)/len(heights))**2 for h in heights)/len(heights))**0.5:.2f}m")
print()

# Vérifier si ce sont bien des hauteurs cohérentes
valid_heights = sum(1 for h in heights if 0 < h < 1000)
print(f"Hauteurs valides (0-1000m) : {valid_heights}/{len(heights)} ({valid_heights/len(heights)*100:.1f}%)")

print("\n" + "="*80)
print("CONCLUSION")
print("="*80)

if valid_heights > 1000:
    print("\n✓ Le .bterr contient le HEIGHTMAP (résolution éditeur)")
    print("✗ Pas de QTRE de textures dans ce fichier")
    print()
    print("Les poids pour blocs 6-7 textures sont probablement :")
    print("  1. Calculés à la volée par le Workbench lors du rendu")
    print("  2. Ou stockés dans un autre fichier")
    print("  3. Ou distribués uniformément (1/6 ou 1/7)")
else:
    print("\n? Format inconnu, nécessite analyse plus approfondie")
