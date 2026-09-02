"""
NatureMap Generator (Occupation du Sol)
Génère une carte d'occupation basée sur pentes, altitude et distance eau.
Utilise BaseMap comme source de données structurées.
"""

import numpy as np
import cv2
from PIL import Image
from base_map import BaseMap


class NaturemapGenerator:
    """
    Génère une NatureMap (occupation du sol) à partir d'une BaseMap.
    
    7 Biomes:
    - Water: Bleu azur (#3D85C6)
    - Sand: Sable (#E2C992)
    - Snow: Neige (#FFFFFF)
    - Rock: Roche (#828282)
    - Tundra: Toundra (#939D79)
    - Forest Dense: Forêt dense (#2D4C2A)
    - Prairie: Prairie (#A8C67D)
    """
    
    # Couleurs finales (BGR pour OpenCV)
    COLORS = {
        'water': (198, 133, 61),       # Bleu azur #3D85C6
        'sand': (146, 217, 226),       # Sable #E2C992
        'snow': (255, 255, 255),       # Neige #FFFFFF
        'rock': (130, 130, 130),       # Roche #828282
        'tundra': (121, 157, 147),     # Toundra #939D79
        'forest_dense': (42, 76, 45),  # Forêt dense #2D4C2A
        'prairie': (125, 198, 168),    # Prairie #A8C67D
    }
    
    def __init__(self, base_map: BaseMap):
        """
        Initialise le générateur NatureMap.
        
        Args:
            base_map: Instance de BaseMap pré-calculée
        """
        print("[NatureMap] Initialisation...")
        self.base_map = base_map
        
        # Générer Perlin fin pour texture forêt
        self.perlin_canopy = self._generate_perlin_fine()
        
        # Créer la naturemap
        self.naturemap_array = self._generate_naturemap()
        
        print("[NatureMap] ✓ Générée avec succès")
    
    def _generate_perlin_fine(self):
        """
        Génère Perlin noise fin pour simuler canopée (5px scale).
        """
        print("  [Génération bruit Perlin (canopée)...]")
        
        height, width = self.base_map.heightmap.shape
        
        # Créer noise aléatoire
        noise = np.random.randint(0, 256, (height, width), dtype=np.uint8)
        
        # Appliquer GaussianBlur fin (5px scale)
        kernel_size = 5
        if kernel_size % 2 == 0:
            kernel_size += 1
        perlin = cv2.GaussianBlur(noise, (kernel_size, kernel_size), 0)
        
        return perlin.astype(np.float32) / 255.0
    
    def _generate_naturemap(self):
        """
        Génère la NatureMap colorée selon les biomes.
        """
        print("  [Génération de la NatureMap...]")
        
        height, width = self.base_map.heightmap.shape
        naturemap = np.zeros((height, width, 3), dtype=np.uint8)
        
        # Récupérer les masques biomes de BaseMap
        biome_masks = self.base_map.biome_masks
        
        # Appliquer les couleurs biomes dans l'ordre de priorité
        for biome_name, biome_mask in biome_masks.items():
            if np.any(biome_mask):
                color = self.COLORS[biome_name]
                naturemap[biome_mask] = color
                count = np.sum(biome_mask)
                pct = (count / (height * width)) * 100
                print(f"    {biome_name:15} {count:10} pixels ({pct:5.1f}%)")
        
        # Ajouter texture fine à la forêt (canopée)
        if np.any(biome_masks['forest_dense']):
            print("  [Application texture canopée...]")
            forest_mask = biome_masks['forest_dense']
            
            # Récupérer valeurs Perlin pour forêt
            perlin_vals = self.perlin_canopy[forest_mask]
            
            # Appliquer variation texture (±5% environ)
            for c in range(3):
                base = naturemap[forest_mask, c].astype(np.float32)
                # Varier: si perlin > 0.5, éclaircir; sinon assombrir
                texture_mod = (perlin_vals - 0.5) * 0.1 * 255  # ±12% de variation
                final = base + texture_mod
                naturemap[forest_mask, c] = np.clip(final, 0, 255).astype(np.uint8)
        
        return naturemap
    
    def get_pil_image(self):
        """Retourne la naturemap en PIL Image."""
        # Convertir BGR → RGB pour PIL
        naturemap_rgb = np.flip(self.naturemap_array, axis=2)
        return Image.fromarray(naturemap_rgb, mode='RGB')
    
    def save(self, filepath):
        """Sauvegarde la naturemap en PNG."""
        img = self.get_pil_image()
        img.save(filepath)
        print(f"[NatureMap] Sauvegardée: {filepath}")


# Test
if __name__ == "__main__":
    base = BaseMap(r"c:\Users\jordi\Desktop\Map generator\input\bornholm_ter.asc")
    naturemap = NaturemapGenerator(base)
    naturemap = NatureMapGenerator(base, perlin_scale=10, perlin_intensity=0.3)
    naturemap.save("output/naturemap_test.png")
    print("✓ NatureMap générée!")
