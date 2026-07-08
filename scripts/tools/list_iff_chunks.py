"""
Lister tous les chunks IFF d'un fichier .ttile
"""

import sys
import io
from pathlib import Path
import struct

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

ttile = Path(r"I:\reforger_travail\Zimnitrita_map\World\Zimnitrita\Terrain\.Data\Terrain_1000.ttile")
with open(ttile, 'rb') as f:
    data = f.read()

# Lister tous les chunks
pos = 0
chunks = []
while pos + 8 <= len(data):
    cid = data[pos:pos+4]
    csz = struct.unpack_from('>I', data, pos+4)[0]
    if csz > len(data) or pos + 8 + csz > len(data):
        break
    chunks.append((pos, cid, csz))
    pos = pos + 8 + csz + (csz % 2)

print('Chunks IFF dans le fichier:')
for offset, cid, size in chunks:
    try:
        cid_str = cid.decode('ascii')
    except:
        cid_str = str(cid)
    print(f'  Offset {offset:8d} : {cid_str:10s} ({size:10d} bytes)')

print(f'\nTotal : {len(chunks)} chunks')
