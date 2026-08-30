"""
Décoder le format .bterr pour extraire les QTRE des blocs 6-7 textures
"""

import sys
import io
from pathlib import Path
import struct
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Charger un .bterr
bterr_path = Path(r"I:\reforger_travail\Zimnitrita_map_test\World\Zimnitrita\Terrain\.EditorData\Terrain_1000.bterr")
with open(bterr_path, 'rb') as f:
    data = f.read()

print("="*80)
print("ANALYSE FICHIER .bterr")
print("="*80 + "\n")

# Parser IFF
assert data[:4] == b'FORM'
form_size = struct.unpack_from('>I', data, 4)[0]
form_type = data[8:12].decode('ascii')

print(f"Type : {form_type}")
print(f"Taille totale : {len(data)} bytes")
print(f"Form size : {form_size} bytes\n")

# Trouver chunk DATA
pos = 12
data_offset = None
data_size = None

while pos + 8 <= len(data):
    chunk_id = data[pos:pos+4].decode('ascii', errors='ignore')
    chunk_size = struct.unpack_from('>I', data, pos+4)[0]

    print(f"Chunk {chunk_id} : {chunk_size} bytes (offset {pos})")

    if chunk_id == 'DATA':
        data_offset = pos + 8
        data_size = chunk_size

    pos = pos + 8 + chunk_size + (chunk_size % 2)

print(f"\nChunk DATA : offset={data_offset}, size={data_size}")
print("="*80 + "\n")

# Analyser le chunk DATA
chunk_data = data[data_offset:data_offset+data_size]

# Hypothèse 1 : 16 blocs de taille variable
print("HYPOTHÈSE 1 : Structure par blocs")
print("-"*80)

# Essayer de détecter la structure
# Si c'est comme .ttile, chaque bloc devrait avoir :
# - Coordonnées bx, by
# - Nombre de matériaux
# - QTRE data

# Mais ici pas de structure BMAT, donc peut-être juste un tableau de QTRE ?

# Hypothèse 2 : Tableau de 16 QTRE de taille fixe
bytes_per_block = data_size / 16
print(f"Bytes par bloc (si 16 blocs) : {bytes_per_block}")
print(f"Bytes restants : {data_size % 16}\n")

# Analyser les premiers bytes de chaque bloc
print("Premiers 32 bytes de chaque bloc (si division par 16) :")
for i in range(min(4, 16)):  # Afficher 4 premiers blocs
    offset = int(i * bytes_per_block)
    bloc = chunk_data[offset:offset+32]
    print(f"  Bloc {i} (offset {offset}) : {bloc.hex(' ', 4)}")

print("\n" + "="*80)
print("ANALYSE DÉTAILLÉE BLOC 0")
print("="*80 + "\n")

# Analyser le premier bloc en détail
bloc0_size = int(bytes_per_block)
bloc0 = chunk_data[:bloc0_size]

print(f"Taille bloc 0 : {len(bloc0)} bytes")

# Essayer de détecter un header
print(f"\nPremiers 128 bytes :")
for i in range(0, min(128, len(bloc0)), 16):
    chunk = bloc0[i:i+16]
    hex_str = chunk.hex(' ')
    # Essayer de décoder comme floats
    try:
        floats = struct.unpack('<4f', chunk)
        float_str = f" | floats: {floats[0]:.2f} {floats[1]:.2f} {floats[2]:.2f} {floats[3]:.2f}"
    except:
        float_str = ""
    print(f"  {i:4d} : {hex_str:47s}{float_str}")

# Comparer avec taille QTRE connues
print("\n" + "="*80)
print("COMPARAISON AVEC FORMATS QTRE CONNUS")
print("="*80)
print(f"QTRE 2-mat : variable (quadtree)")
print(f"QTRE 3-mat : 4156 bytes (60 header + 4096 data = 32×32×4)")
print(f"QTRE 4-5 mat : 6204 bytes (60 header + 6144 data = 32×32×6)")
print(f"QTRE 6-7 mat : ??? bytes")
print(f"\nBloc .bterr : {bloc0_size} bytes")
print(f"Différence avec 3-mat : {bloc0_size - 4156} bytes")
print(f"Différence avec 4-5 mat : {bloc0_size - 6204} bytes")

# Si c'est 4160 bytes, c'est peut-être 60 + 4100 ?
if abs(bloc0_size - 4160) < 10:
    print(f"\n4160 bytes = 60 header + 4100 data")
    print(f"4100 data = 32×32×4 + 4 bytes extra ?")
    print(f"Ou bien : structure différente ?")
