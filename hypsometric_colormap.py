#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hypsometric Colormap Generator

Génère une colormap hypsométrique pure à partir d'une heightmap.
Gradient basé sur l'altitude avec interpolation lisse.

Gradient d'altitude:
- 0%-10%: Vert profond (#2ca25f) → Vert clair (#addd8e)
- 10%-50%: Jaune (#fec44f) → Orange clair (#ffb347)
- 50%-90%: Orange vif → Rouge brique (#d95f0e)
- >90%: Rouge sombre/Brun (#993404)
"""

import numpy as np
from PIL import Image
import os
from scipy.interpolate import interp1d
import matplotlib.pyplot as plt
import cv2


class HypsometricColormapGenerator:
    """Générateur de colormap hypsométrique."""
    
    def __init__(self, heightmap_path, output_dir="output"):
        """
        Initialise le générateur avec altitudes ABSOLUES.
        
        Args:
            heightmap_path: Chemin vers la heightmap (PNG/TGA/ASC)
            output_dir: Répertoire de sortie
        """
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        
        # Charger heightmap
        self.heightmap_original = self._load_heightmap(heightmap_path)
        self.height, self.width = self.heightmap_original.shape
        
        self.h_min = float(np.min(self.heightmap_original))
        self.h_max = float(np.max(self.heightmap_original))
        
        print(f"[HYPSOMETRIC] Heightmap chargée: {self.width}×{self.height}px")
        print(f"[HYPSOMETRIC] Min: {self.h_min:.1f}m, Max: {self.h_max:.1f}m")
        
        # Normaliser 0-1
        self.heightmap_normalized = (self.heightmap_original - self.h_min) / (self.h_max - self.h_min + 1e-6)
        
        # Définir zones d'altitude ABSOLUES (fixes pour toutes les maps)
        self._define_altitude_zones()
        
        # Palette hypsométrique basée sur zones absolues
        self.palette = self._build_hypsometric_palette()
        
    def _load_heightmap(self, path):
        """Charge une heightmap (PNG, TGA, ASC)."""
        path = str(path)
        
        if path.lower().endswith('.asc'):
            return self._load_asc(path)
        else:
            img = Image.open(path)
            heightmap = np.array(img)
            
            # Convertir en grayscale si RGB
            if len(heightmap.shape) == 3:
                if heightmap.shape[2] == 4:  # RGBA
                    heightmap = heightmap[:, :, :3]
                heightmap = np.mean(heightmap, axis=2)
            
            return heightmap.astype(float)
    
    def _load_asc(self, path):
        """Charge un fichier ASC (ESRI Grid format)."""
        with open(path, 'r') as f:
            headers = {}
            for _ in range(6):
                line = f.readline().strip().split()
                headers[line[0].lower()] = float(line[1])
            
            data = np.loadtxt(f)
            return data
    
    def _define_altitude_zones(self):
        """
        Définit les zones d'altitude ABSOLUES (fixes).
        Indépendant de chaque heightmap.
        """
        # Zones SIG standard (couvrent -500m à +3000m)
        # Couleurs BGR (format OpenCV)
        self.altitude_zones = [
            {"min": -500, "max": 0, "label": "🌊 Eau/Dépression", "color": (255, 0, 0)},      # Bleu pur
            {"min": 0, "max": 100, "label": "🌾 Plaines basses", "color": (0, 200, 50)},      # Vert clair
            {"min": 100, "max": 300, "label": "🏞️ Collines", "color": (0, 255, 255)},        # Jaune
            {"min": 300, "max": 600, "label": "🏔️ Montagnes", "color": (50, 100, 200)},      # Rouge orangé
            {"min": 600, "max": 1200, "label": "⛰️ Hauts pics", "color": (0, 50, 255)},       # Rouge vif
            {"min": 1200, "max": 3000, "label": "❄️ Sommets", "color": (128, 128, 128)},    # Gris
        ]
        
        print(f"[HYPSOMETRIC] Zones d'altitude absolues définies")
        for zone in self.altitude_zones:
            print(f"  {zone['label']}: {zone['min']:.0f}m - {zone['max']:.0f}m")
    
    def _build_hypsometric_palette(self):
        """
        Construit la palette basée sur zones d'altitude ABSOLUES.
        Chaque zone a sa couleur propre (pas d'interpolation entre zones).
        """
        alt_min_all = -500
        alt_max_all = 3000
        alt_range = alt_max_all - alt_min_all
        
        # Créer palette 256 niveaux (chaque index = 1% de -500 à 3000m)
        palette = np.zeros((256, 3), dtype=np.uint8)
        
        for idx in range(256):
            # Altitude réelle correspondant à cet index
            altitude = alt_min_all + (idx / 256.0) * alt_range
            
            # Trouver la zone appropriée et utiliser sa couleur SANS interpolation
            color_bgr = None
            for zone in self.altitude_zones:
                if zone["min"] <= altitude < zone["max"]:
                    color_bgr = np.array(zone["color"], dtype=np.uint8)
                    break
            
            # Si pas trouvé (ex. > 3000m), utiliser dernière zone
            if color_bgr is None:
                color_bgr = np.array(self.altitude_zones[-1]["color"], dtype=np.uint8)
            
            palette[idx] = color_bgr
        
        return palette
    
    def get_altitude_zones(self):
        """
        Retourne les zones d'altitude pour affichage dans la légende.
        Utile pour app.py
        """
        return self.altitude_zones
    
    def generate(self, smooth=True):
        """
        Génère la colormap hypsométrique avec altitudes ABSOLUES.
        Chaque couleur représente une zone d'altitude réelle (en mètres).
        
        Args:
            smooth: Appliquer lissage bilinéaire
        
        Returns:
            (Image PIL, array colormap BGR)
        """
        # Créer la colormap
        colormap = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        
        # Mapper chaque pixel selon sa vraie altitude
        alt_min_all = -500  # Minimum absolu
        alt_max_all = 3000  # Maximum absolu
        alt_range = alt_max_all - alt_min_all
        
        # Normaliser les altitudes réelles à indices palette (0-255)
        altitude_indices = np.clip(
            ((self.heightmap_original - alt_min_all) / alt_range) * 255,
            0, 255
        ).astype(np.uint8)
        
        # Appliquer la palette
        for h in range(self.height):
            for w in range(self.width):
                idx = altitude_indices[h, w]
                colormap[h, w] = self.palette[idx]
        
        if smooth:
            # Lissage bilinéaire pour éviter les escaliers
            colormap = cv2.resize(
                colormap,
                (self.width * 2, self.height * 2),
                interpolation=cv2.INTER_LINEAR
            )
            colormap = cv2.resize(
                colormap,
                (self.width, self.height),
                interpolation=cv2.INTER_LINEAR
            )
        
        # Convertir en PIL Image (RGB)
        colormap = colormap.astype(np.uint8)
        colormap_rgb = cv2.cvtColor(colormap, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(colormap_rgb, mode='RGB')
        
        return img, colormap
    
    # ──────────────────────────────────────────────────────────────────
    # ENRICHISSEMENT MORPHOLOGIQUE (TPI + Flow + Dépressions)
    # ──────────────────────────────────────────────────────────────────

    def _compute_tpi_local(self, window_size=25):
        """TPI : altitude pixel - moyenne locale. Crêtes > 0, creux < 0."""
        from scipy.ndimage import uniform_filter
        h = self.heightmap_original.astype(np.float32)
        return h - uniform_filter(h, size=window_size)

    def _compute_flow_log(self):
        """Flow accumulation D8, retourné en log(1+n)."""
        h = self.heightmap_original.astype(np.float32)
        rows, cols = h.shape
        N = rows * cols

        h_pad = np.pad(h, 1, mode='edge')
        neighbors = np.stack([
            h_pad[0:rows,   0:cols],
            h_pad[0:rows,   1:cols+1],
            h_pad[0:rows,   2:cols+2],
            h_pad[1:rows+1, 0:cols],
            h_pad[1:rows+1, 2:cols+2],
            h_pad[2:rows+2, 0:cols],
            h_pad[2:rows+2, 1:cols+1],
            h_pad[2:rows+2, 2:cols+2],
        ], axis=0)

        dr = np.array([-1, -1, -1,  0,  0,  1,  1,  1])
        dc = np.array([-1,  0,  1, -1,  1, -1,  0,  1])

        min_idx = np.argmin(neighbors, axis=0)
        r_g, c_g = np.mgrid[0:rows, 0:cols]
        target_r = np.clip(r_g + dr[min_idx], 0, rows - 1)
        target_c = np.clip(c_g + dc[min_idx], 0, cols - 1)
        flow_to = (target_r * cols + target_c).flatten()

        min_val = neighbors[min_idx, r_g, c_g]
        is_sink = (min_val >= h).flatten()
        flow_to[is_sink] = np.arange(N)[is_sink]

        acc = np.ones(N, dtype=np.float32)
        for i in np.argsort(-h.flatten()):
            t = flow_to[i]
            if t != i:
                acc[t] += acc[i]

        return np.log1p(acc.reshape(rows, cols))

    def _compute_depression_mask(self):
        """Dépressions fermées : minima locaux hors zone eau."""
        from scipy.ndimage import minimum_filter
        h = self.heightmap_original.astype(np.float32)
        water_threshold = np.percentile(h, 15)
        local_min = minimum_filter(h, size=3)
        return (h <= local_min + 0.01) & (h > water_threshold)

    def add_enrichment(self, colormap, tpi_strength=0.18, flow_strength=0.45, depression_strength=0.4):
        """
        Enrichit la colormap hypsométrique avec les données morphologiques.

        - TPI : modulation de luminosité (crêtes +, creux -)
        - Flow D8 : filets bleutés sur les talwegs (top 5%)
        - Dépressions : teinte cyan sur les cavités fermées

        Args:
            colormap : array (H, W, 3) BGR
            tpi_strength : intensité de la modulation TPI (0-1)
            flow_strength : intensité de la teinte bleue sur talwegs (0-1)
            depression_strength : intensité de la teinte cyan sur dépressions (0-1)

        Returns:
            array (H, W, 3) BGR enrichi
        """
        print("[HYPSOMETRIC] Enrichissement morphologique (TPI + Flow + Dépressions)...")
        result = colormap.astype(np.float32)

        # 1. TPI — modulation luminosité
        tpi = self._compute_tpi_local(window_size=25)
        sigma = np.std(tpi)
        if sigma > 0:
            tpi_norm = np.clip(tpi / (sigma * 3), -1.0, 1.0)
            factor = 1.0 + tpi_strength * tpi_norm          # [0.82 … 1.18]
            result *= np.stack([factor] * 3, axis=2)
            print(f"  • TPI appliqué (σ={sigma:.1f}m, force={tpi_strength})")

        # 2. Flow D8 — teinte bleue sur talwegs (top 5%)
        print("  • Calcul flow accumulation...")
        flow = self._compute_flow_log()
        threshold = np.percentile(flow, 95)
        flow_mask = flow > threshold
        # BGR : boost Blue, réduction Green+Red
        blend = np.array([1.0 + flow_strength, 1.0 - flow_strength * 0.5, 1.0 - flow_strength * 0.5])
        result[flow_mask] = result[flow_mask] * blend
        print(f"  • Flow : {np.sum(flow_mask)} px talwegs colorés")

        # 3. Dépressions fermées — teinte cyan
        dep_mask = self._compute_depression_mask()
        if np.any(dep_mask):
            blend_dep = np.array([1.0 + depression_strength * 0.6, 1.0 - depression_strength * 0.2, 1.0 - depression_strength * 0.3])
            result[dep_mask] = result[dep_mask] * blend_dep
            print(f"  • Dépressions : {np.sum(dep_mask)} px teintés")

        return np.clip(result, 0, 255).astype(np.uint8)

    def add_hillshading(self, colormap, strength=0.3):
        """
        Ajoute du hillshading pour améliorer la profondeur 3D.
        
        Args:
            colormap: Array colormap (H, W, 3)
            strength: Force du hillshading (0-1)
        
        Returns:
            Array colormap modifiée
        """
        # Calculer gradients (pentes)
        gy, gx = np.gradient(self.heightmap_normalized)
        
        # Ombrage directionnel (lumière 315°, élévation 45°)
        azimuth = np.radians(315)
        elevation = np.radians(45)
        
        # Vecteur lumière
        lx = np.cos(azimuth) * np.cos(elevation)
        ly = np.sin(azimuth) * np.cos(elevation)
        lz = np.sin(elevation)
        
        # Normale du terrain
        norm = np.sqrt(gx**2 + gy**2 + 1)
        nx = -gx / norm
        ny = -gy / norm
        nz = 1 / norm
        
        # Produit scalaire (cosinus angle d'incidence)
        hillshade = np.clip(nx * lx + ny * ly + nz * lz, 0, 1)
        
        # Appliquer ombrage
        hillshade = 0.5 + strength * (hillshade - 0.5)  # Contraste
        hillshade = np.stack([hillshade] * 3, axis=2)
        
        colormap_shaded = (colormap.astype(float) * hillshade).astype(np.uint8)
        
        return colormap_shaded
    
    def save(self, output_path="color_map_hypsometric.png", add_hillshade=True, add_enrichment=False):
        """
        Génère et sauvegarde la colormap.

        Args:
            output_path: Chemin de sortie
            add_hillshade: Ajouter hillshading
            add_enrichment: Ajouter enrichissement morphologique (TPI + Flow + Dépressions)

        Returns:
            PIL Image
        """
        img, colormap_array = self.generate(smooth=True)

        if add_enrichment:
            colormap_array = self.add_enrichment(colormap_array)

        if add_hillshade:
            colormap_array = self.add_hillshading(colormap_array, strength=0.2)

        colormap_array_rgb = cv2.cvtColor(colormap_array, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(colormap_array_rgb, mode='RGB')

        full_path = os.path.join(self.output_dir, output_path)
        img.save(full_path)

        print(f"[HYPSOMETRIC] ✅ Colormap sauvegardée: {full_path}")
        print(f"[HYPSOMETRIC] Résolution: {img.width}×{img.height}px")
        print(f"[HYPSOMETRIC] Zones absolues | hillshade={add_hillshade} | enrichissement={add_enrichment}")

        return img


def demo():
    """Démo rapide."""
    import sys
    
    # Chercher une heightmap
    heightmap_files = [
        "input/bornholm_ter.asc",
        "input/dem.png",
        "temp_heightmap_demo.png",
    ]
    
    heightmap_path = None
    for f in heightmap_files:
        if os.path.exists(f):
            heightmap_path = f
            break
    
    if not heightmap_path:
        print("❌ Aucune heightmap trouvée!")
        print("Utilisation: python hypsometric_colormap.py <heightmap_path>")
        sys.exit(1)
    
    # Générer colormap
    print(f"📍 Heightmap: {heightmap_path}")
    gen = HypsometricColormapGenerator(heightmap_path)
    gen.save("color_map_hypsometric.png", add_hillshade=True)
    print("✅ Terminé!")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        heightmap_path = sys.argv[1]
        output_path = sys.argv[2] if len(sys.argv) > 2 else "color_map_hypsometric.png"
        
        gen = HypsometricColormapGenerator(heightmap_path)
        gen.save(output_path, add_hillshade=True)
    else:
        demo()
