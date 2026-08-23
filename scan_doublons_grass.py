"""
scan_doublons_grass.py — Détecte les blocs avec 2+ textures parmi Grass_03 / Grass_03b / Grass_03_default
Usage: python scan_doublons_grass.py
"""
import struct, json
from pathlib import Path
from collections import defaultdict

DATA     = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain\.Data")
SURFACES = Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\surfaces.json")
OUT      = Path(r"H:\logiciel perso\Map generator\data\doublons_grass.txt")

surfaces = json.loads(SURFACES.read_text())
mat_ids  = surfaces["materials"]

TARGETS = {"Grass_03", "Grass_03b", "Grass_03_default"}
id_map  = {mat_ids[t]: t for t in TARGETS if t in mat_ids}

print(f"Textures cibles : {id_map}")
print("Scan en cours...")

results = []
for ttile in sorted(DATA.glob("Terrain_*.ttile")):
    tid  = int(ttile.stem.split("_")[1])
    data = ttile.read_bytes()
    pos  = 12
    while pos < len(data) - 8:
        tag  = bytes(data[pos:pos+4])
        size = struct.unpack_from(">I", data, pos+4)[0]
        if size > len(data): break
        if tag == b"LRS2":
            lrs2 = bytes(data[pos+8:pos+8+size])
            p = 0
            while p < len(lrs2) - 6:
                index = struct.unpack_from("<I", lrs2, p)[0]
                count = struct.unpack_from("<H", lrs2, p+4)[0]
                if count == 0 or count > 7: break
                mats  = list(struct.unpack_from(f"<{count}H", lrs2, p+6))
                found = [id_map[m] for m in mats if m in id_map]
                if len(found) >= 2:
                    bx_g = index & 0x7F
                    by_g = (index >> 7) & 0x7F
                    tx, ty = bx_g // 4, by_g // 4
                    tile_id = ty * 32 + tx
                    bxl, byl = bx_g % 4, by_g % 4
                    results.append((tile_id, tx, ty, bxl, byl, found))
                p += 6 + count * 2
            break
        pos += 8 + size + (size % 2)

# Regrouper par tuile
by_tile = defaultdict(list)
for tile_id, tx, ty, bxl, byl, found in results:
    by_tile[(tile_id, tx, ty)].append((bxl, byl, found))

lines = [f"DOUBLONS GRASS_03 / GRASS_03b / GRASS_03_default"]
lines.append(f"{len(results)} blocs dans {len(by_tile)} tuiles\n")
for (tid, tx, ty), blocs in sorted(by_tile.items()):
    lines.append(f"T{tid} ({tx},{ty}) — {len(blocs)} blocs:")
    for bxl, byl, found in sorted(blocs):
        lines.append(f"  bloc local ({bxl},{byl}) : {' + '.join(found)}")

# Blocs avec EXACTEMENT Grass_03 + Grass_03b (pas d'autre texture)
pure_pairs = []
for ttile in sorted(DATA.glob("Terrain_*.ttile")):
    tid  = int(ttile.stem.split("_")[1])
    data = ttile.read_bytes()
    pos  = 12
    while pos < len(data) - 8:
        tag  = bytes(data[pos:pos+4])
        size = struct.unpack_from(">I", data, pos+4)[0]
        if size > len(data): break
        if tag == b"LRS2":
            lrs2 = bytes(data[pos+8:pos+8+size])
            p = 0
            while p < len(lrs2) - 6:
                index = struct.unpack_from("<I", lrs2, p)[0]
                count = struct.unpack_from("<H", lrs2, p+4)[0]
                if count == 0 or count > 7: break
                mats = set(struct.unpack_from(f"<{count}H", lrs2, p+6))
                grass_ids = {mat_ids["Grass_03"], mat_ids["Grass_03b"]}
                if mats == grass_ids:
                    tx, ty = (index & 0x7F) // 4, ((index >> 7) & 0x7F) // 4
                    pure_pairs.append(f"{tx},{ty}")
                p += 6 + count * 2
            break
        pos += 8 + size + (size % 2)

pure_pairs = sorted(set(pure_pairs))
cmd = f"python merge_mat.py --src mat:10 --dst 8 --tiles {' '.join(pure_pairs)}"
Path(r"H:\logiciel perso\Map generator\data\merge_pure_grass.bat").write_text(cmd, encoding="utf-8")
print(f"✓ {len(pure_pairs)} tuiles avec blocs purs → merge_pure_grass.bat")

OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"\n✓ {len(results)} blocs dans {len(by_tile)} tuiles")
print(f"✓ Résultat : {OUT}")
