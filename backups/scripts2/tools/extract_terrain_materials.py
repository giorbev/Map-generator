"""
Extraire la liste COMPLETE des materiaux depuis Terrain.terr
Dans l'ordre EXACT du moteur (pas reordonne)
"""

from pathlib import Path
import re

terrain_file = Path(r'I:\reforger_travail\Zimnitrita_map_test\World\Zimnitrita\Terrain\Terrain.terr')
output_file = Path(r'I:\reforger_travail\Zimnitrita_map_test\World\Zimnitrita\Terrain\terrain_materials_list_CORRECT.txt')

print("="*80)
print("EXTRACTION LISTE MATERIAUX DEPUIS Terrain.terr")
print("="*80)
print()

# Lire le fichier en BINAIRE
with open(terrain_file, 'rb') as f:
    content = f.read()

# Decoder en string (ignorer erreurs)
content_str = content.decode('utf-8', errors='ignore')

# Extraire tous les chemins .emat
# Pattern : chercher tout ce qui finit par .emat
# Format : ...quelquepart/nom_fichier.emat
pattern = r'([A-Za-z0-9_]+\.emat)'
matches = re.findall(pattern, content_str)

# Dédupliquer tout en préservant l'ordre
seen = set()
materials_ordered = []
for m in matches:
    if m not in seen:
        seen.add(m)
        materials_ordered.append(m)
matches = materials_ordered

print(f"Trouve {len(matches)} materiaux\n")

# Extraire juste les noms de fichiers (pas les chemins complets)
materials = []
for path in matches:
    # Prendre juste le nom de fichier
    name = path.split('/')[-1]
    materials.append(name)
    print(f"ID {len(materials)-1:2d} : {name}")

print()
print("="*80)

# Sauvegarder
with open(output_file, 'w', encoding='utf-8') as f:
    for mat in materials:
        f.write(mat + '\n')

print(f"Liste sauvegardee : {output_file}")
print(f"Total : {len(materials)} materiaux")
print()

# Verifier ancres connues
print("Verification ancres :")
if len(materials) > 5:
    print(f"  ID 5 : {materials[5]} (devrait etre Crop_Field_01)")
if len(materials) > 6:
    print(f"  ID 6 : {materials[6]} (devrait etre Crop_Field_02)")
if len(materials) > 3:
    print(f"  ID 3 : {materials[3]} (devrait etre Grass_03)")
