"""
Parser pour terrain_materials_list.txt

Extrait la liste globale des surfaces dans l'ordre exact
utilise par les IDs du chunk LRS2
"""

from pathlib import Path
from typing import List, Optional


def parse_terrain_materials_list(file_path: Path) -> Optional[List[str]]:
    """
    Parse le fichier terrain_materials_list.txt

    Args:
        file_path: Chemin vers terrain_materials_list.txt

    Returns:
        Liste des noms de surfaces (sans chemin, avec .emat)
        Ex: ["ZI_Crop_Field_03.emat", "Grass_03_default.emat", ...]
    """
    if not file_path.exists():
        print(f"Fichier non trouve : {file_path}")
        return None

    surfaces = []

    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()

            # Ignorer lignes vides, titres, separateurs
            if not line or line.startswith("=") or ":" in line and not ".emat" in line:
                continue

            # Chercher lignes avec .emat
            if ".emat" in line:
                # Extraire juste le nom du fichier
                # Ex: "  Terrains/Common/Surfaces/ZI_Crop_Field_03.emat"
                #  -> "ZI_Crop_Field_03.emat"
                parts = line.split("/")
                surface_name = parts[-1].strip()

                surfaces.append(surface_name)

    return surfaces


def load_surfaces_list_from_world(terrain_dir: Path) -> Optional[List[str]]:
    """
    Charge la liste des surfaces depuis le monde Reforger

    Args:
        terrain_dir: Dossier Terrain/

    Returns:
        Liste surfaces ou None
    """
    materials_file = terrain_dir / "terrain_materials_list.txt"

    if materials_file.exists():
        return parse_terrain_materials_list(materials_file)

    print(f"Fichier terrain_materials_list.txt non trouve dans {terrain_dir}")
    return None


# Test
if __name__ == "__main__":
    import sys

    test_path = Path(r"I:\reforger_travail\Zimnitrita_map_test\World\Zimnitrita\Terrain\terrain_materials_list.txt")

    if not test_path.exists():
        print(f"Fichier test non trouve : {test_path}")
        sys.exit(1)

    print(f"Test parsing : {test_path.name}\n")

    surfaces = parse_terrain_materials_list(test_path)

    if surfaces:
        print(f"OK {len(surfaces)} surfaces chargees\n")

        print("Premieres 10 surfaces :")
        for i, surface in enumerate(surfaces[:10]):
            print(f"  ID {i:2d} : {surface}")

        print("\n...")

        print(f"\nDernieres 5 surfaces :")
        for i, surface in enumerate(surfaces[-5:], start=len(surfaces)-5):
            print(f"  ID {i:2d} : {surface}")

    else:
        print("Echec parsing")
        sys.exit(1)
