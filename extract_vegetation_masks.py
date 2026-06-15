#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Extrait 7 masks PNG depuis vegetation_map.png coloré
=====================================================

Usage:
    python extract_vegetation_masks.py <vegetation_map.png> <output_dir>

Exemple:
    python extract_vegetation_masks.py \
        data/projects/Zimnitrita/generated/vegetation_20260615_161514/vegetation_map.png \
        data/projects/Zimnitrita/vegetation_masks
"""

import numpy as np
import cv2
from pathlib import Path
import sys

# Couleurs de référence des 7 zones (RGB 0-1)
ZONE_COLORS = {
    "eau": np.array([0.20, 0.40, 0.70]),               # Bleu
    "plateau_herbeux": np.array([0.55, 0.67, 0.43]),   # Vert olive
    "prairie_seche": np.array([0.71, 0.77, 0.35]),     # Jaune-vert
    "foret_mixte": np.array([0.26, 0.47, 0.21]),       # Vert foncé
    "foret_coniferes": np.array([0.14, 0.34, 0.12]),   # Vert très foncé
    "veg_rupestre": np.array([0.54, 0.61, 0.55]),      # Vert-gris
    "non_attribue": np.array([0.78, 0.76, 0.72]),      # Beige-gris
}

def extract_vegetation_masks(vegetation_png, output_dir, tolerance=0.3):
    """
    Extrait 7 masks PNG depuis une carte végétation colorée.

    Args:
        vegetation_png: Chemin vers vegetation_map.png
        output_dir: Dossier de sortie pour les 7 PNG
        tolerance: Tolérance de couleur (0.3 = 30% de distance max)
    """
    print("="*80)
    print("EXTRACTION MASKS VÉGÉTATION")
    print("="*80)
    print(f"Source : {vegetation_png}")
    print(f"Output : {output_dir}\n")

    # Charger image
    img = cv2.imread(str(vegetation_png), cv2.IMREAD_COLOR)
    if img is None:
        print(f"[ERREUR] ERREUR : Impossible de lire {vegetation_png}")
        return False

    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img_f = img.astype(np.float32) / 255.0

    print(f"Image : {img.shape[1]}x{img.shape[0]} pixels\n")

    # Créer dossier sortie
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Extraire chaque zone
    for zone_name, ref_color in ZONE_COLORS.items():
        print(f"Extraction : {zone_name:20s} ", end="")

        # Distance euclidienne par pixel
        diff = np.linalg.norm(img_f - ref_color, axis=2)

        # Score de proximité normalisé (0-1)
        score = np.clip(1.0 - diff / tolerance, 0.0, 1.0)

        # Convertir en uint16 (0-65535)
        mask_uint16 = (score * 65535).astype(np.uint16)

        # Sauvegarder PNG 16-bit
        output_file = output_path / f"{zone_name}.png"
        cv2.imwrite(str(output_file), mask_uint16)

        # Stats
        coverage = np.mean(score > 0.3) * 100
        max_val = np.max(mask_uint16)

        print(f"-> {coverage:5.2f}% couvert (max: {max_val:5d})")

    print("\n" + "="*80)
    print(f"[OK] 7 masks PNG créés dans : {output_dir}")
    print("="*80)
    print("\n🎯 Prochaine étape :")
    print("   1. Vérifier les masks générés")
    print("   2. Onglet Génération → MODE 2")
    print(f"   3. Source végétation : {output_dir}")
    print("   4. Générer masks → 15 masks enrichis !\n")

    return True


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        print("\n[ERREUR] ERREUR : Arguments manquants")
        print("\nUsage:")
        print("    python extract_vegetation_masks.py <vegetation_map.png> <output_dir>")
        sys.exit(1)

    vegetation_png = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])

    if not vegetation_png.exists():
        print(f"[ERREUR] ERREUR : Fichier inexistant : {vegetation_png}")
        sys.exit(1)

    success = extract_vegetation_masks(vegetation_png, output_dir)
    sys.exit(0 if success else 1)
