import struct
from pathlib import Path
from collections import Counter

data = Path('I:/Reforger_addons travail/Zimnitrita_map/World/Zimnitrita/Terrain/.Data/Terrain_616.ttile').read_bytes()

gctd_pos = data.find(b'GCTD')
gctd_size = struct.unpack_from('>I', data, gctd_pos+4)[0]
gctd_data = data[gctd_pos+8 : gctd_pos+8+gctd_size]

# Header : 2026=0x07EA, 32=0x20, 76=0x4C
h0 = struct.unpack_from('<H', gctd_data, 0)[0]  # 2026
h1 = struct.unpack_from('<H', gctd_data, 2)[0]  # 32
h2 = struct.unpack_from('<H', gctd_data, 4)[0]  # 76

print(f"Header: {h0}, {h1}, {h2}")
print(f"Données depuis offset 6 : {len(gctd_data)-6} bytes")
print()

# Les données depuis offset 6 : 30452-6 = 30446 bytes
# 512*512 = 262144 pixels -> trop grand
# 128*128 = 16384 blocs -> trop grand  
# 16*16 = 256 blocs -> trop petit (256*118=30208, proche de 30446)
# Essai: 256 blocs * 119 bytes = 30464 ~ 30452

body = gctd_data[6:]
print(f"Body size : {len(body)} bytes")
print(f"Body / 256 : {len(body)/256:.2f} bytes/bloc")
print()

# Essai: chaque bloc = 119 bytes, 16 blocs par tuile (4x4)
# 119 * 256 = 30464 != 30446
# Essai offset différent
for start in range(0, 12):
    body2 = gctd_data[start:]
    if len(body2) % 256 == 0:
        print(f"Offset {start} -> divisible par 256 : {len(body2)//256} bytes/bloc")
    if len(body2) % 16 == 0:
        bpb = len(body2) // 16
        if bpb < 5000:
            print(f"Offset {start} -> divisible par 16 : {bpb} bytes/bloc")

print()
# Chercher le bloc (bx_local=2, by_local=3) = bloc global (34,79)
# tx=616%32=8, ty=616//32=19
# bx_local = 34 - 8*4 = 34-32 = 2
# by_local = 79 - 19*4 = 79-76 = 3
tile_id = 616
tx = tile_id % 32
ty = tile_id // 32
bx_local = 34 - tx*4
by_local = 79 - ty*4
print(f"Tuile 616: tx={tx}, ty={ty}")
print(f"Bloc local: bx={bx_local}, by={by_local}")
bloc_idx = by_local * 4 + bx_local
print(f"Index bloc: {bloc_idx}")
print()

# Chercher les bytes non-0/non-2 et leurs positions
rare = [(i, v) for i, v in enumerate(gctd_data) if v not in (0, 2)]
print(f"Bytes rares (non 0/2) : {len(rare)}")
for pos, val in rare[:30]:
    print(f"  offset {pos} (0x{pos:X}) : 0x{val:02X} = {val}")
