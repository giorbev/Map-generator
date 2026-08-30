#!/usr/bin/env python3
"""
Chargeur de DebugColors des matériaux de terrain Arma Reforger
Utilise le fichier CSV généré depuis les .emat
"""

import csv
from pathlib import Path
from typing import Dict, Tuple
import numpy as np


class MaterialColorDB:
    """Base de données des couleurs de matériaux"""

    def __init__(self, csv_path: str = None):
        """
        Args:
            csv_path: Chemin du CSV, par défaut cherche dans Notes/
        """
        if csv_path is None:
            csv_path = Path(__file__).parent.parent / "Notes" / "Material_DebugColors.csv"

        self.csv_path = Path(csv_path)
        self.materials: Dict[str, Dict] = {}
        self._load_csv()

    def _load_csv(self):
        """Charge le CSV des couleurs de matériaux"""
        if not self.csv_path.exists():
            raise FileNotFoundError(f"Fichier CSV non trouvé: {self.csv_path}")

        with open(self.csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row['Material']
                self.materials[name] = {
                    'name': name,
                    'color': (
                        float(row['R']),
                        float(row['G']),
                        float(row['B']),
                        float(row['A'])
                    ),
                    'category': row['Category'],
                    'file_path': row['FilePath']
                }

        print(f"✓ Chargé {len(self.materials)} matériaux")

    def get_color(self, material_name: str) -> Tuple[float, float, float, float]:
        """
        Récupère la couleur RGBA d'un matériau

        Args:
            material_name: Nom du matériau (sans .emat)

        Returns:
            Tuple (R, G, B, A) en float [0, 1]
        """
        mat = self.materials.get(material_name)
        if mat:
            return mat['color']
        else:
            raise KeyError(f"Matériau '{material_name}' non trouvé")

    def get_color_rgb8(self, material_name: str) -> Tuple[int, int, int]:
        """
        Récupère la couleur RGB d'un matériau en [0, 255]

        Args:
            material_name: Nom du matériau

        Returns:
            Tuple (R, G, B) en int [0, 255]
        """
        r, g, b, a = self.get_color(material_name)
        return (
            int(r * 255),
            int(g * 255),
            int(b * 255)
        )

    def find_by_category(self, category: str) -> list:
        """
        Trouve tous les matériaux d'une catégorie

        Args:
            category: Vegetation, Rock, Dirt, Sand, Artificial, Agriculture, Other

        Returns:
            Liste des noms de matériaux
        """
        return [
            name for name, mat in self.materials.items()
            if mat['category'] == category
        ]

    def get_all_categories(self) -> list:
        """Retourne toutes les catégories disponibles"""
        categories = set(mat['category'] for mat in self.materials.values())
        return sorted(categories)

    def list_materials(self):
        """Affiche tous les matériaux avec leurs couleurs"""
        print(f"\n{'Matériau':<40} {'RGB':<20} {'Catégorie':<15}")
        print("=" * 75)

        for name, mat in sorted(self.materials.items()):
            r, g, b, a = mat['color']
            rgb_str = f"({r:.3f}, {g:.3f}, {b:.3f})"
            print(f"{name:<40} {rgb_str:<20} {mat['category']:<15}")

    def create_color_lut(self, layer_mapping: Dict[int, str]) -> np.ndarray:
        """
        Crée une Look-Up Table (LUT) pour convertir layer_index → couleur

        Args:
            layer_mapping: Dictionnaire {layer_index: material_name}
                          Ex: {0: "Grass_01", 1: "Dirt_01", 2: "Rock_01", ...}

        Returns:
            np.ndarray shape (7, 3) dtype float32 - Couleurs RGB [0, 1]
        """
        lut = np.zeros((7, 3), dtype=np.float32)

        for layer_idx, material_name in layer_mapping.items():
            if 0 <= layer_idx < 7:
                r, g, b, a = self.get_color(material_name)
                lut[layer_idx] = [r, g, b]

        return lut


# ===== EXEMPLE D'UTILISATION =====

if __name__ == "__main__":
    # Charger la base de données
    db = MaterialColorDB()

    print("\n=== Exemple 1: Récupérer une couleur ===")
    color = db.get_color("Grass_01")
    print(f"Grass_01 (RGBA): {color}")

    rgb8 = db.get_color_rgb8("Grass_01")
    print(f"Grass_01 (RGB 0-255): {rgb8}")

    print("\n=== Exemple 2: Catégories ===")
    print(f"Catégories disponibles: {db.get_all_categories()}")

    vegetation = db.find_by_category("Vegetation")
    print(f"\nMatériaux de végétation ({len(vegetation)}):")
    for mat in vegetation[:5]:
        print(f"  - {mat}")

    print("\n=== Exemple 3: Créer une LUT pour satmap ===")
    # Exemple de mapping (à adapter selon votre terrain)
    layer_map = {
        0: "Grass_01",           # Layer 0 = Herbe
        1: "Dirt_01",            # Layer 1 = Terre
        2: "Rock_01",            # Layer 2 = Roche
        3: "ForestConiferous_01_Base",  # Layer 3 = Forêt
        4: "BeachGrass_01",      # Layer 4 = Plage
        5: "MountainGrass_01",   # Layer 5 = Montagne
        6: "Pebbles_01",         # Layer 6 = Galets
    }

    lut = db.create_color_lut(layer_map)
    print(f"\nLUT créée: shape {lut.shape}")
    print("Couleurs RGB par layer:")
    for i, color in enumerate(lut):
        print(f"  Layer {i}: RGB({color[0]:.3f}, {color[1]:.3f}, {color[2]:.3f})")

    print("\n=== Liste complète des matériaux ===")
    db.list_materials()
