"""
patch_catalog_cropfield_rock.py
Corrige les avg_color des CropField ZI et Rock_02 dans catalog.json.
Valeurs issues des .emat (Color field) × 0.75 pour simuler le rendu BCR en jeu.

Usage : python patch_catalog_cropfield_rock.py catalog.json [--dry-run]
"""

import json, sys, shutil, pathlib
from datetime import datetime

UPDATES = {
    # Color emat × 0.75 → rendu BCR simulé
    "zi_CropField_01":     [185, 180, 162],  # blé mûr terne
    "zi_CropField_02":     [180, 175, 158],  # blé paille
    "zi_CropField_03":     [158, 180, 164],  # vert olive pâle
    "zi_CropField_04":     [158, 180, 164],  # vert olive pâle
    "zi_CropField_Cut_01": [148, 148, 148],  # champ fauché gris
    "zi_CropField_Cut_02": [186, 160, 138],  # hérite Crop_Field_02 vanilla × 0.75
    "Rock_02":             [178, 174, 166],  # gris chaud (vs Rock_01 vanilla [204,204,204])
}

def patch(catalog_path: str, dry_run: bool = False):
    p = pathlib.Path(catalog_path)
    if not p.exists():
        print(f"[ERR] Fichier introuvable : {p}")
        sys.exit(1)

    with open(p, encoding="utf-8") as f:
        catalog = json.load(f)

    updated, skipped, not_found = [], [], []

    for mat, new_color in UPDATES.items():
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

    print(f"\n{'[DRY-RUN] ' if dry_run else ''}Patch CropField + Rock_02")
    print("=" * 55)
    print(f"  Mis à jour  : {len(updated)}")
    print(f"  Inchangés   : {len(skipped)}")
    print(f"  Non trouvés : {len(not_found)}")

    if updated:
        print("\n  Changements :")
        for name, old, new in updated:
            print(f"    {name:<25} {str(old):>20} → {new}")

    if not_found:
        print(f"\n  ⚠ Absents du catalog : {not_found}")

    if dry_run:
        print("\n  Mode dry-run — aucune écriture.")
        return

    backup = p.with_suffix(f".bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    shutil.copy(p, backup)
    print(f"\n  Backup : {backup.name}")

    with open(p, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
    print(f"  ✓ catalog.json mis à jour.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage : python patch_catalog_cropfield_rock.py catalog.json [--dry-run]")
        sys.exit(1)
    patch(sys.argv[1], dry_run="--dry-run" in sys.argv)
