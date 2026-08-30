"""
patch_catalog_bcr_global.py
Mise à jour globale des avg_color depuis les vraies moyennes BCR texture.
48 matériaux couverts — source : mesures directes sur PNG BCR exportés.

Usage : python patch_catalog_bcr_global.py catalog.json [--dry-run]
"""

import json, sys, shutil, pathlib
from datetime import datetime

BCR_COLORS = {
    # ── ZI CropField ──────────────────────────────────────────────────────
    "zi_CropField_01":              [121, 111,  78],
    "zi_CropField_02":              [121, 119,  78],
    "zi_CropField_03":              [ 35,  42,  28],  # Crop_Field_01 × tint #a7dfb5
    "zi_CropField_04":              [121, 132,  90],
    "zi_CropField_Cut_01":          [ 72,  69,  57],
    "zi_CropField_Cut_02":          [103,  95,  73],
    # ── Vanilla CropField ─────────────────────────────────────────────────
    "Crop_Field_01":                [ 54,  48,  40],
    "Crop_Field_02":                [ 69,  61,  50],
    # ── Dirt ──────────────────────────────────────────────────────────────
    "Dirt_01":                      [ 83,  75,  63],
    "Dirt_02":                      [ 83,  72,  57],
    "Dirt_03":                      [ 49,  42,  34],  # middle × tint #433b31
    # ── Grass ─────────────────────────────────────────────────────────────
    "Grass_01":                     [ 53,  64,  36],
    "Grass_01_aut":                 [ 45,  50,  36],
    "Grass_01_aut_leaves":          [ 45,  50,  36],
    "Grass_02":                     [ 59,  62,  39],
    "Grass_02_aut":                 [ 53,  62,  43],
    "Grass_03":                     [ 58,  68,  40],
    "Grass_03_aut":                 [ 70,  71,  53],
    # ── MountainGrass ─────────────────────────────────────────────────────
    "MountainGrass_01":             [ 68,  69,  42],
    "MountainGrass_02":             [ 86,  89,  66],
    "MountainGrass_02_aut":         [ 81,  79,  60],
    "MountainGrass_03":             [ 56,  60,  37],
    "MountainGrass_03_aut":         [ 81,  70,  46],
    # ── Forest ────────────────────────────────────────────────────────────
    "ForestConiferous_01_Base":     [ 87,  73,  56],
    "ForestConiferous_02":          [ 75,  79,  39],
    "ForestDeciduous_01_Base":      [ 88,  72,  57],
    "ForestDeciduous_02":           [ 75,  73,  41],
    "ForestPine_01_Base":           [ 87,  73,  61],
    "ForestClearing_Coniferous_01": [ 34,  24,  17],  # dirt01_middle × tint #291e15
    "ForestClearing_Deciduous_01":  [ 26,  18,  11],  # dirt01_middle × tint #20160e
    # ── Rock ──────────────────────────────────────────────────────────────
    "Rock_01":                      [ 68,  67,  65],
    "Rock_02":                      [ 68,  67,  65],  # hérite Rock_01
    "Debris_Rock_01":               [ 68,  67,  65],
    "Debris_Rock_01_V2":            [ 68,  67,  65],
    # ── Debris Coal ───────────────────────────────────────────────────────
    "Debris_Coal_01":               [ 17,  17,  16],  # × tint #3b3b3b
    "Debris_Coal_02":               [ 33,  31,  27],  # × tint #7f776e
    "Debris_Coal_03":               [ 23,  23,  19],  # × tint #5a5b4f
    # ── Végétation côtière / sol ──────────────────────────────────────────
    "BeachGrass_01":                [ 74,  72,  49],
    "Heather_01":                   [ 71,  68,  44],
    "Pebbles_01":                   [ 88,  85,  77],
    "Pebbles_02":                   [ 85,  79,  74],
    "SeaBed_01":                    [ 68,  61,  52],
    "SulfurStream_01_bed":          [136,  93,  14],  # dirt01_middle × tint #a47012
    # ── Artificiel ────────────────────────────────────────────────────────
    "Asphalt_01":                   [ 70,  70,  70],
    "Cobblestone_01_Wave":          [ 87,  85,  83],
    "Cobblestone_01_Wave_V2":       [ 87,  85,  83],
    "Concrete_01":                  [107, 102,  97],
    "Concrete_02":                  [ 69,  66,  63],  # × tint #a6a6a6
}


def patch(catalog_path: str, dry_run: bool = False):
    p = pathlib.Path(catalog_path)
    if not p.exists():
        print(f"[ERR] Introuvable : {p}")
        sys.exit(1)

    with open(p, encoding="utf-8") as f:
        catalog = json.load(f)

    updated, skipped, not_found = [], [], []

    for mat, new_color in BCR_COLORS.items():
        if mat not in catalog:
            not_found.append(mat)
            continue
        old = catalog[mat].get("avg_color")
        if old == new_color:
            skipped.append(mat)
            continue
        if not dry_run:
            catalog[mat]["avg_color"] = new_color
        updated.append((mat, old, new_color))

    print(f"\n{'[DRY-RUN] ' if dry_run else ''}Patch BCR global — {len(BCR_COLORS)} matériaux")
    print("=" * 65)
    print(f"  Mis à jour  : {len(updated)}")
    print(f"  Inchangés   : {len(skipped)}")
    print(f"  Non trouvés : {len(not_found)}")

    if updated:
        print("\n  Changements :")
        for name, old, new in updated:
            print(f"    {name:<35} {str(old):>20} → {new}")

    if not_found:
        print(f"\n  ⚠ Absents du catalog :")
        for n in not_found:
            print(f"    - {n}")

    if dry_run:
        print("\n  Dry-run — aucune écriture.")
        return

    backup = p.with_suffix(f".bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    shutil.copy(p, backup)
    print(f"\n  Backup : {backup.name}")

    with open(p, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
    print(f"  ✓ catalog.json mis à jour ({len(updated)} entrées).")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage : python patch_catalog_bcr_global.py catalog.json [--dry-run]")
        sys.exit(1)
    patch(sys.argv[1], dry_run="--dry-run" in sys.argv)
