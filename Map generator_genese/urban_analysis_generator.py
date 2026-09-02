"""
Générateur d'Analyse Stratégique Urbaine - Maillage Voronoi basé sur les Biomes
=================================================================================

Génère un maillage Voronoi pour la planification urbaine en utilisant:
- Nature map pour l'analyse des biomes
- Heightmap pour la topographie
- Seeds placés prioritairement sur Prairie/Plaines
- Hiérarchie Alpha/Beta/Gamma basée sur les surfaces
"""

import numpy as np
from PIL import Image, ImageDraw
import cv2
from scipy.spatial import Voronoi
from scipy.ndimage import label, find_objects
import json
from pathlib import Path


class UrbanAnalysisGenerator:
    def __init__(self, nature_map_path, heightmap_path):
        """
        Initialise le générateur d'analyse urbaine.
        
        Args:
            nature_map_path: Chemin vers la nature_map.png générée
            heightmap_path: Chemin vers la heightmap source
        """
        self.nature_map_path = nature_map_path
        self.heightmap_path = heightmap_path
        
        # Charger les images
        # PIL charge en RGB, convertir en BGR pour OpenCV
        nature_map_pil = Image.open(nature_map_path)
        self.nature_map = cv2.cvtColor(np.array(nature_map_pil), cv2.COLOR_RGB2BGR)
        self.heightmap = self._load_heightmap(heightmap_path)
        
        # Dimensions
        self.height, self.width = self.nature_map.shape[:2]
        
        # Couleurs des biomes en BGR (OpenCV)
        self.biome_colors = {
            'eau': (198, 133, 61),        # #3D85C6 Azure
            'neige': (255, 248, 240),    # #F0F8FF
            'roche': (130, 130, 130),    # #828282
            'toundra': (121, 157, 147),  # #939D79
            'foret': (42, 76, 45),       # #2D4C2A
            'prairie': (168, 198, 125),  # #A8C67D (PRIORITÉ)
            'sable': (226, 201, 146),    # #E2C992
        }
        
        # Résultats
        self.voronoi_diagram = None
        self.seeds = []
        self.alpha_seeds = []
        self.beta_gamma_seeds = []
        self.voronoi_overlay = None
    
    def _load_heightmap(self, path):
        """Charge la heightmap dans différents formats."""
        if path.lower().endswith('.asc'):
            return self._load_asc(path)
        else:
            img = Image.open(path)
            return np.array(img, dtype=np.float32)
    
    def _load_asc(self, path):
        """Charge une heightmap au format ESRI ASCII Grid."""
        with open(path, 'r') as f:
            header = {}
            for _ in range(6):
                parts = f.readline().strip().split()
                header[parts[0].lower()] = float(parts[1])
            
            data = []
            for line in f:
                data.extend(map(float, line.strip().split()))
            
            return np.array(data, dtype=np.float32).reshape(
                int(header['nrows']), int(header['ncols'])
            )
    
    def _get_biome_mask(self, biome_name, tolerance=5):
        """
        Crée un masque binaire pour un biome spécifique.
        
        Args:
            biome_name: Nom du biome ('prairie', 'eau', etc.)
            tolerance: Tolérance de correspondance de couleur
        
        Returns:
            Masque binaire (2D)
        """
        if biome_name not in self.biome_colors:
            return np.zeros((self.height, self.width), dtype=bool)
        
        target_color = np.array(self.biome_colors[biome_name], dtype=np.uint8)
        
        # Calculer la distance couleur
        distance = np.sqrt(np.sum((self.nature_map - target_color) ** 2, axis=2))
        mask = distance <= tolerance
        
        return mask
    
    def _select_seeds_adaptive(self, num_seeds=20):
        """
        Place les seeds prioritairement sur Prairie, en évitant Eau et Roche.
        
        Args:
            num_seeds: Nombre total de seeds à placer
        
        Returns:
            Liste de tuples (x, y) représentant les seeds
        """
        prairie_mask = self._get_biome_mask('prairie', tolerance=10)
        eau_mask = self._get_biome_mask('eau', tolerance=5)
        roche_mask = self._get_biome_mask('roche', tolerance=5)
        
        # Zone valide: Prairie ET NON Eau ET NON Roche
        valid_zone = prairie_mask & ~eau_mask & ~roche_mask
        
        # Si prairie insuffisante, ajouter forêt et toundra
        if valid_zone.sum() < num_seeds * 100:
            foret_mask = self._get_biome_mask('foret', tolerance=10)
            toundra_mask = self._get_biome_mask('toundra', tolerance=10)
            valid_zone = valid_zone | (foret_mask & ~eau_mask) | (toundra_mask & ~eau_mask)
        
        # Obtenir les coordonnées valides
        valid_pixels = np.where(valid_zone)
        
        if len(valid_pixels[0]) == 0:
            # Fallback: utiliser tout sauf l'eau
            valid_zone = ~eau_mask
            valid_pixels = np.where(valid_zone)
        
        # Sélectionner aléatoirement les seeds
        indices = np.random.choice(len(valid_pixels[0]), size=min(num_seeds, len(valid_pixels[0])), replace=False)
        
        seeds = [(valid_pixels[1][i], valid_pixels[0][i]) for i in indices]
        
        return seeds
    
    def _compute_voronoi_areas(self, vor, water_mask):
        """
        Calcule la surface de chaque cellule Voronoi en excluant l'eau.
        
        Args:
            vor: Objet Voronoi de scipy
            water_mask: Masque des pixels d'eau
        
        Returns:
            Dictionnaire {seed_index: surface_en_pixels}
        """
        areas = {}
        
        # Créer une grille de cellules Voronoi
        y, x = np.meshgrid(np.arange(self.width), np.arange(self.height))
        
        # Assigner chaque pixel à la seed la plus proche
        distances = np.zeros((len(self.seeds), self.height, self.width), dtype=np.float32)
        for i, (sx, sy) in enumerate(self.seeds):
            distances[i] = np.sqrt((x - sx) ** 2 + (y - sy) ** 2)
        
        cell_assignment = np.argmin(distances, axis=0)
        
        # Calculer la surface de chaque cellule (exclure eau)
        for i in range(len(self.seeds)):
            cell_mask = (cell_assignment == i) & ~water_mask
            areas[i] = np.sum(cell_mask)
        
        return areas
    
    def _select_hierarchy(self, areas):
        """
        Sélectionne Alpha (2 plus grandes), Beta/Gamma (reste).
        
        Args:
            areas: Dictionnaire {seed_index: surface}
        
        Returns:
            Dictionnaire avec 'alpha', 'beta_gamma'
        """
        sorted_seeds = sorted(areas.items(), key=lambda x: x[1], reverse=True)
        
        alpha = [self.seeds[idx] for idx, _ in sorted_seeds[:2]]
        beta_gamma = [self.seeds[idx] for idx, _ in sorted_seeds[2:]]
        
        return {
            'alpha': alpha,
            'beta_gamma': beta_gamma,
            'areas': {idx: area for idx, area in sorted_seeds}
        }
    
    def generate(self, num_seeds=20, seed_value=42):
        """
        Génère le maillage Voronoi et la hiérarchie urbaine.
        
        Args:
            num_seeds: Nombre de seeds Voronoi à générer
            seed_value: Graine aléatoire pour reproductibilité
        
        Returns:
            Dictionnaire avec résultats
        """
        np.random.seed(seed_value)
        
        # Étape 1: Placer les seeds
        self.seeds = self._select_seeds_adaptive(num_seeds=num_seeds)
        
        if len(self.seeds) < 3:
            raise ValueError("Impossible de placer au minimum 3 seeds. Vérifier la nature_map.")
        
        # Étape 2: Générer le Voronoi
        seeds_array = np.array(self.seeds)
        try:
            vor = Voronoi(seeds_array)
        except Exception as e:
            raise RuntimeError(f"Erreur Voronoi: {e}")
        
        # Étape 3: Masque d'eau
        eau_mask = self._get_biome_mask('eau', tolerance=5)
        
        # Étape 4: Calculer les surfaces
        areas = self._compute_voronoi_areas(vor, eau_mask)
        
        # Étape 5: Sélectionner hiérarchie
        hierarchy = self._select_hierarchy(areas)
        
        self.alpha_seeds = hierarchy['alpha']
        self.beta_gamma_seeds = hierarchy['beta_gamma']
        
        return {
            'num_seeds': len(self.seeds),
            'alpha_count': len(self.alpha_seeds),
            'beta_gamma_count': len(self.beta_gamma_seeds),
            'areas': hierarchy['areas'],
            'seeds': self.seeds,
            'voronoi': vor
        }
    
    def create_overlay(self, line_width=2, line_color=(50, 50, 50)):
        """
        Crée un overlay Voronoi sur la nature_map avec lignes des cellules.
        Les lignes Voronoi sont clippées par le masque d'eau.
        
        Args:
            line_width: Épaisseur des lignes Voronoi
            line_color: Couleur des lignes en BGR (noir par défaut)
        
        Returns:
            PIL Image
        """
        if not self.seeds:
            raise ValueError("Générer d'abord le Voronoi avec generate()")
        
        # Copier la nature_map
        overlay = self.nature_map.copy()
        
        # Créer un masque d'eau (exclure l'eau des lignes Voronoi)
        eau_mask = self._get_biome_mask('eau', tolerance=5)
        
        # Créer grille Voronoi: assigner chaque pixel à la seed la plus proche
        y, x = np.meshgrid(np.arange(self.width), np.arange(self.height))
        distances = np.zeros((len(self.seeds), self.height, self.width), dtype=np.float32)
        
        for i, (sx, sy) in enumerate(self.seeds):
            distances[i] = np.sqrt((x - sx) ** 2 + (y - sy) ** 2)
        
        cell_assignment = np.argmin(distances, axis=0)
        
        # Déterminer les pixels de frontière: où la cellule voisine diffère
        edges = np.zeros((self.height, self.width), dtype=bool)
        
        # Vérifier les différences horizontales
        edges[:-1, :] |= (cell_assignment[:-1, :] != cell_assignment[1:, :])
        # Vérifier les différences verticales
        edges[:, :-1] |= (cell_assignment[:, :-1] != cell_assignment[:, 1:])
        
        # Clipper les edges par le masque d'eau (pas de Voronoi sur l'eau)
        edges = edges & ~eau_mask
        
        # Appliquer les lignes Voronoi à l'image (seulement sur terre)
        overlay[edges] = line_color
        
        # Convertir en PIL pour dessiner les seeds
        overlay_pil = Image.fromarray(cv2.cvtColor(overlay, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(overlay_pil)
        
        # Dessiner tous les seeds (points rouges)
        seed_color = (255, 0, 0)  # Rouge
        for sx, sy in self.seeds:
            draw.ellipse([sx-3, sy-3, sx+3, sy+3], fill=seed_color)
        
        # Dessiner les seeds Alpha en vert (plus grands)
        alpha_color = (0, 255, 0)  # Vert
        for sx, sy in self.alpha_seeds:
            draw.ellipse([sx-5, sy-5, sx+5, sy+5], fill=alpha_color, outline=alpha_color, width=2)
        
        # Convertir back to BGR numpy
        overlay_cv = cv2.cvtColor(np.array(overlay_pil), cv2.COLOR_RGB2BGR)
        
        self.voronoi_overlay = overlay_cv
        return Image.fromarray(cv2.cvtColor(overlay_cv, cv2.COLOR_BGR2RGB))
    
    def save_overlay(self, output_path='output/urban_planning_overlay.png'):
        """
        Sauvegarde l'overlay Voronoi.
        
        Args:
            output_path: Chemin de sortie
        """
        if self.voronoi_overlay is None:
            raise ValueError("Créer d'abord l'overlay avec create_overlay()")
        
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        
        overlay_pil = Image.fromarray(cv2.cvtColor(self.voronoi_overlay, cv2.COLOR_BGR2RGB))
        overlay_pil.save(output_path)
    
    def get_analysis_report(self):
        """
        Génère un rapport d'analyse structuré.
        
        Returns:
            Dictionnaire avec statistiques
        """
        return {
            'num_total_seeds': len(self.seeds),
            'num_alpha': len(self.alpha_seeds),
            'num_beta_gamma': len(self.beta_gamma_seeds),
            'alpha_coordinates': self.alpha_seeds,
            'beta_gamma_coordinates': self.beta_gamma_seeds,
            'grid_dimensions': (self.width, self.height)
        }
