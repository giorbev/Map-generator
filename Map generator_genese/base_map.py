"""
BaseMap Generator
Couche fondamentale qui calcule les données structurées une seule fois.
Source unique de vérité pour toutes les cartes dérivées (ColorMap, NatureMap).
"""

import numpy as np
import cv2
from PIL import Image
import os
from pathlib import Path


class BaseMap:
    """
    Génère une BaseMap cohérente à partir d'une heightmap.
    
    Contient:
    - heightmap (brut, float)
    - altitudes réelles (min/max en mètres)
    - slopes (degrés via Sobel)
    - water_mask (booléen)
    - biome_masks (dict des 7 biomes selon hiérarchie)
    
    Toutes les cartes dérivées (ColorMap, NatureMap) utilisent BaseMap comme source.
    """
    
    # Couleurs finales des biomes (BGR pour OpenCV/PIL)
    COLORS = {
        'water': (200, 133, 61),      # Bleu azur #3D85C6
        'sand': (146, 217, 226),      # Sable #E2C992
        'snow': (255, 255, 255),      # Neige #FFFFFF
        'rock': (130, 130, 130),      # Roche #828282
        'tundra': (121, 157, 147),    # Toundra #939D79
        'forest_dense': (42, 76, 45), # Forêt dense #2D4C2A
        'prairie': (125, 198, 168),   # Prairie #A8C67D
    }
    
    def __init__(self, heightmap_path, vertical_exaggeration=10.0):
        """
        Initialise la BaseMap.
        
        Args:
            heightmap_path: Chemin vers la heightmap (PNG, JPG, ASC)
            vertical_exaggeration: Facteur d'exagération verticale (pour slopes)
        """
        print("[BaseMap] Initialisation...")
        
        # Charger heightmap selon le format
        self.heightmap_uint8 = self._load_heightmap(heightmap_path)
        
        self.height, self.width = self.heightmap_uint8.shape
        print(f"  • Dimensions: {self.width}×{self.height}px")
        
        # Altitudes réelles (en mètres, stockées par _load_asc_file)
        if hasattr(self, 'altitude_real_min'):
            self.altitude_min = self.altitude_real_min
            self.altitude_max = self.altitude_real_max
        else:
            # Pour images classiques: utiliser 0-255
            self.altitude_min = 0.0
            self.altitude_max = 255.0
        
        self.altitude_range = self.altitude_max - self.altitude_min
        
        print(f"  • Altitudes réelles: {self.altitude_min:.1f} - {self.altitude_max:.1f} m")
        print(f"  • Plage: {self.altitude_range:.1f} m")
        
        # Convertir heightmap en float pour calculs
        self.heightmap = self.heightmap_uint8.astype(np.float32)
        
        # Mapper heightmap normalisée (0-255) → altitudes réelles
        # heightmap_uint8 va de 0-255, on la mappe à altitude_min-max
        self.heightmap = self.altitude_min + (self.heightmap / 255.0) * self.altitude_range
        
        # Normaliser heightmap 0-1 pour calculs
        if self.altitude_range > 0:
            self.heightmap_normalized = (self.heightmap - self.altitude_min) / self.altitude_range
        else:
            self.heightmap_normalized = self.heightmap
        
        # Calculer slopes
        self.vertical_exaggeration = vertical_exaggeration
        self.slopes = self._compute_slopes()
        
        # Déterminer seuil eau (Otsu)
        self.water_level = self._calculate_water_level()
        self.water_mask = self.heightmap < self.water_level
        
        print(f"  • Eau détectée: {np.sum(self.water_mask)} pixels")
        
        # Calculer 4 tiers d'altitude (pour LUT)
        self.tier1 = self.altitude_min + self.altitude_range * 0.25
        self.tier2 = self.altitude_min + self.altitude_range * 0.50
        self.tier3 = self.altitude_min + self.altitude_range * 0.75
        self.tier4 = self.altitude_max
        
        print(f"  • Tiers d'altitude:")
        print(f"    Tier1 (0-25%): {self.tier1:.1f}m")
        print(f"    Tier2 (25-50%): {self.tier2:.1f}m")
        print(f"    Tier3 (50-75%): {self.tier3:.1f}m")
        print(f"    Tier4 (75-100%): {self.tier4:.1f}m")
        
        # Calculer masques de distance à l'eau (pour sable et forêt)
        self.distance_to_water = self._calculate_distance_to_water()
        
        # Calculer biome_masks selon hiérarchie
        self.biome_masks = self._calculate_biome_masks()
        
        print("[BaseMap] ✓ Initialisée avec succès")
    
    def _compute_slopes(self):
        """
        Calcule les pentes via Sobel en degrés.
        """
        print("  [Calcul des pentes...]")
        
        h_scaled = (self.heightmap_normalized * 100.0).astype(np.float32)
        sobelx = cv2.Sobel(h_scaled, cv2.CV_32F, 1, 0, ksize=3)
        sobely = cv2.Sobel(h_scaled, cv2.CV_32F, 0, 1, ksize=3)
        
        slope_raw = np.sqrt(sobelx**2 + sobely**2) * self.vertical_exaggeration
        slopes = np.degrees(np.arctan(slope_raw / (1.0 + 1e-8)))
        
        print(f"    Slopes: min={slopes.min():.1f}°, max={slopes.max():.1f}°")
        
        return slopes
    
    def _calculate_water_level(self):
        """
        Calcule le seuil d'eau automatiquement via Otsu.
        """
        heightmap_8 = cv2.normalize(
            self.heightmap_uint8.astype(np.float32), 
            None, 0, 255, 
            cv2.NORM_MINMAX
        ).astype(np.uint8)
        
        threshold_otsu, _ = cv2.threshold(
            heightmap_8, 0, 255, 
            cv2.THRESH_OTSU
        )
        
        # Convertir de uint8 (0-255) vers altitude réelle
        water_level = self.altitude_min + (threshold_otsu / 255.0) * self.altitude_range
        
        print(f"  • Seuil eau (Otsu): {water_level:.1f}m")
        
        return water_level
    
    def _calculate_distance_to_water(self):
        """
        Calcule distance euclidienne de chaque pixel à l'eau.
        Utilisée pour sable (< 3px) et forêt humide (< 200px).
        """
        print("  [Calcul distance à l'eau...]")
        
        # Créer masque eau inversion pour distanceTransform
        water_inverted = (~self.water_mask).astype(np.uint8) * 255
        
        # distanceTransform: retourne distance en pixels
        distance = cv2.distanceTransform(water_inverted, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
        
        print(f"    Distance max à l'eau: {distance.max():.1f}px")
        
        return distance
    
    def _calculate_biome_masks(self):
        """
        Calcule les masques biomes selon la hiérarchie simplifiée.
        
        Hiérarchie:
        1. EAU: altitude < seuil_eau
        2. SABLE: distance_eau < 3px (non-eau)
        3. NEIGE: altitude > tier4 ET pentes < 30
        4. ROCHE: (altitude > tier3 ET pentes > 35) OU (altitude > tier4 ET pentes > 20)
        5. TOUNDRA: tier3 < altitude <= tier4 ET pentes < 35
        6. FORET DENSE: altitude < tier3 ET 15 <= pentes <= 40 ET distance_eau < 200px
        7. PRAIRIE: altitude < tier2 ET pentes < 15 (fallback default)
        """
        print("  [Calcul des masques biomes...]")
        
        masks = {}
        terrain = ~self.water_mask  # Non-eau
        
        # 1. EAU
        masks['water'] = self.water_mask.copy()
        
        # 2. SABLE (bordure eau, non-eau)
        masks['sand'] = (
            terrain & 
            (self.distance_to_water < 3)
        )
        
        # 3. NEIGE (sommet plat)
        masks['snow'] = (
            (self.heightmap > self.tier4) &
            (self.slopes < 30) &
            ~masks['water'] &
            ~masks['sand']
        )
        
        # 4. ROCHE (pentes raides ou très haut)
        masks['rock'] = (
            (
                (self.heightmap > self.tier3) & (self.slopes > 35) |
                (self.heightmap > self.tier4) & (self.slopes > 20)
            ) &
            ~masks['water'] &
            ~masks['sand'] &
            ~masks['snow']
        )
        
        # 5. TOUNDRA (zone alpine, pentes modérées)
        masks['tundra'] = (
            (self.heightmap > self.tier3) & 
            (self.heightmap <= self.tier4) &
            (self.slopes < 35) &
            ~masks['water'] &
            ~masks['sand'] &
            ~masks['snow'] &
            ~masks['rock']
        )
        
        # 6. FORÊT DENSE (pentes modérées + humide)
        masks['forest_dense'] = (
            (self.heightmap < self.tier3) &
            (self.slopes >= 15) & (self.slopes <= 40) &
            (self.distance_to_water < 200) &
            ~masks['water'] &
            ~masks['sand'] &
            ~masks['snow'] &
            ~masks['rock'] &
            ~masks['tundra']
        )
        
        # 7. PRAIRIE (plaines, très plat - fallback)
        masks['prairie'] = (
            (self.heightmap < self.tier2) &
            (self.slopes < 15) &
            ~masks['water'] &
            ~masks['sand'] &
            ~masks['snow'] &
            ~masks['rock'] &
            ~masks['tundra'] &
            ~masks['forest_dense']
        )
        
        # 8. FALLBACK: tous les pixels non assignés vont en PRAIRIE
        classified = masks['water'] | masks['sand'] | masks['snow'] | masks['rock'] | masks['tundra'] | masks['forest_dense'] | masks['prairie']
        unclassified = ~classified
        if np.any(unclassified):
            print(f"    [FALLBACK] {np.sum(unclassified)} pixels non classifiés → PRAIRIE")
            masks['prairie'] = masks['prairie'] | unclassified
        
        # Afficher stats
        total = self.height * self.width
        for biome_name, biome_mask in masks.items():
            count = np.sum(biome_mask)
            pct = (count / total) * 100
            print(f"    {biome_name:15} {count:10} pixels ({pct:5.1f}%)")
        
        return masks
    
    def _load_heightmap(self, heightmap_path):
        """
        Charge une heightmap (PNG, JPG, ASC).
        
        Args:
            heightmap_path: Chemin vers le fichier
            
        Returns:
            Heightmap normalisée en uint8
        """
        path = Path(heightmap_path)
        
        if path.suffix.lower() == '.asc':
            # Format ASCII Grid (ESRI)
            return self._load_asc_file(heightmap_path)
        else:
            # Format image classique (PNG, JPG, etc.)
            # Pour PNG: on charge directement sans normalisation
            # (suppose que la PNG est déjà normalisée 0-255)
            img = Image.open(heightmap_path)
            heightmap = np.array(img)
            
            # Si couleur, convertir en grayscale
            if len(heightmap.shape) == 3:
                heightmap = cv2.cvtColor(heightmap.astype(np.uint8), cv2.COLOR_BGR2GRAY)
            
            # Pour PNG, on assume altitudes = valeurs pixel * quelque_chose
            # Utiliser simple 0-255 mapping
            self.altitude_real_min = 0.0
            self.altitude_real_max = 255.0
            
            return heightmap.astype(np.uint8)
    
    def _load_asc_file(self, filepath):
        """
        Charge un fichier ASC (ESRI ASCII Grid).
        Retourne une array uint8 (0-255) correspondant aux données de hauteur normalisées.
        Stocke aussi les altitudes réelles dans self.altitude_real_min/max.
        """
        with open(filepath, 'r') as f:
            # Lire les lignes d'en-tête
            ncols = int(f.readline().split()[1])
            nrows = int(f.readline().split()[1])
            xllcorner = float(f.readline().split()[1])
            yllcorner = float(f.readline().split()[1])
            cellsize = float(f.readline().split()[1])
            nodata = float(f.readline().split()[1])
            
            print(f"  [ASC] {ncols}×{nrows}px, cellsize={cellsize}, nodata={nodata}")
            
            # Lire les données de hauteur
            data = []
            for line in f:
                values = list(map(float, line.split()))
                data.extend(values)
            
            # Convertir en array 2D
            heightmap_real = np.array(data).reshape(nrows, ncols).astype(np.float32)
            
            # Remplacer nodata par 0
            if not np.isnan(nodata):
                heightmap_real[heightmap_real == nodata] = 0
            
            # Stocker altitudes REELLES en mètres
            self.altitude_real_min = float(np.min(heightmap_real))
            self.altitude_real_max = float(np.max(heightmap_real))
            
            # Normaliser à 0-255 pour compatibilité
            h_min = self.altitude_real_min
            h_max = self.altitude_real_max
            if h_max > h_min:
                heightmap_norm = ((heightmap_real - h_min) / (h_max - h_min)) * 255
            else:
                heightmap_norm = heightmap_real
            
            return heightmap_norm.astype(np.uint8)
    
    def get_altitude_at_pixel(self, x, y):
        """Retourne l'altitude réelle (m) à un pixel (x, y)."""
        return float(self.heightmap[y, x])
    
    def get_biome_at_pixel(self, x, y):
        """Retourne le biome à un pixel (x, y)."""
        for biome_name, biome_mask in self.biome_masks.items():
            if biome_mask[y, x]:
                return biome_name
        return 'unknown'


# Test rapide
if __name__ == "__main__":
    base = BaseMap(
        r"c:\Users\jordi\Desktop\Map generator\input\bornholm_ter.asc"
    )
    print("\nBaseMap prêt pour ColorMap et NatureMap!")
