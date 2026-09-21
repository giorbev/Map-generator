import json
from pathlib import Path

catalog_path = Path(r"H:\logiciel perso\Map generator\data\Textures_ArmaReforger\Textures\catalog.json")

with open(catalog_path, 'r', encoding='utf-8') as f:
    catalog = json.load(f)

# Copier Rock_01 → Rock_01b
if 'Rock_01.emat' in catalog and 'Rock_01b.emat' not in catalog:
    entry = dict(catalog['Rock_01.emat'])
    entry['provenance'] = 'custom'
    entry['parent'] = 'Rock_01.emat'
    catalog['Rock_01b.emat'] = entry
    print(f"✅ Rock_01b.emat ajouté depuis Rock_01.emat")
else:
    print("Rock_01b déjà présent ou Rock_01 introuvable")

with open(catalog_path, 'w', encoding='utf-8') as f:
    json.dump(catalog, f, indent=2, ensure_ascii=False)

print("catalog.json mis à jour")
