"""
patch_catalog_cropfield_v2.py
CropField ZI × 0.55 — plus ternes, moins flashy.
Usage : python patch_catalog_cropfield_v2.py catalog.json [--dry-run]
"""
import json, sys, shutil, pathlib
from datetime import datetime

UPDATES = {
    "zi_CropField_01":     [158, 153, 130],  # blé doré terne
    "zi_CropField_02":     [153, 148, 126],  # paille sèche
    "zi_CropField_03":     [126, 144, 124],  # vert olive foncé
    "zi_CropField_04":     [126, 144, 124],  # vert olive foncé
    "zi_CropField_Cut_01": [118, 118, 118],  # champ fauché gris foncé
    "zi_CropField_Cut_02": [149, 128, 110],  # brun-ocre terne
}

def patch(catalog_path, dry_run=False):
    p = pathlib.Path(catalog_path)
    if not p.exists():
        print(f"[ERR] Introuvable : {p}"); sys.exit(1)
    with open(p, encoding="utf-8") as f:
        catalog = json.load(f)

    updated, skipped, not_found = [], [], []
    for mat, new_color in UPDATES.items():
        if mat not in catalog:
            not_found.append(mat); continue
        old = catalog[mat].get("avg_color")
        if old == new_color:
            skipped.append(mat); continue
        if not dry_run:
            catalog[mat]["avg_color"] = new_color
        updated.append((mat, old, new_color))

    print(f"\n{'[DRY-RUN] ' if dry_run else ''}Patch CropField v2 (×0.55)")
    print("=" * 55)
    print(f"  Mis à jour  : {len(updated)}")
    print(f"  Inchangés   : {len(skipped)}")
    print(f"  Non trouvés : {len(not_found)}")
    if updated:
        print("\n  Changements :")
        for name, old, new in updated:
            print(f"    {name:<25} {str(old):>20} → {new}")
    if not_found:
        print(f"\n  ⚠ Absents : {not_found}")
    if dry_run:
        print("\n  Dry-run — aucune écriture."); return

    backup = p.with_suffix(f".bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    shutil.copy(p, backup)
    print(f"\n  Backup : {backup.name}")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
    print(f"  ✓ catalog.json mis à jour.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage : python patch_catalog_cropfield_v2.py catalog.json [--dry-run]")
        sys.exit(1)
    patch(sys.argv[1], dry_run="--dry-run" in sys.argv)
