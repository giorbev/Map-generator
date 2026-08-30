"""
rename_middles.py — Normalise les noms de fichiers dans texture_Middle
Convention : NomTexture_Middle_BCR.jpg
Exécuter depuis le dossier texture_Middle ou passer le chemin en argument.
"""
import os
import sys
from pathlib import Path

# Mapping ancien nom → nouveau nom
RENAMES = {
    'ForestClearing_Deciduous_01_aut_BCR.jpg':   'ForestClearing_Deciduous_01_aut_Middle_BCR.jpg',
    'ForestDeciduous_base_aut_BCR.jpg':           'ForestDeciduous_01_Base_aut_Middle_BCR.jpg',
    'forestDecidous_Base_aut_BCR.jpg':            'ForestDeciduous_01_Base_aut_Middle_BCR.jpg',
    'MountainGrass_Middle_02_BCR.jpg':            'MountainGrass_02_Middle_BCR.jpg',
    'MountainGrass_Middle_02_aut_BCR.jpg':        'MountainGrass_02_aut_Middle_BCR.jpg',
    'MountainGrass_Middle_03_BCR.jpg':            'MountainGrass_03_Middle_BCR.jpg',
    'MountainGrass_Middle_03_aut_BCR.jpg':        'MountainGrass_03_aut_Middle_BCR.jpg',
    'zi_ground_sport_Middle.jpg':                 'ZI_Ground_Sport_01_Middle_BCR.jpg',
    'zi_MountainGrass_04_middle.png':             'ZI_MountainGrass_04_Middle_BCR.jpg',
    'Dirt_01_BCR_custom_Middle.jpg':              'Dirt_01_custom_Middle_BCR.jpg',
    'Dirt_03_BCR_custom_Middle.jpg':              'Dirt_03_custom_Middle_BCR.jpg',
    'forestclearing_coniferous_01_middle.png':    'ForestClearing_Coniferous_01_Middle_BCR.jpg',
    'ForestClearing_Middle_01_BCR.jpg':           'ForestClearing_01_Middle_BCR.jpg',
}

folder = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('.')
print(f"Dossier : {folder.resolve()}")
print()

renamed = 0
skipped = 0

for old_name, new_name in RENAMES.items():
    old_path = folder / old_name
    new_path = folder / new_name
    if old_path.exists():
        if new_path.exists():
            print(f"  ⚠️  SKIP (cible existe déjà) : {old_name} → {new_name}")
            skipped += 1
        else:
            old_path.rename(new_path)
            print(f"  ✅ {old_name} → {new_name}")
            renamed += 1
    else:
        print(f"  — Absent (OK) : {old_name}")

print()
print(f"Renommages effectués : {renamed}")
print(f"Ignorés (cible déjà présente) : {skipped}")
