import struct
import lz4.block
from pathlib import Path

data = Path('I:/Reforger_addons travail/Zimnitrita_map/World/Zimnitrita/Terrain/.Data/Terrain_616.ttile').read_bytes()

gctd_pos = data.find(b'GCTD')
gctd_size = struct.unpack_from('>I', data, gctd_pos+4)[0]
gctd_data = data[gctd_pos+8 : gctd_pos+8+gctd_size]

print(f"GCTD size : {gctd_size} bytes")
print(f"Header (8 bytes) : {gctd_data[:8].hex()}")
print()

# Tenter décompression LZ4 depuis offset 0, 4, 8
for offset in [0, 4, 6, 8]:
    try:
        decompressed = lz4.block.decompress(gctd_data[offset:], uncompressed_size=512*512*4)
        print(f"LZ4 decompress @ offset {offset} -> {len(decompressed)} bytes OK")
        print(f"  premiers bytes : {decompressed[:32].hex()}")
        break
    except Exception as e:
        print(f"LZ4 @ offset {offset} : {e}")

print()
# Analyser le header comme des uint16/uint32
print("Header interprété :")
for i in range(0, 16, 2):
    val16 = struct.unpack_from('<H', gctd_data, i)[0]
    print(f"  offset {i:2d} uint16_le : {val16}")
print()

# Chercher si c'est du zlib
import zlib
for offset in [0, 2, 4, 6]:
    try:
        dec = zlib.decompress(gctd_data[offset:])
        print(f"ZLIB @ offset {offset} -> {len(dec)} bytes OK")
    except:
        pass

# Valeurs uniques dans le GCTD
vals = set(gctd_data)
print(f"Valeurs uniques dans GCTD : {sorted(vals)}")
print(f"Proportion 0x02 : {gctd_data.count(2)/len(gctd_data)*100:.1f}%")
print(f"Proportion 0x00 : {gctd_data.count(0)/len(gctd_data)*100:.1f}%")
