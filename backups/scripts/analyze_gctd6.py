import struct
from pathlib import Path

data = Path('I:/Reforger_addons travail/Zimnitrita_map/World/Zimnitrita/Terrain/.Data/Terrain_616.ttile').read_bytes()

gctd_pos = data.find(b'GCTD')
gctd_size = struct.unpack_from('>I', data, gctd_pos+4)[0]
gctd_data = data[gctd_pos+8 : gctd_pos+8+gctd_size]

# Lire tout comme uint16 little-endian
n = len(gctd_data) // 2
vals = struct.unpack_from(f'<{n}H', gctd_data)

print(f"Total uint16 : {n}")
print(f"Valeurs uniques : {sorted(set(vals))}")
print()

# Trouver les uint16 != 2 et != 0
rare = [(i, v) for i, v in enumerate(vals) if v not in (0, 2)]
print(f"Uint16 rares : {len(rare)}")
for idx, v in rare:
    print(f"  index {idx:5d} (offset {idx*2:5d}) : {v} (0x{v:04X})")
print()

# 15 sections de 2030/2 = 1015 uint16 chacune
# + header 6 bytes = 3 uint16
# Section 0 commence à index 3
HEADER_U16 = 3
SECTION_U16 = 1015
print(f"Structure: header={HEADER_U16} uint16, sections={SECTION_U16} uint16 chacune")
print(f"Nombre de sections : {(n - HEADER_U16) / SECTION_U16:.2f}")
print()

# Afficher chaque section et ses valeurs rares
for sec in range(15):
    start = HEADER_U16 + sec * SECTION_U16
    end = start + SECTION_U16
    sec_vals = vals[start:end]
    rare_in_sec = [(i, v) for i, v in enumerate(sec_vals) if v not in (0, 2)]
    if rare_in_sec:
        print(f"Section {sec:2d} (indices {start}-{end}) :")
        for i, v in rare_in_sec:
            print(f"  pos {i:4d} : {v} (0x{v:04X})")
