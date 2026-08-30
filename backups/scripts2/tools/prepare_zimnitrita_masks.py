"""
Preparation automatique des masques Zimnitrita :
- Verification format (uint16 requis)
- Conversion float32 -> uint16 si necessaire
- Renommage selon logique geologique

Usage:
    python prepare_zimnitrita_masks.py
"""

import sys
import io
from pathlib import Path
import cv2
import numpy as np
import shutil
from datetime import datetime

# Fix encodage Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


# Configuration
SOURCE_DIR = Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\generated\new2\assembled_exports")
BACKUP_DIR = SOURCE_DIR / f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
OUTPUT_DIR = SOURCE_DIR / "corrected"

# Mapping de renommage : ancien nom → nouveau nom
TERRAIN_MAPPING = {
    "01_seabed_noconflict.png": "10_seabed.png",
    "02_coast_uint16_bw.png": "20_coast.png",
    "03_deposit_uint16_bw_01.png": "30_deposit.png",
    "04_flowv2_uint16_bw.png": "40_flow.png",
    "02b_rock_final_exclu_b.png": "50_rock.png",
}

# Préfixe pour végétation (pas de numéros, juste préfixe veg_)
VEGETATION_PREFIX = "veg_"

# Patterns pour identifier la végétation
VEG_KEYWORDS = [
    "prairie", "grass", "foret", "forest", "alpages", "montain",
    "landes", "maquis", "clearing", "coniferous", "deciduous",
    "coniferes", "feuillue", "pins", "rocheuses"
]


def is_vegetation_mask(filename):
    """Détermine si un masque est un masque de végétation."""
    name_lower = filename.lower()
    # Déjà numéroté 05-06 ou contient un mot-clé végétation
    if any(name_lower.startswith(f"0{i}_") for i in range(5, 10)):
        return True
    return any(keyword in name_lower for keyword in VEG_KEYWORDS)


def check_and_convert_format(img_path):
    """Vérifie le format et convertit si nécessaire.

    Returns:
        tuple: (image_uint16, was_converted, original_dtype)
    """
    img = cv2.imread(str(img_path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"Impossible de lire: {img_path}")

    original_dtype = img.dtype
    was_converted = False

    # Conversion RGB/RGBA → niveaux de gris
    if img.ndim == 3:
        if img.shape[2] == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            was_converted = True
        elif img.shape[2] == 4:
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
            was_converted = True

    # Vérifier et convertir dtype
    if img.dtype == np.float32:
        # Normalisation float32 → uint16
        img_min = np.min(img)
        img_max = np.max(img)

        if img_max > img_min:
            img_normalized = (img - img_min) / (img_max - img_min)
        else:
            img_normalized = np.zeros_like(img)

        img = np.clip(np.round(img_normalized * 65535.0), 0, 65535).astype(np.uint16)
        was_converted = True
        print(f"    ⚠️  Converti float32 → uint16 (plage: [{img_min:.6f}, {img_max:.6f}])")

    elif img.dtype == np.uint8:
        # uint8 → uint16
        img = (img.astype(np.uint16) * 257)
        was_converted = True
        print(f"    ⚠️  Converti uint8 → uint16")

    elif img.dtype == np.uint16:
        print(f"    ✅ Déjà uint16")

    else:
        raise ValueError(f"Format non supporté: {img.dtype}")

    return img, was_converted, original_dtype


def clean_vegetation_name(filename):
    """Nettoie le nom d'un masque de végétation."""
    # Supprimer les préfixes existants
    name = filename.replace("assembled_exclusion_", "")
    name = name.replace("mask exclu modif4k_", "")
    name = name.replace("mask_", "")

    # Supprimer numérotation 05_, 06_, etc.
    import re
    name = re.sub(r'^0\d+_', '', name)

    # Remplacer espaces et caractères spéciaux
    name = name.replace(" ", "_")
    name = name.replace("Ã¹", "m")  # Fix encoding

    return name


def process_masks():
    """Traite tous les masques : vérification + conversion + renommage."""

    if not SOURCE_DIR.exists():
        print(f"❌ Dossier source introuvable: {SOURCE_DIR}")
        return

    # Créer dossiers
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("🔧 PRÉPARATION MASQUES ZIMNITRITA")
    print("=" * 70)
    print(f"📂 Source: {SOURCE_DIR}")
    print(f"💾 Backup: {BACKUP_DIR}")
    print(f"📁 Sortie: {OUTPUT_DIR}")
    print("=" * 70)
    print()

    # Lister tous les PNG
    all_pngs = sorted(SOURCE_DIR.glob("*.png"))

    if not all_pngs:
        print("⚠️  Aucun fichier PNG trouvé")
        return

    print(f"📋 {len(all_pngs)} fichier(s) PNG détecté(s)\n")

    terrain_count = 0
    vegetation_count = 0
    converted_count = 0
    errors = []

    # Traiter chaque masque
    for png_file in all_pngs:
        filename = png_file.name
        print(f"📄 {filename}")

        try:
            # 1. Backup original
            backup_path = BACKUP_DIR / filename
            shutil.copy2(png_file, backup_path)

            # 2. Vérifier et convertir format
            img_uint16, was_converted, original_dtype = check_and_convert_format(png_file)
            if was_converted:
                converted_count += 1

            # 3. Déterminer nouveau nom
            if filename in TERRAIN_MAPPING:
                # Masque terrain → mapping direct
                new_name = TERRAIN_MAPPING[filename]
                terrain_count += 1
                category = "TERRAIN"
            elif is_vegetation_mask(filename):
                # Masque végétation → préfixe veg_
                clean_name = clean_vegetation_name(filename)
                new_name = f"{VEGETATION_PREFIX}{clean_name}"
                vegetation_count += 1
                category = "VÉGÉTATION"
            else:
                # Fichier non reconnu → garder nom original avec préfixe unknown_
                new_name = f"unknown_{filename}"
                category = "INCONNU"
                print(f"    ⚠️  Type inconnu, préfixe 'unknown_' ajouté")

            # 4. Sauvegarder avec nouveau nom
            output_path = OUTPUT_DIR / new_name
            ok = cv2.imwrite(str(output_path), img_uint16)

            if ok:
                print(f"    ✅ [{category}] → {new_name}")
            else:
                raise ValueError("Échec écriture")

        except Exception as exc:
            error_msg = f"{filename}: {exc}"
            errors.append(error_msg)
            print(f"    ❌ ERREUR: {exc}")

        print()

    # Rapport final
    print("=" * 70)
    print("📊 RAPPORT FINAL")
    print("=" * 70)
    print(f"✅ Masques TERRAIN traités: {terrain_count}")
    print(f"✅ Masques VÉGÉTATION traités: {vegetation_count}")
    print(f"🔄 Conversions format: {converted_count}")

    if errors:
        print(f"❌ Erreurs: {len(errors)}")
        for err in errors:
            print(f"   - {err}")
    else:
        print("✅ Aucune erreur")

    print()
    print("📁 Fichiers corrigés dans:")
    print(f"   {OUTPUT_DIR}")
    print()
    print("💾 Originaux sauvegardés dans:")
    print(f"   {BACKUP_DIR}")
    print("=" * 70)

    # Lister l'ordre final des masques terrain
    print()
    print("🔢 ORDRE DE PRIORITÉ TERRAIN (décroissant = haute priorité d'abord):")
    print("-" * 70)
    terrain_files = sorted([f for f in OUTPUT_DIR.glob("*.png") if not f.name.startswith("veg_")],
                          reverse=True)
    for i, f in enumerate(terrain_files, 1):
        print(f"   {i}. {f.name}")
    print("=" * 70)


if __name__ == "__main__":
    try:
        process_masks()
    except KeyboardInterrupt:
        print("\n⚠️  Interruption utilisateur")
    except Exception as exc:
        print(f"\n❌ Erreur fatale: {exc}")
        import traceback
        traceback.print_exc()
