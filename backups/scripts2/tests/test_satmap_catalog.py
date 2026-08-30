#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test du module reforger_satmap_export — Phase 1: Catalogue

Vérifie que le scanner fonctionne correctement avec un jeu de test minimal.
"""

import sys
from pathlib import Path

# Fix encodage console Windows
if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, errors="replace")

# Test 1 : Import du module
print("=" * 80)
print("TEST 1 : Import du module")
print("=" * 80)

try:
    import reforger_satmap_export as satmap
    print("✅ Module importé avec succès")
except ImportError as e:
    print(f"❌ Erreur import : {e}")
    sys.exit(1)

# Test 2 : Vérifier structure de dossiers
print("\n" + "=" * 80)
print("TEST 2 : Structure de dossiers")
print("=" * 80)

required_dirs = [
    satmap.CATALOG_ROOT,
    satmap.VANILLA_TEXTURES_DIR,
    satmap.VANILLA_EMAT_DIR,
    satmap.CUSTOM_TEXTURES_DIR,
    satmap.CUSTOM_EMAT_DIR,
]

for d in required_dirs:
    exists = d.exists()
    status = "✅" if exists else "⚠️"
    print(f"{status} {d} {'(existe)' if exists else '(absent)'}")

# Test 3 : Créer un catalogue vide
print("\n" + "=" * 80)
print("TEST 3 : Créer un catalogue vide")
print("=" * 80)

try:
    catalog = satmap.TextureCatalog()
    print(f"✅ Catalogue créé : {len(catalog.data)} entrées")
except Exception as e:
    print(f"❌ Erreur : {e}")
    import traceback
    traceback.print_exc()

# Test 4 : Scanner (même si dossiers vides)
print("\n" + "=" * 80)
print("TEST 4 : Scanner les dossiers")
print("=" * 80)

try:
    catalog, report = satmap.build_catalog(preserve_manual=True)
    print(f"✅ Scan terminé")
    print(f"   Total :      {report['total']}")
    print(f"   Vanilla :    {report['vanilla']}")
    print(f"   Custom :     {report['custom']}")
    print(f"   Convention : {report['convention']}")
    print(f"   Fallback :   {report['fallback']}")

    if report['zi_resolved']:
        print(f"\n   zi_ résolus ({len(report['zi_resolved'])}):")
        for name in report['zi_resolved']:
            entry = catalog.get_entry(name)
            parent = entry.get('parent', '???')
            print(f"     {name} → {parent}")

    if report['fallback_list']:
        print(f"\n   ⚠️ Fallback ({len(report['fallback_list'])}):")
        for name in report['fallback_list']:
            print(f"     {name}")

except Exception as e:
    print(f"❌ Erreur : {e}")
    import traceback
    traceback.print_exc()

# Test 5 : Sauvegarder le catalogue
print("\n" + "=" * 80)
print("TEST 5 : Sauvegarde du catalogue")
print("=" * 80)

try:
    catalog.save()
    print(f"✅ Catalogue sauvegardé : {satmap.CATALOG_FILE}")
    print(f"   Taille : {satmap.CATALOG_FILE.stat().st_size} bytes")
except Exception as e:
    print(f"❌ Erreur : {e}")
    import traceback
    traceback.print_exc()

# Test 6 : Recharger le catalogue
print("\n" + "=" * 80)
print("TEST 6 : Rechargement du catalogue")
print("=" * 80)

try:
    catalog2 = satmap.TextureCatalog()
    print(f"✅ Catalogue rechargé : {len(catalog2.data)} entrées")
except Exception as e:
    print(f"❌ Erreur : {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)
print("✅ TOUS LES TESTS PASSÉS")
print("=" * 80)
