# -*- coding: utf-8 -*-
"""
Terrain Analysis — Calcul centralisé des données terrain
=========================================================

Calcule TOUS les dérivés terrain depuis la heightmap UNE SEULE FOIS.
Stocké dans session_state['terrain_data'] pour réutilisation dans tous les TABs.

Usage:
    from terrain_analysis import compute_terrain_data
    terrain_data = compute_terrain_data(heightmap_path)
    st.session_state['terrain_data'] = terrain_data
"""

import numpy as np
import time
from pathlib import Path
from scipy.ndimage import gaussian_filter

# ══════════════════════════════════════════════════════════════════════════════
# VERSION DU PIPELINE (pour invalidation automatique du cache)
# ══════════════════════════════════════════════════════════════════════════════
# Incrémenter cette version à chaque modification des algorithmes de calcul
# (flow, curvature, TPI, etc.) pour forcer le recalcul sur les anciens caches
TERRAIN_PIPELINE_VERSION = "2.2.0"  # v2.2.0 : ajout deposit (TWI) + flow/deposit export PNG


def compute_terrain_data(heightmap_path, params=None, progress_callback=None):
    """
    Calcule TOUS les dérivés terrain depuis la heightmap.
    À appeler UNE SEULE FOIS au chargement de la heightmap.

    Args:
        heightmap_path: str ou Path vers fichier .asc
        params: dict optionnel de paramètres (pour auto-calibration)
        progress_callback: fonction optionnelle (step_name: str, progress: float 0-1)

    Returns:
        dict {
            # Données brutes
            'heightmap': array float32,
            'heightmap_smooth': array float32,
            'meta': dict (ncols, nrows, cellsize, etc.),
            'cellsize': float,

            # Dérivés terrain
            'slope': array float32 (degrés),
            'curvature': array float32 (normalisé),
            'tpi_local': array float32 (normalisé),
            'tpi_macro': array float32 (normalisé),
            'flow': array float32 (normalisé),
            'distance_cote': array float32 (mètres),
            'aspect': array float32 (degrés 0-360),
            'roughness': array float32 (normalisé),

            # Paramètres calibrés
            'params': dict,

            # Métadonnées
            'computation_time': float (secondes),
            'timestamp': str (ISO 8601)
        }
    """
    from pipeline_v2 import (
        load_asc,
        calculate_slope,
        calculate_curvature_zt,
        calculate_tpi,
        calculate_flow_accumulation,
        calculate_coastal_distance,
        calculate_aspect,
        calculate_roughness,
        auto_calibrate,
        safe_print
    )
    from datetime import datetime

    start_time = time.time()

    def progress(step, pct):
        if progress_callback:
            progress_callback(step, pct)

    # ═══════════════════════════════════════════════════════════════════════
    # 1. CHARGEMENT HEIGHTMAP
    # ═══════════════════════════════════════════════════════════════════════
    progress("Chargement heightmap", 0.0)
    heightmap, meta = load_asc(str(heightmap_path))
    cellsize = meta['cellsize']

    # ═══════════════════════════════════════════════════════════════════════
    # 2. LISSAGE HEIGHTMAP (pour curvature/TPI/aspect)
    # ═══════════════════════════════════════════════════════════════════════
    progress("Lissage heightmap", 0.1)
    # Sigma adaptatif : 32m de rayon ~ smoothing modéré
    sigma = max(4, int(32 / cellsize))
    heightmap_smooth = gaussian_filter(heightmap, sigma=sigma)

    # ═══════════════════════════════════════════════════════════════════════
    # 3. CALCUL SLOPE (depuis heightmap brute pour précision)
    # ═══════════════════════════════════════════════════════════════════════
    progress("Calcul pente", 0.2)
    slope = calculate_slope(heightmap, cellsize)

    # ═══════════════════════════════════════════════════════════════════════
    # 4. CALCUL CURVATURE (depuis heightmap lisse — Zevenbergen & Thorne)
    # ═══════════════════════════════════════════════════════════════════════
    progress("Calcul courbure", 0.3)

    # Lissage dédié courbure (plus fort pour réduire artefacts haute fréquence)
    curvature_smooth_sigma_m = params.get('curvature_smooth_sigma_m', 64.0) if params else 64.0
    sigma_curvature = max(8, int(curvature_smooth_sigma_m / cellsize))
    heightmap_smooth_curv = gaussian_filter(heightmap_smooth, sigma=sigma_curvature)
    safe_print(f"  [CURV-SMOOTH] sigma dedie applique: {sigma_curvature}px ({sigma_curvature*cellsize:.1f}m)")

    curvature_profile, curvature_plan = calculate_curvature_zt(heightmap_smooth_curv, cellsize)

    # ═══════════════════════════════════════════════════════════════════════
    # 5. CALCUL TPI (local + macro)
    # ═══════════════════════════════════════════════════════════════════════
    progress("Calcul TPI", 0.4)
    tpi_local_radius = 100.0  # mètres
    tpi_macro_radius = 500.0  # mètres

    if params:
        tpi_local_radius = params.get('tpi_local_radius_m', tpi_local_radius)
        tpi_macro_radius = params.get('tpi_macro_radius_m', tpi_macro_radius)

    tpi_local, tpi_macro = calculate_tpi(
        heightmap_smooth, cellsize,
        tpi_local_radius, tpi_macro_radius
    )

    # ═══════════════════════════════════════════════════════════════════════
    # 6. CALCUL FLOW ACCUMULATION
    # ═══════════════════════════════════════════════════════════════════════
    progress("Calcul flow accumulation", 0.5)
    flow = calculate_flow_accumulation(heightmap, cellsize)

    # ═══════════════════════════════════════════════════════════════════════
    # 7. CALCUL DISTANCE CÔTE
    # ═══════════════════════════════════════════════════════════════════════
    progress("Calcul distance côte", 0.7)
    distance_cote = calculate_coastal_distance(heightmap, cellsize)

    # ═══════════════════════════════════════════════════════════════════════
    # 8. CALCUL ASPECT (orientation)
    # ═══════════════════════════════════════════════════════════════════════
    progress("Calcul aspect", 0.8)
    aspect, _ = calculate_aspect(heightmap_smooth, cellsize)

    # ═══════════════════════════════════════════════════════════════════════
    # 9. CALCUL ROUGHNESS (rugosité locale)
    # ═══════════════════════════════════════════════════════════════════════
    progress("Calcul roughness", 0.85)
    roughness = calculate_roughness(heightmap_smooth, cellsize)

    # ═══════════════════════════════════════════════════════════════════════
    # 10. AUTO-CALIBRATION DES PARAMÈTRES
    # ═══════════════════════════════════════════════════════════════════════
    progress("Auto-calibration paramètres", 0.9)

    # Paramètres par défaut complets pour auto_calibrate
    params_default = {
        "coastal_distance_max_m": 60.0,
        "coastal_alt_max_m": None,
        "grass_low_max_m": None,
        "grass_mid_max_m": None,
        "grass_high_max_m": None,
        "debris_min_deg": None,
        "rock_min_deg": None,
        "tpi_local_radius_m": 100.0,
        "tpi_macro_radius_m": 500.0,
        "flow_threshold": None,
        "feather_coastal_m": 20.0,
        "feather_grass_m": 20.0,
        "feather_rock_m": 20.0,
        "feather_debris_m": 25.0,
        "feather_forest_m": 40.0,
        "feather_river_m": 15.0,
        "curvature_smooth_sigma_m": 64.0,
    }

    # Merger avec params fourni (si présent)
    if params:
        params_default.update(params)

    params_calibrated = auto_calibrate(heightmap, slope, flow, params_default)

    # ═══════════════════════════════════════════════════════════════════════
    # 11. ASSEMBLAGE RÉSULTAT
    # ═══════════════════════════════════════════════════════════════════════
    progress("Finalisation", 1.0)

    elapsed = time.time() - start_time

    return {
        # Données brutes
        'heightmap': heightmap,
        'heightmap_smooth': heightmap_smooth,
        'meta': meta,
        'cellsize': cellsize,

        # Dérivés terrain
        'slope': slope,
        'curvature': curvature_plan,  # Alias pour rétrocompat (pointe vers plan curvature)
        'curvature_plan': curvature_plan,
        'curvature_profile': curvature_profile,
        'tpi_local': tpi_local,
        'tpi_macro': tpi_macro,
        'flow': flow,
        'distance_cote': distance_cote,
        'aspect': aspect,
        'roughness': roughness,

        # Paramètres calibrés
        'params': params_calibrated,

        # Métadonnées
        'computation_time': elapsed,
        'timestamp': datetime.now().isoformat(),
        'heightmap_path': str(Path(heightmap_path).resolve()),
        'pipeline_version': TERRAIN_PIPELINE_VERSION  # Ajout version pour invalidation cache
    }


def get_terrain_stats(terrain_data):
    """
    Calcule statistiques descriptives depuis terrain_data.

    Returns:
        dict avec min/max/mean/std pour chaque signal
    """
    stats = {}

    signals = ['heightmap', 'slope', 'curvature', 'tpi_local', 'tpi_macro',
               'flow', 'distance_cote', 'aspect', 'roughness']

    for sig in signals:
        if sig in terrain_data:
            arr = terrain_data[sig]

            # Masquer eau pour heightmap/slope
            if sig in ['heightmap', 'slope']:
                land_mask = terrain_data['heightmap'] > 0
                arr_land = arr[land_mask]
            else:
                arr_land = arr.ravel()

            if arr_land.size > 0:
                stats[sig] = {
                    'min': float(np.nanmin(arr_land)),
                    'max': float(np.nanmax(arr_land)),
                    'mean': float(np.nanmean(arr_land)),
                    'std': float(np.nanstd(arr_land)),
                    'p05': float(np.nanpercentile(arr_land, 5)),
                    'p95': float(np.nanpercentile(arr_land, 95))
                }

    return stats


def recommend_curvature_thresholds(heightmap, slope=None):
    """
    Recommande seuils curvature Instant Terra basés sur analyse heightmap.

    Args:
        heightmap: array numpy altitudes
        slope: array pentes (optionnel, calculé si absent)

    Returns:
        dict: {
            'terrain_type': str,
            'denivele': float,
            'rugosity': float,
            'recommended_min': float,
            'recommended_max': float,
            'confidence': str,
            'notes': str
        }
    """
    # Stats terrain
    valid = heightmap[~np.isnan(heightmap)]
    land = heightmap[heightmap > 0]

    if land.size == 0:
        # Terrain entièrement sous l'eau
        return {
            'terrain_type': 'Aquatique',
            'denivele': 0.0,
            'rugosity': 0.0,
            'recommended_min': -10.0,
            'recommended_max': 10.0,
            'confidence': 'Faible',
            'notes': 'Terrain entièrement aquatique, seuils par défaut'
        }

    denivele = float(np.max(land) - np.min(land))

    # Rugosité (variance pentes)
    if slope is None:
        dy, dx = np.gradient(heightmap)
        slope_approx = np.sqrt(dx**2 + dy**2)
        rugosity = float(np.nanstd(slope_approx))
    else:
        land_slope = slope[heightmap > 0]
        rugosity = float(np.nanstd(land_slope))

    # Déterminer type terrain et seuils recommandés
    if denivele < 100:
        terrain_type = "Plat / Plaine"
        rec_min, rec_max = -10.0, 10.0
        confidence = "Haute"
        notes = "Terrain plat, seuils standard suffisants"
    elif denivele < 300:
        terrain_type = "Vallonné"
        rec_min, rec_max = -12.0, 12.0
        confidence = "Haute"
        notes = "Relief modéré, seuils légèrement élargis"
    elif denivele < 600:
        terrain_type = "Montagneux"
        rec_min, rec_max = -15.0, 15.0
        confidence = "Moyenne"
        notes = "Relief important, seuils élargis recommandés"
    else:
        terrain_type = "Très accidenté / Alpin"
        rec_min, rec_max = -20.0, 20.0
        confidence = "Moyenne"
        notes = "Relief extrême, seuils larges requis"

    # Ajustement selon rugosité
    if rugosity > 8:
        rec_min -= 2
        rec_max += 2
        notes += ". Micro-relief important détecté (rugosité élevée)"

    return {
        'terrain_type': terrain_type,
        'denivele': denivele,
        'rugosity': rugosity,
        'recommended_min': rec_min,
        'recommended_max': rec_max,
        'confidence': confidence,
        'notes': notes
    }


# ══════════════════════════════════════════════════════════════════════════════
# TESTS
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python terrain_analysis.py <heightmap.asc>")
        sys.exit(1)

    heightmap_path = sys.argv[1]

    print(f"Analyse terrain : {heightmap_path}")
    print("=" * 60)

    def progress_print(step, pct):
        print(f"[{pct*100:5.1f}%] {step}")

    terrain_data = compute_terrain_data(heightmap_path, progress_callback=progress_print)

    print("\n" + "=" * 60)
    print(f"✓ Calcul terminé en {terrain_data['computation_time']:.2f}s")
    print(f"  Résolution : {terrain_data['meta']['ncols']}x{terrain_data['meta']['nrows']} px")
    print(f"  Cellsize   : {terrain_data['cellsize']} m/px")

    stats = get_terrain_stats(terrain_data)

    print("\nStatistiques terrain :")
    for signal, stat in stats.items():
        print(f"  {signal:15s} : [{stat['min']:7.2f}, {stat['max']:7.2f}] "
              f"mean={stat['mean']:7.2f} std={stat['std']:7.2f}")

    print("\nParamètres auto-calibrés :")
    for key, val in terrain_data['params'].items():
        print(f"  {key:30s} : {val}")
