import struct
from pathlib import Path

data = Path('I:/Reforger_addons travail/Zimnitrita_map/World/Zimnitrita/Terrain/.Data/Terrain_616.ttile').read_bytes()

gctd_pos = data.find(b'GCTD')
gctd_size = struct.unpack_from('>I', data, gctd_pos+4)[0]
gctd_data = data[gctd_pos+8 : gctd_pos+8+gctd_size]

# Les bytes rares sont espacés de ~2030 bytes
# Regardons la structure autour de chaque paire
rare_offsets = [i for i, v in enumerate(gctd_data) if v not in (0, 2)]
print(f"Offsets rares : {rare_offsets}")
print()

# Espacement entre paires
spacings = [rare_offsets[i+2] - rare_offsets[i] for i in range(0, len(rare_offsets)-2, 2)]
print(f"Espacements entre paires : {spacings}")
print()

# Regarder autour de l'offset 26392 (bloc 34,79)
target = 26392
print(f"Contexte autour offset {target} (bloc bx=34, by=79) :")
start = max(0, target - 8)
end = min(len(gctd_data), target + 20)
chunk = gctd_data[start:end]
print(f"  hex : {chunk.hex()}")
print(f"  valeurs : {list(chunk)}")
print()

# Structure complète d'une section (entre deux paires rares)
# Section 0 : offset 0 à 2032 = 2032 bytes
# Header section : EA 07 20 00 4C 00 puis 2026 bytes de 0x02/0x00
section_size = rare_offsets[2] - rare_offsets[0]
print(f"Taille section : {section_size} bytes")
print(f"Section - 6 bytes header = {section_size - 6} bytes data")
print(f"sqrt({section_size-6}) = {(section_size-6)**0.5:.2f}")
print()

# 2026 bytes de data = 16x16 blocs * ~7.9 bytes ?
# Ou 128*128 pixels / 8 = 2048 bits -> bitmap ?
# 2026 bytes = 16208 bits ~ 127x127
# Essai: bitmap 128x128 = 16384 bits = 2048 bytes -> pas ça
# 2026 = 2 * 1013 -> pas standard
# Regarder le contenu data de la section 0 (après les 6 bytes header)
sec0_data = gctd_data[6:6+section_size-6]
print(f"Section 0 data ({len(sec0_data)} bytes) - valeurs uniques : {sorted(set(sec0_data))}")
print(f"Proportion 0x02 : {sec0_data.count(2)/len(sec0_data)*100:.1f}%")
print(f"Nombre de 0x00  : {sec0_data.count(0)}")
print(f"Nombre de 0x02  : {sec0_data.count(2)}")
print()

# 2026 bytes avec que des 0 et 2... c'est une bitmap 1 bit ?
# 2026 * 8 = 16208 bits
# 16208 / 128 = 126.6 -> non
# Essai: 45*45 = 2025 ~ 2026 -> non
# C'est peut-etre juste 512*512/128 = 2048 avec padding

# Afficher les 32 premiers bytes de la section data
print(f"Section 0 data début : {list(sec0_data[:32])}")
print(f"Section 0 data fin   : {list(sec0_data[-16:])}")
