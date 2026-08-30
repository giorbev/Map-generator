"""
combine_masks_v3.py — Protocole révisé 29 masks
Fill layer WB = Grass_03 (pas de mask pour Grass_03/default)
Ordre : 01→29, du moins prioritaire au plus prioritaire pour WB.

Usage: python combine_masks_v3.py
"""

from PIL import Image
Image.MAX_IMAGE_PIXELS = None
import numpy as np
from pathlib import Path

# ─── CONFIG ────────────────────────────────────────────────────────────────────

MASKS_WB  = Path(r"H:\logiciel perso\Map generator\data\maksoriginaux")
MASKS_ZB  = Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\outputs\masks\latest\masks")
OUT_DIR   = Path(r"H:\logiciel perso\Map generator\data\masks_combined_v3")
MASK_EXCL = Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\inputs\new_exclusion4.png")

OUT_SIZE  = 4096

OUT_DIR.mkdir(parents=True, exist_ok=True)

# ─── HELPERS ───────────────────────────────────────────────────────────────────

def load_gray(path: Path, size: int = OUT_SIZE) -> np.ndarray:
    img = Image.open(path).convert("L")
    if img.size != (size, size):
        img = img.resize((size, size), Image.LANCZOS)
    return np.array(img, dtype=np.uint8)

_n = [0]

def save(arr: np.ndarray, name: str):
    _n[0] += 1
    fname = f"{_n[0]:02d}_{name}"
    Image.fromarray(arr, "L").save(OUT_DIR / fname)
    pct = 100 * (arr > 10).sum() / arr.size
    print(f"  {fname}  ({pct:.1f}% actif)")

def wa(stem: str) -> np.ndarray | None:
    for f in MASKS_WB.glob("*.png"):
        if f.stem.lower() == stem.lower():
            return load_gray(f)
    print(f"  ABSENT WB: {stem}"); return None

def zb(candidates: list[str]) -> np.ndarray | None:
    for name in candidates:
        stem = name.replace(".png", "")
        for f in MASKS_ZB.glob("*.png"):
            if stem.lower() in f.stem.lower():
                arr = load_gray(f)
                result = np.zeros(arr.shape, dtype=np.uint8)
                result[zone_ouest] = arr[zone_ouest]
                return result
    print(f"  ABSENT ZB: {candidates}"); return None

def wb_direct(fname: str, tex: str):
    f = MASKS_WB / fname
    if f.exists():
        save(load_gray(f), f"{tex}.png")
    else:
        print(f"  ABSENT: {fname}")

# ─── MASQUE EXCLUSION ──────────────────────────────────────────────────────────

print("Chargement masque exclusion...")
excl = load_gray(MASK_EXCL)
zone_ouest = excl > 128
zone_est   = ~zone_ouest
print(f"  Zone Ouest {zone_ouest.sum()/excl.size*100:.1f}% / Zone Est {zone_est.sum()/excl.size*100:.1f}%")

# ─── ÉTAPE 1 — FONDATIONS (toute la map) ──────────────────────────────────────
print("\n── Étape 1 : Fondations ──")

# 01. Asphalt
wb_direct("Asphalt_01.png", "Asphalt_01")

# 02. Concrete (01 + 02 fusionnés)
c1 = wa("concrete_01"); c2 = wa("Concrete_02")
if c1 is not None and c2 is not None:
    save(np.maximum(c1, c2), "Concrete_01.png")
elif c1 is not None:
    save(c1, "Concrete_01.png")

# 03. Cobblestone
wb_direct("Cobblestone_01_wave.png", "Cobblestone_01_Wave")

# 04. ZI_Ground_Sport_01
wb_direct("ZI_Ground_Sport_01.png", "ZI_Ground_Sport_01")

# 05-12. Champs
for fname, tex in [
    ("cropfield_01.png",         "Crop_Field_01"),
    ("cropfield_02.png",         "Crop_Field_02"),
    ("ZI_Crop_Field_01.png",     "ZI_Crop_Field_01"),
    ("ZI_Crop_Field_02.png",     "ZI_Crop_Field_02"),
    ("ZI_Crop_Field_03.png",     "ZI_Crop_Field_03"),
    ("ZI_Crop_Field_04.png",     "ZI_Crop_Field_04"),
    ("ZI_Crop_Field_Cut_01.png", "ZI_Crop_Field_Cut_01"),
    ("ZI_Crop_Field_Cut_02.png", "ZI_Crop_Field_Cut_02"),
]:
    wb_direct(fname, tex)

# ─── ÉTAPE 2 — TEXTURES COMMUNES Zone A+B ─────────────────────────────────────
print("\n── Étape 2 : Communes Zone A+B ──")

# 13. SeaBed_01 global
sb_wa = wa("SeaBed_01")
sb_zb = zb(["mask_seabed.png"])
if sb_wa is not None and sb_zb is not None:
    combined = sb_wa.copy()
    combined[zone_ouest] = sb_zb[zone_ouest]
    save(combined, "SeaBed_01_global.png")
elif sb_wa is not None:
    save(sb_wa, "SeaBed_01_global.png")

# 14. Rock_01 — séparé Zone A / Zone B
rk_wa = wa("rock_01")
if rk_wa is not None:
    rk_wa[zone_ouest] = 0
    save(rk_wa, "Rock_01_zoneA_clean.png")

rk_zb = zb(["mask_rock.png"])
if rk_zb is not None:
    rk_zb[zone_est] = 0
    save(rk_zb, "Rock_01_zoneB_pipeline.png")

# 15. Rock_02
wb_direct("Rock_02.png", "Rock_02")

# 16. Debris_Rock_01
wb_direct("debris_rock01.png", "Debris_Rock_01")

# 17-19. Debris_Coal
wb_direct("Debris_Coal_01.png", "Debris_Coal_01")
wb_direct("Debris_Coal_02.png", "Debris_Coal_02")
wb_direct("Debris_Coal_03.png", "Debris_Coal_03")

# 20. Pebbles_01
wb_direct("Pebbles_01.png", "Pebbles_01")

# 21. Pebbles_02 — Zone Est trimée + Zone B coastal
p2_wa = wa("Pebbles_02"); p2_zb = zb(["mask_coastal.png"])
if p2_wa is not None:
    combined = p2_wa.copy()
    combined[zone_ouest] = 0
    if p2_zb is not None:
        combined[zone_ouest] = p2_zb[zone_ouest]
    save(combined, "Pebbles_02_combined.png")

# 22. BeachGrass_01
wb_direct("BeachGrass_01.png", "BeachGrass_01")

# 23. Grass_03_coastal
wb_direct("Grass_03_coastal.png", "Grass_03_coastal")

# 24. Dirt_01 étendu (Dirt_01 + ex-Dirt_02 Zone Est)
d1 = wa("dirt_01"); d2 = wa("dirt_02")
if d1 is not None and d2 is not None:
    combined = d1.copy()
    combined[zone_est] = np.maximum(d1[zone_est], d2[zone_est])
    save(combined, "Dirt_01_extended.png")
elif d1 is not None:
    save(d1, "Dirt_01_extended.png")

# 25. Grass_02 — union
g2_wa = wa("grass_02"); g2_zb = zb(["mask_prairie_humide.png"])
if g2_wa is not None and g2_zb is not None:
    combined = g2_wa.copy()
    combined[zone_ouest] = np.maximum(g2_wa[zone_ouest], g2_zb[zone_ouest])
    save(combined, "Grass_02_combined.png")
elif g2_wa is not None:
    save(g2_wa, "Grass_02_combined.png")

# 26. MountainGrass_01 — union
mg_wa = wa("MountainGrass_01"); mg_zb = zb(["mask_alpages.png"])
if mg_wa is not None and mg_zb is not None:
    combined = mg_wa.copy()
    combined[zone_ouest] = np.maximum(mg_wa[zone_ouest], mg_zb[zone_ouest])
    save(combined, "MountainGrass_01_combined.png")
elif mg_wa is not None:
    save(mg_wa, "MountainGrass_01_combined.png")

# 27. Grass_01
wb_direct("Grass_01.png", "Grass_01")

# ─── ÉTAPE 3 — ZONE B UNIQUEMENT ──────────────────────────────────────────────
print("\n── Étape 3 : Zone B uniquement ──")

for candidates, outname in [
    (["mask_deposit.png"],        "Dirt_02_deposit_zoneB.png"),
    (["mask_flow.png"],           "Dirt_03_flow_zoneB.png"),
    (["mask_landes_plateau.png"], "MountainGrass_03_zoneB.png"),
    (["mask_landes_rocheuses.png"],"zi_MountainGrass_04_zoneB.png"),
    (["mask_maquis_landes.png"],  "Heather_01_zoneB.png"),
    (["mask_prairie_seche.png"],  "Grass_01_aut_zoneB.png"),
]:
    arr = zb(candidates)
    if arr is not None:
        arr[zone_est] = 0
        save(arr, outname)

# ─── ÉTAPE 4 — FORÊTS (2 textures unifiées) ───────────────────────────────────
print("\n── Étape 4 : Forêts ──")

# Conifères : ForestConiferous_02 (ZoneA) + ForestConiferous_01_Base (ZoneB)
fc2 = wa("Forestconiferous_02")
fc1_zb = zb(["mask_foret_coniferes.png"])
if fc2 is not None:
    fc2_boost = np.clip(fc2.astype(np.float32) * 1.8, 0, 255).astype(np.uint8)
    combined = fc2_boost.copy()
    combined[zone_ouest] = 0  # efface Zone A côté Ouest
    if fc1_zb is not None:
        combined[zone_ouest] = fc1_zb[zone_ouest]  # pose ZoneB
    save(combined, "ForestConiferous_02_unified.png")

# Feuillus : ForestDeciduous_02 (ZoneA) + ForestDeciduous_01_Base (ZoneB)
fd2 = wa("forestDeciduous_02")
fd1_zb = zb(["mask_foret_feuillue.png"])
if fd2 is not None:
    fd2_boost = np.clip(fd2.astype(np.float32) * 1.8, 0, 255).astype(np.uint8)
    combined = fd2_boost.copy()
    combined[zone_ouest] = 0
    if fd1_zb is not None:
        combined[zone_ouest] = fd1_zb[zone_ouest]
    save(combined, "ForestDeciduous_02_unified.png")

print(f"\n✓ {_n[0]} masks générés dans : {OUT_DIR}")
print("\nRécapitulatif ordre WB (01→29) :")
print("  Étape 1 (01-12) : Fondations — Asphalt, Concrete, Cobblestone, Sport, Champs")
print("  Étape 2 (13-27) : Communes — SeaBed, Rock, Debris, Pebbles, Beach, Dirt, Grass, MtnGrass")
print("  Étape 3 (28-33) : Zone B — Deposit, Flow, MtnGrass03, zi_MtnGrass04, Heather, Grass01aut")
print("  Étape 4 (34-35) : Forêts unifiées — Conifères, Feuillus")
print()
print("⚠ Fill layer WB = Grass_03 (pas Grass_03_default)")
