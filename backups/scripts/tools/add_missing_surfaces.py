"""
Ajouter Grass_03_default et Rock_02 au catalogue
"""

import sys
import io
import json
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

catalog_path = Path("data/Textures_ArmaReforger/catalog.json")

# Charger
with open(catalog_path, 'r', encoding='utf-8') as f:
    catalog = json.load(f)

print(f"Catalogue actuel : {len(catalog)} surfaces")

# Grass_03_default (basé sur Grass_03)
if 'Grass_03.emat' in catalog and 'Grass_03_default.emat' not in catalog:
    grass03 = catalog['Grass_03.emat']
    catalog['Grass_03_default.emat'] = {
        'provenance': grass03['provenance'],
        'parent': 'Grass_03.emat',
        'middle_bcr': grass03['middle_bcr'],
        'avg_color': grass03['avg_color'],
        'tint': grass03['tint'],
        'role': grass03['role'],
        'resolved': 'inherited',
        'resolved_date': '2026-07-04',
        'tiling_scale': grass03.get('tiling_scale', 100.0)
    }
    print("✓ Grass_03_default.emat ajouté")
elif 'Grass_03_default.emat' in catalog:
    print("⚠️ Grass_03_default.emat existe déjà")

# Rock_02 (basé sur Rock_01)
if 'Rock_01.emat' in catalog and 'Rock_02.emat' not in catalog:
    rock01 = catalog['Rock_01.emat']
    catalog['Rock_02.emat'] = {
        'provenance': rock01['provenance'],
        'parent': 'Rock_01.emat',
        'middle_bcr': rock01['middle_bcr'],
        'avg_color': rock01['avg_color'],
        'tint': rock01['tint'],
        'role': rock01['role'],
        'resolved': 'inherited',
        'resolved_date': '2026-07-04',
        'tiling_scale': rock01.get('tiling_scale', 20.0)
    }
    print("✓ Rock_02.emat ajouté")
elif 'Rock_02.emat' in catalog:
    print("⚠️ Rock_02.emat existe déjà")

# Sauvegarder
with open(catalog_path, 'w', encoding='utf-8') as f:
    json.dump(catalog, f, indent=2, ensure_ascii=False)

print(f"\n✓ Catalogue sauvegardé : {len(catalog)} surfaces")
