"""
Numérotation automatique des masques de végétation.

Hiérarchie végétation (priorité décroissante 09→01) :
- 09 : Forêts denses (pins, conifères)
- 08 : Forêts mixtes (clearing)
- 07 : Forêts feuillues
- 06 : Landes rocheuses
- 05 : Maquis/landes
- 04 : Alpages (montagne)
- 03 : Prairies plateau
- 02 : Prairies humides
- 01 : Prairies sèches

Usage:
    python number_vegetation_masks.py
"""

import sys
import io
from pathlib import Path
import shutil
from datetime import datetime

# Fix encodage Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Configuration
SOURCE_DIR = Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\generated\new2\assembled_exports\corrected")
BACKUP_DIR = SOURCE_DIR / f"backup_veg_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

# Mapping végétation → numéro de priorité
# Plus le numéro est élevé, plus la végétation est dominante/dense
VEG_PRIORITY = {
    # Forêts denses (haute priorité végétation)
    "foret_pins": 9,
    "foret_coniferes": 9,

    # Forêts clearing (mixtes)
    "foret_clearing_coniferous": 8,
    "foret_clearing_deciduous": 8,

    # Forêts feuillues
    "foret_feuillue": 7,

    # Landes rocheuses
    "landes_rocheuses": 6,

    # Maquis/landes
    "maquis_landes": 5,

    # Alpages (montagne)
    "alpages": 4,

    # Prairies plateau
    "prairie_plateau": 3,

    # Prairies humides
    "prairie_humide": 2,

    # Prairies sèches (basse priorité)
    "prairie_seche": 1,
}


def get_vegetation_priority(filename):
    """Détermine le numéro de priorité d'un masque de végétation.

    Returns:
        int or None: Numéro de priorité ou None si pas trouvé
    """
    filename_lower = filename.lower()

    for keyword, priority in VEG_PRIORITY.items():
        if keyword in filename_lower:
            return priority

    # Fallback : si c'est un masque veg_ non reconnu, mettre en priorité 1
    if filename_lower.startswith("veg_"):
        return 1

    return None


def rename_vegetation_masks():
    """Renomme les masques de végétation avec numérotation."""

    if not SOURCE_DIR.exists():
        print(f"❌ Dossier introuvable: {SOURCE_DIR}")
        return

    # Créer backup
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("🔢 NUMÉROTATION MASQUES VÉGÉTATION")
    print("=" * 70)
    print(f"📂 Dossier: {SOURCE_DIR}")
    print(f"💾 Backup: {BACKUP_DIR}")
    print("=" * 70)
    print()

    # Lister masques végétation
    all_files = sorted(SOURCE_DIR.glob("*.png"))
    veg_files = [f for f in all_files if f.name.startswith("veg_")]

    if not veg_files:
        print("⚠️  Aucun masque végétation trouvé (veg_*.png)")
        return

    print(f"📋 {len(veg_files)} masque(s) végétation détecté(s)\n")

    renamed_count = 0
    errors = []

    for veg_file in veg_files:
        filename = veg_file.name

        try:
            # Backup
            shutil.copy2(veg_file, BACKUP_DIR / filename)

            # Déterminer priorité
            priority = get_vegetation_priority(filename)

            if priority is None:
                print(f"⚠️  {filename:50s} Type non reconnu, ignoré")
                continue

            # Enlever le préfixe veg_ pour reconstruire le nom
            name_without_prefix = filename.replace("veg_", "")

            # Nouveau nom avec numéro
            new_name = f"{priority:02d}_{name_without_prefix}"
            new_path = SOURCE_DIR / new_name

            # Renommer
            veg_file.rename(new_path)

            print(f"✅ {filename:50s} → {new_name}")
            renamed_count += 1

        except Exception as exc:
            error_msg = f"{filename}: {exc}"
            errors.append(error_msg)
            print(f"❌ {filename:50s} ERREUR: {exc}")

    print()
    print("=" * 70)
    print("📊 RAPPORT FINAL")
    print("=" * 70)
    print(f"✅ Masques renommés: {renamed_count}")

    if errors:
        print(f"❌ Erreurs: {len(errors)}")
        for err in errors:
            print(f"   - {err}")
    else:
        print("✅ Aucune erreur")

    print()
    print("💾 Originaux sauvegardés dans:")
    print(f"   {BACKUP_DIR}")
    print("=" * 70)

    # Afficher ordre final de TOUS les masques
    print()
    print("🔢 ORDRE DE PRIORITÉ COMPLET (décroissant = haute priorité d'abord):")
    print("-" * 70)
    all_masks_after = sorted(SOURCE_DIR.glob("*.png"), reverse=True)
    for i, f in enumerate(all_masks_after, 1):
        # Extraire numéro si présent
        import re
        match = re.search(r'^(\d+)_', f.name)
        if match:
            num = match.group(1)
            category = "TERRAIN" if int(num) >= 10 else "VÉGÉTATION"
            print(f"   {i:2d}. [{category:10s}] {f.name}")
        else:
            print(f"   {i:2d}. [NON-NUMÉROTÉ] {f.name}")
    print("=" * 70)


if __name__ == "__main__":
    try:
        rename_vegetation_masks()
    except KeyboardInterrupt:
        print("\n⚠️  Interruption utilisateur")
    except Exception as exc:
        print(f"\n❌ Erreur fatale: {exc}")
        import traceback
        traceback.print_exc()
