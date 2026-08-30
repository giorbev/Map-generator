"""
Redimensionne tous les masques vers une taille uniforme.

Usage:
    python resize_masks_uniform.py
"""

import sys
import io
from pathlib import Path
import cv2
import numpy as np

# Fix encodage Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Configuration
SOURCE_DIR = Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\generated\new2\assembled_exports\corrected")
TARGET_SIZE = (4097, 4097)  # (largeur, hauteur) - taille cible

def resize_to_target(img_path, target_size):
    """Redimensionne une image vers la taille cible.

    Args:
        img_path: Chemin de l'image
        target_size: (width, height) tuple

    Returns:
        tuple: (resized_image, was_resized)
    """
    img = cv2.imread(str(img_path), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"Impossible de lire: {img_path}")

    current_size = (img.shape[1], img.shape[0])  # (width, height)

    if current_size == target_size:
        return img, False

    # Redimensionner avec interpolation LANCZOS (meilleure qualité)
    resized = cv2.resize(img, target_size, interpolation=cv2.INTER_LANCZOS4)

    return resized, True


def process_all_masks():
    """Redimensionne tous les masques vers la taille cible."""

    if not SOURCE_DIR.exists():
        print(f"❌ Dossier introuvable: {SOURCE_DIR}")
        return

    print("=" * 70)
    print("📏 UNIFORMISATION DIMENSIONS MASQUES")
    print("=" * 70)
    print(f"📂 Dossier: {SOURCE_DIR}")
    print(f"🎯 Taille cible: {TARGET_SIZE[0]}x{TARGET_SIZE[1]}")
    print("=" * 70)
    print()

    all_pngs = sorted(SOURCE_DIR.glob("*.png"))

    if not all_pngs:
        print("⚠️  Aucun fichier PNG trouvé")
        return

    print(f"📋 {len(all_pngs)} fichier(s) PNG détecté(s)\n")

    resized_count = 0
    skipped_count = 0
    errors = []

    for png_file in all_pngs:
        filename = png_file.name

        try:
            # Lire et vérifier dimension actuelle
            img = cv2.imread(str(png_file), cv2.IMREAD_UNCHANGED)
            if img is None:
                raise ValueError("Lecture impossible")

            current_size = (img.shape[1], img.shape[0])

            if current_size == TARGET_SIZE:
                print(f"✅ {filename:50s} {current_size[0]}x{current_size[1]} (OK)")
                skipped_count += 1
            else:
                # Redimensionner
                resized, _ = resize_to_target(png_file, TARGET_SIZE)

                # Écraser le fichier original
                ok = cv2.imwrite(str(png_file), resized)
                if not ok:
                    raise ValueError("Écriture impossible")

                print(f"🔄 {filename:50s} {current_size[0]}x{current_size[1]} → {TARGET_SIZE[0]}x{TARGET_SIZE[1]}")
                resized_count += 1

        except Exception as exc:
            error_msg = f"{filename}: {exc}"
            errors.append(error_msg)
            print(f"❌ {filename:50s} ERREUR: {exc}")

    print()
    print("=" * 70)
    print("📊 RAPPORT FINAL")
    print("=" * 70)
    print(f"✅ Masques déjà conformes: {skipped_count}")
    print(f"🔄 Masques redimensionnés: {resized_count}")

    if errors:
        print(f"❌ Erreurs: {len(errors)}")
        for err in errors:
            print(f"   - {err}")
    else:
        print("✅ Aucune erreur")

    print("=" * 70)
    print()
    print("✅ Tous les masques ont maintenant la même dimension!")
    print(f"   → {TARGET_SIZE[0]}x{TARGET_SIZE[1]} pixels")
    print()


if __name__ == "__main__":
    try:
        process_all_masks()
    except KeyboardInterrupt:
        print("\n⚠️  Interruption utilisateur")
    except Exception as exc:
        print(f"\n❌ Erreur fatale: {exc}")
        import traceback
        traceback.print_exc()
