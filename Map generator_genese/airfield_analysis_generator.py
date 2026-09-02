"""
Analyseur d'Emplacements d'Aéroports et Aérodromes
===================================================

Scanne la nature_map et heightmap pour identifier les zones les plus plates
et propose des emplacements optimaux pour:
- Gabarit A (Aéroport): 2500m × 400m
- Gabarit B (Aérodrome): 800m × 150m
"""

import numpy as np
from PIL import Image, ImageDraw
import cv2
from pathlib import Path
import json


class AirfieldAnalysisGenerator:
    def __init__(self, nature_map_path, heightmap_path, meters_per_pixel=10.0):
        """
        Initialise l'analyseur d'aéroports.
        
        Args:
            nature_map_path: Chemin vers la nature_map.png
            heightmap_path: Chemin vers la heightmap
            meters_per_pixel: Échelle de conversion pixel→mètres
        """
        self.nature_map_path = nature_map_path
        self.heightmap_path = heightmap_path
        self.mpp = meters_per_pixel  # m/pixel
        
        # Charger les images
        nature_map_pil = Image.open(nature_map_path)
        self.nature_map = cv2.cvtColor(np.array(nature_map_pil), cv2.COLOR_RGB2BGR)
        self.heightmap = self._load_heightmap(heightmap_path)
        
        # Dimensions
        self.height, self.width = self.nature_map.shape[:2]
        
        # Définir les gabarits en pixels
        self.gabarit_a_m = (2500, 400)  # 2500m × 400m (Aéroport)
        self.gabarit_b_m = (800, 150)   # 800m × 150m (Aérodrome)
        
        # Convertir en pixels
        self.gabarit_a_px = (
            int(self.gabarit_a_m[0] / self.mpp),
            int(self.gabarit_a_m[1] / self.mpp)
        )
        self.gabarit_b_px = (
            int(self.gabarit_b_m[0] / self.mpp),
            int(self.gabarit_b_m[1] / self.mpp)
        )
        
        # Couleurs des biomes en BGR
        self.biome_colors = {
            'eau': (198, 133, 61),
            'neige': (255, 248, 240),
            'roche': (130, 130, 130),
            'toundra': (121, 157, 147),
            'foret': (42, 76, 45),
            'prairie': (168, 198, 125),
            'sable': (226, 201, 146),
        }
        
        # Pré-calculer les masques d'eau et roche (une fois)
        print("[AIRFIELD] Pré-calcul des masques...")
        self.eau_mask = self._get_biome_mask('eau', tolerance=5)
        self.roche_mask = self._get_biome_mask('roche', tolerance=5)
        self.prairie_mask = self._get_biome_mask('prairie', tolerance=10)
        
        # Pré-calculer la pente locale (une fois)
        print("[AIRFIELD] Pré-calcul des pentes...")
        self.slope_map = self._precompute_slope_map()
        
        # Résultats
        self.sites = []
        self.diagnostic_image = None
        self.voronoi_seeds = []  # Seeds Voronoi optionnels
    
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
        """Crée un masque binaire pour un biome spécifique."""
        if biome_name not in self.biome_colors:
            return np.zeros((self.height, self.width), dtype=bool)
        
        target_color = np.array(self.biome_colors[biome_name], dtype=np.uint8)
        distance = np.sqrt(np.sum((self.nature_map - target_color) ** 2, axis=2))
        return distance <= tolerance
    
    def _precompute_slope_map(self):
        """
        Pré-calcule la pente locale sur la carte entière.
        Approche simple: max-min sur une petite fenêtre glissante.
        """
        print("[AIRFIELD] Calcul de la pente locale...")
        
        # Fenêtre 21×21 pixels pour évaluer la pente
        window_size = 21
        half = window_size // 2
        
        slope_map = np.zeros((self.height, self.width), dtype=np.float32)
        
        for y in range(half, self.height - half):
            for x in range(half, self.width - half):
                try:
                    window = self.heightmap[y-half:y+half+1, x-half:x+half+1]
                    if window.size == 0:
                        continue
                    alt_diff = float(window.max() - window.min())
                except (IndexError, ValueError):
                    continue
                
                # Pente = rise/run
                # Distance ≈ window_size pixels = window_size * mpp meters
                distance_m = window_size * self.mpp
                slope_percent = (alt_diff / distance_m) * 100 if distance_m > 0 else 0
                slope_map[y, x] = float(slope_percent)
        
        print("[AIRFIELD] Pente locale calculée")
        return slope_map
    
    def _compute_local_slope(self, x, y, window_size=5):
        """
        Calcule la pente locale moyenne en un point.
        
        Args:
            x, y: Coordonnées du pixel
            window_size: Taille de la fenêtre d'analyse
        
        Returns:
            Pente en pourcentage (0-100%)
        """
        half = window_size // 2
        x1 = max(0, x - half)
        x2 = min(self.width, x + half + 1)
        y1 = max(0, y - half)
        y2 = min(self.height, y + half + 1)
        
        window = self.heightmap[y1:y2, x1:x2]
        
        if window.size < 4:
            return 0.0
        
        # Sobel gradient
        gx = cv2.Sobel(window, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(window, cv2.CV_32F, 0, 1, ksize=3)
        
        # Magnitude moyenne
        magnitude = np.sqrt(gx**2 + gy**2).mean()
        
        # Pente en pourcentage (magnitude / distance en pixels * 100)
        slope_percent = (magnitude / self.mpp) * 100
        
        return min(slope_percent, 100.0)
    
    def _evaluate_site(self, x, y, gabarit_px, gabarit_m, debug=False):
        """
        Évalue la faisabilité d'un site de manière ultra-rapide.
        Focus uniquement sur la pente - l'eau/roche seront visibles sur le diagnostic.
        """
        width_px, height_px = gabarit_px
        
        # Vérifier les limites de la carte
        if x + width_px > self.width or y + height_px > self.height:
            return None
        
        # Extraire la zone
        zone = self.heightmap[y:y+height_px, x:x+width_px]
        zone_slope = self.slope_map[y:y+height_px, x:x+width_px]
        
        # Statistiques basiques
        mean_alt = zone.mean()
        altitude_diff = zone.max() - zone.min()
        mean_slope = zone_slope.mean()
        
        # Rejeter les artefacts: pente > 100% (anormal)
        if mean_slope > 100:
            return None
        
        # Vérifier eau/roche dans la zone
        zone_eau = self.eau_mask[y:y+height_px, x:x+width_px]
        zone_roche = self.roche_mask[y:y+height_px, x:x+width_px]
        
        total_pixels = width_px * height_px
        eau_percent = np.sum(zone_eau) / total_pixels * 100
        roche_percent = np.sum(zone_roche) / total_pixels * 100
        
        # Rejeter si trop d'eau OU trop de roche
        if eau_percent > 40 or roche_percent > 50:
            return None
        
        # Score simple et rapide - uniquement basé sur la pente
        # Plus la pente est faible, plus le score est haut
        flatness = max(0, 100 - mean_slope * 15)  # Pente de 1% = -15pts
        feasibility_score = max(0, flatness)
        
        if debug:
            print(f"    ({x}, {y}): pente={mean_slope:.1f}%, eau={eau_percent:.1f}%, roche={roche_percent:.1f}%, score={feasibility_score:.1f}")
        
        return {
            'x': x,
            'y': y,
            'altitude_mean': float(mean_alt),
            'altitude_min': float(zone.min()),
            'altitude_max': float(zone.max()),
            'altitude_diff': float(altitude_diff),
            'mean_slope': float(mean_slope),
            'feasibility_score': float(feasibility_score),
            'requires_earthwork': mean_slope > 5.0,
            'eau_percent': float(eau_percent),
            'roche_percent': float(roche_percent),
        }
    
    def scan_for_airports(self):
        """
        Scanne la carte pour trouver les meilleurs emplacements d'aéroports.
        Exclut les bords (artefacts) et filtre eau/roche excessifs.
        """
        print("[AIRFIELD] Scan complet en cours...")
        print(f"[AIRFIELD] Dimensions carte: {self.width}×{self.height}px")
        
        all_sites = []
        
        # Exclure les bords massifs (artefacts heightmap)
        border = 500
        print(f"[AIRFIELD] Exclusion des bords: {border}px")
        
        # Étape 1: Gabarit A
        print(f"\n[AIRFIELD] === SCAN GABARIT A ===")
        step_a = 100
        alpha_candidates = []
        
        for y in range(border, self.height - self.gabarit_a_px[1] - border, step_a):
            for x in range(border, self.width - self.gabarit_a_px[0] - border, step_a):
                site = self._evaluate_site(x, y, self.gabarit_a_px, self.gabarit_a_m)
                if site is not None:
                    alpha_candidates.append(site)
        
        print(f"[AIRFIELD] Candidats trouvés: {len(alpha_candidates)}")
        if alpha_candidates:
            scores = [s['feasibility_score'] for s in alpha_candidates]
            print(f"[AIRFIELD] Scores A: min={min(scores):.1f}, max={max(scores):.1f}, avg={np.mean(scores):.1f}")
            alpha_candidates_sorted = sorted(alpha_candidates, key=lambda s: s['feasibility_score'], reverse=True)
            for i, s in enumerate(alpha_candidates_sorted[:10], 1):
                print(f"  {i}. ({s['x']}, {s['y']}): score={s['feasibility_score']:.1f}, pente={s['mean_slope']:.1f}%, eau={s['eau_percent']:.1f}%")
        
        alpha_sites = sorted(alpha_candidates, key=lambda s: s['feasibility_score'], reverse=True)[:5]
        for s in alpha_sites:
            s['type'] = 'Alpha (Aéroport)'
            s['gabarit'] = 'A'
        all_sites.extend(alpha_sites)
        
        # Étape 2: Gabarit B
        print(f"\n[AIRFIELD] === SCAN GABARIT B ===")
        step_b = 80
        beta_candidates = []
        
        for y in range(border, self.height - self.gabarit_b_px[1] - border, step_b):
            for x in range(border, self.width - self.gabarit_b_px[0] - border, step_b):
                site = self._evaluate_site(x, y, self.gabarit_b_px, self.gabarit_b_m)
                if site is not None:
                    beta_candidates.append(site)
        
        print(f"[AIRFIELD] Candidats trouvés: {len(beta_candidates)}")
        if beta_candidates:
            scores = [s['feasibility_score'] for s in beta_candidates]
            print(f"[AIRFIELD] Scores B: min={min(scores):.1f}, max={max(scores):.1f}, avg={np.mean(scores):.1f}")
            beta_candidates_sorted = sorted(beta_candidates, key=lambda s: s['feasibility_score'], reverse=True)
            for i, s in enumerate(beta_candidates_sorted[:15], 1):
                print(f"  {i}. ({s['x']}, {s['y']}): score={s['feasibility_score']:.1f}, pente={s['mean_slope']:.1f}%, eau={s['eau_percent']:.1f}%")
        
        beta_sites = sorted(beta_candidates, key=lambda s: s['feasibility_score'], reverse=True)[:15]
        for s in beta_sites:
            s['type'] = 'Beta (Aérodrome)'
            s['gabarit'] = 'B'
        all_sites.extend(beta_sites)
        
        print(f"\n[AIRFIELD] RÉSUMÉ: {len(alpha_sites)} Alpha + {len(beta_sites)} Beta = {len(all_sites)} total")
        
        self.sites = all_sites
        
        return {
            'alpha_count': len(alpha_sites),
            'beta_count': len(beta_sites),
            'total_sites': len(self.sites),
            'sites': self.sites
        }
    
    def scan_for_airports_on_voronoi_seeds(self, voronoi_seeds_list):
        """
        Scanne UNIQUEMENT aux positions des seeds Voronoi situés en Prairie.
        
        Le seed Voronoi = centre de la cellule urbaine (apte à l'urbanisme)
        L'aéroport/aérodrome place son centre sur ce seed.
        L'aéroport peut déborder sur les cellules voisines.
        
        Args:
            voronoi_seeds_list: Liste de tuples [(x, y), (x, y), ...]
        
        Returns:
            dict avec alpha_count, beta_count, total_sites, sites
        """
        print("\n[AIRFIELD-VORONOI] Scan sur seeds Voronoi (Prairie uniquement)...")
        
        # Filtrer: seeds qui doivent être EN PRAIRIE
        prairie_seeds = []
        non_prairie_count = 0
        
        for x, y in voronoi_seeds_list:
            if 0 <= y < self.height and 0 <= x < self.width:
                if self.prairie_mask[y, x] > 0:
                    prairie_seeds.append((x, y))
                else:
                    non_prairie_count += 1
        
        print(f"  → Seeds Voronoi totaux: {len(voronoi_seeds_list)}")
        print(f"  → Seeds EN PRAIRIE: {len(prairie_seeds)}")
        print(f"  → Seeds ignorés (non-prairie): {non_prairie_count}")
        
        all_sites = []
        
        # Évaluer Aéroport (Gabarit A) sur CHAQUE seed Prairie
        print(f"\n[AIRFIELD-VORONOI] Évaluation Aéroport ({self.gabarit_a_m[0]}×{self.gabarit_a_m[1]}m)...")
        alpha_candidates = []
        
        for x, y in prairie_seeds:
            site = self._evaluate_site(x, y, self.gabarit_a_px, self.gabarit_a_m)
            if site is not None:
                site['type'] = 'Alpha (Aéroport)'
                site['gabarit'] = 'A'
                site['voronoi_seed'] = (x, y)  # Marquer le seed
                alpha_candidates.append(site)
        
        print(f"  → Aéroports viables: {len(alpha_candidates)}")
        if alpha_candidates:
            scores = [s['feasibility_score'] for s in alpha_candidates]
            print(f"     Scores: min={min(scores):.1f}, max={max(scores):.1f}, avg={np.mean(scores):.1f}")
        
        all_sites.extend(sorted(alpha_candidates, key=lambda s: s['feasibility_score'], reverse=True))
        
        # Évaluer Aérodrome (Gabarit B) sur CHAQUE seed Prairie
        print(f"\n[AIRFIELD-VORONOI] Évaluation Aérodrome ({self.gabarit_b_m[0]}×{self.gabarit_b_m[1]}m)...")
        beta_candidates = []
        
        for x, y in prairie_seeds:
            site = self._evaluate_site(x, y, self.gabarit_b_px, self.gabarit_b_m)
            if site is not None:
                site['type'] = 'Beta (Aérodrome)'
                site['gabarit'] = 'B'
                site['voronoi_seed'] = (x, y)  # Marquer le seed
                beta_candidates.append(site)
        
        print(f"  → Aérodromes viables: {len(beta_candidates)}")
        if beta_candidates:
            scores = [s['feasibility_score'] for s in beta_candidates]
            print(f"     Scores: min={min(scores):.1f}, max={max(scores):.1f}, avg={np.mean(scores):.1f}")
        
        all_sites.extend(sorted(beta_candidates, key=lambda s: s['feasibility_score'], reverse=True))
        
        # Fusionner et limiter aux 20 meilleures
        self.sites = sorted(all_sites, key=lambda s: s['feasibility_score'], reverse=True)[:20]
        self.voronoi_seeds = prairie_seeds  # Garder pour le diagnostic
        
        print(f"\n[AIRFIELD-VORONOI] RÉSUMÉ:")
        print(f"  → Aéroports viables: {len([s for s in self.sites if s['gabarit'] == 'A'])}")
        print(f"  → Aérodromes viables: {len([s for s in self.sites if s['gabarit'] == 'B'])}")
        print(f"  → Total top 20: {len(self.sites)}")
        
        if self.sites:
            print(f"\n  TOP 10 SITES:")
            for i, site in enumerate(self.sites[:10], 1):
                work = " [TERRASSEMENT]" if site['requires_earthwork'] else ""
                print(f"    #{i}: {site['type']} @ ({site['x']}, {site['y']}) "
                      f"Score={site['feasibility_score']:.1f}{work}")
        
        return {
            'alpha_count': len([s for s in self.sites if s['gabarit'] == 'A']),
            'beta_count': len([s for s in self.sites if s['gabarit'] == 'B']),
            'total_sites': len(self.sites),
            'sites': self.sites,
            'prairie_seeds_count': len(prairie_seeds)
        }
    
    def create_diagnostic_image(self):
        """
        Crée une image de diagnostic avec les sites marqués.
        Couleurs:
        - Bleu: Aéroport (Alpha)
        - Cyan: Aérodrome (Beta)
        - Orange: Site nécessitant terrassement (slope > 5%)
        """
        diagnostic = self.nature_map.copy()
        
        # Couleurs des marques
        color_alpha = (255, 0, 0)      # Bleu
        color_beta = (255, 255, 0)     # Cyan
        color_earthwork = (0, 165, 255) # Orange
        
        # Dessiner chaque site
        for site in self.sites:
            x, y = site['x'], site['y']
            
            if site['gabarit'] == 'A':
                width_px, height_px = self.gabarit_a_px
                color = color_earthwork if site['requires_earthwork'] else color_alpha
            else:  # Gabarit B
                width_px, height_px = self.gabarit_b_px
                color = color_earthwork if site['requires_earthwork'] else color_beta
            
            # Dessiner un rectangle
            cv2.rectangle(
                diagnostic,
                (x, y),
                (x + width_px, y + height_px),
                color,
                thickness=2
            )
            
            # Marquer le centre avec un point
            center_x = x + width_px // 2
            center_y = y + height_px // 2
            cv2.circle(diagnostic, (center_x, center_y), 5, color, -1)
        
        self.diagnostic_image = diagnostic
        return Image.fromarray(cv2.cvtColor(diagnostic, cv2.COLOR_BGR2RGB))
    
    def save_diagnostic(self, output_path='output/site_diagnostic.png'):
        """Sauvegarde l'image de diagnostic."""
        if self.diagnostic_image is None:
            raise ValueError("Générer d'abord le diagnostic avec create_diagnostic_image()")
        
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        diagnostic_pil = Image.fromarray(cv2.cvtColor(self.diagnostic_image, cv2.COLOR_BGR2RGB))
        diagnostic_pil.save(output_path)
    
    def get_report(self):
        """
        Génère un rapport JSON avec tous les sites trouvés.
        """
        report = {
            'scale_mpp': self.mpp,
            'gabarits': {
                'alpha': {
                    'meters': f"{self.gabarit_a_m[0]}m × {self.gabarit_a_m[1]}m",
                    'pixels': f"{self.gabarit_a_px[0]}px × {self.gabarit_a_px[1]}px",
                    'name': 'Aéroport'
                },
                'beta': {
                    'meters': f"{self.gabarit_b_m[0]}m × {self.gabarit_b_m[1]}m",
                    'pixels': f"{self.gabarit_b_px[0]}px × {self.gabarit_b_px[1]}px",
                    'name': 'Aérodrome'
                }
            },
            'summary': {
                'total_sites': len(self.sites),
                'alpha_sites': len([s for s in self.sites if s['gabarit'] == 'A']),
                'beta_sites': len([s for s in self.sites if s['gabarit'] == 'B']),
                'sites_requiring_earthwork': len([s for s in self.sites if s['requires_earthwork']])
            },
            'sites': self.sites
        }
        
        return report
    
    def print_summary(self):
        """Affiche un résumé textuel du rapport."""
        print("\n" + "="*70)
        print("RAPPORT D'ANALYSE DES AÉROPORTS")
        print("="*70)
        print(f"Total: {len(self.sites)} sites trouvés\n")
        
        for i, site in enumerate(self.sites, 1):
            gabarit = "Alpha (Aéroport)" if site['gabarit'] == 'A' else "Beta (Aérodrome)"
            print(f"Site {i}: {gabarit}")
            print(f"  Position: ({site['x']}, {site['y']}) pixels")
            print(f"  Altitude: {site['altitude_mean']:.1f}m (min={site['altitude_min']:.1f}m, max={site['altitude_max']:.1f}m)")
            print(f"  Pente locale: {site['mean_slope']:.1f}%")
            print(f"  Score faisabilité: {site['feasibility_score']:.1f}/100")
            
            if site['requires_earthwork']:
                print(f"  ⚠️  TERRASSEMENT NÉCESSAIRE (pente > 5%)")
            else:
                print(f"  ✅ Plateforme plane")
            
            print()
