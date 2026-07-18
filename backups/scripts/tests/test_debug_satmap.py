"""
Debug : Voir exactement quelles textures sont trouvées/manquantes pendant la génération
"""

import sys
import io
import json
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import reforger_satmap_generator as satmap_gen

# Charger catalogue
catalog_path = Path("data/Textures_ArmaReforger/catalog.json")
with open(catalog_path, 'r', encoding='utf-8') as f:
    catalog_dict = json.load(f)

textures_root = Path("data/Textures_ArmaReforger")

print("="*80)
print("DEBUG RECHERCHE TEXTURES")
print("="*80 + "\n")

found = []
missing = []

for name, entry in catalog_dict.items():
    middle_bcr = entry.get("middle_bcr")

    if not middle_bcr:
        print(f"⚠️  {name} : PAS DE MIDDLE_BCR")
        continue

    # Chercher avec la vraie fonction
    texture_path = satmap_gen.find_texture_png(textures_root, middle_bcr)

    if texture_path:
        found.append((name, middle_bcr, str(texture_path)))
        print(f"✓ {name}")
        print(f"  Cherche: {middle_bcr}")
        print(f"  Trouvé: {texture_path}")
        print()
    else:
        missing.append((name, middle_bcr))
        print(f"❌ {name}")
        print(f"  Cherche: {middle_bcr}")
        print(f"  → NON TROUVÉ")
        print()

print("="*80)
print(f"RÉSUMÉ : {len(found)}/{len(catalog_dict)} trouvées")
print(f"MANQUANTES : {len(missing)}")
print("="*80)
