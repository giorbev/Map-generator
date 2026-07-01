# -*- coding: utf-8 -*-
"""
Script de renommage des textures mappeur
Nettoie les noms pour matching parfait avec get_texture_color()
"""

import os
from pathlib import Path
import shutil

# Chemin source
SOURCE_DIR = Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\sources\export mask text")

# Mapping : nom actuel → nom propre
RENAME_MAP = {
    # Fond marin
    "mask seabed.png": "seabed.png",

    # Côtier
    "mask BeachGrass_01.png": "beachgrass.png",
    "mask Grass_03_coastal.png": "coastal_grass.png",

    # Galets
    "mask pebbles 1.png": "pebbles_01.png",
    "mask peebles2.png": "pebbles_02.png",

    # Herbe
    "mask grass2.png": "grass_02.png",
    "mask grass3.png": "grass_03.png",
    "mask_grass3.png": "grass_03_alt.png",
    "mask_grass3_aut.png": "grass_03_aut.png",

    # Mountain grass
    "mask montainGrass1.png": "mountain_grass_01.png",
    "mask_montaingrass.png": "mountain_grass_02.png",

    # Heather
    "mask heather2.png": "heather.png",

    # Forêt deciduous
    "mask_forest decidious 1.png": "deciduous.png",
    "mask ForestConiferous_01_Base.png": "conifer.png",

    # Forêt pine
    "mask_forest pine.png": "pine.png",

    # Clearing
    "mask ForestClearing_Deciduous_01.png": "clearing_deciduous.png",
    "mask_Forest Clearing_Coniferous_01.png": "clearing_conifer.png",

    # Débris roche
    "mask debrisrock.png": "debris_rock.png",

    # Terre
    "mask_dirt1.png": "dirt_01.png",
    "mask_dirt2.png": "dirt_02.png",

    # Roche
    "mask rock1.png": "rock_01.png",
    "mask_ rock2.png": "rock_02.png",

    # Champs ZI
    "mask Cropfield1.png": "zi_cropfield_01.png",
    "mask Zi CropField2.png": "zi_cropfield_02.png",
    "mask ZI_Crop_Field_03.png": "zi_cropfield_03.png",
    "mask zi cropfield1.png": "zi_cropfield_01_alt.png",

    "mask ZI_Crop_Field_Cut_02.png": "zi_cropfield_cut_02.png",
    "mask zi cropfieldcut1.png": "zi_cropfield_cut_01.png",

    # Urbain
    "mask asphalt1.png": "asphalt.png",
    "mask concrete_2.png": "concrete.png",
    "mask cobblestone.png": "cobblestone.png",

    # Sol spécial ZI
    "mask_ zi groundsport.png": "zi_ground.png",
}


def rename_files(dry_run=True):
    """Renomme les fichiers selon RENAME_MAP"""

    if not SOURCE_DIR.exists():
        print(f"[ERREUR] Dossier non trouve : {SOURCE_DIR}")
        return

    print(f"Dossier : {SOURCE_DIR}\n")

    # Lister tous les fichiers PNG
    all_files = sorted(SOURCE_DIR.glob("*.png"))
    print(f"{len(all_files)} fichiers PNG trouves")
    print(f"{len(RENAME_MAP)} renommages definis\n")

    renamed_count = 0
    skipped_count = 0
    not_in_map = []

    for old_file in all_files:
        old_name = old_file.name

        if old_name in RENAME_MAP:
            new_name = RENAME_MAP[old_name]
            new_path = SOURCE_DIR / new_name

            if dry_run:
                print(f"  {old_name:45} -> {new_name}")
            else:
                # Vérifier si destination existe déjà
                if new_path.exists():
                    print(f"[SKIP] Existe deja : {old_name} -> {new_name}")
                    skipped_count += 1
                else:
                    old_file.rename(new_path)
                    print(f"[OK] {old_name:45} -> {new_name}")
                    renamed_count += 1

        else:
            not_in_map.append(old_name)

    print(f"\n{'-' * 70}")

    if not_in_map:
        print(f"\n[WARNING] {len(not_in_map)} fichiers NON MAPPES (ignores) :")
        for fname in not_in_map:
            print(f"    - {fname}")

    if dry_run:
        print(f"\n[DRY-RUN] MODE SIMULATION")
        print(f"   Pour renommer vraiment : python rename_textures.py --apply")
    else:
        print(f"\n[SUCCESS] RENOMMAGE TERMINE !")
        print(f"   {renamed_count} fichiers renommes")
        if skipped_count > 0:
            print(f"   {skipped_count} fichiers skipes (destination existe)")


if __name__ == "__main__":
    import sys

    # Dry-run par défaut, --apply pour vraiment renommer
    dry_run = "--apply" not in sys.argv

    if dry_run:
        print("=" * 70)
        print("SIMULATION - Aperçu des renommages")
        print("=" * 70 + "\n")
    else:
        print("=" * 70)
        print("RENOMMAGE RÉEL - Application...")
        print("=" * 70 + "\n")

    rename_files(dry_run=dry_run)
