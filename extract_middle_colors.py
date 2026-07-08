"""
Extrait la couleur moyenne des textures middle BCR
Pour les surfaces sans tint (blanc), remplace par la couleur moyenne de la texture
"""

import json
import cv2
import numpy as np
from pathlib import Path

# Chemins
catalog_file = Path(r"h:\logiciel perso\Map generator\data\Textures_ArmaReforger\catalog.json")
textures_dir = Path(r"H:\logiciel perso\Map generator\data\Textures_ArmaReforger\texture_Middle\textures")

# Charger catalogue
with open(catalog_file, 'r', encoding='utf-8') as f:
    catalog = json.load(f)

print("="*80)
print("EXTRACTION COULEURS MOYENNES TEXTURES MIDDLE")
print("="*80)
print()

updated_count = 0
missing_textures = []

for surface_name, entry in catalog.items():
    tint = entry.get('tint_srgb', [128, 128, 128])
    r, g, b = tint

    # Si tint blanc (> 240)
    if r > 240 and g > 240 and b > 240:
        # Récupérer le nom de la texture middle
        middle_bcr = entry.get('middle_bcr', '')

        if not middle_bcr:
            continue

        # Construire chemin texture (remplacer .edds par .jpg)
        texture_name = middle_bcr.replace('.edds', '.jpg').replace('.EDDS', '.jpg')

        # Enlever les chemins (Vanilla/textures/, Customs/, etc.)
        if '/' in texture_name or '\\' in texture_name:
            texture_name = texture_name.split('/')[-1].split('\\')[-1]

        texture_path = textures_dir / texture_name

        if not texture_path.exists():
            missing_textures.append(f"{surface_name} -> {texture_name}")
            continue

        # Charger texture
        try:
            img = cv2.imread(str(texture_path))
            if img is None:
                missing_textures.append(f"{surface_name} -> {texture_name} (lecture échouée)")
                continue

            # Convertir BGR -> RGB
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

            # Calculer couleur moyenne
            mean_color = img_rgb.mean(axis=(0, 1))  # Moyenne sur H et W
            r_mean = int(mean_color[0])
            g_mean = int(mean_color[1])
            b_mean = int(mean_color[2])

            # Mettre à jour catalogue
            entry['tint_srgb'] = [r_mean, g_mean, b_mean]
            entry['tint_source'] = 'texture_middle_average'  # Marquer la source

            print(f"OK {surface_name:45s} RGB({r_mean:3d}, {g_mean:3d}, {b_mean:3d})  <- {texture_name}")
            updated_count += 1

        except Exception as e:
            missing_textures.append(f"{surface_name} -> {texture_name} (erreur: {e})")

print()
print("="*80)
print(f"OK {updated_count} surfaces mises a jour avec couleur moyenne texture")

if missing_textures:
    print()
    print(f"Attention {len(missing_textures)} textures manquantes :")
    for msg in missing_textures:
        print(f"   {msg}")

# Sauvegarder catalogue
print()
print("Sauvegarde catalogue enrichi...")
with open(catalog_file, 'w', encoding='utf-8') as f:
    json.dump(catalog, f, indent=2, ensure_ascii=False)

print("OK Catalogue sauvegarde !")
print()
print("="*80)
print("TERMINE ! Relancez la generation satmap en mode 'colors'")
print("="*80)
