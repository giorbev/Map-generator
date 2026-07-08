"""
Analyser la structure d'un fichier .bterr (format éditeur)
"""

import sys
import io
from pathlib import Path
import struct

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

bterr = Path(r"I:\reforger_travail\Zimnitrita_map_test\World\Zimnitrita\Terrain\.EditorData\Terrain_1000.bterr")
with open(bterr, 'rb') as f:
    data = f.read()

print(f'Taille fichier : {len(data)} bytes')
print(f'\nPremiers 64 bytes (hex) :')
print(data[:64].hex(' ', 4))

# Chercher signature IFF
if data[:4] == b'FORM':
    size = struct.unpack('>I', data[4:8])[0]
    print(f'\nFormat IFF FORM, taille chunk : {size}')
    form_type = data[8:12].decode('ascii', errors='ignore')
    print(f'Type FORM : {form_type}')

    # Lister sous-chunks
    pos = 12
    print('\nSous-chunks :')
    chunks = []
    while pos + 8 <= len(data):
        cid = data[pos:pos+4]
        try:
            cid_str = cid.decode('ascii')
        except:
            cid_str = repr(cid)
        csz = struct.unpack_from('>I', data, pos+4)[0]
        if csz > len(data) or pos + 8 + csz > len(data):
            break
        chunks.append((cid_str, csz, pos))
        print(f'  {cid_str:10s} : {csz:8d} bytes (offset {pos})')
        pos = pos + 8 + csz + (csz % 2)

    print(f'\nTotal : {len(chunks)} chunks')

    # Analyser BMAT si présent
    for cid_str, csz, offset in chunks:
        if 'BMAT' in cid_str or 'TMAT' in cid_str:
            print(f'\nAnalyse chunk {cid_str} :')
            chunk_data = data[offset+8:offset+8+csz]
            print(f'  Taille : {len(chunk_data)} bytes')
            print(f'  Premiers 32 bytes : {chunk_data[:32].hex(" ", 2)}')
            break
else:
    print('\nPas de signature FORM, format inconnu')
    print(f'Signature : {data[:4]}')
