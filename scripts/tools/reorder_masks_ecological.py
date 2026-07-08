"""
Renumérotation écologique des masques selon logique visuelle.

Ordre de priorité (décroissant = haute priorité d'abord) :
70 : Coast (délimite terre/mer)
60 : Rock (éléments rocheux dominants)
50 : Flow (érosion)
40 : Deposit (sédiments)
30 : Landes rocheuses (végétation exposée/pente)
20 : Prairies (herbes, zones ouvertes)
10 : Forêts (végétation dense, zones protégées)
01 : Seabed (mer, pas de conflit normalement)

Usage:
    python reorder_masks_ecological.py
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
BACKUP_DIR = SOURCE_DIR / f"backup_reorder_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

# Mapping nom actuel → nouveau numéro
REORDER_MAP = {
    # TERRAIN
    "coast": 70,
    "rock": 60,
    "flow": 50,
    "deposit": 40,
    "seabed": 1,

    # VÉGÉTATION (ordre écologique)
    "landes_rocheuses": 30,      # Zones exposées/pente
    "alpages": 25,                # Montagne
    "maquis_landes": 24,          # Maquis
    "prairie_plateau": 23,        # Prairies plateau
    "prairie_humide": 22,         # Prairies humides
    "prairie_seche": 21,          # Prairies sèches
    "foret_clearing_coniferous": 15,  # Forêts clairières conifères
    "foret_clearing_deciduous": 14,   # Forêts clairières feuillues
    "foret_pins": 13,             # Forêts pins
    "foret_coniferes": 12,        # Forêts conifères
    "foret_feuillue": 11,         # Forêts feuillues
}


def detect_mask_type(filename):
    """Détecte le type de masque et retourne le nouveau numéro.

    Returns:
        tuple: (new_number, keyword) ou (None, None)
    """
    filename_lower = filename.lower()

    for keyword, number in REORDER_MAP.items():
        if keyword in filename_lower:
            return number, keyword

    return None, None


def reorder_all_masks():
    """Renumérote tous les masques selon l'ordre écologique."""

    if not SOURCE_DIR.exists():
        print(f"❌ Dossier introuvable: {SOURCE_DIR}")
        return

    # Créer backup
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("🌿 RENUMÉROTATION ÉCOLOGIQUE DES MASQUES")
    print("=" * 70)
    print(f"📂 Dossier: {SOURCE_DIR}")
    print(f"💾 Backup: {BACKUP_DIR}")
    print()
    print("Ordre écologique (décroissant = haute priorité) :")
    print("  70 : Coast (contours terre/mer)")
    print("  60 : Rock (éléments rocheux)")
    print("  50 : Flow (érosion)")
    print("  40 : Deposit (sédiments)")
    print("  30 : Landes rocheuses (végétation exposée)")
    print("  20 : Prairies (herbes)")
    print("  10 : Forêts (végétation dense)")
    print("  01 : Seabed (mer)")
    print("=" * 70)
    print()

    all_files = sorted(SOURCE_DIR.glob("*.png"))

    if not all_files:
        print("⚠️  Aucun fichier PNG trouvé")
        return

    print(f"📋 {len(all_files)} fichier(s) PNG détecté(s)\n")

    renamed_count = 0
    skipped_count = 0
    errors = []

    for png_file in all_files:
        filename = png_file.name

        try:
            # Backup
            shutil.copy2(png_file, BACKUP_DIR / filename)

            # Détecter type et nouveau numéro
            new_number, keyword = detect_mask_type(filename)

            if new_number is None:
                print(f"⚠️  {filename:50s} Type non reconnu, ignoré")
                skipped_count += 1
                continue

            # Enlever ancien numéro si présent
            import re
            name_without_number = re.sub(r'^\d+_', '', filename)

            # Nouveau nom
            new_name = f"{new_number:02d}_{name_without_number}"
            new_path = SOURCE_DIR / new_name

            # Si le nom est déjà correct, skip
            if new_name == filename:
                print(f"✅ {filename:50s} (déjà OK)")
                skipped_count += 1
                continue

            # Renommer
            png_file.rename(new_path)

            print(f"🔄 {filename:50s} → {new_name}")
            renamed_count += 1

        except Exception as exc:
            error_msg = f"{filename}: {exc}"
            errors.append(error_msg)
            print(f"❌ {filename:50s} ERREUR: {exc}")

    print()
    print("=" * 70)
    print("📊 RAPPORT FINAL")
    print("=" * 70)
    print(f"🔄 Masques renommés: {renamed_count}")
    print(f"✅ Masques déjà OK: {skipped_count}")

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

    # Afficher ordre final
    print()
    print("🔢 ORDRE DE PRIORITÉ FINAL (décroissant):")
    print("-" * 70)
    all_masks_after = sorted(SOURCE_DIR.glob("*.png"), reverse=True)
    for i, f in enumerate(all_masks_after, 1):
        import re
        match = re.search(r'^(\d+)_', f.name)
        if match:
            num = int(match.group(1))
            if num >= 40:
                category = "TERRAIN"
            elif num >= 20:
                category = "PRAIRIE/LANDES"
            elif num >= 10:
                category = "FORÊT"
            else:
                category = "MER"
            print(f"   {i:2d}. [{num:02d}] [{category:15s}] {f.name}")
        else:
            print(f"   {i:2d}. [NON-NUMÉROTÉ] {f.name}")
    print("=" * 70)


if __name__ == "__main__":
    try:
        reorder_all_masks()
    except KeyboardInterrupt:
        print("\n⚠️  Interruption utilisateur")
    except Exception as exc:
        print(f"\n❌ Erreur fatale: {exc}")
        import traceback
        traceback.print_exc()
