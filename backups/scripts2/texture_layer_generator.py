# -*- coding: utf-8 -*-
"""
Texture Layer Generator for Reforger
Génère des masques de textures noir/blanc basés sur le slope
et applique des masques d'exclusion pour les zones déjà travaillées.

Phase 1: Génération 5 couches slope (PNG 8-bit + 16-bit)
Phase 2: Application masque d'exclusion sur les couches
"""

import numpy as np
import cv2
from PIL import Image
import os
import json
from datetime import datetime


class TextureLayerGenerator:
    """
    Génère des masques de textures basés sur les pentes (slope).
    Export PNG 8-bit + 16-bit pour Reforger.
    """
    
    # Catégories de slope avec seuils par défaut (en degrés)
    SLOPE_CATEGORIES = {
        'herbe': {
            'name': '🌱 Herbe/Prairie (0-3°)',
            'min': 0,
            'max': 3,
            'description': 'Terrain plat - herbe/prairie'
        },
        'terre': {
            'name': '🟤 Terre/Sol (3-12°)',
            'min': 3,
            'max': 12,
            'description': 'Pente modérée - terre/sol'
        },
        'roche_legere': {
            'name': '🪨 Roche Légère (12-25°)',
            'min': 12,
            'max': 25,
            'description': 'Pente forte - roche légère'
        },
        'roche_forte': {
            'name': '⛰️ Roche Forte (25-45°)',
            'min': 25,
            'max': 45,
            'description': 'Pente très forte - roche'
        },
        'escarpement': {
            'name': '🏔️ Escarpement (45°+)',
            'min': 45,
            'max': 90,
            'description': 'Paroi/Intraversable'
        }
    }
    
    def __init__(self, heightmap_path, output_dir="output"):
        """
        Initialise le générateur de couches texture.
        
        Args:
            heightmap_path: Chemin vers la heightmap (PNG, JPG, ou ASC)
            output_dir: Répertoire de sortie
        """
        self.heightmap_path = heightmap_path
        self.output_dir = output_dir
        self.layers_dir = os.path.join(output_dir, "texture_layers")
        
        if not os.path.exists(self.layers_dir):
            os.makedirs(self.layers_dir)
        
        # Charger heightmap (PNG, JPG, ou ASC)
        if heightmap_path.lower().endswith('.asc'):
            # Charger format ESRI ASCII Grid
            self.heightmap = self._load_asc_raster(heightmap_path)
        else:
            # Charger via PIL (PNG, JPG, etc.)
            img = Image.open(heightmap_path)
            self.heightmap = np.array(img).astype(float)
            
            # Si RGB, convertir en grayscale
            if len(self.heightmap.shape) == 3:
                self.heightmap = cv2.cvtColor(
                    self.heightmap.astype(np.uint8), 
                    cv2.COLOR_BGR2GRAY
                ).astype(float)
        
        self.height, self.width = self.heightmap.shape
        print(f"[TEXLAYER] Heightmap chargée: {self.width}×{self.height}px")
        
        # Normaliser heightmap 0-1 (FORCER float32 pour économiser RAM)
        h_min = np.min(self.heightmap)
        h_max = np.max(self.heightmap)
        if h_max > h_min:
            self.heightmap_normalized = ((self.heightmap - h_min) / (h_max - h_min)).astype(np.float32)
        else:
            self.heightmap_normalized = self.heightmap.astype(np.float32)
        
        # Caches
        self.slopes = None
        self.slope_masks = {}
        self.exclusion_mask = None
    
    def _load_asc_raster(self, filepath):
        """
        Charge un fichier ESRI ASCII Grid (.asc).
        Format:
            ncols 4097
            nrows 4097
            xllcorner 0.0
            yllcorner 0.0
            cellsize 1.0
            NODATA_value -9999
            [données numériques...]
        
        Args:
            filepath: Chemin vers le fichier .asc
            
        Returns:
            np.ndarray: Heightmap 2D
        """
        print(f"[TEXLAYER] Chargement ESRI ASCII Grid: {filepath}")
        
        with open(filepath, 'r') as f:
            # Lire en-tête
            header = {}
            for _ in range(6):
                line = f.readline().strip()
                if line:
                    parts = line.split()
                    if len(parts) >= 2:
                        key = parts[0].lower()
                        try:
                            value = float(parts[1])
                        except ValueError:
                            value = parts[1]
                        header[key] = value
            
            # Valider en-tête
            ncols = int(header.get('ncols', 0))
            nrows = int(header.get('nrows', 0))
            nodata = header.get('nodata_value', -9999)
            
            if ncols <= 0 or nrows <= 0:
                raise ValueError(f"❌ En-tête invalide: ncols={ncols}, nrows={nrows}")
            
            print(f"  • Dimensions: {ncols}×{nrows}")
            
            # Lire données
            data = []
            for line in f:
                line = line.strip()
                if line:
                    values = [float(x) for x in line.split()]
                    data.extend(values)
            
            # Convertir en array et remodeler
            data_array = np.array(data, dtype=float)
            
            # Remplacer NODATA par 0
            data_array[data_array == nodata] = 0
            
            # Remodeler en 2D (attention: ordre ligne/colonne)
            heightmap = data_array.reshape(nrows, ncols)
            
            print(f"  • Chargé: {heightmap.shape[0]}×{heightmap.shape[1]} pixels")
            print(f"  • Valeurs: min={heightmap.min():.2f}, max={heightmap.max():.2f}")
            
            return heightmap
    
    def compute_slopes(self):
        """Calcule les pentes via Sobel."""
        print("[TEXLAYER] Calcul des pentes...")
        
        if self.slopes is not None:
            print("[TEXLAYER] Slopes déjà calculées (cache)")
            return
        
        h_scaled = (self.heightmap_normalized * 100.0).astype(np.float32)
        sobelx = cv2.Sobel(h_scaled, cv2.CV_32F, 1, 0, ksize=3)
        sobely = cv2.Sobel(h_scaled, cv2.CV_32F, 0, 1, ksize=3)
        
        slope_raw = np.sqrt(sobelx**2 + sobely**2) * 10.0
        self.slopes = np.degrees(np.arctan(slope_raw))
        
        print(f"  • Pentes: min={self.slopes.min():.1f}°, max={self.slopes.max():.1f}°")
        print(f"  • Moyenne: {self.slopes.mean():.1f}°")
    
    def analyze_slope_distribution(self):
        """
        Analyse la distribution des pentes et retourne les percentiles adaptatifs.
        Cela permet d'adapter les masques de textures à la géométrie réelle de chaque heightmap.
        
        Returns:
            Dict avec statistiques de distribution par catégorie
            Exemple:
            {
                'herbe': {'pct': 20, 'threshold': 2.5, 'count': 2347537},
                'terre': {'pct': 40, 'threshold': 10.0, 'count': 308708},
                ...
            }
        """
        print("[TEXLAYER] Analyse distribution des pentes...")
        
        if self.slopes is None:
            self.compute_slopes()
        
        # Percentiles cibles pour chaque catégorie
        # (% du terrain qui devrait être dans chaque catégorie)
        percentile_targets = {
            'herbe': 20,        # 20% les moins pentues
            'terre': 40,        # 40% (cumul)
            'roche_legere': 65, # 65% (cumul)
            'roche_forte': 85,  # 85% (cumul)
            'escarpement': 100  # 100% (cumul)
        }
        
        distribution = {}
        
        for cat_key, pct_target in percentile_targets.items():
            threshold = np.percentile(self.slopes, pct_target)
            
            # Compter les pixels dans cette zone
            if cat_key == 'herbe':
                in_zone = self.slopes <= threshold
            elif cat_key == 'escarpement':
                prev_pct = percentile_targets['roche_forte']
                prev_threshold = np.percentile(self.slopes, prev_pct)
                in_zone = self.slopes > prev_threshold
            else:
                prev_pct = percentile_targets.get(list(percentile_targets.keys())[list(percentile_targets.values()).index(pct_target) - 1])
                prev_threshold = np.percentile(self.slopes, prev_pct)
                in_zone = (self.slopes > prev_threshold) & (self.slopes <= threshold)
            
            count = np.sum(in_zone)
            pct_actual = (count / self.slopes.size) * 100
            
            distribution[cat_key] = {
                'percentile_target': pct_target,
                'threshold': float(threshold),
                'count': int(count),
                'percentage': float(pct_actual)
            }
            
            print(f"  • {cat_key}: seuil={threshold:.2f}°, {pct_actual:.1f}% des pixels")
        
        return distribution
    
    def _detect_local_minima_maxima(self, kernel_size=7):
        """
        Détecte les creux (minima locaux) et crêtes (maxima locales) dans la heightmap.
        Utilisé pour varier naturellement les textures dans les zones rocheuses.
        
        Args:
            kernel_size: Taille du kernel pour détection (pixels)
        
        Returns:
            Tuple (minima_mask, maxima_mask) - True où il y a creux/crêtes locales
        """
        print("[TEXLAYER] Détection micro-reliefs (creux/crêtes locales)...")
        
        # Utiliser la heightmap normalisée
        h_norm = (self.heightmap_normalized * 255).astype(np.uint8)
        
        # Minima locaux: morphologie
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        minima = cv2.morphologyEx(h_norm, cv2.MORPH_ERODE, kernel)
        minima_mask = (h_norm <= minima + 5)  # Tolérance de 5 pour bruit
        
        # Maxima locaux: morphologie
        maxima = cv2.morphologyEx(h_norm, cv2.MORPH_DILATE, kernel)
        maxima_mask = (h_norm >= maxima - 5)  # Tolérance de 5 pour bruit
        
        print(f"  • Creux (minima) détectés: {np.sum(minima_mask)} pixels")
        print(f"  • Crêtes (maxima) détectées: {np.sum(maxima_mask)} pixels")
        
        return minima_mask, maxima_mask
    
    def _add_rock_variations(self, masks, altitude_thresholds, pct_terre, pct_roche_light, pct_roche_heavy):
        """
        Ajoute des variations naturelles dans les zones rocheuses:
        - Terre dans les creux des roches (10-15%)
        - Herbe dans les petits creux (5%)
        
        Cela crée des transitions naturelles terrain/roche/herbe.
        
        Args:
            masks: Dict des masques à modifier
            altitude_thresholds: Dict des seuils d'altitude
            pct_*: Seuils des percentiles de pentes
        
        Returns:
            Dict masks modifiés avec variations
        """
        print("[TEXLAYER] Ajout variations naturelles dans zones rocheuses...")
        
        # Détecter micro-reliefs
        minima_mask, maxima_mask = self._detect_local_minima_maxima(kernel_size=7)
        
        alt_norm = self.heightmap_normalized
        
        # ===== VARIATION DANS ROCHE LÉGÈRE =====
        # Ajouter 10% de TERRE dans les creux des roches légères
        roche_light_base = (masks['roche_legere'] == 255)
        terre_in_roche_light = roche_light_base & minima_mask
        
        # Sélectionner aléatoirement 10% de ces creux
        if np.any(terre_in_roche_light):
            terre_light_pixels = np.where(terre_in_roche_light)
            n_pixels = len(terre_light_pixels[0])
            n_select = max(1, int(n_pixels * 0.10))  # 10%
            select_indices = np.random.choice(n_pixels, n_select, replace=False)
            
            selected_y = terre_light_pixels[0][select_indices]
            selected_x = terre_light_pixels[1][select_indices]
            
            # Transférer de roche_legere à terre
            masks['roche_legere'][selected_y, selected_x] = 0
            masks['terre'][selected_y, selected_x] = 255
            
            print(f"  • Terre ajoutée dans roche légère: {n_select} px ({n_select/n_pixels*100:.1f}%)")
        
        # Ajouter 3% de HERBE dans les minima très prononcés des roches légères
        herbe_in_roche_light = roche_light_base & minima_mask & (alt_norm < altitude_thresholds['terre_max'])
        
        if np.any(herbe_in_roche_light):
            herbe_light_pixels = np.where(herbe_in_roche_light)
            n_pixels = len(herbe_light_pixels[0])
            n_select = max(1, int(n_pixels * 0.03))  # 3%
            select_indices = np.random.choice(n_pixels, n_select, replace=False)
            
            selected_y = herbe_light_pixels[0][select_indices]
            selected_x = herbe_light_pixels[1][select_indices]
            
            # Transférer de roche_legere à herbe
            masks['roche_legere'][selected_y, selected_x] = 0
            masks['herbe'][selected_y, selected_x] = 255
            
            print(f"  • Herbe ajoutée dans roche légère: {n_select} px ({n_select/n_pixels*100:.1f}%)")
        
        # ===== VARIATION DANS ROCHE FORTE =====
        # Ajouter 15% de TERRE dans les creux des roches fortes
        roche_heavy_base = (masks['roche_forte'] == 255)
        terre_in_roche_heavy = roche_heavy_base & minima_mask
        
        if np.any(terre_in_roche_heavy):
            terre_heavy_pixels = np.where(terre_in_roche_heavy)
            n_pixels = len(terre_heavy_pixels[0])
            n_select = max(1, int(n_pixels * 0.15))  # 15%
            select_indices = np.random.choice(n_pixels, n_select, replace=False)
            
            selected_y = terre_heavy_pixels[0][select_indices]
            selected_x = terre_heavy_pixels[1][select_indices]
            
            # Transférer de roche_forte à terre
            masks['roche_forte'][selected_y, selected_x] = 0
            masks['terre'][selected_y, selected_x] = 255
            
            print(f"  • Terre ajoutée dans roche forte: {n_select} px ({n_select/n_pixels*100:.1f}%)")
        
        # Ajouter 5% de HERBE dans les minima des roches fortes
        herbe_in_roche_heavy = roche_heavy_base & minima_mask & (alt_norm < altitude_thresholds['terre_max'])
        
        if np.any(herbe_in_roche_heavy):
            herbe_heavy_pixels = np.where(herbe_in_roche_heavy)
            n_pixels = len(herbe_heavy_pixels[0])
            n_select = max(1, int(n_pixels * 0.05))  # 5%
            select_indices = np.random.choice(n_pixels, n_select, replace=False)
            
            selected_y = herbe_heavy_pixels[0][select_indices]
            selected_x = herbe_heavy_pixels[1][select_indices]
            
            # Transférer de roche_forte à herbe
            masks['roche_forte'][selected_y, selected_x] = 0
            masks['herbe'][selected_y, selected_x] = 255
            
            print(f"  • Herbe ajoutée dans roche forte: {n_select} px ({n_select/n_pixels*100:.1f}%)")
        
        return masks

    def compute_terrain_curvature(self):
        """
        Calcule la courbure du terrain (Laplacien).
        Positif = concave (creux/vallées)
        Négatif = convexe (émergences/crêtes)
        
        Returns:
            Array (H, W) avec valeurs de courbure
        """
        if not hasattr(self, 'heightmap_normalized') or self.heightmap_normalized is None:
            print("[MORPHO] Normalisant heightmap...")
            h_min = np.min(self.heightmap)
            h_max = np.max(self.heightmap)
            self.heightmap_normalized = ((self.heightmap - h_min) / (h_max - h_min + 1e-8)).astype(np.float32)
        
        # Laplacien pour détecter concavité/convexité
        h_scaled = (self.heightmap_normalized * 100).astype(np.float32)
        laplacian = cv2.Laplacian(h_scaled, cv2.CV_32F)
        return laplacian

    def detect_creux_and_emergences(self, threshold_percentile=50):
        """
        Détecte les creux (vallées) et émergences (crêtes/sommets).
        
        Args:
            threshold_percentile: Percentile pour séparer creux/émergences (50 = équilibré)
        
        Returns:
            (creux_mask, emergences_mask) - Arrays (H, W) binary (0 ou 255)
        """
        print("[MORPHO] Calcul courbure du terrain...")
        laplacian = self.compute_terrain_curvature()
        
        # Seuils dynamiques
        creux_threshold = np.percentile(laplacian, threshold_percentile)
        emergences_threshold = np.percentile(laplacian, 100 - threshold_percentile)
        
        print(f"[MORPHO] Seuils: creux={creux_threshold:.2f} | émergences={emergences_threshold:.2f}")
        
        # Masques binaires
        creux_mask = (laplacian > creux_threshold).astype(np.uint8) * 255
        emergences_mask = (laplacian < emergences_threshold).astype(np.uint8) * 255
        
        # Lisser légèrement pour éviter le bruit
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        creux_mask = cv2.morphologyEx(creux_mask, cv2.MORPH_CLOSE, kernel, iterations=1)
        emergences_mask = cv2.morphologyEx(emergences_mask, cv2.MORPH_CLOSE, kernel, iterations=1)
        
        # Exclure l'eau (pixels très bas)
        alt_norm = self.heightmap_normalized
        water_threshold = np.percentile(alt_norm, 15)
        water_mask = (alt_norm <= water_threshold)
        
        creux_mask[water_mask] = 0
        emergences_mask[water_mask] = 0
        
        # Stats
        creux_pct = (np.sum(creux_mask == 255) / (creux_mask.shape[0] * creux_mask.shape[1])) * 100
        emerg_pct = (np.sum(emergences_mask == 255) / (emergences_mask.shape[0] * emergences_mask.shape[1])) * 100
        print(f"[MORPHO]   Creux (vallées): {creux_pct:.1f}%")
        print(f"[MORPHO]   Émergences (crêtes): {emerg_pct:.1f}%")
        
        return creux_mask, emergences_mask

    def generate_adaptive_masks_with_altitude(self, altitude_thresholds=None):
        """
        Génère les 5 masques de texture avec:
        1. Filtrage par PERCENTILES des pentes (adaptatif)
        2. Filtrage par ALTITUDE DYNAMIQUE (adapté à chaque heightmap)
        3. VARIATIONS NATURELLES dans les zones rocheuses
           - Terre dans les creux (micro-reliefs)
           - Herbe dans les petits creux
        
        NOUVEAU: Les seuils d'altitude sont DYNAMIQUES et calculés
        en fonction de la distribution réelle (excluant l'eau).
        
        Args:
            altitude_thresholds: Dict personnalisé (optionnel)
        
        Returns:
            Dict avec les 5 masques adaptés + variations naturelles
        """
        print("[TEXLAYER] Génération masques ADAPTATIFS (pentes % + altitude DYNAMIQUE + variations)...")
        
        if self.slopes is None:
            self.compute_slopes()
        
        # Calculer les percentiles de pentes
        distribution = self.analyze_slope_distribution()
        
        # Normaliser altitude 0-1
        alt_norm = self.heightmap_normalized
        
        # ===== CALCUL DYNAMIQUE DES SEUILS D'ALTITUDE =====
        # NOUVEAU: Exclure l'eau de l'analyse (15% d'altitude basse)
        # pour que les seuils s'adaptent à la TERRE uniquement
        
        if altitude_thresholds is None:
            print("[TEXLAYER] Calcul DYNAMIQUE des seuils d'altitude (excluant l'eau)...")
            
            # CORRIGER: Déterminer le seuil d'eau en utilisant Otsu-like
            # L'eau c'est les zones BASSES (dépend vraiment de la heightmap)
            # Utiliser une heuristique: si < 40% d'eau probable, utiliser percentile bas
            # sinon trouver la bimodalité
            
            # Simple: calculer histogramme et trouver premier creux (séparation eau/terrain)
            # Pour l'instant, utiliser percentile adaptatif : chercher le point où la densité change
            alt_hist, alt_bins = np.histogram(alt_norm, bins=100)
            
            # Trouver le premier creux significatif (changement de pente)
            hist_diff = np.diff(alt_hist)
            # Chercher où la pente change (augmentation after decrease)
            water_percentile_estimate = 0.15  # Fallback par défaut
            
            for i in range(1, len(hist_diff) - 1):
                if hist_diff[i-1] < -100 and hist_diff[i] > 100:  # Creux significatif
                    water_percentile_estimate = alt_bins[i+1] / 1.0  # Proportion
                    break
            
            # MEILLEUR: Utiliser un percentile dynamique basé sur pixels bas
            # Compter combien de pixels sont dans les 50% d'altitude basse
            pixels_in_lower_50 = np.sum(alt_norm < 0.5)
            proportion = pixels_in_lower_50 / alt_norm.size
            
            # Si plus de 30% sont dans les basses altitudes, c'est probablement de l'eau
            if proportion > 0.30:
                water_percentile_global = np.percentile(alt_norm, min(50, int(proportion * 100)))
            else:
                water_percentile_global = np.percentile(alt_norm, 15)
            
            water_mask = alt_norm <= water_percentile_global
            
            # Afficher détection d'eau
            eau_pixels = np.sum(water_mask)
            eau_pct = (eau_pixels / alt_norm.size) * 100
            print(f"  [WATER DETECTION] Seuil: {water_percentile_global:.3f}, Pixels: {eau_pixels} ({eau_pct:.1f}%)")
            
            # Masque terrain (inverse de l'eau)
            terrain_mask = ~water_mask
            
            if np.any(terrain_mask):
                # Calculer les percentiles d'ALTITUDE SEULEMENT sur le terrain
                terrain_altitudes = alt_norm[terrain_mask]
                
                # Seuils adaptatifs basés sur percentiles du terrain
                herbe_max = np.percentile(terrain_altitudes, 20)         # 20e percentile
                terre_min = np.percentile(terrain_altitudes, 20)         # Même que herbe_max
                terre_max = np.percentile(terrain_altitudes, 50)         # 50e percentile  
                roche_light_min = np.percentile(terrain_altitudes, 60)   # 60e percentile
                roche_heavy_min = np.percentile(terrain_altitudes, 80)   # 80e percentile
                
                altitude_thresholds = {
                    'herbe_max': herbe_max,
                    'terre_min': terre_min,
                    'terre_max': terre_max,
                    'roche_light_min': roche_light_min,
                    'roche_heavy_min': roche_heavy_min,
                    'water_threshold': water_percentile_global
                }
                
                print(f"  • Seuil eau (15%): {water_percentile_global:.3f}")
                print(f"  • Herbe max (20%):  {herbe_max:.3f}")
                print(f"  • Terre: {terre_min:.3f}-{terre_max:.3f} (50%)")
                print(f"  • Roche légère (60%): {roche_light_min:.3f}")
                print(f"  • Roche forte (80%): {roche_heavy_min:.3f}")
            else:
                # Fallback si tout est eau
                altitude_thresholds = {
                    'herbe_max': 0.25,
                    'terre_min': 0.25,
                    'terre_max': 0.50,
                    'roche_light_min': 0.60,
                    'roche_heavy_min': 0.80,
                    'water_threshold': water_percentile_global
                }
        
        # ===== RECALCULER LES SEUILS DE PENTES SUR LE TERRAIN UNIQUEMENT =====
        # IMPORTANT: Les percentiles doivent être calculés sur le terrain (pas eau)
        # pour éviter les seuils figés en degrés qui ne correspondent pas à la réalité
        
        # CORRIGER: Utiliser le VRAI seuil d'eau calculé en altitude_thresholds
        # au lieu d'une valeur fixe 0.15 qui ne marche pas!
        water_threshold = altitude_thresholds.get('water_threshold', None)
        
        if water_threshold is None:
            # FALLBACK: Recalculer le seuil d'eau correctement (45% pour l'île test)
            # Utiliser le 45e percentile pour capturer les basses altitudes
            water_threshold = np.percentile(alt_norm, 45)
            print(f"  [DEBUG] water_threshold recalculé: {water_threshold:.3f} (45e percentile)")
        
        terrain_mask_pentes = alt_norm > water_threshold
        terrain_slopes = self.slopes[terrain_mask_pentes]
        
        print(f"  [DEBUG] Pixels terrain: {np.sum(terrain_mask_pentes)} / {alt_norm.size} ({100*np.sum(terrain_mask_pentes)/alt_norm.size:.1f}%)")
        
        if np.any(terrain_mask_pentes):
            # Calculer les seuils de pentes comme percentiles du terrain
            pct_20_pentes = np.percentile(terrain_slopes, 20)   # 20% pentes les plus basses
            pct_40_pentes = np.percentile(terrain_slopes, 40)   # 40%
            pct_60_pentes = np.percentile(terrain_slopes, 60)   # 60%
            pct_80_pentes = np.percentile(terrain_slopes, 80)   # 80%
            
            print(f"  [PENTES TERRAIN] 20%={pct_20_pentes:.2f}° | 40%={pct_40_pentes:.2f}° | 60%={pct_60_pentes:.2f}° | 80%={pct_80_pentes:.2f}°")
        else:
            # Fallback
            pct_20_pentes = 5.0
            pct_40_pentes = 15.0
            pct_60_pentes = 30.0
            pct_80_pentes = 45.0
        
        # Générer masques
        masks = {}
        
        # HERBE: 20% des pentes les plus basses (terrain uniquement)
        masks['herbe'] = np.zeros((self.height, self.width), dtype=np.uint8)
        herbe_condition = (self.slopes <= pct_20_pentes) & terrain_mask_pentes
        masks['herbe'][herbe_condition] = 255
        
        # TERRE: 20-40% des pentes (terrain)
        masks['terre'] = np.zeros((self.height, self.width), dtype=np.uint8)
        terre_condition = (self.slopes > pct_20_pentes) & (self.slopes <= pct_40_pentes) & terrain_mask_pentes
        masks['terre'][terre_condition] = 255
        
        # ROCHE LÉGÈRE: 40-60% des pentes
        masks['roche_legere'] = np.zeros((self.height, self.width), dtype=np.uint8)
        roche_light_condition = (self.slopes > pct_40_pentes) & (self.slopes <= pct_60_pentes) & terrain_mask_pentes
        masks['roche_legere'][roche_light_condition] = 255
        
        # ROCHE FORTE: 60-80% des pentes
        masks['roche_forte'] = np.zeros((self.height, self.width), dtype=np.uint8)
        roche_heavy_condition = (self.slopes > pct_60_pentes) & (self.slopes <= pct_80_pentes) & terrain_mask_pentes
        masks['roche_forte'][roche_heavy_condition] = 255
        
        # ESCARPEMENT: 80%+ des pentes
        masks['escarpement'] = np.zeros((self.height, self.width), dtype=np.uint8)
        escarpement_condition = (self.slopes > pct_80_pentes) & terrain_mask_pentes
        masks['escarpement'][escarpement_condition] = 255
        
        # ===== AJOUTER VARIATIONS NATURELLES DANS ROCHES =====
        masks = self._add_rock_variations(masks, altitude_thresholds, pct_40_pentes, pct_60_pentes, pct_80_pentes)
        
        # ===== DÉTECTER CREUX ET ÉMERGENCES (MORPHOLOGIE) =====
        print("\n[TEXLAYER] Détection morphologie du terrain...")
        creux_mask, emergences_mask = self.detect_creux_and_emergences(threshold_percentile=50)
        masks['creux'] = creux_mask
        masks['emergences'] = emergences_mask

        # ===== FUSION REFORGER: escarpement -> roche_forte, creux -> terre =====
        # Évite 2 surfaces supplémentaires dans Enfusion (limite 5/block).
        # escarpement (pentes extrêmes) = roche_forte visuellement
        # creux (vallées) = terre visuellement
        print("\n[TEXLAYER] Fusion escarpement -> roche_forte, creux -> terre...")
        masks['roche_forte'] = np.maximum(masks['roche_forte'], masks['escarpement'])
        masks['terre'] = np.maximum(masks['terre'], masks['creux'])
        del masks['escarpement']
        del masks['creux']

        # Afficher stats finales
        print("\n[TEXLAYER] Masques FINAUX après variations + morphologie:")
        ordered_keys = ['herbe', 'terre', 'roche_legere', 'roche_forte', 'emergences']
        for cat_key in ordered_keys:
            pixels_count = np.sum(masks[cat_key] == 255)
            percentage = (pixels_count / (self.height * self.width)) * 100
            emoji = {'creux': '🌊', 'emergences': '⛰️'}.get(cat_key, '')
            label = f"{emoji} {cat_key}".strip()
            print(f"  • {label}: {pixels_count} px ({percentage:.1f}%)")
        
        self.slope_masks = masks
        return masks
    
    def upscale_masks_for_reforger(self, masks, target_resolution=16257, reduce_blockiness=True):
        """
        Upscale les masques de 4097x4097 -> 16257x16257 pour Reforger avec qualité optimisée.
        
        Zimnitrita: HeightMap 4097x4097 -> Surface Map 16257x16257 (ratio 4x)
        
        Optimisations:
        - INTER_CUBIC pour meilleure interpolation
        - Filtrage médian optionnel pour réduire les blocs carrés
        - Reseuillissage intelligent avec transition lisse
        
        Args:
            masks: Dict des masques (hauteur, largeur)
            target_resolution: Résolution cible (default 16257 pour Zimnitrita)
            reduce_blockiness: Appliquer filtrage médian (default True)
        
        Returns:
            Dict des masques upscalés
        """
        print(f"\n[UPSCALE] Upscaling masques pour Reforger (qualité optimisée)...")
        print(f"  Résolution actuelle: {self.height}x{self.width}px")
        print(f"  Résolution cible: {target_resolution}x{target_resolution}px")
        if reduce_blockiness:
            print(f"  🎨 Optimisation: Réduction des blocs carrés activée")
        
        upscaled_masks = {}
        
        for cat_key, mask in masks.items():
            if mask is None or mask.size == 0:
                continue
            
            # Upscaler avec INTER_CUBIC (meilleure qualité que LINEAR)
            upscaled = cv2.resize(
                mask, 
                (target_resolution, target_resolution),
                interpolation=cv2.INTER_CUBIC
            )
            
            # Optionnel: Filtrage médian pour réduire les blocs carrés
            if reduce_blockiness and target_resolution > 2048:
                # Médian filter 3x3 pour lisser les transitions dures
                upscaled = cv2.medianBlur(upscaled, 3)
            
            # Reseuilliser avec seuil adaptatif (125 au lieu de 127 pour transitions plus douces)
            upscaled = np.where(upscaled > 125, 255, 0).astype(np.uint8)
            upscaled_masks[cat_key] = upscaled
            
            pixels = np.sum(upscaled == 255)
            percentage = (pixels / (target_resolution * target_resolution)) * 100
            print(f"  • {cat_key}: ✓ {target_resolution}x{target_resolution}px ({percentage:.1f}%)")
        
        return upscaled_masks
    
    def generate_automaterial_reforger(self):
        """
        🎮 AUTOMATERIAL INTELLIGENT POUR REFORGER
        
        Combine trois critères pour assigner automatiquement les textures:
        1. ALTITUDE (zones basse/moyenne/haute)
        2. PENTE (degrés - plat/modéré/pentu/escarpement)
        3. MORPHOLOGIE (creux/normal/émergences)
        
        Résultat: 5 masques intelligents où chaque pixel obtient
        la texture la plus appropriée automatiquement.
        
        LOGIQUE D'ASSIGNATION:
        - HERBE: Zones très plates + altitudes basses + creux (vallées) 
        - TERRE: Pentes modérées + altitudes basses/moyennes + terrain normal
        - ROCHE LÉGÈRE: Pentes fortes + altitudes moyennes + flancs
        - ROCHE FORTE: Pentes très fortes + altitudes hautes + émergences  
        - ESCARPEMENT: Pentes extrêmes (45°+) + parois verticales
        
        Returns:
            Dict avec 5 masques intelligents (herbe, terre, roche_legere, roche_forte, escarpement)
        """
        print("\n" + "="*60)
        print("🎮 AUTOMATERIAL REFORGER - Génération intelligente")
        print("="*60)
        
        # 1. Vérifier que tous les pré-calculs existent
        if self.slopes is None:
            self.compute_slopes()
        
        # 2. Obtenir les masques morphologiques
        print("\n[AUTOMATERIAL] Étape 1: Analyse morphologie du terrain...")
        creux_mask, emergences_mask = self.detect_creux_and_emergences(threshold_percentile=50)
        
        # 3. Normaliser l'altitude (0-1)
        alt_norm = self.heightmap_normalized
        
        # Détecter zones d'altitude
        print("[AUTOMATERIAL] Étape 2: Détection zones d'altitude...")
        alt_water_threshold = np.percentile(alt_norm, 15)
        
        zone_basse = (alt_norm >= alt_water_threshold) & (alt_norm < np.percentile(alt_norm, 40))
        zone_moyenne = (alt_norm >= np.percentile(alt_norm, 40)) & (alt_norm < np.percentile(alt_norm, 70))
        zone_haute = alt_norm >= np.percentile(alt_norm, 70)
        
        print(f"  • Zones basses: {np.sum(zone_basse)} px")
        print(f"  • Zones moyennes: {np.sum(zone_moyenne)} px")
        print(f"  • Zones hautes: {np.sum(zone_haute)} px")
        
        # Masque eau
        water_mask = alt_norm <= alt_water_threshold
        
        # 4. Analyser distribution des pentes pour seuils adaptatifs
        print("[AUTOMATERIAL] Étape 3: Analyse pentes pour seuils adaptatifs...")
        terrain_slopes = self.slopes[~water_mask]
        
        if np.any(~water_mask):
            pente_3deg = np.percentile(terrain_slopes, 15)    # 15%
            pente_12deg = np.percentile(terrain_slopes, 35)   # 35%
            pente_25deg = np.percentile(terrain_slopes, 60)   # 60%
            pente_45deg = np.percentile(terrain_slopes, 85)   # 85%
        else:
            pente_3deg = 3
            pente_12deg = 12
            pente_25deg = 25
            pente_45deg = 45
        
        print(f"  • Seuil 15% (plat): {pente_3deg:.2f}°")
        print(f"  • Seuil 35% (modéré): {pente_12deg:.2f}°")
        print(f"  • Seuil 60% (pentu): {pente_25deg:.2f}°")
        print(f"  • Seuil 85% (très pentu): {pente_45deg:.2f}°")
        
        # 5. GÉNÉRATION INTELLIGENTE DES 5 MASQUES
        # APPROCHE MORPHOLOGIE-FIRST: Utiliser creux/émergences comme base
        print("\n[AUTOMATERIAL] Étape 4: Assignation intelligente textures (Morphologie-First)...")
        
        masks = {}
        
        # === HERBE ===
        # Base: Creux (vallées naturelles) + pentes très faibles
        masks['herbe'] = (
            (creux_mask == 255) &                   # Dans les vallées
            (self.slopes <= pente_3deg) &           # Très plat
            ~water_mask                             # Pas dans l'eau
        ).astype(np.uint8) * 255
        
        # Fallback: Si herbe vide, utiliser uniquement creux
        if np.sum(masks['herbe'] == 255) < 100000:  # Si très peu d'herbe (< 100k pixels)
            masks['herbe'] = (creux_mask == 255) & ~water_mask.astype(np.uint8) * 255
        
        # === ESCARPEMENT ===
        # Base: Émergences (crêtes) + pentes extrêmes
        masks['escarpement'] = (
            (emergences_mask == 255) &              # Sur les crêtes
            (self.slopes > pente_45deg) &           # Très pentu
            ~water_mask                             # Pas dans l'eau
        ).astype(np.uint8) * 255
        
        # Fallback: Si escarpement vide, utiliser uniquement émergences + pentes fortes
        if np.sum(masks['escarpement'] == 255) < 100000:
            masks['escarpement'] = (
                (emergences_mask == 255) & 
                (self.slopes > pente_25deg) &
                ~water_mask
            ).astype(np.uint8) * 255
        
        # === TERRAIN RESTANT (non herbe, non escarpement, non eau) ===
        terrain_remaining = ~water_mask & (masks['herbe'] < 255) & (masks['escarpement'] < 255)
        
        # Diviser le terrain restant par PENTE pour distribuer textures
        # Les pixels sans affectation = terrain normal à distribuer
        
        # === TERRE ===
        # Pentes les PLUS FAIBLES du terrain restant
        masks['terre'] = (
            terrain_remaining &
            (self.slopes > pente_3deg) & (self.slopes <= pente_12deg)
        ).astype(np.uint8) * 255
        
        # === ROCHE LÉGÈRE ===
        # Pentes modérées du terrain restant
        masks['roche_legere'] = (
            terrain_remaining &
            (self.slopes > pente_12deg) & (self.slopes <= pente_25deg)
        ).astype(np.uint8) * 255
        
        # === ROCHE FORTE ===
        # Pentes fortes du terrain restant
        masks['roche_forte'] = (
            terrain_remaining &
            (self.slopes > pente_25deg) & (self.slopes <= pente_45deg)
        ).astype(np.uint8) * 255
        
        # 6. AFFICHER STATISTIQUES FINALES
        print("\n[AUTOMATERIAL] Masques générés intelligemment:")
        ordered_keys = ['herbe', 'terre', 'roche_legere', 'roche_forte', 'escarpement']
        total_assigned = 0
        
        for cat_key in ordered_keys:
            pixels_count = np.sum(masks[cat_key] == 255)
            percentage = (pixels_count / (self.height * self.width)) * 100
            total_assigned += pixels_count
            
            emoji_map = {
                'herbe': '🌱',
                'terre': '🟤', 
                'roche_legere': '🪨',
                'roche_forte': '⛰️',
                'escarpement': '🏔️'
            }
            emoji = emoji_map.get(cat_key, '')
            
            print(f"  • {emoji} {cat_key.replace('_', ' ').title()}: {pixels_count:>8} px ({percentage:>5.1f}%)")
        
        # Pixels non assignés
        water_pct = (np.sum(water_mask) / (self.height * self.width)) * 100
        unassigned_pct = 100.0 - (total_assigned / (self.height * self.width) * 100) - water_pct
        
        print(f"  • 🌊 Eau: {np.sum(water_mask):>8} px ({water_pct:>5.1f}%)")
        print(f"  • ⚪ Non assignés: {int(unassigned_pct * self.height * self.width / 100):>8} px ({unassigned_pct:>5.1f}%)")
        
        print("="*60 + "\n")
        
        # Sauvegarder en session
        self.automaterial_masks = masks
        self.automaterial_thresholds = {
            'pente_3deg': pente_3deg,
            'pente_12deg': pente_12deg,
            'pente_25deg': pente_25deg,
            'pente_45deg': pente_45deg,
        }
        
        return masks
    
    def generate_slope_masks(self, thresholds=None):
        """
        Génère les 5 masques de slope.
        
        Args:
            thresholds: Dict avec seuils personnalisés
                       {'herbe': 2.5, 'terre': 10, 'roche_legere': 22, ...}
                       
        Logique CASCADE: Les seuils définissent la LIMITE HAUTE de chaque catégorie
                        et la limite basse de la suivante (sans gaps)
                        
        Exemple avec thresholds={'herbe': 2.5, 'terre': 10, 'roche_legere': 22}:
            - herbe:        0-2.5°   -> pixels avec pente >= 0 ET < 2.5°
            - terre:        2.5-10°  -> pixels avec pente >= 2.5 ET < 10°
            - roche_legere: 10-22°   -> pixels avec pente >= 10 ET < 22°
            - roche_forte:  22-45°   -> pixels avec pente >= 22 ET < 45°
            - escarpement:  45°+     -> pixels avec pente >= 45°
        
        Returns:
            Dict avec masques numpy pour chaque catégorie
        """
        print("[TEXLAYER] Génération masques slope...")
        
        if self.slopes is None:
            self.compute_slopes()
        
        # Copie des catégories
        categories = {}
        for k, v in self.SLOPE_CATEGORIES.items():
            categories[k] = v.copy()
        
        # Ordre des catégories (important pour le chaînage)
        ordered_keys = ['herbe', 'terre', 'roche_legere', 'roche_forte', 'escarpement']
        
        # Si thresholds personnalisés, mettre à jour les limites avec CASCADE
        if thresholds:
            for i, cat_key in enumerate(ordered_keys):
                if cat_key in thresholds and cat_key in categories:
                    # Mettre à jour la limite HAUTE de cette catégorie
                    new_max = thresholds[cat_key]
                    categories[cat_key]['max'] = new_max
                    
                    # Mettre à jour la limite BASSE de la PROCHAINE catégorie
                    # (pour éviter les gaps)
                    if i + 1 < len(ordered_keys):
                        next_cat = ordered_keys[i + 1]
                        if next_cat in categories:
                            categories[next_cat]['min'] = new_max
        
        # Générer masques (blanc=255, noir=0)
        masks = {}
        for cat_key in ordered_keys:
            if cat_key not in categories:
                continue
                
            cat_info = categories[cat_key]
            min_slope = cat_info['min']
            max_slope = cat_info['max']
            
            # Créer masque: 255 si dans la plage, 0 sinon
            mask = np.zeros((self.height, self.width), dtype=np.uint8)
            in_range = (self.slopes >= min_slope) & (self.slopes < max_slope)
            mask[in_range] = 255
            
            masks[cat_key] = mask
            
            pixels_count = np.sum(in_range)
            percentage = (pixels_count / (self.height * self.width)) * 100
            print(f"  • {cat_key}: {min_slope:.1f}-{max_slope:.1f}° = {pixels_count} px ({percentage:.1f}%)")
        
        self.slope_masks = masks
        return masks
    
    def load_exclusion_mask(self, mask_path):
        """
        Charge un masque d'exclusion noir/blanc.
        Gère tous les formats PIL: L, LA, RGB, RGBA
        
        Args:
            mask_path: Chemin vers le masque PNG
        
        Returns:
            numpy array (même résolution que heightmap)
        """
        print(f"[TEXLAYER] Chargement masque d'exclusion: {mask_path}")
        
        # Charger image PIL
        mask_img = Image.open(mask_path)
        print(f"  • Mode PIL: {mask_img.mode}, Size: {mask_img.size}")

        # Convertir PIL en grayscale d'abord (avant numpy/OpenCV)
        if mask_img.mode in ('LA', 'PA', 'RGBA'):
            # Mode avec alpha: convertir en grayscale, ignorer alpha
            mask_img = mask_img.convert('L')
        elif mask_img.mode in ('RGB', 'BGR'):
            # Mode RGB/BGR: convertir en grayscale
            mask_img = mask_img.convert('L')
        elif mask_img.mode != 'L':
            # Mode inconnu: essayer de convertir en grayscale
            mask_img = mask_img.convert('L')

        # Maintenant PIL est en mode 'L' (grayscale)
        mask = np.array(mask_img).astype(np.uint8)
        print(f"  • Shape après PIL: {mask.shape}")
        
        # Vérifier résolution
        if mask.shape != (self.height, self.width):
            print(f"[TEXLAYER] ⚠️ Redimensionnement masque: {mask.shape} -> {(self.height, self.width)}")
            mask = cv2.resize(mask, (self.width, self.height), interpolation=cv2.INTER_NEAREST)
        
        # Normaliser en 0/255 (blanc=255 = appliquer, noir=0 = exclure)
        mask = np.where(mask > 127, 255, 0).astype(np.uint8)
        
        self.exclusion_mask = mask
        
        white_pixels = np.sum(mask == 255)
        black_pixels = np.sum(mask == 0)
        print(f"  • Blanc (appliquer): {white_pixels} px ({(white_pixels/(white_pixels+black_pixels)*100):.1f}%)")
        print(f"  • Noir (exclure): {black_pixels} px ({(black_pixels/(white_pixels+black_pixels)*100):.1f}%)")
        
        return mask
    
    def apply_exclusion_mask(self, layer_mask):
        """
        Applique le masque d'exclusion sur une couche slope.
        Noir (0) = exclure du slope, Blanc (255) = garder le slope
        
        Args:
            layer_mask: Masque slope (0-255)
        
        Returns:
            Masque slope filtré
        """
        if self.exclusion_mask is None:
            print("[TEXLAYER] ⚠️ Aucun masque d'exclusion chargé")
            return layer_mask
        
        # Appliquer masque: garder slope SEULEMENT où masque est blanc
        filtered = np.where(
            self.exclusion_mask == 255,
            layer_mask,  # Garder le slope
            0  # Mettre à noir (exclure)
        ).astype(np.uint8)
        
        return filtered
    
    def save_mask_png8(self, mask, filename):
        """
        Sauvegarde un masque en PNG 8-bit (0-255 grayscale).
        
        Args:
            mask: Array numpy uint8
            filename: Nom du fichier (sans extension)
        
        Returns:
            Chemin complet du fichier
        """
        output_path = os.path.join(self.layers_dir, f"{filename}_8bit.png")
        cv2.imwrite(output_path, mask)
        print(f"  ✓ PNG 8-bit: {filename}_8bit.png (résolution: {mask.shape[1]}×{mask.shape[0]}px)")
        return output_path
    
    def save_mask_png16(self, mask, filename):
        """
        Sauvegarde un masque en PNG 16-bit (0-65535 grayscale).
        Remappage: 0-255 -> 0-65535
        
        Args:
            mask: Array numpy uint8
            filename: Nom du fichier (sans extension)
        
        Returns:
            Chemin complet du fichier
        """
        # Remap 0-255 -> 0-65535
        mask_16bit = (mask.astype(np.uint16) * 257)  # 257 = 65535/255
        
        # Sauvegarder avec PIL (supporte PNG 16-bit)
        output_path = os.path.join(self.layers_dir, f"{filename}_16bit.png")
        img_16 = Image.fromarray(mask_16bit, mode='I;16')
        img_16.save(output_path)
        
        print(f"  ✓ PNG 16-bit: {filename}_16bit.png (résolution: {mask.shape[1]}×{mask.shape[0]}px)")
        return output_path
    
    def save_mask_raw16(self, mask, filename):
        """
        Sauvegarde un masque en RAW 16-bit (format brut).
        
        Args:
            mask: Array numpy uint8
            filename: Nom du fichier (sans extension)
        
        Returns:
            Chemin complet du fichier
        """
        # Remap 0-255 -> 0-65535
        mask_16bit = (mask.astype(np.uint16) * 257)
        
        output_path = os.path.join(self.layers_dir, f"{filename}_raw.raw")
        mask_16bit.astype(np.uint16).tofile(output_path)
        
        print(f"  ✓ RAW 16-bit: {filename}_raw.raw (résolution: {mask.shape[1]}×{mask.shape[0]}px)")
        return output_path
    
    def export_all_formats(self, layer_name, mask, apply_exclusion=False):
        """
        Exporte un masque dans tous les formats (PNG 8-bit, PNG 16-bit, RAW 16-bit).
        Garantit que la résolution correspond à celle de la heightmap.
        
        Args:
            layer_name: Nom de la couche (ex: 'herbe', 'terre')
            mask: Array numpy uint8
            apply_exclusion: Si True, applique le masque d'exclusion
        
        Returns:
            Dict avec chemins des fichiers exportés
        """
        # Appliquer masque d'exclusion si demandé
        if apply_exclusion:
            mask = self.apply_exclusion_mask(mask)
        
        # GARANTIR que le masque a la bonne résolution
        if mask.shape != (self.height, self.width):
            print(f"[TEXLAYER] ⚠️ Redimensionnement masque export: {mask.shape} -> {(self.height, self.width)}")
            mask = cv2.resize(mask, (self.width, self.height), interpolation=cv2.INTER_NEAREST)
        
        files = {}
        
        # PNG 8-bit
        files['png8'] = self.save_mask_png8(mask, layer_name)
        
        # PNG 16-bit
        files['png16'] = self.save_mask_png16(mask, layer_name)
        
        # RAW 16-bit
        files['raw16'] = self.save_mask_raw16(mask, layer_name)
        
        return files
    
    def generate_and_export(self, apply_exclusion=False, thresholds=None):
        """
        Pipeline complet: générer tous les masques + exporter.
        
        Args:
            apply_exclusion: Si True, applique le masque d'exclusion chargé
            thresholds: Seuils personnalisés
        
        Returns:
            Dict avec infos export
        """
        print("\n" + "="*60)
        print("TEXTURE LAYER GENERATOR - EXPORT COMPLET")
        print("="*60)
        
        # Étape 1: Générer masques
        masks = self.generate_slope_masks(thresholds)
        
        print("\n[TEXLAYER] Export en tous formats...")
        
        export_info = {
            'timestamp': datetime.now().isoformat(),
            'heightmap': self.heightmap_path,
            'resolution': f"{self.width}×{self.height}",
            'layers': {}
        }
        
        # Étape 2: Exporter chaque couche
        for cat_key, cat_info in self.SLOPE_CATEGORIES.items():
            if cat_key in masks:
                print(f"\n[TEXLAYER] Export {cat_info['name']}...")
                
                mask = masks[cat_key]
                files = self.export_all_formats(
                    cat_key, 
                    mask, 
                    apply_exclusion=apply_exclusion
                )
                
                export_info['layers'][cat_key] = {
                    'name': cat_info['name'],
                    'description': cat_info['description'],
                    'files': files,
                    'stats': {
                        'white_pixels': int(np.sum(mask == 255)),
                        'percentage': float(np.sum(mask == 255) / (self.height * self.width) * 100)
                    }
                }
        
        # Sauvegarder métadonnées JSON
        metadata_path = os.path.join(self.layers_dir, "metadata.json")
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(export_info, f, indent=2, ensure_ascii=False)
        
        print("\n" + "="*60)
        print(f"✅ EXPORT COMPLET ({len(export_info['layers'])} couches)")
        print(f"📁 Dossier: {self.layers_dir}")
        print("="*60)
        
        return export_info
    
    def get_preview_image(self, layer_name, apply_exclusion=False):
        """
        Génère une image de prévisualisation colorée pour un masque.
        
        Args:
            layer_name: Clé de la couche
            apply_exclusion: Appliquer masque d'exclusion
        
        Returns:
            PIL Image colorisée
        """
        if layer_name not in self.slope_masks:
            return None
        
        mask = self.slope_masks[layer_name].copy()
        
        if apply_exclusion:
            mask = self.apply_exclusion_mask(mask)
        
        # Créer image RGB colorisée
        preview = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        
        # Blanc (255,255,255) où masque = 255
        white_pixels = mask == 255
        preview[white_pixels] = [255, 255, 255]
        
        # Gris clair où masque = 0 (contexte)
        black_pixels = mask == 0
        preview[black_pixels] = [50, 50, 50]
        
        return Image.fromarray(preview)
