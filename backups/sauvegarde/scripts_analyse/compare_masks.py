#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Compare masque manuel vs masque généré P58
"""

import numpy as np
import cv2
from pathlib import Path

# Chemins
MANUAL = Path("data/projects/Zimnitrita/sources/reforger/export curv.png")
P58 = Path("data/projects/Zimnitrita/debug/curvature_deep_P58.png")
OUTPUT = Path("data/projects/Zimnitrita/debug/comparison_manual_vs_P58.png")

print("=" * 80)
print("COMPARAISON MASQUE MANUEL vs P58")
print("=" * 80)

# Charger masques
print(f"\n[1/3] Chargement masques...")
manual = cv2.imread(str(MANUAL), cv2.IMREAD_GRAYSCALE)
p58 = cv2.imread(str(P58), cv2.IMREAD_GRAYSCALE)

print(f"  Manuel : {manual.shape}")
print(f"  P58    : {p58.shape}")

# Downsampler pour accélérer (travail sur 4097x4097 au lieu de 16257x16257)
TARGET_SIZE = 2048  # Résolution de travail
if manual.shape[0] > TARGET_SIZE:
    print(f"  Downsample manuel vers {TARGET_SIZE}x{TARGET_SIZE}...")
    manual = cv2.resize(manual, (TARGET_SIZE, TARGET_SIZE), interpolation=cv2.INTER_AREA)

if p58.shape[0] > TARGET_SIZE:
    print(f"  Downsample P58 vers {TARGET_SIZE}x{TARGET_SIZE}...")
    p58 = cv2.resize(p58, (TARGET_SIZE, TARGET_SIZE), interpolation=cv2.INTER_AREA)

# Redimensionner si encore différents
if manual.shape != p58.shape:
    print(f"  Resize manuel vers {p58.shape}...")
    manual = cv2.resize(manual, (p58.shape[1], p58.shape[0]), interpolation=cv2.INTER_NEAREST)

# Binariser (>128 = peint/concave)
manual_bin = (manual > 128).astype(np.uint8)
p58_bin = (p58 > 128).astype(np.uint8)

# Stats
n_total = manual_bin.size
n_manual = int(np.sum(manual_bin))
n_p58 = int(np.sum(p58_bin))
n_both = int(np.sum(manual_bin & p58_bin))
n_only_manual = int(np.sum(manual_bin & ~p58_bin))
n_only_p58 = int(np.sum(~manual_bin & p58_bin))
n_neither = int(np.sum(~manual_bin & ~p58_bin))

print(f"\n[2/3] Statistiques...")
print(f"  Pixels totaux        : {n_total:,}")
print(f"  Manuel seul          : {n_manual:,} ({n_manual/n_total*100:.2f}%)")
print(f"  P58 seul             : {n_p58:,} ({n_p58/n_total*100:.2f}%)")
print(f"  Correspondance (AND) : {n_both:,} ({n_both/n_total*100:.2f}%)")
print(f"  Seulement manuel     : {n_only_manual:,} ({n_only_manual/n_total*100:.2f}%) <- MANQUE P58")
print(f"  Seulement P58        : {n_only_p58:,} ({n_only_p58/n_total*100:.2f}%) <- TROP PERMISSIF")
print(f"  Aucun des deux       : {n_neither:,} ({n_neither/n_total*100:.2f}%)")

# Métriques
if n_manual > 0:
    recall = n_both / n_manual * 100  # % du manuel capturé par P58
else:
    recall = 0

if n_p58 > 0:
    precision = n_both / n_p58 * 100  # % de P58 qui est dans le manuel
else:
    precision = 0

if (precision + recall) > 0:
    f1 = 2 * (precision * recall) / (precision + recall)
else:
    f1 = 0

print(f"\n  RECALL    (couverture manuel) : {recall:.1f}%")
print(f"  PRECISION (justesse P58)      : {precision:.1f}%")
print(f"  F1-SCORE  (equilibre)         : {f1:.1f}%")

# Image de comparaison RGB
print(f"\n[3/3] Generation image comparaison...")
comparison = np.zeros((p58.shape[0], p58.shape[1], 3), dtype=np.uint8)

# Blanc = correspondance (les deux)
comparison[manual_bin & p58_bin] = [255, 255, 255]

# Vert = seulement manuel (P58 manque ces zones)
comparison[manual_bin & ~p58_bin] = [0, 255, 0]

# Rouge = seulement P58 (trop permissif)
comparison[~manual_bin & p58_bin] = [255, 0, 0]

# Noir = aucun des deux
comparison[~manual_bin & ~p58_bin] = [0, 0, 0]

# Sauvegarder
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
cv2.imwrite(str(OUTPUT), comparison)

print(f"  Sauvegarde : {OUTPUT}")

print("\n" + "=" * 80)
print("LEGENDE")
print("=" * 80)
print("""
  BLANC = Correspondance (manuel ET P58) - PARFAIT
  VERT  = Seulement manuel (P58 manque) - AUGMENTER percentile
  ROUGE = Seulement P58 (trop permissif) - DIMINUER percentile
  NOIR  = Aucun des deux
""")

print("=" * 80)
print("RECOMMANDATION")
print("=" * 80)

if recall < 80:
    print(f"\nRECALL faible ({recall:.1f}%) : P58 manque {100-recall:.1f}% de vos zones")
    print("  --> AUGMENTER percentile (P60, P65, P70)")
elif precision < 50:
    print(f"\nPRECISION faible ({precision:.1f}%) : P58 capture trop de faux positifs")
    print("  --> DIMINUER percentile (P50, P45, P40)")
elif f1 > 70:
    print(f"\nF1-SCORE excellent ({f1:.1f}%) : P58 est bien calibre !")
    print("  --> GARDER P58")
else:
    print(f"\nF1-SCORE moyen ({f1:.1f}%) : Ajustement possible")
    print(f"  Recall {recall:.1f}% / Precision {precision:.1f}%")
    if recall < precision:
        print("  --> Legere augmentation (P60) pour capturer plus de zones manuelles")
    else:
        print("  --> Legere diminution (P55) pour reduire faux positifs")

print(f"\nImage sauvegardee : {OUTPUT}")
