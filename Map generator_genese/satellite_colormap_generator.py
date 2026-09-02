"""
Satellite Colormap Generator
Génère une colormap réaliste (satellite) à partir d'une heightmap.
Utilise bruit Perlin, ombrage directionnel, et rendu de terrain réaliste.
"""

import numpy as np
import cv2
from PIL import Image
import os


class SatelliteColormapGenerator:
    """
    Génère une Satellite Map (Colormap) réaliste à partir d'une Heightmap.
    
    Fonctionnalités:
    1. Palette naturelle désaturée (Forêt, Plaine, Roche, Eau)
    2. Texture Blending avec Perlin Noise à 2 échelles
    3. Rendu des pentes (strates rocheuses)
    4. Analytical Hillshading (lumière 315°, élévation 45°)
    5. Ombrage directionnel pour profondeur 3D
    """
    
    # Palette naturelle désaturée (BGR - format OpenCV)
    COLOR_FOREST = (40, 85, 45)       # Vert forêt désaturé
    COLOR_PLAIN = (160, 195, 205)     # Beige plaine
    COLOR_ROCK = (95, 105, 110)       # Gris roche
    COLOR_WATER = (120, 100, 60)      # Bleu ocean (BGR: B=120, G=100, R=60)
    
    # Variations de couleur (pour bruit)
    COLOR_FOREST_VAR = [(30, 75, 35), (50, 95, 55)]     # Variations forêt
    COLOR_PLAIN_VAR = [(150, 180, 190), (170, 210, 220)]  # Variations plaine
    COLOR_ROCK_VAR = [(80, 90, 100), (110, 120, 130)]    # Variations roche
    
    def __init__(self, heightmap_path, output_dir="output", vertical_exaggeration=10.0):
        """
        Initialise le générateur de colormap.
        
        Args:
            heightmap_path: Chemin vers l'image heightmap
            output_dir: Répertoire de sortie
            vertical_exaggeration: Exagération verticale pour ombrage
        """
        self.output_dir = output_dir
        self.vertical_exaggeration = vertical_exaggeration
        
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Charger heightmap
        img = Image.open(heightmap_path)
        self.heightmap = np.array(img).astype(float)
        if len(self.heightmap.shape) == 3:
            self.heightmap = cv2.cvtColor(self.heightmap.astype(np.uint8), cv2.COLOR_BGR2GRAY).astype(float)
        
        self.height, self.width = self.heightmap.shape
        print(f"[COLORMAP] Heightmap chargée: {self.width}×{self.height}px")
        
        # Normaliser heightmap 0-1
        h_min = np.min(self.heightmap)
        h_max = np.max(self.heightmap)
        if h_max > h_min:
            self.heightmap_normalized = (self.heightmap - h_min) / (h_max - h_min)
        else:
            self.heightmap_normalized = self.heightmap
        
        # Initialiser colormap
        self.colormap = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        
        # Caches
        self.slopes = None
        self.hillshade = None
        self.perlin_noise_large = None
        self.perlin_noise_small = None
        self.water_mask_final = None  # Masque d'eau pour ÉTAPE 6
        self.sea_level = 0.15  # Niveau de mer par défaut (15% altitude basse)
    
    def generate_perlin_noise(self, scale=50):
        """Génère du bruit Perlin via upscaling + lissage."""
        print(f"[COLORMAP] Génération bruit Perlin (scale={scale})...")
        
        small_h = self.height // scale
        small_w = self.width // scale
        
        noise = np.random.rand(small_h + 1, small_w + 1).astype(np.float32) * 255
        noise = cv2.resize(noise, (self.width, self.height), interpolation=cv2.INTER_CUBIC)
        noise = cv2.GaussianBlur(noise, (15, 15), 2.0)
        
        return noise.astype(np.float32) / 255.0
    
    def compute_slopes(self):
        """Calcule les pentes via Sobel."""
        print("[COLORMAP] Calcul des pentes...")
        
        h_scaled = (self.heightmap_normalized * 100.0).astype(np.float32)
        sobelx = cv2.Sobel(h_scaled, cv2.CV_32F, 1, 0, ksize=3)
        sobely = cv2.Sobel(h_scaled, cv2.CV_32F, 0, 1, ksize=3)
        
        slope_raw = np.sqrt(sobelx**2 + sobely**2) * self.vertical_exaggeration
        self.slopes = np.degrees(np.arctan(slope_raw))
        
        print(f"  • Pentes: min={self.slopes.min():.1f}°, max={self.slopes.max():.1f}°")
    
    def apply_analytical_hillshading(self, azimuth=315, elevation=45):
        """
        Algorithme Hillshade SIG avancé avec ombrage directionnel réaliste.
        Azimut 315° (Nord-Ouest) avec élévation 45° pour lumière douce.
        Crée ombres portées sombres dans les vallons (Ouest) et zones éclairées aux sommets.
        """
        print(f"[COLORMAP] Analytical Hillshading SIG (azimuth={azimuth}°, élévation={elevation}°)...")
        
        if self.slopes is None:
            self.compute_slopes()
        
        # Convertir angles en radians
        azimuth_rad = np.radians(azimuth)
        elevation_rad = np.radians(elevation)
        
        # Gradient X et Y (pour direction de la pente)
        h_scaled = (self.heightmap_normalized * 100.0).astype(np.float32)
        
        # Gradients Sobel avec facteur Z RÉDUIT
        Z = 1.2  # RÉDUIT (était 3.0) pour moins d'intensité brute
        
        gx1 = cv2.Sobel(h_scaled, cv2.CV_32F, 1, 0, ksize=3)
        gy1 = cv2.Sobel(h_scaled, cv2.CV_32F, 0, 1, ksize=3)
        
        # Normaliser gradients
        magnitude = np.sqrt(gx1**2 + gy1**2)
        gx_norm = gx1 / (magnitude + 1e-8)
        gy_norm = gy1 / (magnitude + 1e-8)
        
        # Lumière directionelle: produit scalaire entre normale de surface et direction lumière
        # Normal = (-gx, -gy, Z) / magnitude
        # Light direction = (sin(az)cos(el), cos(az)cos(el), sin(el))
        light_x = np.sin(azimuth_rad) * np.cos(elevation_rad)
        light_y = np.cos(azimuth_rad) * np.cos(elevation_rad)
        light_z = np.sin(elevation_rad)
        
        # Normale de surface normalisée avec facteur Z RÉDUIT
        norm_mag = np.sqrt(gx1**2 + gy1**2 + Z**2)
        nx = -gx1 / norm_mag
        ny = -gy1 / norm_mag
        nz = Z / norm_mag
        
        # Produit scalaire = ombrage
        shaded = nx * light_x + ny * light_y + nz * light_z
        
        # Normaliser à 0-1
        self.hillshade = np.clip((shaded + 1.0) / 2.0, 0, 1)
        
        # Accentuation subtile des vallons (-5%) et crêtes (+5%)
        valley_mask = (magnitude > np.percentile(magnitude, 40))
        self.hillshade[valley_mask] *= 0.95  # -5% pour vallons (subtil)
        
        ridge_mask = (magnitude > np.percentile(magnitude, 85))
        self.hillshade[ridge_mask] *= 1.05  # +5% pour crêtes (subtil)
        
        self.hillshade = np.clip(self.hillshade, 0, 1)
        
        print(f"  OK Ombrage SIG applique (intensite Z reduite a {Z})")
    
    def create_hypsometric_palette(self, altitude):
        """
        Palette hypsométrique SIG optimisée.
        Priorité: Eau en bleu satellite, terrains lumineux, relief visible.
        """
        # Normaliser altitude 0-1
        alt_norm = np.clip(altitude, 0, 1)
        
        # NIVEAU DE MER: 0.15 (15% altitude la plus basse)
        sea_level = 0.15
        
        # Couleurs SIG optimisées
        # Eau: Bleu satellite (R:60, G:120, B:180) = BGR (180, 120, 60)
        water_color = np.array([180, 120, 60], dtype=np.float32)
        
        # Basses terres: VERT PRINTANIER (R:120, G:160, B:80) = BGR (80, 160, 120)
        plain_low_color = np.array([80, 160, 120], dtype=np.float32)
        
        # Plaines: Vert plus clair
        plain_high_color = np.array([120, 180, 100], dtype=np.float32)
        
        # Plateaux: BEIGE SABLE (R:220, G:210, B:180) = BGR (180, 210, 220)
        plateau_color = np.array([180, 210, 220], dtype=np.float32)
        
        # Collines: Beige ocre
        hills_color = np.array([160, 180, 200], dtype=np.float32)
        
        # Sommets bas: Gris beige
        summit_color = np.array([180, 190, 200], dtype=np.float32)
        
        # Crêtes: Gris clair (roches)
        ridge_color = np.array([210, 210, 210], dtype=np.float32)
        
        # Interpolation linéaire par zone
        result = np.zeros((altitude.shape[0], altitude.shape[1], 3), dtype=np.float32)
        
        # Zone 0.0-0.15: EAU (BLEU - priorité!)
        mask = alt_norm <= sea_level
        result[mask] = water_color
        
        # Zone 0.15-0.30: Plaines basses (vert saturé)
        mask = (alt_norm > sea_level) & (alt_norm < 0.30)
        t = ((alt_norm[mask] - sea_level) / (0.30 - sea_level))
        result[mask] = plain_low_color * (1 - t[:, np.newaxis]) + plain_high_color * t[:, np.newaxis]
        
        # Zone 0.30-0.50: Plateaux (beige très clair)
        mask = (alt_norm >= 0.30) & (alt_norm < 0.50)
        t = ((alt_norm[mask] - 0.30) / 0.20)
        result[mask] = plain_high_color * (1 - t[:, np.newaxis]) + plateau_color * t[:, np.newaxis]
        
        # Zone 0.50-0.70: Collines (ocre clair)
        mask = (alt_norm >= 0.50) & (alt_norm < 0.70)
        t = ((alt_norm[mask] - 0.50) / 0.20)
        result[mask] = plateau_color * (1 - t[:, np.newaxis]) + hills_color * t[:, np.newaxis]
        
        # Zone 0.70-0.85: Sommets bas (brun clair)
        mask = (alt_norm >= 0.70) & (alt_norm < 0.85)
        t = ((alt_norm[mask] - 0.70) / 0.15)
        result[mask] = hills_color * (1 - t[:, np.newaxis]) + summit_color * t[:, np.newaxis]
        
        # Zone 0.85-1.0: Crêtes (gris très clair)
        mask = alt_norm >= 0.85
        t = ((alt_norm[mask] - 0.85) / 0.15)
        result[mask] = summit_color * (1 - t[:, np.newaxis]) + ridge_color * t[:, np.newaxis]
        
        return result.astype(np.uint8), sea_level
    
    def create_biome_masks(self):
        """Crée les masques de biomes basés sur pentes et altitude."""
        print("[COLORMAP] Création masques biomes...")
        
        if self.slopes is None:
            self.compute_slopes()
        
        # Masque eau: utiliser seuil plus élevé pour capturer plus d'eau
        # 0.15 = 15% altitude la plus basse
        water_threshold = 0.15
        water_mask = self.heightmap_normalized < water_threshold
        
        print(f"  [DEBUG] Seuil eau: {water_threshold}")
        print(f"  [DEBUG] Pixels eau détectés: {np.sum(water_mask)} / {water_mask.size}")
        
        # Pentes pour déterminer biome (SAUF eau)
        terrain_mask = ~water_mask
        
        # Forêt = zones pentues (40% des terres)
        terrain_slopes = self.slopes.copy()
        terrain_slopes[~terrain_mask] = -999  # Exclure eau
        forest_threshold = np.percentile(terrain_slopes[terrain_mask], 60)
        forest_mask = (self.slopes > forest_threshold) & terrain_mask
        
        # Roche = très pentue (15% des terres)
        rock_threshold = np.percentile(terrain_slopes[terrain_mask], 85)
        rock_mask = (self.slopes > rock_threshold) & terrain_mask
        
        # Plaine = le reste des terres
        plain_mask = ~forest_mask & ~rock_mask & ~water_mask
        
        print(f"  • Eau: {np.sum(water_mask)} pixels")
        print(f"  • Forêt: {np.sum(forest_mask)} pixels")
        print(f"  • Plaine: {np.sum(plain_mask)} pixels")
        print(f"  • Roche: {np.sum(rock_mask)} pixels")
        
        return forest_mask, plain_mask, rock_mask, water_mask
    
    def apply_texture_blending(self, forest_mask, plain_mask, rock_mask, water_mask):
        """
        CARTE TOPOGRAPHIQUE AVANCÉE avec:
        - Palette hypsométrique (couleurs basées altitude)
        - Hillshade intense (Lambertian reflectance, éclairage rasant)
        - Superposition masques biomes (forêt texturée, pentes marquées)
        - Aspect "papier" (désaturation)
        - Bleu d'eau visible
        """
        print("[COLORMAP] Rendu Topographique Avance...")
        print("  * Palette hypsometrique (riviere -> cretes)")
        print("  * Hillshade intense (Lambertian)")
        print("  * Superposition masques biomes")
        print("  * Aspect papier (desaturation)")
        
        # ÉTAPE 1: Créer palette hypsométrique de base
        print("[COLORMAP] Etape 1: Palette hypsometrique...")
        palette_result = self.create_hypsometric_palette(self.heightmap_normalized)
        self.colormap, self.sea_level = palette_result[0], palette_result[1]
        
        # ÉTAPE 1b: Créer masque eau AVANT hillshade (priorité absolue)
        print("[COLORMAP] Etape 1b: Masque eau prioritaire (seuil=0.15)...")
        water_mask_sea = self.heightmap_normalized < 0.15
        # Fusionner avec masque rivière si disponible
        if hasattr(self, 'water_mask_river') and self.water_mask_river is not None:
            self.water_mask_final = (water_mask_sea | self.water_mask_river).astype(bool)
        else:
            self.water_mask_final = water_mask_sea.astype(bool)
        
        if np.any(self.water_mask_final):
            # Appliquer bleu satellite (R:60, G:120, B:180) = BGR (180, 120, 60)
            water_blue = np.array([180, 120, 60], dtype=np.uint8)
            self.colormap[self.water_mask_final] = water_blue
            print(f"  [OK] {np.sum(self.water_mask_final)} pixels d'eau masque prioritaire")
        
        # ÉTAPE 2: Appliquer hillshade avec formule LUMINEUSE (0.7 + 0.3*Hillshade)
        print("[COLORMAP] Etape 2: Ombrage lumineux (ColorMap * (0.7 + 0.3*Hillshade))...")
        if self.hillshade is None:
            self.apply_analytical_hillshading()
        
        # Formule SIG optimisée: ColorMap * (0.7 + 0.3 * Hillshade)
        # Garantit 70% de couleur d'origine même en ombre totale
        # Exclure eau de l'ombrage (garder lumineuse et plate)
        for c in range(3):
            colormap_float = self.colormap[:,:,c].astype(np.float32) / 255.0
            # Formule: 0.7 + 0.3 * Hillshade
            blend_factor = 0.7 + 0.3 * self.hillshade
            blended = colormap_float * blend_factor
            # Appliquer SEULEMENT sur terrain, pas sur eau
            result = np.where(
                self.water_mask_final,
                colormap_float * 255,  # Eau inchangée (lumineuse)
                blended * 255  # Terrain avec ombrage
            )
            self.colormap[:,:,c] = result.astype(np.uint8)
        
        # ÉTAPE 3: Eau réaffichée en bleu après hillshade
        print("[COLORMAP] Etape 3: Eau bleu satellite apres hillshade...")
        if np.any(self.water_mask_final):
            # Réappliquer bleu satellite pour garantir
            water_blue = np.array([180, 120, 60], dtype=np.uint8)
            self.colormap[self.water_mask_final] = water_blue
            print(f"  [OK] {np.sum(self.water_mask_final)} pixels eau re-affichee bleu")
        
        # ÉTAPE 4: Superposer les masques de biomes
        print("[COLORMAP] Etape 4: Superposition masques biomes...")
        
        # Générer bruit Perlin pour texture forêt
        self.perlin_noise_small = self.generate_perlin_noise(scale=20)
        
        # Forêt: vert texturé par-dessus le relief
        # IMPORTANT: Exclure eau (self.water_mask_final) de la forêt
        forest_mask_bool = forest_mask.astype(bool) & ~self.water_mask_final
        if np.any(forest_mask_bool):
            noise_vals = self.perlin_noise_small[forest_mask_bool]
            
            # Couleur forêt: vert moyen
            forest_color_bgr = np.array([60, 130, 80], dtype=np.float32)
            
            # Appliquer avec variation texture
            for c in range(3):
                base = self.colormap[forest_mask_bool, c].astype(np.float32)
                # Mélange: 60% couleur forêt, 40% relief sous-jacent
                texture_var = (noise_vals - 0.5) * 0.1
                final = forest_color_bgr[c] * 0.6 + base * 0.4 + texture_var * 20
                self.colormap[forest_mask_bool, c] = np.clip(final, 0, 255).astype(np.uint8)
        
        # Pentes: marquer avec assombrissement léger
        slope_threshold = np.percentile(self.slopes, 75)
        steep_slope_mask = (self.slopes > slope_threshold) & ~self.water_mask_final & ~forest_mask_bool
        
        if np.any(steep_slope_mask):
            # Assombrir pentes pour marquer cassure du relief
            for c in range(3):
                self.colormap[steep_slope_mask, c] = (
                    self.colormap[steep_slope_mask, c].astype(float) * 0.85
                ).astype(np.uint8)
        
        # HIGHLIGHTS: Eclaircir les cretes FACE A LA LUMIERE (azimut -45 = Nord-Ouest)
        print("[COLORMAP] Ajout highlights sur cretes (relief face a lumiere)...")
        
        # Calculer direction des pentes (face à la lumière ou non)
        # Important: convertir en float32 pour Sobel
        heightmap_float32 = self.heightmap.astype(np.float32)
        gx = cv2.Sobel(heightmap_float32, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(heightmap_float32, cv2.CV_32F, 0, 1, ksize=3)
        
        # Direction lumiere: azimut -45 (NW), elevation 45
        light_az = np.radians(-45)
        light_el = np.radians(45)
        
        light_x = np.cos(light_el) * np.sin(light_az)  # NO = -45
        light_y = np.cos(light_el) * np.cos(light_az)
        
        # Produit scalaire gradient · direction_lumière
        # Positif = pente face à la lumière (crête ÉCLAIRÉE)
        gx_norm = gx / (np.sqrt(gx**2 + gy**2) + 1e-8)
        gy_norm = gy / (np.sqrt(gx**2 + gy**2) + 1e-8)
        
        slope_to_light = gx_norm * light_x + gy_norm * light_y
        
        # Sélectionner pentes face à la lumière (slope_to_light > 0.3) et pentes fortes
        highlight_mask = (slope_to_light > 0.3) & (self.slopes > np.percentile(self.slopes, 60)) & ~self.water_mask_final
        
        if np.any(highlight_mask):
            # Éclaircir les crêtes face à la lumière (vibrer le relief)
            intensity = np.clip(slope_to_light[highlight_mask], 0, 1)
            for c in range(3):
                base = self.colormap[highlight_mask, c].astype(np.float32)
                # Ajouter 15% de blanc pour faire "vibrer" les crêtes
                highlighted = base + (255 - base) * intensity[:] * 0.15
                self.colormap[highlight_mask, c] = np.clip(highlighted, 0, 255).astype(np.uint8)
            
            print(f"  [OK] {np.sum(highlight_mask)} pixels de cretes illuminees")
        
        # ÉTAPE 5: Desaturation subtile (SAUF eau)
        print("[COLORMAP] Etape 5: Desaturation naturelle (sauf eau)...")
        
        # Convertir en HSV pour désaturation sélective
        colormap_hsv = cv2.cvtColor(self.colormap, cv2.COLOR_BGR2HSV).astype(np.float32)
        
        # Réduire saturation 60% SAUF sur eau (garder eau vive)
        # Appliquer SEULEMENT sur terrain
        terrain_mask = ~self.water_mask_final
        colormap_hsv[terrain_mask, 1] *= 0.60  # -40% saturation terrain
        colormap_hsv = np.clip(colormap_hsv, 0, 255).astype(np.uint8)
        self.colormap = cv2.cvtColor(colormap_hsv, cv2.COLOR_HSV2BGR)
        
        # ÉTAPE 6: GARANTIR EAU BLEUE APRÈS TOUTES LES OPÉRATIONS
        print("[COLORMAP] Etape 6: Eau bleu satellite (post-processing final)...")
        if np.any(self.water_mask_final):
            # Bleu satellite vif: (R:60, G:120, B:180) = BGR (180, 120, 60)
            water_blue = np.array([180, 120, 60], dtype=np.uint8)
            self.colormap[self.water_mask_final] = water_blue
            print(f"  [OK] {np.sum(self.water_mask_final)} pixels eau bleu satellite (priorite absolue)")
        
        print(f"  [OK] Carte topographique avancee generee")
    
    def apply_hillshade_overlay(self, strength=0.40, water_mask=None):
        """
        Fusion Overlay intensifiee pour carte topographique.
        Force elevee pour faire ressortir le relief avec eclairage rasant.
        NE PAS appliquer sur l'eau pour garder le bleu visible.
        """
        print(f"[COLORMAP] Fusion Overlay Topographique (force={strength:.2f})...")
        
        if self.hillshade is None:
            self.apply_analytical_hillshading()
        
        # Intensifier le hillshade avec power curve
        hillshade_intense = np.power(self.hillshade, 0.75)
        
        # IMPORTANT: Utiliser self.water_mask_final (altitude-based) au lieu de water_mask (biome-based)
        if self.water_mask_final is not None:
            terrain_mask = ~self.water_mask_final
        else:
            terrain_mask = np.ones(hillshade_intense.shape, dtype=bool)
        
        for c in range(3):
            colormap_float = self.colormap[:,:,c].astype(np.float32) / 255.0
            
            # Blend formula: ColorMap * (0.7 + 0.3 * Hillshade)
            blend_factor = 0.7 + 0.3 * hillshade_intense
            blended = colormap_float * blend_factor
            blended = np.clip(blended, 0, 1)
            
            # Appliquer SEULEMENT sur terrain (pas eau)
            self.colormap[:,:,c] = np.where(
                terrain_mask,
                (blended * 255).astype(np.uint8),
                self.colormap[:,:,c]  # Eau lumineuse inchangée
            )
        
        print(f"  [OK] Relief amplifie (ombres rasantes, cassures marquees)")
    
    def generate_satellite_colormap(self):
        """Pipeline complet de génération."""
        print("\n" + "="*60)
        print("SATELLITE COLORMAP GENERATOR")
        print("="*60)
        
        # Étape 1: Calculs de base
        self.compute_slopes()
        self.apply_analytical_hillshading()
        
        # Étape 2: Masques biomes
        forest_mask, plain_mask, rock_mask, water_mask = self.create_biome_masks()
        
        # Étape 3: Rendu topographique avancé (remplace blending simple)
        self.apply_texture_blending(forest_mask, plain_mask, rock_mask, water_mask)
        
        # Étape 4: Ombrage overlay INTENSE pour relief visible (SAUF eau)
        self.apply_hillshade_overlay(strength=0.40, water_mask=water_mask)
        
        # Étape 7: GARANTIR EAU BLEUE APRÈS TOUS LES TRAITEMENTS
        print("[COLORMAP] Etape 7: Eau bleu satellite (final apres hillshade)...")
        if np.any(self.water_mask_final):
            water_blue = np.array([180, 120, 60], dtype=np.uint8)
            self.colormap[self.water_mask_final] = water_blue
            print(f"  [OK] {np.sum(self.water_mask_final)} pixels eau garantie bleue")
        
        print("\n" + "="*60)
        print("CARTE TOPOGRAPHIQUE SIG GENEREE [OK]")
        print("="*60)
        
        return self.colormap
    
    def save_colormap(self, filename="satellite_colormap.png"):
        """Sauvegarde la colormap."""
        output_path = os.path.join(self.output_dir, filename)
        
        # Utiliser cv2.imwrite directement (sauvegarde BGR tel quel)
        # Ne PAS utiliser PIL car elle interprete BGR comme RGB
        cv2.imwrite(output_path, self.colormap)
        
        print(f"\n[OK] Colormap sauvegardee: {output_path}")
        
        return output_path


def generate_satellite_colormap_from_heightmap(heightmap_path, output_dir="output"):
    """
    Fonction wrapper simple pour générer une colormap satellite.
    
    Args:
        heightmap_path: Chemin vers heightmap
        output_dir: Répertoire de sortie
        
    Returns:
        Chemin vers colormap générée
    """
    generator = SatelliteColormapGenerator(heightmap_path, output_dir=output_dir)
    colormap = generator.generate_satellite_colormap()
    colormap_path = generator.save_colormap("satellite_colormap.png")
    
    return colormap_path
