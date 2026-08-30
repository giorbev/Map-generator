"""
simulate_qtre.py — Simulation QTRE après empilement des 32 passes de masks
Sortie : image 4096×4096 couleur + bilan global

Usage: python simulate_qtre.py
"""

from PIL import Image
Image.MAX_IMAGE_PIXELS = None
import numpy as np
from pathlib import Path

# ─── CONFIG ────────────────────────────────────────────────────────────────────

MASKS_WB      = Path(r"H:\logiciel perso\Map generator\data\maksoriginaux")
MASKS_COMBINED = Path(r"H:\logiciel perso\Map generator\data\masks_combined")
OUT_PATH      = Path(r"H:\logiciel perso\Map generator\data\simulate_qtre.png")

OUT_SIZE  = 4096
GRID      = 128        # 128×128 blocs
PPB       = OUT_SIZE // GRID  # 32 px/bloc
THRESHOLD = 50         # seuil activation mask (0-255)

# ─── ORDRE 32 PASSES ───────────────────────────────────────────────────────────
# (fichier, texture_name) — combined=MASKS_COMBINED, wb=MASKS_WB

PASSES = [
    # 1. Seabed global
    ("combined", "seabed_global.png",               "SeaBed_01"),
    # 2. Infrastructures
    ("wb",       "Asphalt_01.png",                  "Asphalt_01"),
    ("combined", "concrete_01_extended.png",         "Concrete_01"),
    ("wb",       "Cobblestone_01_wave.png",          "Cobblestone_01_Wave"),
    ("wb",       "ZI_Ground_Sport_01.png",           "ZI_Ground_Sport_01"),
    # 3. Champs
    ("wb",       "cropfield_01.png",                "Crop_Field_01"),
    ("wb",       "cropfield_02.png",                "Crop_Field_02"),
    ("wb",       "ZI_Crop_Field_01.png",            "ZI_Crop_Field_01"),
    ("wb",       "ZI_Crop_Field_02.png",            "ZI_Crop_Field_02"),
    ("wb",       "ZI_Crop_Field_03.png",            "ZI_Crop_Field_03"),
    ("wb",       "ZI_Crop_Field_04.png",            "ZI_Crop_Field_04"),
    ("wb",       "ZI_Crop_Field_Cut_01.png",        "ZI_Crop_Field_Cut_01"),
    ("wb",       "ZI_Crop_Field_Cut_02.png",        "ZI_Crop_Field_Cut_02"),
    # 4. Roches/débris
    ("combined", "rock_01_combined.png",             "Rock_01"),
    ("wb",       "Rock_02.png",                     "Rock_02"),
    ("wb",       "debris_rock01.png",               "Debris_Rock_01"),
    ("wb",       "Debris_Coal_01.png",              "Debris_Coal_01"),
    ("wb",       "Debris_Coal_02.png",              "Debris_Coal_02"),
    ("wb",       "Debris_Coal_03.png",              "Debris_Coal_03"),
    # 5. Côtier
    ("combined", "pebbles_02_combined.png",          "Pebbles_02"),
    ("wb",       "Pebbles_01.png",                  "Pebbles_01"),
    ("wb",       "BeachGrass_01.png",               "BeachGrass_01"),
    ("wb",       "Grass_03_coastal.png",            "Grass_03_coastal"),
    # 6. Forêts
    ("combined", "forestconiferous_02_zoneA.png",   "ForestConiferous_02"),
    ("combined", "forestconiferous_01base_zoneB.png","ForestConiferous_01_Base"),
    ("combined", "forestdeciduous_02_zoneA.png",    "ForestDeciduous_02"),
    ("combined", "forestdeciduous_01base_zoneB.png","ForestDeciduous_01_Base"),
    ("wb",       "forestClearing_coniferous_01.png","ForestClearing_Coniferous_01"),
    ("wb",       "forestClearing__Decidous_01.png", "ForestClearing_Deciduous_01"),
    # 7. Végétation
    ("combined", "heather_01_zoneB_only.png",       "Heather_01"),
    ("combined", "mountaingrass_01_combined.png",   "MountainGrass_01"),
    ("combined", "mountaingrass_03_zoneB.png",      "MountainGrass_03"),
    ("combined", "zi_mountaingrass04_zoneB.png",    "zi_MountainGrass_04"),
    ("combined", "grass_02_combined.png",           "Grass_02"),
    ("wb",       "Grass_01.png",                    "Grass_01"),
    ("combined", "grass_01aut_zoneB.png",           "Grass_01_aut"),
    # 8. Dirt
    ("combined", "dirt_01_extended.png",            "Dirt_01"),
    ("combined", "dirt_02_zoneB_only.png",          "Dirt_02"),
    ("combined", "dirt_03_flow_zoneB.png",          "Dirt_03"),
]

# ─── COULEURS QTRE ─────────────────────────────────────────────────────────────

COLORS = {
    0: ( 50,  50,  50),   # vide
    1: (100, 200, 100),   # 1 tex
    2: (120, 210, 120),
    3: (140, 220, 140),
    4: (160, 230, 160),
    5: (180, 240, 180),
    6: (200, 255, 200),   # 6 = limite max ✓ vert
    7: (255, 200,   0),   # 7 = orange dépassement
    8: (255, 100,   0),
    9: (255,  50,   0),
   10: (255,   0,   0),   # ≥10 = rouge critique
}

def get_color(n):
    return COLORS.get(min(n, 10), (255, 0, 0))

# ─── CHARGEMENT ────────────────────────────────────────────────────────────────

def load(folder: Path, fname: str) -> np.ndarray | None:
    p = folder / fname
    if not p.exists():
        # Recherche case-insensitive
        for f in folder.glob("*.png"):
            if f.name.lower() == fname.lower():
                p = f
                break
        else:
            print(f"  ABSENT: {fname}")
            return None
    img = Image.open(p).convert("L")
    if img.size != (OUT_SIZE, OUT_SIZE):
        img = img.resize((OUT_SIZE, OUT_SIZE), Image.LANCZOS)
    return np.array(img, dtype=np.uint8)

# ─── SIMULATION ────────────────────────────────────────────────────────────────

print("Chargement des masks...")
loaded = []
for src, fname, tex in PASSES:
    folder = MASKS_COMBINED if src == "combined" else MASKS_WB
    arr = load(folder, fname)
    if arr is not None:
        loaded.append((tex, arr))
        print(f"  ✓ {tex}")
    else:
        print(f"  ✗ {tex} ({fname})")

print(f"\n{len(loaded)}/{len(PASSES)} masks chargés.")

print("\nSimulation par bloc...")

# Pour chaque pixel 4096×4096 : compter textures actives
# On travaille par colonne de pixels pour économiser la mémoire
slot_count = np.zeros((OUT_SIZE, OUT_SIZE), dtype=np.uint8)

for tex, arr in loaded:
    slot_count[arr >= THRESHOLD] += 1

# Par bloc : prendre le MAX du slot_count dans le bloc
print("Agrégation par bloc...")
bloc_max = np.zeros((GRID, GRID), dtype=np.uint8)
for by in range(GRID):
    for bx in range(GRID):
        y0, x0 = by * PPB, bx * PPB
        region = slot_count[y0:y0+PPB, x0:x0+PPB]
        bloc_max[by, bx] = int(region.max())

# Stats
total = GRID * GRID
counts = {n: int((bloc_max == n).sum()) for n in range(11)}
ok     = sum(counts[n] for n in range(7))
warn   = counts.get(7, 0)
over   = sum(counts[n] for n in range(8, 11))
empty  = counts.get(0, 0)

print(f"\n=== RÉSULTATS QTRE ===")
print(f"  Vides (0 tex)      : {empty:5d} blocs ({100*empty/total:.1f}%)")
for n in range(1, 7):
    print(f"  {n} texture(s)        : {counts.get(n,0):5d} blocs ({100*counts.get(n,0)/total:.1f}%)")
print(f"  --- budget max 6 ---")
print(f"  ✓ OK  (≤6 tex)     : {ok:5d} blocs ({100*ok/total:.1f}%)")
print(f"  ⚠ 7 textures       : {warn:5d} blocs ({100*warn/total:.1f}%)")
print(f"  ✗ >7 textures      : {over:5d} blocs ({100*over/total:.1f}%)")
print(f"  TOTAL              : {total} blocs")

# Générer image
print("\nGénération image QTRE...")
out = np.zeros((OUT_SIZE, OUT_SIZE, 3), dtype=np.uint8)

for by in range(GRID):
    for bx in range(GRID):
        n = int(bloc_max[by, bx])
        color = get_color(n)
        y0, x0 = by * PPB, bx * PPB
        out[y0:y0+PPB, x0:x0+PPB] = color

# Grille tuiles
TILE_PX = PPB * 4
for i in range(0, OUT_SIZE, TILE_PX):
    out[i, :] = (out[i, :] * 0.4).astype(np.uint8)
    out[:, i] = (out[:, i] * 0.4).astype(np.uint8)

# Légende
from PIL import ImageDraw
img_out = Image.fromarray(out, "RGB")
draw = ImageDraw.Draw(img_out)
legend = [
    ((200,255,200), "≤6 textures (OK)"),
    ((255,200,  0), "7 textures (dépassement)"),
    ((255, 50,  0), ">7 textures (critique)"),
    (( 50, 50, 50), "0 texture (vide)"),
]
x, y = 10, OUT_SIZE - 90
for color, label in legend:
    draw.rectangle([x, y, x+20, y+15], fill=color, outline=(0,0,0))
    draw.text((x+25, y), label, fill=(255,255,255))
    y += 20

img_out.save(OUT_PATH)
print(f"✓ Sauvegardé : {OUT_PATH}")
