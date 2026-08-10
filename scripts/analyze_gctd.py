import struct
from pathlib import Path

data = Path('I:/Reforger_addons travail/Zimnitrita_map/World/Zimnitrita/Terrain/.Data/Terrain_616.ttile').read_bytes()

gctd_pos = data.find(b'GCTD')
gctd_size = struct.unpack_from('>I', data, gctd_pos+4)[0]
gctd_data = data[gctd_pos+8 : gctd_pos+8+gctd_size]

bytes_per_bloc = gctd_size // 256
print(f"Bytes par bloc : {bytes_per_bloc}")
for i in range(4):
    bloc = gctd_data[i*bytes_per_bloc:(i+1)*bytes_per_bloc]
    print(f"Bloc {i} : {bloc[:32].hex()}")
