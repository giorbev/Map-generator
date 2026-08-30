"""
patch_catalog_middlecolor.py
Applique les avg_color issus des MiddleColor .emat (linear → sRGB)
sur catalog.json existant. Ne touche qu'au champ avg_color.
Usage : python patch_catalog_middlecolor.py catalog.json [--dry-run]
"""

import json, sys, shutil, pathlib
from datetime import datetime

# ── Valeurs sources : MiddleColor .emat linear → sRGB (gamma 2.2) ─────────
# Règles d'héritage appliquées :
#   Rock_02+      → hérite Rock_01
#   zi_Heather_01 → même texture que Heather_01 vanilla
#   Debris_Coal   → inspiré Debris_Rock mais assombri (charbon)
EMAT_AVG_COLORS = {
    "Asphalt_01":                   [164, 164, 164],
    "BeachGrass_01":                [199, 210, 153],
    "Cobblestone_01_Wave":          [219, 219, 219],
    "Cobblestone_01_Wave_V2":       [219, 219, 219],
    "Concrete_01":                  [163, 180, 224],
    "Concrete_02":                  [185, 199, 231],
    "Crop_Field_01":                [235, 235, 160],
    "Crop_Field_02":                [248, 234, 185],
    "Debris_Coal_01":               [ 30,  30,  30],  # noir profond (charbon)
    "Debris_Coal_02":               [ 80,  80,  80],  # gris-noir
    "Debris_Coal_03":               [110, 105,  95],  # gris-anthracite
    "Debris_Rock_01":               [167, 167, 167],
    "Debris_Rock_01_V2":            [167, 167, 167],
    "Dirt_01":                      [177, 170, 148],
    "Dirt_02":                      [186, 163,   0],  # ocre-brun, bleu=0 fidèle emat
    "Dirt_03":                      [177, 170, 148],
    "ForestClearing_Coniferous_01": [ 77, 196, 120],
    "ForestClearing_Deciduous_01":  [ 77, 196, 120],
    "ForestConiferous_01_Base":     [ 77, 196, 120],
    "ForestConiferous_02":          [ 49, 125,  77],
    "ForestDeciduous_01_Base":      [163, 224, 180],
    "ForestDeciduous_02":           [124, 170, 138],
    "ForestPine_01_Base":           [195, 173, 139],
    "Grass_01":                     [ 77, 196, 120],
    "Grass_01_aut":                 [144, 187, 127],
    "Grass_01_aut_leaves":          [240, 214,  93],
    "Grass_02":                     [138, 215, 161],
    "Grass_02_aut":                 [161, 191, 120],
    "Grass_03":                     [211, 232, 187],
    "Grass_03_aut":                 [217, 226, 178],
    "Heather_01":                   [210, 153, 178],
    "zi_Heather_01":                [210, 153, 178],  # même texture vanilla
    "MountainGrass_01":             [240, 233, 210],
    "MountainGrass_01_aut":         [199, 191, 164],
    "MountainGrass_02":             [199, 191, 166],
    "MountainGrass_02_aut":         [255, 245, 212],
    "MountainGrass_03":             [180, 205, 156],
    "MountainGrass_03_aut":         [205, 171, 138],
    "Pebbles_01":                   [206, 206, 150],
    "Rock_01":                      [204, 204, 204],
    "Rock_02":                      [204, 204, 204],  # hérite Rock_01
    "SeaBed_01":                    [255, 170,   0],
    "SulfurStream_01_bed":          [255, 255,   0],
}

def patch(catalog_path: str, dry_run: bool = False):
    p = pathlib.Path(catalog_path)
    if not p.exists():
        print(f"[ERR] Fichier introuvable : {p}")
        sys.exit(1)

    with open(p, encoding="utf-8") as f:
        catalog = json.load(f)

    updated, skipped, not_found = [], [], []

    for mat_name, new_color in EMAT_AVG_COLORS.items():
        if mat_name not in catalog:
            not_found.append(mat_name)
            continue
        old = catalog[mat_name].get("avg_color")
        if old == new_color:
            skipped.append(mat_name)
            continue
        if not dry_run:
            catalog[mat_name]["avg_color"] = new_color
        updated.append((mat_name, old, new_color))

    # Rapport
    print(f"\n{'[DRY-RUN] ' if dry_run else ''}Patch catalog.json — MiddleColor emat")
    print("=" * 60)
    print(f"  Mis à jour  : {len(updated)}")
    print(f"  Inchangés   : {len(skipped)}")
    print(f"  Non trouvés : {len(not_found)}")

    if updated:
        print("\n  Changements :")
        for name, old, new in updated:
            old_str = str(old) if old else "absent"
            print(f"    {name:<35} {old_str} → {new}")

    if not_found:
        print("\n  ⚠ Absents du catalog (à ajouter manuellement si nécessaire) :")
        for n in not_found:
            print(f"    - {n}")

    if dry_run:
        print("\n  Mode dry-run — aucune écriture.")
        return

    # Backup
    backup = p.with_suffix(f".bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    shutil.copy(p, backup)
    print(f"\n  Backup : {backup.name}")

    with open(p, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
    print(f"  ✓ catalog.json mis à jour ({len(updated)} entrées).")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage : python patch_catalog_middlecolor.py catalog.json [--dry-run]")
        sys.exit(1)
    dry = "--dry-run" in sys.argv
    patch(sys.argv[1], dry_run=dry)
