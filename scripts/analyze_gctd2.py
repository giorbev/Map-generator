import struct
from pathlib import Path

data = Path('I:/Reforger_addons travail/Zimnitrita_map/World/Zimnitrita/Terrain/.Data/Terrain_616.ttile').read_bytes()

gctd_pos = data.find(b'GCTD')
gctd_size = struct.unpack_from('>I', data, gctd_pos+4)[0]
gctd_data = data[gctd_pos+8 : gctd_pos+8+gctd_size]

print(f"GCTD size : {gctd_size} bytes")
print(f"GCTD / 16 blocs     : {gctd_size / 16:.2f}")
print(f"GCTD / 256 blocs    : {gctd_size / 256:.2f}")
print(f"GCTD / 512x512      : {gctd_size / (512*512):.4f}")
print()

# Header GCTD
print(f"GCTD header (32 bytes) : {gctd_data[:32].hex()}")
print()

# Chercher des sous-chunks dans GCTD
for tag in [b'BMAT', b'WGHT', b'LAYR', b'BLCK', b'GRID']:
    pos = gctd_data.find(tag)
    if pos >= 0:
        print(f"  Sous-chunk {tag} @ +{pos}")

# Afficher les 256 premiers bytes avec structure
print()
print("GCTD raw (256 premiers bytes) :")
for i in range(0, 256, 16):
    hex_str = gctd_data[i:i+16].hex()
    print(f"  {i:4d}: {hex_str}")
