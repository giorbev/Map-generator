#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NatureMap Biomes Generator

Génère une carte d'occupation des sols basée sur 8 biomes.
Altitude + Pentes → Biomes avec règles en cascade.

Biomes:
  1. Eau: Z ≤ 0m → Bleu Azure (#3D85C6)
  2. Neige: Z > 92% → Blanc Cassé (#F0F8FF)
  3. Roche: pente > 35° OU Z > 80% → Gris Roche (#828282)
  4. Toundra: 70% ≤ Z ≤ 80% → Vert Olive (#939D79)
  5. Forêt Dense: 15° ≤ pente ≤ 35° → Vert Forêt (#2D4C2A)
  6. Plaine/Prairie: défaut → Vert Tendre (#A8C67D)
  7. Sable: Bordure eau/plaine, +2px → Sable (#E2C992)
"""

import numpy as np
from PIL import Image
import cv2
import os
from scipy.ndimage import binary_dilation


class NatureMapBiomesGenerator:
    """Générateur de NatureMap basé sur 8 biomes."""
    
    # Palettes biomes (BGR - format OpenCV) — harmonisées avec BaseMap.COLORS
    COLOR_WATER  = np.array([200, 133,  61], dtype=np.uint8)  # Bleu  #3D85C8
    COLOR_SNOW   = np.array([255, 255, 255], dtype=np.uint8)  # Blanc #FFFFFF
    COLOR_ROCK   = np.array([130, 130, 130], dtype=np.uint8)  # Gris  #828282
    COLOR_TUNDRA = np.array([121, 157, 147], dtype=np.uint8)  # Olive #939D79
    COLOR_FOREST = np.array([ 42,  76,  45], dtype=np.uint8)  # Vert foncé #2D4C2A
    COLOR_PRAIRIE= np.array([125, 198, 168], dtype=np.uint8)  # Prairie #A8C67D
    COLOR_SAND   = np.array([146, 217, 226], dtype=np.uint8)  # Sable  #E2D992
    
    def __init__(self, heightmap_path, output_dir="output", png_alt_max=1000.0, png_cellsize=None):
        """
        Initialise le générateur.
        
        Args:
            heightmap_path: Chemin vers la heightmap (PNG/TGA/ASC)
            output_dir: Répertoire de sortie
            png_alt_max: Altitude réelle max (m) pour PNG 8-bit ou 16-bit (ignoré pour ASC)
            png_cellsize: Résolution spatiale (m/px) pour PNG (ignoré pour ASC)
        """
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        
        # Résolution spatiale (mètres/pixel) — lue depuis le header ASC si disponible
        self.cellsize = 1.0  # valeur par défaut (non-ASC ou non spécifié)
        self.nodata_mask = None

        # Paramètres PNG
        self._png_alt_max = float(png_alt_max)
        self._png_bit_depth = None  # rempli par _load_heightmap si PNG
        if png_cellsize is not None:
            self.cellsize = float(png_cellsize)

        # Charger heightmap
        self.heightmap_original = self._load_heightmap(heightmap_path)
        # _auto_adjust_elevation_units seulement pour ASC (les PNG sont déjà scalés en mètres)
        if str(heightmap_path).lower().endswith('.asc'):
            self.heightmap_original = self._auto_adjust_elevation_units(self.heightmap_original)
        self.height, self.width = self.heightmap_original.shape
        
        print(f"[NATUREMAP] Heightmap chargée: {self.width}×{self.height}px")
        print(f"[NATUREMAP] Min: {np.min(self.heightmap_original):.1f}m, Max: {np.max(self.heightmap_original):.1f}m")
        
        # Normaliser altitude 0-1 (FORCER float32 pour économiser RAM)
        h_min = np.min(self.heightmap_original)
        h_max = np.max(self.heightmap_original)
        self.heightmap_norm = ((self.heightmap_original - h_min) / (h_max - h_min + 1e-6)).astype(np.float32)
        self.h_min = h_min
        self.h_max = h_max
        
        print(f"[NATUREMAP] Altitudes réelles: {h_min:.1f}m à {h_max:.1f}m")
        
        # ✅ ANALYSE COMPLÈTE UNE SEULE FOIS au chargement
        # Hypsométrique, NatureMap et Analyse utiliseront ces données stockées
        self._analyze_heightmap()
        
        # Créer naturemap
        self.naturemap = np.zeros((self.height, self.width, 3), dtype=np.uint8)
    
    def _load_heightmap(self, path):
        """Charge une heightmap (PNG, TGA, ASC)."""
        path = str(path)
        
        if path.lower().endswith('.asc'):
            return self._load_asc(path)
        else:
            img = Image.open(path)
            img_mode = img.mode  # 'L'=8bit, 'I'=16bit/32bit, 'F'=float32
            heightmap = np.array(img)
            alpha = None
            self.nodata_mask = np.zeros(heightmap.shape[:2], dtype=bool)
            
            # Convertir en grayscale si RGB
            if len(heightmap.shape) == 3:
                if heightmap.shape[2] == 4:  # RGBA
                    alpha = heightmap[:, :, 3]
                    heightmap = heightmap[:, :, :3]
                heightmap = np.mean(heightmap, axis=2)

            h = heightmap.astype(np.float32)

            # Si alpha transparent disponible, considérer ces pixels comme NoData -> 0m.
            if alpha is not None:
                self.nodata_mask = (alpha == 0)
                h[alpha == 0] = 0.0

            # Détection bit-depth et normalisation en mètres
            if img_mode == 'I':
                # 16-bit PNG: valeurs brutes 0-65535
                max_raw = 65535.0
                self._png_bit_depth = 16
            elif img_mode == 'F':
                # 32-bit float normalisé 0.0-1.0 (ex: Houdini, Blender)
                max_raw = 1.0
                self._png_bit_depth = 32
            else:
                # 8-bit PNG (mode 'L', 'RGB', 'P', etc.): valeurs 0-255
                max_raw = 255.0
                self._png_bit_depth = 8

            # Scaler les valeurs brutes → mètres réels
            h_scaled = (h / max_raw) * self._png_alt_max
            # Préserver les zéros (bord NoData, mer)
            h_scaled[h == 0.0] = 0.0

            raw_min = float(np.min(h))
            raw_max = float(np.max(h))
            print(
                f"[NATUREMAP] PNG {self._png_bit_depth}-bit: "
                f"raw [{raw_min:.0f}-{raw_max:.0f}] -> "
                f"[{float(np.min(h_scaled)):.1f}-{float(np.max(h_scaled)):.1f}]m "
                f"(alt_max={self._png_alt_max:.0f}m)"
            )
            return h_scaled

    def _sanitize_nodata_spikes(self, h):
        """
        Remplace les valeurs sentinelles NoData (pics extrêmes) par 0m.

        Cas ciblé: rasters 16-bit avec fond/no-data proche de 65535
        qui polluent min/max et toute la calibration.
        """
        arr = h.astype(np.float32)
        finite = np.isfinite(arr)
        if not np.any(finite):
            return arr

        v = arr[finite]
        p50 = float(np.percentile(v, 50))
        p999 = float(np.percentile(v, 99.9))
        v_max = float(np.max(v))

        # Heuristique conservative: grand pic haut isolé avec médiane basse.
        # Exemple typique: terrain <= 200m et NoData ~65535.
        if v_max > 5000.0 and p50 < 1500.0 and (v_max - p999) > 1000.0:
            spike_mask = arr >= (v_max - 64.0)
            spike_pct = float(np.mean(spike_mask) * 100.0)
            if spike_pct >= 0.01:
                print(
                    f"[NATUREMAP] NoData haut detecte (~{v_max:.1f}), "
                    f"remplace par 0m ({spike_pct:.2f}% px)"
                )
                arr[spike_mask] = 0.0

        return arr

    def _auto_adjust_elevation_units(self, heightmap):
        """
        Corrige automatiquement certaines cartes encodées en dm/cm au lieu de mètres.

        Heuristique volontairement conservatrice:
        - dm probable: p99 in [900, 5000] et p50 < 250
        - cm probable: p99 in [9000, 50000] et p50 < 2500

        Returns:
            Heightmap corrigée en mètres (float32)
        """
        h = heightmap.astype(np.float32)

        # Exclure les valeurs NoData usuelles si présentes
        finite = np.isfinite(h)
        if not np.any(finite):
            return h

        hv = h[finite]
        p50 = float(np.percentile(hv, 50))
        p99 = float(np.percentile(hv, 99))

        scale = 1.0
        unit_hint = "m"
        if 900.0 <= p99 <= 5000.0 and p50 < 250.0:
            scale = 0.1
            unit_hint = "dm -> m"
        elif 9000.0 <= p99 <= 50000.0 and p50 < 2500.0:
            scale = 0.01
            unit_hint = "cm -> m"

        if scale != 1.0:
            print(
                f"[NATUREMAP] Ajustement vertical auto: {unit_hint} "
                f"(p50={p50:.1f}, p99={p99:.1f}, facteur={scale})"
            )
            h = h * scale

        return h
    
    def _load_asc(self, path):
        """Charge un fichier ASC (ESRI Grid format)."""
        with open(path, 'r') as f:
            headers = {}
            for _ in range(6):
                line = f.readline().strip().split()
                headers[line[0].lower()] = float(line[1])

            # Stocker la résolution spatiale (mètres/pixel)
            if 'cellsize' in headers:
                self.cellsize = float(headers['cellsize'])
                print(f"[NATUREMAP] Résolution ASC: {self.cellsize:.2f} m/px")

            raw = f.read()

        ncols = int(headers['ncols'])
        nrows = int(headers['nrows'])
        data  = np.array(raw.split(), dtype=np.float32).reshape(nrows, ncols)

        # Appliquer NoData ASC (ex: -32768) -> 0m pour stabiliser l'analyse.
        nodata_val = headers.get('nodata_value', None)
        self.nodata_mask = np.zeros(data.shape, dtype=bool)
        if nodata_val is not None:
            nodata_mask = np.isclose(data, float(nodata_val), atol=1e-3)
            if np.any(nodata_mask):
                nodata_pct = float(np.mean(nodata_mask) * 100.0)
                print(f"[NATUREMAP] NoData ASC remplace par 0m: {nodata_pct:.2f}% px")
                self.nodata_mask = nodata_mask
                data[nodata_mask] = 0.0

        return data
    
    def _analyze_heightmap(self):
        """
        ANALYSE COMPLÈTE ET UNIQUE de la heightmap.
        Appelée UNE FOIS à l'init, utilisée par tous les générateurs.
        
        ✅ Résultat: Cohérence garantie entre hypsométrique, naturemap et analyse.
        """
        print("[HEIGHTMAP ANALYSIS] Analyse complète et unique...")
        
        # 1. PENTES (avec lissage robuste)
        self.slopes = self._compute_slopes()

        # 1b. RUGOSITÉ — écart-type local d'altitude (fenêtre 5m)
        self.roughness = self._compute_roughness(window_m=5.0)

        # 1c. COURBURE — Laplacien total + courbure profil
        self.curvature, self.curvature_profile = self._compute_curvature()

        # 2. EAU — conservatrice, hors NoData, connectée au bord si mer/côte
        self.water_mask, self.water_threshold = self._compute_water_mask()
        valid_water_den = max(1, int(np.sum(~self.nodata_mask)))
        self.water_coverage_pct = np.sum(self.water_mask) / valid_water_den * 100
        print(f"  • Eau (seuil conservateur): {self.water_threshold:.1f}m, {self.water_coverage_pct:.2f}%")
        
        # 3. ZONES D'ALTITUDE ABSOLUES (vraies zones SIG standards)
        total_pixels = self.height * self.width
        self.altitude_distribution = {
            'eau (<0m)': np.sum((self.heightmap_original < 0)),
            'plaines (0-100m)': np.sum((self.heightmap_original >= 0) & (self.heightmap_original < 100)),
            'collines (100-300m)': np.sum((self.heightmap_original >= 100) & (self.heightmap_original < 300)),
            'montagnes (300-600m)': np.sum((self.heightmap_original >= 300) & (self.heightmap_original < 600)),
            'hauts_pics (600-1200m)': np.sum((self.heightmap_original >= 600) & (self.heightmap_original < 1200)),
            'sommets (>1200m)': np.sum((self.heightmap_original >= 1200)),
        }
        
        print("  • Distribution d'altitude (zones SIG absolues):")
        for zone_name, pixel_count in self.altitude_distribution.items():
            pct = pixel_count / total_pixels * 100
            print(f"    - {zone_name}: {pixel_count} px ({pct:.1f}%)")
        
        # 4. PENTES (distribution par catégories)
        self.slope_distribution = {
            '0-15°': np.sum((self.slopes >= 0) & (self.slopes < 15)),
            '15-35°': np.sum((self.slopes >= 15) & (self.slopes < 35)),
            '>35°': np.sum(self.slopes >= 35),
        }
        
        print("  • Distribution des pentes:")
        for slope_cat, pixel_count in self.slope_distribution.items():
            pct = pixel_count / total_pixels * 100
            print(f"    - {slope_cat}: {pixel_count} px ({pct:.1f}%)")

        # 5. EXPOSITION (Aspect) — réutilise gx/gy de _compute_slopes()
        self.aspect = self._compute_aspect()
        aspect_labels = [
            ('N (337-22°)',   (self.aspect >= 337) | (self.aspect < 22)),
            ('NE (22-67°)',   (self.aspect >= 22)  & (self.aspect < 67)),
            ('E (67-112°)',   (self.aspect >= 67)  & (self.aspect < 112)),
            ('SE (112-157°)', (self.aspect >= 112) & (self.aspect < 157)),
            ('S (157-202°)',  (self.aspect >= 157) & (self.aspect < 202)),
            ('SO (202-247°)', (self.aspect >= 202) & (self.aspect < 247)),
            ('O (247-292°)',  (self.aspect >= 247) & (self.aspect < 292)),
            ('NO (292-337°)', (self.aspect >= 292) & (self.aspect < 337)),
        ]
        self.aspect_distribution = {
            label: int(np.sum(mask)) for label, mask in aspect_labels
        }
        print("  • Distribution de l'exposition:")
        for label, count in self.aspect_distribution.items():
            print(f"    - {label}: {count} px ({count/total_pixels*100:.1f}%)")

        # 6. TPI MULTI-ÉCHELLE (local ~250m, moyen ~1000m, large ~3000m)
        #    Les fenêtres sont converties en pixels selon self.cellsize.
        def _meters_to_odd_px(meters):
            px = max(3, int(round(meters / self.cellsize)))
            return px if px % 2 == 1 else px + 1

        win_local  = _meters_to_odd_px(250)
        win_medium = _meters_to_odd_px(1000)
        win_large  = _meters_to_odd_px(3000)

        print(f"  • TPI fenêtres (cellsize={self.cellsize:.1f}m/px): "
              f"local={win_local}px ({win_local*self.cellsize:.0f}m), "
              f"moyen={win_medium}px ({win_medium*self.cellsize:.0f}m), "
              f"large={win_large}px ({win_large*self.cellsize:.0f}m)")

        self.tpi_local  = self._compute_tpi(window_size=win_local)   # détail texture
        self.tpi        = self._compute_tpi(window_size=win_medium)   # classification matériaux
        self.tpi_large  = self._compute_tpi(window_size=win_large)    # contexte morpho régional
        self.tpi_windows_m = {
            'local_m':  win_local  * self.cellsize,
            'medium_m': win_medium * self.cellsize,
            'large_m':  win_large  * self.cellsize,
        }

        self.tpi_distribution = {
            'creux (<-5m)':      int(np.sum(self.tpi < -5)),
            'versant (-5 à 5m)': int(np.sum((self.tpi >= -5) & (self.tpi <= 5))),
            'crête (>5m)':       int(np.sum(self.tpi > 5)),
        }
        print("  • Distribution TPI moyen (crêtes/creux):")
        for label, count in self.tpi_distribution.items():
            print(f"    - {label}: {count} px ({count/total_pixels*100:.1f}%)")

        # 7. FLOW ACCUMULATION D8 — talwegs et rivières potentielles
        self.flow_accumulation = self._compute_flow_accumulation()

        # 8. DÉPRESSIONS FERMÉES — cavités, dolines
        self.depression_mask = self._compute_depressions()

        # 9. LITHOLOGIE PROXY — 4 classes inférées du relief
        self.lithology_proxy = self._compute_lithology_proxy()
        litho_labels = ['alluvial', 'altérite/plateau', 'roche tendre', 'roche dure']
        self.lithology_distribution = {
            label: int(np.sum(self.lithology_proxy == i))
            for i, label in enumerate(litho_labels)
        }
        print("  • Lithologie proxy (4 classes):")
        for label, count in self.lithology_distribution.items():
            print(f"    - {label}: {count} px ({count/total_pixels*100:.1f}%)")

        # 10. RÉSEAU HYDROGRAPHIQUE — ruisseaux et rivières
        self.stream_network = self._compute_stream_network()
        stream_count = int(np.sum(self.stream_network))
        print(f"  • Réseau hydrographique: {stream_count} px ({stream_count/total_pixels*100:.2f}%)")

        # 11. LACS NATURELS — dépressions remplies de superficie significative
        self.lake_mask = self._compute_lake_mask()
        lake_count = int(np.sum(self.lake_mask))
        print(f"  • Lacs naturels: {lake_count} px ({lake_count/total_pixels*100:.2f}%)")

        # 12. STATISTIQUES DE CALIBRATION — percentiles terrain → pipeline texture
        # Cohérentes avec les calculs de compute_texture_scores (p2-p98 des pixels terre).
        _land   = ~self.water_mask
        _h_land = self.heightmap_original[_land].astype(np.float64)
        _s_land = self.slopes[_land].astype(np.float64)
        _r_land = self.roughness[_land].astype(np.float64)
        _c_land = self.curvature[_land].astype(np.float64)
        _alt_p2  = float(np.percentile(_h_land,  2))
        _alt_p98 = float(np.percentile(_h_land, 98))
        _alt_rng = max(_alt_p98 - _alt_p2, 1.0)
        def _frac(m):  # altitude réelle → fraction normalisée (espace p2-p98)
            return float(np.clip((m - _alt_p2) / _alt_rng, 0.0, 1.0))
        _p25m = float(np.percentile(_h_land, 25))
        _p50m = float(np.percentile(_h_land, 50))
        _p75m = float(np.percentile(_h_land, 75))
        _p90m = float(np.percentile(_h_land, 90))
        self.terrain_stats = {
            # Altitude réelle — pixels terre uniquement (mètres)
            "alt_p2_m":   _alt_p2,
            "alt_p25_m":  _p25m,
            "alt_p50_m":  _p50m,
            "alt_p75_m":  _p75m,
            "alt_p90_m":  _p90m,
            "alt_p98_m":  _alt_p98,
            "alt_range_m": _alt_rng,
            # Fractions normalisées (repère p2-p98, cohérent avec compute_texture_scores)
            "frac_p25":   _frac(_p25m),
            "frac_p50":   _frac(_p50m),
            "frac_p75":   _frac(_p75m),
            "frac_p90":   _frac(_p90m),
            # Pentes en vrais degrés (Sobel métrique sur pixels terre)
            "slope_mean_deg": float(np.mean(_s_land)),
            "slope_p50_deg":  float(np.percentile(_s_land, 50)),
            "slope_p75_deg":  float(np.percentile(_s_land, 75)),
            "slope_p85_deg":  float(np.percentile(_s_land, 85)),
            "slope_p90_deg":  float(np.percentile(_s_land, 90)),
            "slope_p95_deg":  float(np.percentile(_s_land, 95)),
            # Rugosité (écart-type local d'altitude, fenêtre 5m) — pixels terre
            "roughness_mean_m": float(np.mean(_r_land)),
            "roughness_p50_m":  float(np.percentile(_r_land, 50)),
            "roughness_p75_m":  float(np.percentile(_r_land, 75)),
            "roughness_p90_m":  float(np.percentile(_r_land, 90)),
            "roughness_p95_m":  float(np.percentile(_r_land, 95)),
            # Courbure totale (Laplacien) — pixels terre
            "curvature_mean":   float(np.mean(_c_land)),
            "curvature_p10":    float(np.percentile(_c_land, 10)),
            "curvature_p25":    float(np.percentile(_c_land, 25)),
            "curvature_p75":    float(np.percentile(_c_land, 75)),
            "curvature_p90":    float(np.percentile(_c_land, 90)),
        }
        print("  • terrain_stats (calibration auto-matériau) :")
        print(f"    alt p2={_alt_p2:.0f}m  p50={_p50m:.0f}m  p75={_p75m:.0f}m  p90={_p90m:.0f}m  p98={_alt_p98:.0f}m")
        print(f"    pentes moy={self.terrain_stats['slope_mean_deg']:.1f}°  "
              f"p75={self.terrain_stats['slope_p75_deg']:.1f}°  "
              f"p90={self.terrain_stats['slope_p90_deg']:.1f}°  "
              f"p95={self.terrain_stats['slope_p95_deg']:.1f}°")
        print(f"    rugosité p50={self.terrain_stats['roughness_p50_m']:.3f}m  "
              f"p75={self.terrain_stats['roughness_p75_m']:.3f}m  "
              f"p90={self.terrain_stats['roughness_p90_m']:.3f}m  "
              f"p95={self.terrain_stats['roughness_p95_m']:.3f}m")
        print(f"    courbure p10={self.terrain_stats['curvature_p10']:.4f}  "
              f"moy={self.terrain_stats['curvature_mean']:.4f}  "
              f"p90={self.terrain_stats['curvature_p90']:.4f}  (1/m)")

        print("[HEIGHTMAP ANALYSIS] Analyse stockee et coherente OK")
    
    def _compute_slopes(self):
        """
        Calcule les pentes en degrés avec LISSAGE.
        Utilise Gaussian blur + Sobel pour gradients robustes.
        
        Le lissage (astuce Gemini) élimine le bruit pixel et capture les VRAIES pentes du relief.
        
        Returns:
            Array (H, W) avec pentes en degrés
        """
        print("[NATUREMAP] Calcul des pentes (avec lissage robuste)...")
        
        # ✅ ÉTAPE 1: Travailler sur les VRAIES altitudes en mètres
        h = self.heightmap_original.astype(np.float32)

        # 🔑 ÉTAPE 2: Lissage Gaussian AVANT gradient (élimine le bruit)
        print("  • Lissage Gaussian (5x5, sigma=1.5)...")
        h_smooth = cv2.GaussianBlur(h, (5, 5), 1.5)
        self._h_smooth = h_smooth  # stocké pour rugosité et courbure

        # ✅ ÉTAPE 3: Gradient métrique avec pas spatial réel (cellsize)
        print(f"  • Calcul gradients métriques (cellsize={self.cellsize:.3f} m/px)...")
        gy, gx = np.gradient(h_smooth, self.cellsize, self.cellsize)

        # Magnitude du gradient (tan(theta) = dz/dxy)
        magnitude = np.sqrt(gx**2 + gy**2)
        
        # Stocker gx/gy pour le calcul d'exposition (aspect)
        self._gx_raw = gx
        self._gy_raw = gy
        
        # ✅ ÉTAPE 4: Convertir en degrés (physiquement significatif)
        slopes_deg = np.degrees(np.arctan(magnitude))
        
        print(f"[NATUREMAP] Pentes (lissées): min={np.min(slopes_deg):.1f}°, max={np.max(slopes_deg):.1f}°")
        print(f"  Distribution: 0-15°={np.sum((slopes_deg >= 0) & (slopes_deg < 15))}, "
              f"15-35°={np.sum((slopes_deg >= 15) & (slopes_deg < 35))}, "
              f">35°={np.sum(slopes_deg >= 35)}")
        
        return slopes_deg

    def _compute_roughness(self, window_m: float = 5.0) -> np.ndarray:
        """
        Rugosité locale : écart-type d'altitude dans une fenêtre carrée.
        Distingue terrain rocheux (rugueux) de prairies (lisses) à pente identique.

        Formule : sqrt(E[h²] - E[h]²) via uniform_filter — rapide et exact.
        """
        from scipy.ndimage import uniform_filter

        win_px = max(3, int(round(window_m / self.cellsize)))
        if win_px % 2 == 0:
            win_px += 1

        h = self._h_smooth.astype(np.float64)
        mean_h   = uniform_filter(h,    size=win_px)
        mean_h2  = uniform_filter(h**2, size=win_px)
        variance = np.maximum(mean_h2 - mean_h**2, 0.0)
        roughness = np.sqrt(variance).astype(np.float32)

        print(f"[NATUREMAP] Rugosité (fenêtre {win_px}px={win_px*self.cellsize:.1f}m): "
              f"min={roughness.min():.3f}m  moy={roughness.mean():.3f}m  "
              f"p75={np.percentile(roughness, 75):.3f}m  max={roughness.max():.3f}m")
        return roughness

    def _compute_curvature(self) -> tuple:
        """
        Courbure du terrain depuis h_smooth (dérivées secondes).

        curvature         : Laplacien total (positif = concave/vallée, négatif = convexe/crête)
        curvature_profile : courbure dans la direction de la pente (accélère/freine l'écoulement)

        Unités : 1/m (courbure géomorphologique standard).
        """
        h  = self._h_smooth.astype(np.float64)
        dx = float(self.cellsize)

        # Laplacien : d²z/dx² + d²z/dy²
        d2z_dx2  = np.gradient(np.gradient(h, dx, axis=1), dx, axis=1)
        d2z_dy2  = np.gradient(np.gradient(h, dx, axis=0), dx, axis=0)
        laplacian = (d2z_dx2 + d2z_dy2).astype(np.float32)

        # Courbure profil : dans la direction du gradient (vecteur pente)
        gx = self._gx_raw.astype(np.float64)
        gy = self._gy_raw.astype(np.float64)
        dzdx     = np.gradient(h, dx, axis=1)
        dzdy     = np.gradient(h, dx, axis=0)
        d2_xx    = np.gradient(dzdx, dx, axis=1)
        d2_yy    = np.gradient(dzdy, dx, axis=0)
        d2_xy    = np.gradient(dzdx, dx, axis=0)

        mag2 = gx**2 + gy**2 + 1e-12
        profile_curv = (gx**2 * d2_xx + 2.0 * gx * gy * d2_xy + gy**2 * d2_yy) / mag2
        profile_curv = profile_curv.astype(np.float32)

        print(f"[NATUREMAP] Courbure totale  : "
              f"p10={np.percentile(laplacian, 10):.4f}  moy={laplacian.mean():.4f}  "
              f"p90={np.percentile(laplacian, 90):.4f}  (1/m)")
        print(f"[NATUREMAP] Courbure profil  : "
              f"p10={np.percentile(profile_curv, 10):.4f}  moy={profile_curv.mean():.4f}  "
              f"p90={np.percentile(profile_curv, 90):.4f}  (1/m)")
        return laplacian, profile_curv

    def _compute_lithology_proxy(self):
        """
        Infère une carte lithologique proxy en 4 classes à partir du relief.
        Ne nécessite aucune donnée externe.

        Classes (valeurs 0-3):
            0 — Alluvial / dépôts     : talwegs, flow fort, TPI très négatif, pentes faibles
            1 — Altérite / plateau    : relief doux, TPI proche 0, pentes modérées
            2 — Roche tendre          : versants intermédiaires, TPI modéré
            3 — Roche dure            : crêtes convexes, TPI très positif, pentes fortes

        Returns:
            Array uint8 (H, W) avec valeurs 0-3
        """
        from scipy.ndimage import uniform_filter
        print("[HEIGHTMAP ANALYSIS] Calcul lithologie proxy (4 classes)...")

        slopes = self.slopes
        tpi = self.tpi_local   # Échelle locale (~250m) : plus de détail pour la texture
        flow = self.flow_accumulation

        # Normaliser flow 0-1 pour les seuils relatifs
        flow_norm = (flow - np.min(flow)) / (np.max(flow) - np.min(flow) + 1e-6)

        # Normaliser TPI par son écart-type pour être indépendant du relief
        tpi_sigma = np.std(tpi)
        tpi_norm = tpi / (tpi_sigma + 1e-6)  # unités: sigma

        # Classe 0 — Alluvial: talwegs humides, pentes douces, TPI négatif
        class_alluvial = (
            (flow_norm > 0.65)
            & (slopes < 15.0)
            & (tpi_norm < -0.3)
        )

        # Classe 3 — Roche dure: crêtes convexes, pentes fortes
        class_hard_rock = (
            (tpi_norm > 0.6)
            & (slopes >= 25.0)
        )

        # Classe 1 — Altérite/plateau: relief doux, TPI quasi-nul
        class_alteration = (
            (slopes < 12.0)
            & (np.abs(tpi_norm) < 0.3)
            & (~class_alluvial)
            & (~class_hard_rock)
        )

        # Classe 2 — Roche tendre: tout le reste
        result = np.full((self.height, self.width), 2, dtype=np.uint8)
        result[class_alteration] = 1
        result[class_alluvial]   = 0
        result[class_hard_rock]  = 3

        counts = [np.sum(result == i) for i in range(4)]
        print(f"  • alluvial={counts[0]}, altérite={counts[1]}, roche tendre={counts[2]}, roche dure={counts[3]}")
        return result

    def _compute_stream_network(self):
        """
        Extrait le réseau de ruisseaux/rivières à partir du flow D8.

        Critères (conservateurs pour éviter l'inondation visuelle):
          - flow_accumulation > percentile 99.2   (seulement les axes majeurs)
          - tpi_local < -0.5                      (vraie concavité, pas juste plat)
          - slopes > 0.5°                         (exclut les zones aplaties)
          - hors water_mask                       (pas déjà classé eau)

        Returns:
            Array booléen (H, W)
        """
        print("[HEIGHTMAP ANALYSIS] Extraction réseau hydrographique...")
        flow_thr = np.percentile(self.flow_accumulation, 99.2)
        stream = (
            (self.flow_accumulation >= flow_thr)
            & (self.tpi_local < -0.5)
            & (self.slopes > 0.5)
            & (~self.water_mask)
        )
        return stream.astype(bool)

    def _compute_water_mask(self):
        """
        Détecte l'eau de manière conservative pour éviter d'inonder les bas-fonds.

        Principes:
          - exclure strictement les pixels NoData
          - travailler sur les pixels valides uniquement
          - ne garder que les zones très basses et peu pentues
          - conserver seulement les composantes connectées au bord
            (cas classique: mer, littoral, raster incluant l'océan)

        Returns:
            tuple(Array booléen (H, W), seuil altitude utilisé)
        """
        from scipy.ndimage import label as ndlabel

        h = self.heightmap_original.astype(np.float32)
        nodata_mask = self.nodata_mask
        if nodata_mask is None:
            nodata_mask = np.zeros((self.height, self.width), dtype=bool)

        valid_mask = ~nodata_mask
        water_mask = np.zeros((self.height, self.width), dtype=bool)
        if not np.any(valid_mask):
            return water_mask, 0.0

        hv = h[valid_mask]
        h_min = float(np.min(hv))
        h_max = float(np.max(hv))
        relief = max(h_max - h_min, 1.0)

        # Si la heightmap contient de vraies altitudes négatives (données altimétriques
        # avec niveau de la mer), utiliser 0m comme seuil. Cela couvre les cartes côtières
        # et îles où l'océan est encodé en mètres négatifs réels.
        # Sinon, recourir au seuil conservateur (évite d'inonder les bas-fonds normalisés).
        if h_min < -1.0:
            low_alt_threshold = 0.0
        else:
            low_alt_threshold = min(
                float(np.percentile(hv, 2.0)),
                h_min + max(1.5, relief * 0.01)
            )

        candidates = (
            valid_mask
            & (h <= low_alt_threshold)
            & (self.slopes <= 8.0)   # élargi : pentes sous-marines peuvent dépasser 2.5°
        )

        labeled, n_comp = ndlabel(candidates)
        if n_comp == 0:
            return water_mask, low_alt_threshold

        border_ids = np.unique(np.concatenate([
            labeled[0, :], labeled[-1, :], labeled[:, 0], labeled[:, -1]
        ]))
        border_ids = border_ids[border_ids > 0]
        if border_ids.size == 0:
            return water_mask, low_alt_threshold

        comp_sizes = np.bincount(labeled.ravel())
        min_area_px = max(64, int(np.sum(valid_mask) * 0.0005))

        for cid in border_ids:
            if comp_sizes[cid] >= min_area_px:
                water_mask |= (labeled == cid)

        return water_mask.astype(bool), low_alt_threshold

    def _compute_lake_mask(self, min_area_px=150, min_depth_m=6.0):
        """
        Détecte les lacs naturels comme cuvettes réelles de superficie significative.

        Méthode robuste (corrigée pour zones aplaties):
          1. Dépression réelle: altitude < maximum régional (fenêtre 31px) - min_depth_m
             (les zones aplaties ont un maximum régional égal à elles-mêmes → exclues)
          2. Pente très faible: < 2.5° (évite les talwegs doux)
          3. Concavité locale réelle: TPI local <= -1.5
          4. Composantes connexes ≥ min_area_px
          5. Hors water_mask, stream_network et NoData

        Args:
            min_area_px : surface minimale en pixels (défaut 150)
            min_depth_m : profondeur minimale par rapport au bord (défaut 6m)

        Returns:
            Array booléen (H, W)
        """
        from scipy.ndimage import label as ndlabel, maximum_filter
        print("[HEIGHTMAP ANALYSIS] Détection lacs naturels (méthode profondeur réelle)...")

        h = self.heightmap_original.astype(np.float32)
        nodata_mask = self.nodata_mask
        if nodata_mask is None:
            nodata_mask = np.zeros((self.height, self.width), dtype=bool)

        # Maximum régional dans une fenêtre plus large = bord potentiel du lac
        regional_max = maximum_filter(h, size=31)
        depth = regional_max - h  # profondeur relative par rapport au bord

        # Candidats: cuvette réelle + pente douce + hors eau/rivières
        candidates = (
            (depth >= min_depth_m)
            & (self.slopes < 2.5)
            & (self.tpi_local <= -1.5)
            & (~self.water_mask)
            & (~self.stream_network)
            & (~nodata_mask)
        )

        labeled, n_comp = ndlabel(candidates)
        lake_mask = np.zeros((self.height, self.width), dtype=bool)

        if n_comp == 0:
            print("  • Aucun lac détecté")
            return lake_mask

        comp_sizes = np.bincount(labeled.ravel())
        large_comps = np.where(comp_sizes >= min_area_px)[0]
        large_comps = large_comps[large_comps > 0]

        for cid in large_comps:
            lake_mask |= (labeled == cid)

        print(f"  • {len(large_comps)} lac(s) détecté(s) (>= {min_area_px}px, profondeur>= {min_depth_m}m)")
        return lake_mask

    def _compute_aspect(self):
        """
        Calcule l'exposition (aspect) en degrés géographiques.
        Convention: 0° = Nord, 90° = Est, 180° = Sud, 270° = Ouest.

        Utilise les gradients Sobel déjà calculés par _compute_slopes().

        Returns:
            Array (H, W) float32 avec exposition 0-360°
        """
        print("[HEIGHTMAP ANALYSIS] Calcul de l'exposition (aspect)...")
        # arctan2(-gy, gx): convention mathématique → géographique
        aspect_rad = np.arctan2(-self._gy_raw, self._gx_raw)
        aspect_deg = (np.degrees(aspect_rad) + 360.0) % 360.0
        return aspect_deg.astype(np.float32)

    def _compute_tpi(self, window_size=25):
        """
        Calcule le Topographic Position Index (TPI).
        TPI = altitude pixel - moyenne locale dans une fenêtre.

        Valeur positive → crête / sommet local.
        Valeur négative → creux / talweg / vallée.

        Args:
            window_size: Taille de la fenêtre en pixels.
                         Convertir des mètres: int(round(meters / self.cellsize))

        Returns:
            Array (H, W) float32 en mètres
        """
        from scipy.ndimage import uniform_filter
        scale_m = window_size * self.cellsize
        print(f"[HEIGHTMAP ANALYSIS] Calcul TPI (fenêtre {window_size}px = {scale_m:.0f}m)...")
        h = self.heightmap_original.astype(np.float32)
        local_mean = uniform_filter(h, size=window_size)
        tpi = h - local_mean
        print(f"  • TPI ({scale_m:.0f}m): min={np.min(tpi):.1f}m, max={np.max(tpi):.1f}m")
        return tpi

    def _compute_flow_accumulation(self):
        """
        Calcule l'accumulation de flux D8.
        Chaque pixel draine vers son voisin le plus bas (8 directions).
        Le résultat (log) indique les talwegs et rivières potentiels.

        Returns:
            Array (H, W) float32 — log(1 + nb pixels drainés)
        """
        print("[HEIGHTMAP ANALYSIS] Calcul flow accumulation D8...")
        h = self.heightmap_original.astype(np.float32)
        rows, cols = h.shape
        N = rows * cols

        # Empiler les 8 voisins via padding
        h_pad = np.pad(h, 1, mode='edge')
        neighbors = np.stack([
            h_pad[0:rows,   0:cols],    # NW
            h_pad[0:rows,   1:cols+1],  # N
            h_pad[0:rows,   2:cols+2],  # NE
            h_pad[1:rows+1, 0:cols],    # W
            h_pad[1:rows+1, 2:cols+2],  # E
            h_pad[2:rows+2, 0:cols],    # SW
            h_pad[2:rows+2, 1:cols+1],  # S
            h_pad[2:rows+2, 2:cols+2],  # SE
        ], axis=0)  # (8, rows, cols)

        dr_offsets = np.array([-1, -1, -1,  0,  0,  1,  1,  1])
        dc_offsets = np.array([-1,  0,  1, -1,  1, -1,  0,  1])

        # Voisin le plus bas pour chaque pixel
        min_nb_idx = np.argmin(neighbors, axis=0)  # (rows, cols)
        r_grid, c_grid = np.mgrid[0:rows, 0:cols]

        target_r = np.clip(r_grid + dr_offsets[min_nb_idx], 0, rows - 1)
        target_c = np.clip(c_grid + dc_offsets[min_nb_idx], 0, cols - 1)
        flow_to = (target_r * cols + target_c).flatten()

        # Sinks: voisin min >= pixel courant → pas de drain
        min_nb_val = neighbors[min_nb_idx, r_grid, c_grid]
        is_sink = (min_nb_val >= h).flatten()
        flow_to[is_sink] = np.arange(N)[is_sink]

        # Accumulation: traiter du plus haut au plus bas
        flat_h = h.flatten()
        sorted_idx = np.argsort(-flat_h)
        accumulation = np.ones(N, dtype=np.float32)

        print(f"  • Accumulation D8 ({N} pixels)...")
        for i in sorted_idx:
            t = flow_to[i]
            if t != i:
                accumulation[t] += accumulation[i]

        result = np.log1p(accumulation.reshape(rows, cols))
        high_flow_pct = np.sum(result > np.percentile(result, 90)) / N * 100
        print(f"  • Flow (log): max={np.max(result):.1f}, zones hautes (top 10%): {high_flow_pct:.1f}%")
        return result

    def _compute_depressions(self):
        """
        Détecte les dépressions fermées (cavités, dolines, mares potentielles).
        Un pixel est une dépression s'il est le minimum local dans sa fenêtre 3×3
        et n'est pas déjà dans le masque eau.

        Returns:
            Array booléen (H, W) — True = dépression/cavité
        """
        from scipy.ndimage import minimum_filter
        print("[HEIGHTMAP ANALYSIS] Détection des dépressions fermées...")
        h = self.heightmap_original.astype(np.float32)
        local_min = minimum_filter(h, size=3)
        # Pixel = minimum local ET hors zone eau déjà connue
        depressions = (h <= local_min + 0.01) & ~self.water_mask
        count = np.sum(depressions)
        pct = count / (self.height * self.width) * 100
        print(f"  • Dépressions détectées: {count} px ({pct:.2f}%)")
        return depressions

    def create_hypsometric_palette(self):
        """
        Crée une palette hypsométrique avec ZONES D'ALTITUDE ABSOLUES.
        Cohérent avec l'Hypsométrique Pure (altitudes en mètres, pas percentiles).
        
        Zones SIG standards:
        - 🌊 Eau: < 0m → Bleu
        - 🌾 Plaines: 0-100m → Vert clair
        - 🏞️ Collines: 100-300m → Jaune
        - 🏔️ Montagnes: 300-600m → Rouge orangé
        - ⛰️ Hauts pics: 600-1200m → Rouge vif
        - ❄️ Sommets: 1200m+ → Gris
        
        Returns:
            Naturemap colorée avec zones d'altitude absolues
        """
        print("[NATUREMAP] Génération palette hypsométrique (altitudes absolues)...")
        
        # Zones d'altitude ABSOLUES (mêmes que Hypsométrique)
        altitude_zones = [
            {"min": -500, "max": 0, "color": np.array([200, 100, 10], dtype=np.float32)},      # Eau: Bleu
            {"min": 0, "max": 100, "color": np.array([80, 160, 120], dtype=np.float32)},       # Plaines: Vert clair
            {"min": 100, "max": 300, "color": np.array([0, 255, 255], dtype=np.float32)},      # Collines: Jaune
            {"min": 300, "max": 600, "color": np.array([50, 100, 200], dtype=np.float32)},     # Montagnes: Rouge orangé
            {"min": 600, "max": 1200, "color": np.array([0, 50, 255], dtype=np.float32)},      # Hauts pics: Rouge vif
            {"min": 1200, "max": 3000, "color": np.array([128, 128, 128], dtype=np.float32)}, # Sommets: Gris
        ]
        
        result = np.zeros((self.height, self.width, 3), dtype=np.float32)
        
        # Appliquer chaque zone basée sur VRAIES altitudes
        for zone in altitude_zones:
            zone_min = zone["min"]
            zone_max = zone["max"]
            zone_color = zone["color"]
            
            # Masque: pixels dans cette zone d'altitude
            mask = (self.heightmap_original >= zone_min) & (self.heightmap_original < zone_max)
            
            if np.any(mask):
                result[mask] = zone_color
                coverage = np.sum(mask) / mask.size * 100
                print(f"[NATUREMAP]   {zone_min:.0f}-{zone_max:.0f}m: {coverage:.1f}%")
        
        # Pixels > 3000m: utiliser couleur sommets
        mask = self.heightmap_original >= 3000
        if np.any(mask):
            result[mask] = altitude_zones[-1]["color"]
        
        return result.astype(np.uint8)
    
    def create_topographic_palette(self):
        """
        Palette hypsométrique PROFESSIONNELLE (National Geographic style).
        
        Format BGR (OpenCV):
        - Eau profonde: Bleu foncé
        - Eau côtière: Cyan
        - Basses terres: Vert émeraude
        - Altitudes moyennes: Ocre/Beige
        - Hautes altitudes: Marron
        - Sommets: Blanc (neige)
        """
        print("[TOPOGRAPHIC] Génération palette professionnelle...")
        
        # COULEURS EN BGR (CORRECT FORMAT OPENCV)
        gradient_points = [
            # Eau (0-10% altitude normalisée)
            (0.00, np.array([255, 100, 0], dtype=np.float32)),       # Bleu foncé (RGB: 0, 100, 255)
            (0.08, np.array([255, 200, 100], dtype=np.float32)),     # Bleu clair (RGB: 100, 200, 255)
            (0.12, np.array([255, 255, 0], dtype=np.float32)),       # Cyan (RGB: 0, 255, 255)
            
            # Basses terres (12-25% altitude)
            (0.15, np.array([100, 180, 50], dtype=np.float32)),      # Vert émeraude (RGB: 50, 180, 100)
            (0.25, np.array([120, 200, 80], dtype=np.float32)),      # Vert tendre (RGB: 80, 200, 120)
            
            # Altitudes moyennes (25-60% altitude)
            (0.35, np.array([100, 180, 150], dtype=np.float32)),     # Vert gris → beige (RGB: 150, 180, 100)
            (0.50, np.array([120, 160, 200], dtype=np.float32)),     # Ocre-beige (RGB: 200, 160, 120)
            
            # Plateaux/Montagnes basses (60-80% altitude)
            (0.65, np.array([80, 120, 180], dtype=np.float32)),      # Marron clair (RGB: 180, 120, 80)
            (0.80, np.array([60, 100, 160], dtype=np.float32)),      # Marron foncé (RGB: 160, 100, 60)
            
            # Hauts pics/Sommets (80-100% altitude)
            (0.90, np.array([150, 150, 200], dtype=np.float32)),     # Gris-brun (RGB: 200, 150, 150)
            (1.00, np.array([255, 255, 255], dtype=np.float32)),     # Blanc pur neige (RGB: 255, 255, 255)
        ]
        
        # Vectoriser interpolation
        result = np.zeros((self.height, self.width, 3), dtype=np.float32)
        result[:, :] = gradient_points[0][1]
        
        alt_flat = self.heightmap_norm.flatten()
        result_flat = result.reshape(-1, 3)
        
        for i in range(len(gradient_points) - 1):
            alt1, col1 = gradient_points[i]
            alt2, col2 = gradient_points[i + 1]
            
            mask = (alt_flat >= alt1) & (alt_flat <= alt2)
            if np.any(mask):
                t = (alt_flat[mask] - alt1) / (alt2 - alt1 + 1e-8)
                color_interp = col1 * (1 - t[:, np.newaxis]) + col2 * t[:, np.newaxis]
                result_flat[mask] = color_interp
        
        result = result_flat.reshape(self.height, self.width, 3)
        
        # Lissage léger pour continuité
        for c in range(3):
            result[:, :, c] = cv2.GaussianBlur(result[:, :, c], (3, 3), 0.8)
        
        print("[TOPOGRAPHIC] Palette hypsométrique générée ✓")
        return np.clip(result, 0, 255).astype(np.uint8)
    
    def compute_contour_lines(self, scale=50):
        """
        Génère des lignes de niveau fines et discrètes.
        
        Args:
            scale: Intervalle de contour (pixels de heightmap)
        
        Returns:
            Array grayscale [0,255] avec contours fins
        """
        print("[TOPOGRAPHIC] Génération des lignes de niveau...")
        
        # Normaliser sur 0-1000 pour avoir des contours réguliers
        hm_scaled = (self.heightmap_norm * 1000).astype(np.float32)
        
        # Modulo pour créer les lignes
        contour_map = np.mod(hm_scaled, scale)
        contour_map = np.abs(contour_map - scale/2)  # Distance à la ligne de niveau
        
        # Épaissir autour de 0 (les vraies lignes)
        contour_lines = np.exp(-contour_map / 2).astype(np.float32) * 255
        
        # Réduire opacity (10% au lieu de 100%)
        contour_lines = (contour_lines * 0.1).astype(np.uint8)
        
        return contour_lines
    
    def compute_analytical_hillshade(self, azimuth=315, elevation=45):
        """
        Hillshade analytique depuis le Nord-Ouest.
        
        Args:
            azimuth: Direction lumière (315° = NW)
            elevation: Angle élévation source (45°)
        
        Returns:
            Array [0,1] factor de luminosité
        """
        print("[TOPOGRAPHIC] Calcul hillshade (NW, 45°)...")
        
        # Gradients Sobel
        sx = cv2.Sobel(self.heightmap_norm, cv2.CV_32F, 1, 0, ksize=3)
        sy = cv2.Sobel(self.heightmap_norm, cv2.CV_32F, 0, 1, ksize=3)
        
        # Normaliser
        sx = sx / (np.max(np.abs(sx)) + 1e-8)
        sy = sy / (np.max(np.abs(sy)) + 1e-8)
        
        # Vecteur normal à la surface
        nx = -sx
        ny = -sy
        nz = np.ones_like(sx)
        
        norm = np.sqrt(nx**2 + ny**2 + nz**2) + 1e-8
        nx /= norm
        ny /= norm
        nz /= norm
        
        # Vecteur lumière depuis NW (azimuth 315°, elevation 45°)
        az_rad = np.radians(azimuth)
        el_rad = np.radians(elevation)
        
        lx = np.cos(az_rad) * np.cos(el_rad)
        ly = np.sin(az_rad) * np.cos(el_rad)
        lz = np.sin(el_rad)
        
        # Produit scalaire
        shading = nx * lx + ny * ly + nz * lz
        shading = np.clip(shading, 0, 1)
        
        # Rehausser légèrement (0.5-1.5 range pour subtilité)
        shading = 0.5 + 0.5 * shading
        
        return shading.astype(np.float32)
    
    def create_google_maps_palette(self):
        """
        Crée une palette GOOGLE MAPS avec dégradés continus (pas de zones nettes).
        
        Gradient continu par altitude:
        - Eau: Bleu léger
        - 0-100m: Vert très clair (plaines)
        - 100-300m: Vert clair (collines basses)
        - 300-600m: Vert moyen (collines moyennes)
        - 600-1200m: Vert-marron (zones hautes)
        - 1200m+: Marron clair (crêtes)
        
        Returns:
            Array BGR avec dégradés continus
        """
        print("[NATUREMAP] Génération palette Google Maps (vectorisée)...")
        
        # Points de gradient (altitude_normalized, couleur_BGR)
        gradient_points = [
            (0.00, np.array([210, 240, 210], dtype=np.float32)),    # Eau
            (0.15, np.array([180, 220, 140], dtype=np.float32)),    # Plaines
            (0.35, np.array([150, 200, 120], dtype=np.float32)),    # Collines basses
            (0.60, np.array([130, 170, 100], dtype=np.float32)),    # Collines moyennes
            (0.80, np.array([160, 150, 120], dtype=np.float32)),    # Zones hautes
            (1.00, np.array([190, 160, 130], dtype=np.float32)),    # Sommets
        ]
        
        # Vectoriser l'interpolation (beaucoup plus rapide)
        result = np.zeros((self.height, self.width, 3), dtype=np.float32)
        result[:, :] = gradient_points[0][1]
        
        alt_flat = self.heightmap_norm.flatten()
        result_flat = result.reshape(-1, 3)
        
        for i in range(len(gradient_points) - 1):
            alt1, col1 = gradient_points[i]
            alt2, col2 = gradient_points[i + 1]
            
            mask = (alt_flat >= alt1) & (alt_flat <= alt2)
            if np.any(mask):
                t = (alt_flat[mask] - alt1) / (alt2 - alt1 + 1e-8)
                color_interp = col1 * (1 - t[:, np.newaxis]) + col2 * t[:, np.newaxis]
                result_flat[mask] = color_interp
        
        result = result_flat.reshape(self.height, self.width, 3)
        
        # Lissage avec Gaussian blur pour réduire les artefacts
        print("  • Lissage des dégradés (Gaussian)...")
        for c in range(3):
            result[:, :, c] = cv2.GaussianBlur(result[:, :, c], (3, 3), 1.0)
        
        print("[NATUREMAP] Palette Google Maps générée (dégradés lisses)✓")
        return np.clip(result, 0, 255).astype(np.uint8)
    
    def get_altitude_zones(self):
        """
        Retourne les zones d'altitude pour affichage.
        """
        return [
            {"min": -500, "max": 0, "label": "🌊 Eau"},
            {"min": 0, "max": 100, "label": "🌾 Plaines"},
            {"min": 100, "max": 300, "label": "🏞️ Collines"},
            {"min": 300, "max": 600, "label": "🏔️ Montagnes"},
            {"min": 600, "max": 1200, "label": "⛰️ Hauts pics"},
            {"min": 1200, "max": 3000, "label": "❄️ Sommets"},
        ]
    
    def generate(self):
        """
        Génère la NatureMap avec 8 biomes en cascade.
        ✅ UTILISE L'ANALYSE STOCKÉE (pas de recalcul!)
        
        Returns:
            PIL Image (RGB)
        """
        print("[NATUREMAP] Génération des biomes (analyse stockée)...")
        
        # Initialiser avec prairie par défaut
        self.naturemap[:, :] = self.COLOR_PRAIRIE
        
        # Dict pour stocker les masques
        self.biome_masks = {}
        
        # 1. EAU - ✅ Utilise le mask stocké
        print("  • Eau...")
        water_mask = self.water_mask  # ✅ STOCKÉ dans _analyze_heightmap()
        self.biome_masks['eau'] = water_mask
        self.naturemap[water_mask] = self.COLOR_WATER
        print(f"    [Seuil eau (percentile 15%): {self.water_threshold:.1f}m, {np.sum(water_mask)} px]")
        
        # 2. NEIGE (Z > 92%)
        print("  • Neige...")
        neige_mask = self.heightmap_norm > 0.92
        self.biome_masks['neige'] = neige_mask
        self.naturemap[neige_mask] = self.COLOR_SNOW
        
        # 3. ROCHE (pente > 35° OU Z > 80%)
        print("  • Roche...")
        roche_mask = (self.slopes > 35) | (self.heightmap_norm > 0.80)
        roche_mask &= ~water_mask  # Pas d'eau
        self.biome_masks['roche'] = roche_mask
        self.naturemap[roche_mask] = self.COLOR_ROCK
        
        # 4. TOUNDRA (70% ≤ Z ≤ 80%)
        print("  • Toundra...")
        toundra_mask = (self.heightmap_norm >= 0.70) & (self.heightmap_norm <= 0.80)
        toundra_mask &= ~roche_mask & ~water_mask
        self.biome_masks['toundra'] = toundra_mask
        self.naturemap[toundra_mask] = self.COLOR_TUNDRA
        
        # 5. FORÊT DENSE (15° ≤ pente ≤ 35°)
        print("  • Forêt...")
        foret_mask = (self.slopes >= 15) & (self.slopes <= 35)
        foret_mask &= ~water_mask & ~neige_mask & ~roche_mask & ~toundra_mask
        self.biome_masks['foret'] = foret_mask
        self.naturemap[foret_mask] = self.COLOR_FOREST
        
        # 6. PRAIRIE - par défaut
        prairie_mask = np.ones_like(water_mask)
        for mask in self.biome_masks.values():
            prairie_mask &= ~mask
        self.biome_masks['prairie'] = prairie_mask
        
        # 7. SABLE - Bordure eau/plaine
        print("  • Sable (bordures eau/plaine)...")
        sand_mask = self._apply_sand_border(water_mask)
        self.biome_masks['sable'] = sand_mask
        
        # Convertir en PIL Image (BGR → RGB)
        naturemap_rgb = cv2.cvtColor(self.naturemap, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(naturemap_rgb, mode='RGB')
        
        return img
    
    def generate_hypsometric(self):
        """
        Génère la NatureMap avec VRAIE palette hypsométrique CONTINUE basée sur l'altitude.
        ✅ UTILISE L'ANALYSE STOCKÉE (pentes + eau + slopes)
        
        Combine:
        - Palette hypsométrique CONTINUE (couleurs dégradées 100% basées sur l'altitude)
        - Hillshading analytique pour relief 3D visible
        - Eau avec seuil 15% (visible et prioritaire!)
        
        Résultat: Les variations d'altitude sont CLAIREMENT visibles
        - Bleu → Vert → Beige → Gris → Blanc selon altitude
        - Relief 3D visible via hillshading subtil
        
        Returns:
            PIL Image (RGB)
        """
        print("[NATUREMAP] Génération PALETTE HYPSOMÉTRIQUE PURE (analyse stockée)...")
        
        # ÉTAPE 1: Créer la VRAIE palette hypsométrique continue (basée 100% sur altitude)
        print("  • Création palette hypsométrique continue...")
        hypsometric_colors = self.create_hypsometric_palette()
        self.naturemap[:, :] = hypsometric_colors
        
        # ÉTAPE 2: Calculer hillshade (slopes déjà stockés dans _analyze_heightmap)
        print("  • Calcul du hillshade analytique...")
        self.hillshade = self.compute_analytical_hillshade(azimuth=315, elevation=45)
        
        # ÉTAPE 3: Utiliser le mask eau STOCKÉ (pas de recalcul!)
        print("  • Masque eau prioritaire (analyse stockée)...")
        water_mask = self.water_mask  # ✅ STOCKÉ
        
        # ÉTAPE 4: Appliquer hillshade SUBTIL par-dessus la palette hypsométrique (sauf eau)
        print("  • Application du hillshading très subtil (0.92-1.0 range)...")
        # Formule SIG: Couleur * (0.92 + 0.08 * Hillshade) pour éviter les bandes
        # Exclure eau de l'ombrage pour la garder lumineuse
        for c in range(3):
            colormap_float = self.naturemap[:,:,c].astype(np.float32) / 255.0
            # Appliquer uniquement sur terrain (pas eau)
            blend_factor = 0.92 + 0.08 * self.hillshade  # Très léger (0.92-1.0)
            blended = colormap_float * blend_factor
            
            result = np.where(
                water_mask,
                colormap_float * 255,  # Eau inchangée (lumineuse)
                blended * 255          # Terrain avec ombrage subtil
            )
            self.naturemap[:,:,c] = result.astype(np.uint8)
        
        # ÉTAPE 5: Réafficher eau en bleu après hillshade (PRIORITÉ ABSOLUE)
        print("  • Eau bleu prioritaire...")
        self.naturemap[water_mask] = self.COLOR_WATER
        
        print(f"    Palette hypsométrique appliquée: {np.sum(water_mask)} pixels d'eau")
        print(f"    Résultat: Dégradés continus d'altitude visibles partout")
        print(f"    Progression: Bleu (eau) → Vert (basses) → Beige (plateaux) → Gris (collines) → Blanc (crêtes)")
        
        # Convertir en PIL Image (BGR → RGB)
        naturemap_rgb = cv2.cvtColor(self.naturemap, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(naturemap_rgb, mode='RGB')
        
        return img
    
    def _compute_hillshade(self):
        """Calcule l'ombrage hillshade SIG."""
        print("    [Hillshading analytic...]")
        h_scaled = (self.heightmap_norm * 100.0).astype(np.float32)
        
        # Gradients Sobel
        sobelx = cv2.Sobel(h_scaled, cv2.CV_32F, 1, 0, ksize=3)
        sobely = cv2.Sobel(h_scaled, cv2.CV_32F, 0, 1, ksize=3)
        
        # Direction lumière (azimut 315°, élévation 45°)
        azimuth_rad = np.radians(315)
        elevation_rad = np.radians(45)
        
        Z = 1.2  # Facteur d'exagération verticale
        
        # Normale de surface
        magnitude = np.sqrt(sobelx**2 + sobely**2)
        norm_mag = np.sqrt(sobelx**2 + sobely**2 + Z**2)
        
        nx = -sobelx / (norm_mag + 1e-8)
        ny = -sobely / (norm_mag + 1e-8)
        nz = Z / (norm_mag + 1e-8)
        
        # Lumière directionnelle
        light_x = np.sin(azimuth_rad) * np.cos(elevation_rad)
        light_y = np.cos(azimuth_rad) * np.cos(elevation_rad)
        light_z = np.sin(elevation_rad)
        
        # Produit scalaire
        shaded = nx * light_x + ny * light_y + nz * light_z
        hillshade = np.clip((shaded + 1.0) / 2.0, 0, 1)
        
        return hillshade
    
    def _apply_sand_border(self, water_mask, sand_width=2):
        """
        Ajoute du sable comme bordure entre eau et plaine.
        
        Args:
            water_mask: Masque eau booléen
            sand_width: Largeur de la bordure en pixels
        
        Returns:
            sand_mask: Masque du sable
        """
        # Identifier les pixels plaine
        prairie_mask = np.all(self.naturemap == self.COLOR_PRAIRIE, axis=2)
        
        # Dilater le masque eau
        water_dilated = binary_dilation(water_mask, iterations=sand_width)
        
        # Sable = dilatation eau ET prairie
        sand_mask = water_dilated & prairie_mask
        self.naturemap[sand_mask] = self.COLOR_SAND
        
        return sand_mask
    
    def _compute_morphology(self):
        """
        Détecte les creux (vallées concaves) et émergences (crêtes convexes).
        Utilise le Laplacien pour la courbure.
        
        Returns:
            Tuple (creux_mask, emergences_mask)
        """
        print("[NATUREMAP] Analyse morphologique (creux/émergences)...")
        
        # Normaliser heightmap 0-100 pour Laplacian
        h_normalized = (self.heightmap_norm * 100.0).astype(np.float32)
        
        # Laplacien: détecte la courbure
        # Positif = concave (creux), Négatif = convexe (émergences)
        laplacian = cv2.Laplacian(h_normalized, cv2.CV_32F, ksize=3)
        
        # Calculer percentiles pour seuillage adaptatif
        laplacian_threshold = np.percentile(np.abs(laplacian), 50)  # 50e percentile
        
        # Creux: Laplacian > seuil
        creux = laplacian > laplacian_threshold
        
        # Émergences: Laplacian < -seuil
        emergences = laplacian < -laplacian_threshold
        
        # Exclure eau
        water_threshold = np.percentile(self.heightmap_original, 15)
        water_mask = self.heightmap_original <= water_threshold
        
        creux &= ~water_mask
        emergences &= ~water_mask
        
        # Morphological closing pour lisser
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        creux = cv2.morphologyEx(creux.astype(np.uint8), cv2.MORPH_CLOSE, kernel).astype(bool)
        emergences = cv2.morphologyEx(emergences.astype(np.uint8), cv2.MORPH_CLOSE, kernel).astype(bool)
        
        creux_pct = np.sum(creux) / creux.size * 100
        emergences_pct = np.sum(emergences) / emergences.size * 100
        print(f"  • Creux (vallées): {creux_pct:.1f}%")
        print(f"  • Émergences (crêtes): {emergences_pct:.1f}%")
        
        return creux, emergences
    
    def generate_enhanced_for_reforger(self, upscale_to_reforger=True):
        """
        Génère carte topographique basée sur l'analyse STOCKÉE.
        ✅ Utilise les données précalculées au chargement (pas de recalcul!)
        """
        print("[TOPOGRAPHIC MAP] Génération à partir de l'analyse stockée...")
        print(f"  • Utilise analyse: Eau={self.water_coverage_pct:.1f}%")
        
        result = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        result[:,:] = [100, 200, 100]  # Vert par défaut
        
        # ✅ VRAIES altitudes absolues (pas percentiles!)
        # Zones SIG standards utilisées dans l'analyse
        
        # Eau: < 0m → BLEU
        mask_eau = self.heightmap_original < 0
        result[mask_eau] = [255, 0, 0]  # BLEU
        
        # Plaines: 0-100m → VERT CLAIR
        mask_plains = (self.heightmap_original >= 0) & (self.heightmap_original < 100)
        result[mask_plains] = [120, 200, 80]
        
        # Collines: 100-300m → OCRE
        mask_collines = (self.heightmap_original >= 100) & (self.heightmap_original < 300)
        result[mask_collines] = [100, 180, 150]
        
        # Montagnes: 300-600m → MARRON CLAIR
        mask_montagnes = (self.heightmap_original >= 300) & (self.heightmap_original < 600)
        result[mask_montagnes] = [80, 120, 180]
        
        # Hauts pics: 600-1200m → MARRON FONCÉ
        mask_hauts = (self.heightmap_original >= 600) & (self.heightmap_original < 1200)
        result[mask_hauts] = [60, 100, 160]
        
        # Sommets: >1200m → BLANC (neige)
        mask_sommets = self.heightmap_original >= 1200
        result[mask_sommets] = [255, 255, 255]
        
        self.naturemap = result
        
        # Hillshade TRÈS SUBTIL seulement sur terrain (pas eau)
        print("  • Hillshade subtil (terrain seulement)...")
        hillshade = self.compute_analytical_hillshade(azimuth=315, elevation=45)
        
        terrain_mask = ~self.water_mask  # ✅ Utilise mask stocké
        for c in range(3):
            base_color = self.naturemap[terrain_mask, c].astype(np.float32)
            shaded = base_color * (0.92 + 0.08 * hillshade[terrain_mask])
            self.naturemap[terrain_mask, c] = np.clip(shaded, 0, 255).astype(np.uint8)

        # Convention visuelle : océan/NoData → bleu profond (en dernier)
        # Stratégie 1 : nodata_mask explicite (PNG alpha ou ASC nodata détecté)
        # Stratégie 2 : fallback border-connected pour ASC dont l'océan vaut 0.000
        visual_ocean = None
        if self.nodata_mask is not None and np.any(self.nodata_mask):
            visual_ocean = self.nodata_mask
        else:
            # Les pixels mer sont exportés à 0.000 : détection par composante connexe du bord
            from scipy.ndimage import label as _lbl
            h = self.heightmap_original
            flat_zero = (h <= 0.0)
            if np.any(flat_zero):
                labeled, _ = _lbl(flat_zero)
                border_labels = set()
                border_labels.update(labeled[0, :].tolist())
                border_labels.update(labeled[-1, :].tolist())
                border_labels.update(labeled[:, 0].tolist())
                border_labels.update(labeled[:, -1].tolist())
                border_labels.discard(0)
                if border_labels:
                    visual_ocean = np.isin(labeled, list(border_labels))

        if visual_ocean is not None and np.any(visual_ocean):
            # BGR (avant cvtColor) : [160, 90, 30] → RGB [30, 90, 160] = bleu océan
            self.naturemap[visual_ocean] = [160, 90, 30]

        # UPSCALING
        if upscale_to_reforger and (self.height, self.width) != (16257, 16257):
            print("  • Upscaling à 16257×16257...")
            upscaled = cv2.resize(self.naturemap, (16257, 16257), interpolation=cv2.INTER_CUBIC)
            upscaled = cv2.medianBlur(upscaled, 3)
            self.naturemap = upscaled
        
        # BGR → RGB
        naturemap_rgb = cv2.cvtColor(self.naturemap, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(naturemap_rgb, mode='RGB')
        
        print(f"[TOPOGRAPHIC MAP] Complète: {img.width}×{img.height}px ✓")
        return img
    
    def generate_vpn(self, profile='europe_temperee'):
        """
        Vegetation Potentielle Naturelle (VPN) — 4 profils biogéographiques.
        Profils : europe_temperee | boreal | mediterraneen | arctique
        Retourne (PIL Image RGB, dict {biome: pct}).
        """
        from scipy.ndimage import label as _lbl, gaussian_filter

        h      = self.heightmap_original.astype(np.float32)
        sl     = self.slopes.astype(np.float32)
        asp    = self.aspect.astype(np.float32)
        tpi    = self.tpi.astype(np.float32)
        flow   = self.flow_accumulation.astype(np.float32)
        H, W   = self.height, self.width
        total  = H * W

        north_factor = np.cos(np.radians(asp))
        flow_norm    = np.clip(flow / (np.percentile(flow, 99) + 1e-6), 0.0, 1.0)
        valid        = ~(self.nodata_mask if self.nodata_mask is not None
                         else np.zeros((H, W), dtype=bool))

        h_v = h[valid]
        def _pct(p): return float(np.percentile(h_v, p)) if h_v.size else 0.0
        p10 = _pct(10); p15 = _pct(15); p30 = _pct(30)
        p55 = _pct(55); p75 = _pct(75); p90 = _pct(90)

        # ── Océan / eau (communs à tous les profils) ────────────────────
        mask_ocean = np.zeros((H, W), dtype=bool)
        if self.nodata_mask is not None and np.any(self.nodata_mask):
            mask_ocean = self.nodata_mask.copy()
        else:
            flat = (h <= 0.0)
            if np.any(flat):
                labeled, _ = _lbl(flat)
                bl = set()
                for edge in [labeled[0,:], labeled[-1,:], labeled[:,0], labeled[:,-1]]:
                    bl.update(edge.tolist())
                bl.discard(0)
                if bl:
                    mask_ocean = np.isin(labeled, list(bl))

        mask_eau = (self.water_mask | self.lake_mask) & ~mask_ocean

        def _base():
            """Masque de base : exclure océan + eau."""
            return ~mask_ocean & ~mask_eau

        def _excl(*masks):
            """Exclusion cumulée."""
            m = mask_ocean | mask_eau
            for x in masks: m = m | x
            return m

        # ── PROFIL : Europe Tempérée ────────────────────────────────────
        if profile == 'europe_temperee':
            m_rip   = (flow_norm > 0.95) & (h > 0.0) & (sl < 8.0)  & _base()
            m_hum   = (h > 0.0) & (h <= p15) & (sl < 3.0) & (flow_norm > 0.6) & _base() & ~m_rip
            m_alpin = (h >= p90) & (tpi > 0.0) & (sl < 20.0) & _base()
            m_ebou  = (sl >= 25.0) & _base()
            m_coni  = (h >= p75) & (h < p90) & (sl < 25.0) & ~_excl(m_alpin, m_ebou)
            m_ubac  = (h >= p30) & (h < p75) & (north_factor > 0.3) & (sl >= 5.0) & (sl < 25.0) & ~_excl(m_coni, m_ebou)
            m_adret = (h >= p15) & (h < p55) & (north_factor < -0.2) & (sl >= 3.0) & ~_excl(m_coni, m_ubac, m_ebou)
            m_mixte = valid & ~_excl(m_rip, m_hum, m_alpin, m_ebou, m_coni, m_ubac, m_adret)
            VPN_BIOMES = [
                ("Foret mixte de plaine",   m_mixte, ( 34, 100,  34)),
                ("Chenaie seche (adret)",   m_adret, (120, 160,  50)),
                ("Hetraie-chenaie (ubac)",  m_ubac,  ( 20,  80,  40)),
                ("Foret de coniferes",      m_coni,  ( 15,  60,  30)),
                ("Zones humides",           m_hum,   ( 90, 160, 100)),
                ("Ripisylve",               m_rip,   ( 50, 180,  80)),
                ("Lande/pelouse alpine",    m_alpin, (160, 130,  80)),
                ("Eboulis / rochers",       m_ebou,  (170, 155, 140)),
                ("Eau interieure",          mask_eau,( 90, 160, 220)),
                ("Ocean / hors emprise",    mask_ocean,( 30, 90, 160)),
            ]

        # ── PROFIL : Boréal / Scandinave ────────────────────────────────
        elif profile == 'boreal':
            m_tourbiere = (h > 0.0) & (h <= p15) & (sl < 2.0) & (flow_norm > 0.5) & _base()
            m_rip       = (flow_norm > 0.95) & (h > 0.0) & (sl < 10.0) & _base() & ~m_tourbiere
            m_toundra   = (h >= p90) & _base()
            m_lande_sub = (h >= p75) & (h < p90) & (sl < 25.0) & ~_excl(m_toundra)
            m_ebou      = (sl >= 30.0) & ~_excl(m_toundra)
            m_taiga_n   = (h >= p30) & (h < p75) & (north_factor > 0.2) & ~_excl(m_lande_sub, m_ebou)
            m_taiga_s   = (h >= p30) & (h < p75) & (north_factor <= 0.2) & ~_excl(m_lande_sub, m_ebou, m_taiga_n)
            m_boreal    = valid & ~_excl(m_tourbiere, m_rip, m_toundra, m_lande_sub, m_ebou, m_taiga_n, m_taiga_s)
            VPN_BIOMES = [
                ("Foret boreale (plaine)",      m_boreal,    ( 20,  70,  40)),
                ("Taiga (ubac dense)",          m_taiga_n,   ( 10,  50,  25)),
                ("Taiga (adret clair)",         m_taiga_s,   ( 40,  90,  50)),
                ("Tourbieres",                  m_tourbiere, ( 80, 120,  60)),
                ("Ripisylve boreale",           m_rip,       ( 60, 150,  70)),
                ("Lande subalpine",             m_lande_sub, (140, 120,  60)),
                ("Toundra / pelouse",           m_toundra,   (190, 180, 130)),
                ("Eboulis / rochers",           m_ebou,      (170, 155, 140)),
                ("Eau interieure",              mask_eau,    ( 90, 160, 220)),
                ("Ocean / hors emprise",        mask_ocean,  ( 30,  90, 160)),
            ]

        # ── PROFIL : Méditerranéen ──────────────────────────────────────
        elif profile == 'mediterraneen':
            m_rip    = (flow_norm > 0.92) & (h > 0.0) & (sl < 10.0) & _base()
            m_steppe = (h > 0.0) & (h <= p15) & (sl < 5.0) & (north_factor < 0.0) & _base() & ~m_rip
            m_aride  = (sl >= 28.0) & _base()
            m_garri  = (h >= p10) & (h < p55) & (north_factor < -0.1) & (sl >= 3.0) & (sl < 28.0) & ~_excl(m_rip, m_aride)
            m_maquis = (h >= p15) & (h < p55) & (north_factor >= -0.1) & ~_excl(m_rip, m_aride, m_garri)
            m_pin    = (h >= p55) & (h < p90) & (sl < 28.0) & ~_excl(m_aride)
            m_alpin  = (h >= p90) & ~_excl(m_aride)
            m_mixte  = valid & ~_excl(m_rip, m_steppe, m_aride, m_garri, m_maquis, m_pin, m_alpin)
            VPN_BIOMES = [
                ("Chenaie mixte med.",          m_mixte,    ( 80, 130,  40)),
                ("Maquis",                      m_maquis,   (130, 160,  50)),
                ("Garrigue / steppe",           m_garri,    (190, 170,  80)),
                ("Steppe basse",                m_steppe,   (210, 190, 100)),
                ("Pinede",                      m_pin,      ( 50,  90,  40)),
                ("Pelouse/lande d altitude",    m_alpin,    (175, 155, 100)),
                ("Eboulis / rochers arides",    m_aride,    (170, 155, 140)),
                ("Ripisylve mediterraneenne",   m_rip,      ( 30, 160,  80)),
                ("Eau interieure",              mask_eau,   ( 90, 160, 220)),
                ("Ocean / hors emprise",        mask_ocean, ( 30,  90, 160)),
            ]

        # ── PROFIL : Arctique / Toundra ─────────────────────────────────
        elif profile == 'arctique':
            m_neve      = (h >= p90) & (sl < 30.0) & _base()
            m_ebou      = (sl >= 30.0) & ~_excl(m_neve)
            m_pelouse   = (h >= p75) & (h < p90) & (sl < 20.0) & ~_excl(m_neve, m_ebou)
            m_tourbiere = (h <= p15) & (sl < 2.0) & (flow_norm > 0.4) & _base()
            m_rip       = (flow_norm > 0.93) & _base() & ~m_tourbiere
            m_arb       = (h >= p30) & (h < p75) & ~_excl(m_neve, m_ebou, m_pelouse)
            m_herb      = valid & ~_excl(m_neve, m_ebou, m_pelouse, m_tourbiere, m_rip, m_arb)
            VPN_BIOMES = [
                ("Toundra herbacee",            m_herb,      (160, 175, 110)),
                ("Toundra arbustive",           m_arb,       (110, 140,  70)),
                ("Tourbieres",                  m_tourbiere, ( 90, 120,  70)),
                ("Ripisylve polaire",           m_rip,       ( 70, 150,  90)),
                ("Pelouse arctique",            m_pelouse,   (195, 190, 150)),
                ("Neves / glace permanente",    m_neve,      (225, 235, 255)),
                ("Eboulis / rochers",           m_ebou,      (170, 155, 140)),
                ("Eau interieure",              mask_eau,    ( 90, 160, 220)),
                ("Ocean / hors emprise",        mask_ocean,  ( 30,  90, 160)),
            ]

        else:
            raise ValueError(f"Profil inconnu: {profile}")

        # ── Lissage + rendu ─────────────────────────────────────────────
        def _smooth(m, sigma=1.5):
            return gaussian_filter(m.astype(np.float32), sigma=sigma) > 0.4

        result = np.full((H, W, 3), 200, dtype=np.uint8)
        stats  = {}
        vpn_masks = {}
        for name, mask, color in VPN_BIOMES:
            if name not in ("Eau interieure", "Ocean / hors emprise"):
                mask = _smooth(mask)
            result[mask] = color
            stats[name]  = float(np.sum(mask) / total * 100)
            vpn_masks[name] = mask.astype(np.bool_)

        # Stocker pour usage externe (ex: VegetationPolylineExporter)
        self.vpn_masks   = vpn_masks
        self.vpn_profile = profile

        img = Image.fromarray(result, mode='RGB')
        print(f"[VPN] {profile} — {W}x{H}px OK")
        return img, stats

    def get_biome_masks(self):
        """
        Retourne les masques des biomes détectés.
        
        Returns:
            Dict {biome_name: bool_mask} - uniquement les biomes avec pixels
        """
        # Générer la naturemap pour avoir les masques
        if not hasattr(self, 'biome_masks') or self.biome_masks is None:
            _ = self.generate()
        
        # Filtrer les biomes non-vides
        detected_masks = {}
        for biome_name, mask in self.biome_masks.items():
            if np.any(mask):  # Si au moins 1 pixel
                detected_masks[biome_name] = mask
                pixel_count = np.sum(mask)
                pct = (pixel_count / mask.size) * 100
                print(f"  • {biome_name}: {pixel_count} px ({pct:.1f}%)")
        
        return detected_masks
    
    def export_masks_arma_reforger(self, masks_dict, output_dir="output/masks"):
        """
        Exporte les masques au format Arma Reforger (PNG 16-bit Grayscale).
        
        Args:
            masks_dict: Dict {biome_name: bool_mask}
            output_dir: Répertoire de sortie
        
        Returns:
            Dict {biome_name: filepath}
        """
        os.makedirs(output_dir, exist_ok=True)
        saved_files = {}
        
        for biome_name, mask in masks_dict.items():
            # Convertir bool → uint16 (0 ou 65535)
            mask_uint16 = (mask * 65535).astype(np.uint16)
            
            # Sauvegarder en PNG 16-bit Grayscale
            img = Image.fromarray(mask_uint16, mode='I;16')
            filepath = os.path.join(output_dir, f"mask_{biome_name}_reforger.png")
            img.save(filepath)
            saved_files[biome_name] = filepath
            print(f"  ✅ {biome_name}: {filepath}")
        
        return saved_files
    
    def export_masks_unity(self, masks_dict, output_dir="output/masks"):
        """
        Exporte les masques au format Unity (RAW 16-bit Little Endian).
        
        Args:
            masks_dict: Dict {biome_name: bool_mask}
            output_dir: Répertoire de sortie
        
        Returns:
            Dict {biome_name: filepath}
        """
        os.makedirs(output_dir, exist_ok=True)
        saved_files = {}
        
        for biome_name, mask in masks_dict.items():
            # Convertir bool → uint16 (0 ou 65535)
            mask_uint16 = (mask * 65535).astype(np.uint16)
            
            # Sauvegarder en RAW 16-bit Little Endian
            filepath = os.path.join(output_dir, f"mask_{biome_name}_unity.raw")
            mask_uint16.astype('<u2').tofile(filepath)  # Little Endian uint16
            saved_files[biome_name] = filepath
            print(f"  ✅ {biome_name}: {filepath}")
        
        return saved_files
    
    def save(self, output_path="nature_map.png"):
        """
        Génère et sauvegarde la NatureMap.
        
        Args:
            output_path: Chemin de sortie
        
        Returns:
            PIL Image
        """
        img = self.generate()
        
        full_path = os.path.join(self.output_dir, output_path)
        img.save(full_path)
        
        print(f"[NATUREMAP] ✅ NatureMap sauvegardée: {full_path}")
        print(f"[NATUREMAP] Résolution: {img.width}×{img.height}px")
        
        return img


def demo():
    """Démo rapide."""
    import sys
    
    # Chercher une heightmap
    heightmap_files = [
        "input/bornholm_ter.asc",
        "input/dem.png",
    ]
    
    heightmap_path = None
    for f in heightmap_files:
        if os.path.exists(f):
            heightmap_path = f
            break
    
    if not heightmap_path:
        print("❌ Aucune heightmap trouvée!")
        print("Utilisation: python naturemap_biomes_generator.py <heightmap_path>")
        sys.exit(1)
    
    # Générer naturemap
    print(f"📍 Heightmap: {heightmap_path}")
    gen = NatureMapBiomesGenerator(heightmap_path)
    gen.save("nature_map_biomes.png")
    print("✅ Terminé!")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        heightmap_path = sys.argv[1]
        output_path = sys.argv[2] if len(sys.argv) > 2 else "nature_map_biomes.png"
        
        gen = NatureMapBiomesGenerator(heightmap_path)
        gen.save(output_path)
    else:
        demo()
