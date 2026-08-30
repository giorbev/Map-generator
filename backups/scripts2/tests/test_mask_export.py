#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test rapide du module reforger_mask_export — Phase 2 & 3"""

import sys
from pathlib import Path

if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, errors="replace")

print("=" * 80)
print("TEST : Import module reforger_mask_export")
print("=" * 80)

try:
    import reforger_mask_export as mask_export
    print("✅ Module importé avec succès")
except ImportError as e:
    print(f"❌ Erreur import : {e}")
    sys.exit(1)

print("\n" + "=" * 80)
print("TEST : Décodeurs QTRE variantes poids complets")
print("=" * 80)

# Test décodeur 2-mat (fallback sans données)
print("\n1. decode_qtre_2mat_weights (fallback)")
result = mask_export.decode_qtre_block_weights([0, 1], None, (128, 128))
print(f"   ✅ {len(result)} matériaux, shapes: {[v.shape for v in result.values()]}")

# Test décodeur mono-mat
print("\n2. decode_qtre_block_weights mono-mat")
result = mask_export.decode_qtre_block_weights([5], None, (128, 128))
print(f"   ✅ {len(result)} matériau, shape: {result[5].shape}, sum: {result[5].sum():.1f}")

print("\n" + "=" * 80)
print("✅ TESTS BASIQUES PASSÉS")
print("=" * 80)
print("\nPour tester l'export complet, utilisez l'interface Streamlit :")
print("  1. Ouvrez l'onglet '🛰️ Satmap Export'")
print("  2. Section 4 : Export masques")
print("  3. Fournissez le dossier de votre monde Reforger")
print("  4. Cliquez sur 'Exporter'")
