"""
Analyse masque Rock Zimnitrita
- Coverage %
- Distribution pixels
- Diagnostic erreur Workbench
"""
import numpy as np
from PIL import Image
from pathlib import Path

mask_path = Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\generated\terrain_masks\10_rock_walls.png")

print("="*60)
print("ANALYSE MASQUE ROCK - ZIMNITRITA")
print("="*60)

# Charger masque
img = Image.open(mask_path)
arr = np.array(img, dtype=np.uint16)

print(f"\nRésolution masque : {arr.shape[1]} × {arr.shape[0]} px")
print(f"Dtype : {arr.dtype}")
print(f"Min value : {np.min(arr)}")
print(f"Max value : {np.max(arr)}")

# Seuil activation (16-bit, seuil à 32768)
threshold = 32768
mask_active = arr > threshold

# Coverage
total_pixels = arr.size
active_pixels = np.sum(mask_active)
coverage_pct = (active_pixels / total_pixels) * 100

print(f"\n{'='*60}")
print("COVERAGE")
print(f"{'='*60}")
print(f"Total pixels      : {total_pixels:,}")
print(f"Pixels actifs     : {active_pixels:,}")
print(f"Coverage          : {coverage_pct:.2f}%")

# Diagnostic
print(f"\n{'='*60}")
print("DIAGNOSTIC WORKBENCH")
print(f"{'='*60}")

if coverage_pct > 40:
    print(f"⚠️  COVERAGE TRÈS ÉLEVÉ ({coverage_pct:.1f}%)")
    print(f"   Workbench refuse généralement masques >40% coverage")
    print(f"   -> Rock_min probablement trop bas (trop de pentes classées rock)")
elif coverage_pct > 30:
    print(f"⚠️  COVERAGE ÉLEVÉ ({coverage_pct:.1f}%)")
    print(f"   Limite acceptable mais proche du seuil Workbench (~30-35%)")
elif coverage_pct > 20:
    print(f"✅ COVERAGE MODÉRÉ ({coverage_pct:.1f}%)")
    print(f"   Normal pour terrain montagneux")
else:
    print(f"✅ COVERAGE FAIBLE ({coverage_pct:.1f}%)")
    print(f"   OK")

# Distribution valeurs
unique_vals, counts = np.unique(arr, return_counts=True)
print(f"\n{'='*60}")
print("DISTRIBUTION VALEURS")
print(f"{'='*60}")
print(f"Valeurs uniques : {len(unique_vals)}")
print(f"  - 0 (inactif)  : {counts[0]:,} pixels ({counts[0]/total_pixels*100:.2f}%)")
if len(unique_vals) > 1:
    print(f"  - 65535 (actif): {counts[-1]:,} pixels ({counts[-1]/total_pixels*100:.2f}%)")

# Vérifier intégrité (masque binaire 0 ou 65535 uniquement)
expected_binary = set([0, 65535])
actual_values = set(unique_vals.tolist())

if actual_values == expected_binary:
    print(f"\n✅ Masque binaire valide (0 ou 65535 uniquement)")
else:
    print(f"\n⚠️  Masque contient valeurs intermédiaires : {actual_values - expected_binary}")
    print(f"   Peut causer problèmes import Workbench")

print("\n" + "="*60)
print("RECOMMANDATIONS")
print("="*60)

if coverage_pct > 35:
    print("1. Augmenter rock_min dans calibration (pentes plus strictes)")
    print("   Exemple : rock_min_actuel × 1.2 (ajout +20%)")
    print("2. Ou forcer rock_min = 40° au lieu de Jenks auto")
    print("3. Régénérer masques avec nouveau seuil")
elif coverage_pct > 25:
    print("Coverage acceptable mais proche limite.")
    print("Si erreur Workbench persiste :")
    print("  - Vérifier que masque error rock.png est bien ignoré")
    print("  - Essayer import sans Rock (texture base uniquement)")
else:
    print("Coverage OK. Erreur Workbench probablement autre cause :")
    print("  - Format PNG corrompu ?")
    print("  - Résolution incompatible ?")
    print("  - Vérifier logs Workbench pour message erreur précis")

print("\n" + "="*60)
