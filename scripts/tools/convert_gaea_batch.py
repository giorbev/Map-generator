"""
Conversion batch Gaea float32 → Reforger uint16

Usage:
    python convert_gaea_batch.py <dossier_source>

Convertit tous les PNG float32 d'un dossier en PNG uint16 compatibles Reforger.
"""

import sys
from pathlib import Path
import cv2
import numpy as np


def convert_float32_to_uint16_safe(input_path, output_path=None):
    """Convertit une image float32 en uint16 PNG normalisé."""
    input_path = Path(input_path)
    if not input_path.exists():
        raise ValueError(f"Fichier introuvable: {input_path}")

    # Lecture
    img = cv2.imread(str(input_path), cv2.IMREAD_UNCHANGED)
    if img is None:
        print(f"❌ Impossible de lire: {input_path.name}")
        return False

    # Vérifier dtype
    if img.dtype != np.float32:
        print(f"⏭️  Déjà converti ou format non-float32: {input_path.name} ({img.dtype})")
        return False

    # Conversion RGB/RGBA → niveaux de gris
    if img.ndim == 3:
        if img.shape[2] == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        elif img.shape[2] == 4:
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)

    # Normalisation float32 → uint16 (0..1 → 0..65535)
    img_min = np.min(img)
    img_max = np.max(img)

    if img_max > img_min:
        img_normalized = (img - img_min) / (img_max - img_min)
    else:
        img_normalized = np.zeros_like(img)

    img_uint16 = np.clip(np.round(img_normalized * 65535.0), 0, 65535).astype(np.uint16)

    # Génération du chemin de sortie
    if output_path is None:
        output_path = input_path.parent / f"{input_path.stem}_uint16.png"
    else:
        output_path = Path(output_path)

    # Sauvegarde
    ok = cv2.imwrite(str(output_path), img_uint16)
    if not ok:
        print(f"❌ Impossible d'écrire: {output_path}")
        return False

    print(f"✅ {input_path.name} → {output_path.name} (plage: [{img_min:.6f}, {img_max:.6f}] → [0, 65535])")
    return True


def convert_folder(source_dir):
    """Convertit tous les PNG float32 d'un dossier."""
    source_dir = Path(source_dir)
    if not source_dir.exists():
        print(f"❌ Dossier introuvable: {source_dir}")
        return

    png_files = sorted(source_dir.glob("*.png"))
    if not png_files:
        print(f"⚠️  Aucun fichier PNG trouvé dans: {source_dir}")
        return

    print(f"📂 Dossier source: {source_dir}")
    print(f"📋 {len(png_files)} fichier(s) PNG détecté(s)\n")

    converted = 0
    skipped = 0
    errors = 0

    for png_file in png_files:
        try:
            result = convert_float32_to_uint16_safe(png_file)
            if result:
                converted += 1
            else:
                skipped += 1
        except Exception as exc:
            print(f"❌ Erreur sur {png_file.name}: {exc}")
            errors += 1

    print(f"\n{'='*60}")
    print(f"✅ Convertis: {converted}")
    print(f"⏭️  Ignorés: {skipped}")
    if errors > 0:
        print(f"❌ Erreurs: {errors}")
    print(f"{'='*60}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python convert_gaea_batch.py <dossier_source>")
        print("\nExemple:")
        print('  python convert_gaea_batch.py "H:/exports_gaea/zimnitrita"')
        sys.exit(1)

    source_dir = sys.argv[1]
    convert_folder(source_dir)
