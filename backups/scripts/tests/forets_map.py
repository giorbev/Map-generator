"""
forets_map.py — Scan des textures forêt dans les .ttile + génération carte visuelle
Usage: python forets_map.py
"""
import struct, json
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw

# ─── CONFIG ────────────────────────────────────────────────────────────────────
DATA     = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain\.Data")
SURFACES = Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\surfaces.json")
OUT_TXT  = Path(r"H:\logiciel perso\Map generator\data\forets_map.txt")
OUT_IMG  = Path(r"H:\logiciel perso\Map generator\data\forets_carte.png")

TARGETS = [
    "Dirt_01",
    "Dirt_02",

]

COLORS = {
    "Dirt_01":        ( 15,  80,  30),  # vert très foncé
    "Dirt_02":         ( 60, 150,  60),  # vert moyen
    "ForestClearing_Coniferous_01":(100, 170,  80),  # vert jaune
    "ForestClearing_Deciduous_01": (150, 210, 120),  # vert clair
    "ForestPine_01_Base":          (  0,  40,  20),  # vert nuit
}

MAP_GRID = 128
PPB      = 8   # pixels par bloc → image 1024×1024

# ─── SCAN ──────────────────────────────────────────────────────────────────────
surfaces  = json.loads(SURFACES.read_text())
mat_ids   = surfaces["materials"]
target_map = {mat_ids[t]: t for t in TARGETS if t in mat_ids}

results = {t: [] for t in TARGETS}

print("Scan des .ttile...")
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
                mats = list(struct.unpack_from(f"<{count}H", lrs2, p+6))
                bx_g = index & 0x7F
                by_g = (index >> 7) & 0x7F
                for mid in mats:
                    if mid in target_map:
                        results[target_map[mid]].append((bx_g, by_g))
                p += 6 + count * 2
            break
        pos += 8 + size + (size % 2)

# ─── EXPORT TXT ────────────────────────────────────────────────────────────────
lines = []
for tex, blocs in results.items():
    lines.append(f"{tex}: {len(blocs)} blocs")
    for bx_g, by_g in blocs:
        lines.append(f"  ({bx_g},{by_g})")
OUT_TXT.write_text("\n".join(lines), encoding="utf-8")
print(f"Texte sauvegardé : {OUT_TXT}")
for tex, blocs in results.items():
    print(f"  {tex}: {len(blocs)} blocs")

# ─── CARTE VISUELLE ────────────────────────────────────────────────────────────
out = np.full((MAP_GRID*PPB, MAP_GRID*PPB, 3), 25, dtype=np.uint8)

for tex, blocs in results.items():
    color = COLORS.get(tex, (200, 200, 200))
    for (bx_g, by_g) in blocs:
        by_img = MAP_GRID - 1 - by_g  # flip Y (by=0 = sud = bas image)
        y0, x0 = by_img * PPB, bx_g * PPB
        if 0 <= y0 < MAP_GRID*PPB and 0 <= x0 < MAP_GRID*PPB:
            out[y0:y0+PPB, x0:x0+PPB] = color

# Grille tuiles
TILE_PX = PPB * 4
for i in range(0, MAP_GRID*PPB, TILE_PX):
    out[i, :] = (out[i, :] * 0.4).astype(np.uint8)
    out[:, i] = (out[:, i] * 0.4).astype(np.uint8)

# Légende
img  = Image.fromarray(out, "RGB")
draw = ImageDraw.Draw(img)
y = 5
for tex in TARGETS:
    color = COLORS.get(tex, (200, 200, 200))
    n = len(results[tex])
    draw.rectangle([5, y, 20, y+10], fill=color)
    draw.text((25, y), f"{tex} ({n} blocs)", fill=(220, 220, 220))
    y += 14

img.save(OUT_IMG)
print(f"Carte sauvegardée : {OUT_IMG}")
