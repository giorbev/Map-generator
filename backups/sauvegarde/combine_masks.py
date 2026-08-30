"""
combine_masks.py — Génération des masks combinés Zone A (WB) + Zone B (pipeline)
Ordre de sortie : du moins prioritaire (01) au plus prioritaire (40) pour WB.
Usage: python combine_masks.py
"""

from PIL import Image
Image.MAX_IMAGE_PIXELS = None
import numpy as np
from pathlib import Path

# ─── CONFIG ────────────────────────────────────────────────────────────────────

MASKS_WB   = Path(r"H:\logiciel perso\Map generator\data\maksoriginaux")
MASKS_ZB   = Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\outputs\masks\latest\masks")
OUT_DIR    = Path(r"H:\logiciel perso\Map generator\data\masks_combined")
MASK_EXCL  = Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\inputs\new_exclusion4.png")

OUT_SIZE   = 4096

OUT_DIR.mkdir(parents=True, exist_ok=True)

# ─── HELPERS ───────────────────────────────────────────────────────────────────

def load_gray(path: Path, size: int) -> np.ndarray:
    img = Image.open(path).convert("L")
    if img.size != (size, size):
        img = img.resize((size, size), Image.LANCZOS)
    return np.array(img, dtype=np.uint8)

_pass_counter = [0]

def save(arr: np.ndarray, name: str):
    _pass_counter[0] += 1
    prefixed = f"{_pass_counter[0]:02d}_{name}"
    Image.fromarray(arr, "L").save(OUT_DIR / prefixed)
    pct = 100 * (arr > 10).sum() / arr.size
    print(f"  → {prefixed}  ({pct:.1f}% actif)")

def wa(stem: str) -> np.ndarray | None:
    for f in MASKS_WB.glob("*.png"):
        if f.stem.lower() == stem.lower():
            return load_gray(f, OUT_SIZE)
    print(f"  ABSENT WB: {stem}")
    return None

def zb(candidates: list[str]) -> np.ndarray | None:
    for name in candidates:
        stem = name.replace(".png", "")
        for f in MASKS_ZB.glob("*.png"):
            if stem.lower() in f.stem.lower():
                arr = load_gray(f, OUT_SIZE)
                result = np.zeros(arr.shape, dtype=np.uint8)
                result[zone_ouest] = arr[zone_ouest]
                return result
    print(f"  ABSENT ZB: {candidates}")
    return None

def direct_wb(fname: str, tex: str):
    f = MASKS_WB / fname
    if f.exists():
        save(load_gray(f, OUT_SIZE), f"{tex}.png")
    else:
        print(f"  ABSENT: {fname}")

# ─── CHARGEMENT MASQUE EXCLUSION ───────────────────────────────────────────────

print("Chargement masque exclusion...")
excl_raw = load_gray(MASK_EXCL, OUT_SIZE)
zone_ouest = excl_raw > 128
zone_est   = ~zone_ouest
print(f"  Zone Ouest : {zone_ouest.sum()/excl_raw.size*100:.1f}%")
print(f"  Zone Est   : {zone_est.sum()/excl_raw.size*100:.1f}%")

# ─── GÉNÉRATION — ordre 01→40 (moins prioritaire → plus prioritaire) ───────────

print("\n=== GÉNÉRATION 40 MASKS ===\n")

# 01. Grass_03_default (WB direct)
direct_wb("grass_03_default.png", "Grass_03_default")

# 02. Grass_03 (WB direct)
direct_wb("grass_03.png", "Grass_03")

# 03. Grass_03_coastal (WB direct)
direct_wb("Grass_03_coastal.png", "Grass_03_coastal")

# 04. Grass_01 (WB direct)
direct_wb("Grass_01.png", "Grass_01")

# 05. Grass_02 — union Zone Est WB + Zone Ouest pipeline
g2_wa = wa("grass_02")
g2_zb = zb(["mask_prairie_humide.png"])
if g2_wa is not None and g2_zb is not None:
    combined = g2_wa.copy()
    combined[zone_ouest] = np.maximum(g2_wa[zone_ouest], g2_zb[zone_ouest])
    save(combined, "Grass_02_combined.png")
elif g2_wa is not None:
    save(g2_wa, "Grass_02.png")

# 06. Grass_01_aut — Zone B uniquement
arr = zb(["mask_prairie_seche.png"])
if arr is not None:
    arr[zone_est] = 0
    save(arr, "Grass_01_aut_zoneB.png")

# 07. BeachGrass_01 (WB direct)
direct_wb("BeachGrass_01.png", "BeachGrass_01")

# 08. MountainGrass_01 — union Zone Est WB + Zone Ouest pipeline
mg_wa = wa("MountainGrass_01")
mg_zb = zb(["mask_alpages.png"])
if mg_wa is not None and mg_zb is not None:
    combined = mg_wa.copy()
    combined[zone_ouest] = np.maximum(mg_wa[zone_ouest], mg_zb[zone_ouest])
    save(combined, "MountainGrass_01_combined.png")
elif mg_wa is not None:
    save(mg_wa, "MountainGrass_01.png")

# 09. MountainGrass_03 — Zone B uniquement
arr = zb(["mask_landes_plateau.png"])
if arr is not None:
    arr[zone_est] = 0
    save(arr, "MountainGrass_03_zoneB.png")

# 10. zi_MountainGrass_04 — Zone B uniquement
arr = zb(["mask_landes_rocheuses.png"])
if arr is not None:
    arr[zone_est] = 0
    save(arr, "zi_MountainGrass_04_zoneB.png")

# 11. Heather_01 — Zone B uniquement
arr = zb(["mask_maquis_landes.png"])
if arr is not None:
    arr[zone_est] = 0
    save(arr, "Heather_01_zoneB.png")

# 12. ForestClearing_Deciduous_01 (WB direct)
direct_wb("forestClearing__Decidous_01.png", "ForestClearing_Deciduous_01")

# 13. ForestClearing_Coniferous_01 (WB direct)
direct_wb("forestClearing_coniferous_01.png", "ForestClearing_Coniferous_01")

# 14. ForestDeciduous_01_Base — Zone B uniquement
arr = zb(["mask_foret_feuillue.png"])
if arr is not None:
    arr[zone_est] = 0
    save(arr, "ForestDeciduous_01_Base_zoneB.png")

# 15. ForestDeciduous_02 — Zone Est uniquement (WB)
fd2_wa = wa("forestDeciduous_02")
if fd2_wa is not None:
    fd2_wa[zone_ouest] = 0
    fd2_wa = np.clip(fd2_wa.astype(np.float32) * 1.8, 0, 255).astype(np.uint8)
    save(fd2_wa, "ForestDeciduous_02_zoneA.png")

# 16. ForestConiferous_01_Base — Zone B uniquement
arr = zb(["mask_foret_coniferes.png"])
if arr is not None:
    arr[zone_est] = 0
    save(arr, "ForestConiferous_01_Base_zoneB.png")

# 17. ForestConiferous_02 — Zone Est uniquement (WB)
fc2_wa = wa("Forestconiferous_02")
if fc2_wa is not None:
    fc2_wa[zone_ouest] = 0
    fc2_wa = np.clip(fc2_wa.astype(np.float32) * 1.8, 0, 255).astype(np.uint8)
    save(fc2_wa, "ForestConiferous_02_zoneA.png")

# 18. Dirt_01 étendu — Dirt_01 + ex-Dirt_02 Zone Est
d1_wa = wa("dirt_01")
d2_wa = wa("dirt_02")
if d1_wa is not None and d2_wa is not None:
    combined = d1_wa.copy()
    combined[zone_est] = np.maximum(d1_wa[zone_est], d2_wa[zone_est])
    save(combined, "Dirt_01_extended.png")
elif d1_wa is not None:
    save(d1_wa, "Dirt_01.png")

# 19. Dirt_02 — Zone B uniquement (deposit)
arr = zb(["mask_deposit.png"])
if arr is not None:
    arr[zone_est] = 0
    save(arr, "Dirt_02_zoneB.png")

# 20. Dirt_03 — Zone B uniquement (flow)
arr = zb(["mask_flow.png"])
if arr is not None:
    arr[zone_est] = 0
    save(arr, "Dirt_03_flow_zoneB.png")

# 21. Pebbles_01 (WB direct)
direct_wb("Pebbles_01.png", "Pebbles_01")

# 22. Pebbles_02 — Zone Est trimée + Zone B coastal
p2_wa = wa("Pebbles_02")
p2_zb = zb(["mask_coastal.png"])
if p2_wa is not None:
    combined = p2_wa.copy()
    combined[zone_ouest] = 0
    if p2_zb is not None:
        combined[zone_ouest] = p2_zb[zone_ouest]
    save(combined, "Pebbles_02_combined.png")

# 23. Debris_Coal_01 (WB direct)
direct_wb("Debris_Coal_01.png", "Debris_Coal_01")

# 24. Debris_Coal_02 (WB direct)
direct_wb("Debris_Coal_02.png", "Debris_Coal_02")

# 25. Debris_Coal_03 (WB direct)
direct_wb("Debris_Coal_03.png", "Debris_Coal_03")

# 26. Debris_Rock_01 (WB direct)
direct_wb("debris_rock01.png", "Debris_Rock_01")

# 27. Rock_02 (WB direct)
direct_wb("Rock_02.png", "Rock_02")

# 28. Rock_01 — union Zone Est WB + Zone Ouest pipeline
rock_wa = wa("rock_01")
rock_zb = zb(["mask_rock.png"])
if rock_wa is not None and rock_zb is not None:
    combined = rock_wa.copy()
    combined[zone_ouest] = np.maximum(rock_wa[zone_ouest], rock_zb[zone_ouest])
    save(combined, "Rock_01_combined.png")
elif rock_wa is not None:
    save(rock_wa, "Rock_01.png")

# 29. ZI_Crop_Field_Cut_02 (WB direct)
direct_wb("ZI_Crop_Field_Cut_02.png", "ZI_Crop_Field_Cut_02")

# 30. ZI_Crop_Field_Cut_01 (WB direct)
direct_wb("ZI_Crop_Field_Cut_01.png", "ZI_Crop_Field_Cut_01")

# 31. ZI_Crop_Field_04 (WB direct)
direct_wb("ZI_Crop_Field_04.png", "ZI_Crop_Field_04")

# 32. ZI_Crop_Field_03 (WB direct)
direct_wb("ZI_Crop_Field_03.png", "ZI_Crop_Field_03")

# 33. ZI_Crop_Field_02 (WB direct)
direct_wb("ZI_Crop_Field_02.png", "ZI_Crop_Field_02")

# 34. ZI_Crop_Field_01 (WB direct)
direct_wb("ZI_Crop_Field_01.png", "ZI_Crop_Field_01")

# 35. Crop_Field_02 (WB direct)
direct_wb("cropfield_02.png", "Crop_Field_02")

# 36. Crop_Field_01 (WB direct)
direct_wb("cropfield_01.png", "Crop_Field_01")

# 37. ZI_Ground_Sport_01 (WB direct)
direct_wb("ZI_Ground_Sport_01.png", "ZI_Ground_Sport_01")

# 38. Concrete_01 — union Concrete_01 + Concrete_02
c1_wa = wa("concrete_01")
c2_wa = wa("Concrete_02")
if c1_wa is not None and c2_wa is not None:
    save(np.maximum(c1_wa, c2_wa), "Concrete_01_extended.png")
elif c1_wa is not None:
    save(c1_wa, "Concrete_01.png")

# 39. Asphalt_01 (WB direct)
direct_wb("Asphalt_01.png", "Asphalt_01")

# 40. SeaBed_01 — global (Zone Ouest = pipeline, Zone Est = WB)
seabed_wb = wa("SeaBed_01")
seabed_zb = zb(["mask_seabed.png"])
if seabed_wb is not None and seabed_zb is not None:
    combined = seabed_wb.copy()
    combined[zone_ouest] = seabed_zb[zone_ouest]
    save(combined, "SeaBed_01_global.png")
elif seabed_wb is not None:
    save(seabed_wb, "SeaBed_01_global.png")

print(f"\n✓ {_pass_counter[0]} masks générés dans : {OUT_DIR}")
