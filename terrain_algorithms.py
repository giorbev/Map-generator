# -*- coding: utf-8 -*-
"""
Terrain Algorithms — Algorithmes géomorphologiques
===================================================

Fonctions de calcul terrain extraites de pipeline_v2.py.
Utilisé par terrain_analysis.py pour le calcul des dérivés terrain.

Fonctions:
    - safe_print: Print safe Windows
    - load_asc: Charge heightmap ASC
    - calculate_slope: Calcul pente
    - calculate_aspect: Calcul aspect + humidité
    - calculate_curvature_zt: Curvature Zevenbergen & Thorne
    - calculate_tpi: Topographic Position Index
    - calculate_flow_accumulation: Flow accumulation D8
    - calculate_coastal_distance: Distance côte
    - calculate_roughness: Rugosité locale
    - auto_calibrate: Auto-calibration paramètres
"""

import numpy as np
from pathlib import Path
from scipy.ndimage import gaussian_filter, uniform_filter, distance_transform_edt, generic_filter, label
from skimage.morphology import reconstruction


def safe_print(*args, **kwargs):
    """Print safe pour Windows - évite les erreurs d'encodage et I/O closed."""
    # Essayer print normal d'abord
    try:
        print(*args, **kwargs, flush=True)
        return
    except (UnicodeEncodeError, OSError, ValueError, AttributeError):
        pass

    # Fallback: conversion ASCII
    try:
        safe_args = [arg.encode('ascii', 'replace').decode('ascii')
                     if isinstance(arg, str) else arg
                     for arg in args]
        print(*safe_args, **kwargs, flush=True)
        return
    except:
        pass

    # Dernier recours: écrire dans fichier log
    try:
        from pathlib import Path
        log_file = Path("terrain_algorithms.log")
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(' '.join(str(a) for a in args) + '\n')
    except:
        pass  # Silence complet si tout échoue


def load_asc(path):
    """
    Charge heightmap ASC format ArcGIS

    Returns:
        heightmap: array 2D altitudes (float32, nodata=NaN)
        meta: dict {ncols, nrows, cellsize, xllcorner, yllcorner, nodata_value}
    """
    safe_print(f"[1/15] Chargement heightmap: {path}")

    with open(path, 'r') as f:
        lines = f.readlines()

    # Parser header
    meta = {}
    for i in range(6):
        parts = lines[i].strip().split()
        key = parts[0].lower()
        value = float(parts[1]) if '.' in parts[1] else int(parts[1])
        meta[key] = value

    # Parser données
    data_lines = lines[6:]
    heightmap = np.array([
        [float(val) for val in line.split()]
        for line in data_lines if line.strip()
    ], dtype=np.float32)

    # Remplacer nodata par NaN
    nodata = meta.get('nodata_value', -9999)
    heightmap[heightmap == nodata] = np.nan

    safe_print(f"  Resolution: {heightmap.shape[0]}x{heightmap.shape[1]}")
    safe_print(f"  Cellsize: {meta['cellsize']}m/px")
    safe_print(f"  Altitude: {np.nanmin(heightmap):.1f}m -> {np.nanmax(heightmap):.1f}m")

    return heightmap, meta


def calculate_slope(heightmap, cellsize):
    """
    Calcule pente en degrés depuis heightmap

    Returns:
        slope: array 2D pentes (degrés, float32)
    """
    safe_print("[2/15] Calcul pentes...")

    gy, gx = np.gradient(heightmap, cellsize)
    slope = np.degrees(np.arctan(np.sqrt(gx**2 + gy**2))).astype(np.float32)

    safe_print(f"  Min: {np.nanmin(slope):.1f}, Max: {np.nanmax(slope):.1f}, "
          f"Median: {np.nanmedian(slope):.1f}")

    return slope


def calculate_aspect(heightmap, cellsize):
    """
    Calcule orientation versants + coefficient humidité

    Nord (ombragé, humide) -> forêt dense
    Sud (ensoleillé, sec) -> herbe dominante

    Returns:
        aspect: array 2D orientation 0-360° (float32)
        humidity: array 2D coefficient 0.4-1.0 (float32)
    """
    safe_print("[3/15] Calcul aspect et coefficient humidite...")

    # Gradient
    gy, gx = np.gradient(heightmap, cellsize)

    # Aspect en degrés (0=Nord, 90=Est, 180=Sud, 270=Ouest)
    aspect = np.degrees(np.arctan2(-gx, gy)) % 360
    aspect = aspect.astype(np.float32)

    # Coefficient humidité selon orientation
    humidity = np.ones_like(aspect, dtype=np.float32)

    # Nord (315°-45°) -> 1.0 (forêt dense)
    north = (aspect > 315) | (aspect < 45)
    humidity[north] = 1.0

    # Nord-Est / Nord-Ouest -> 0.85
    north_side = ((aspect >= 45) & (aspect < 90)) | \
                 ((aspect >= 270) & (aspect <= 315))
    humidity[north_side] = 0.85

    # Est / Ouest -> 0.7
    east_west = ((aspect >= 90) & (aspect < 135)) | \
                ((aspect >= 225) & (aspect < 270))
    humidity[east_west] = 0.7

    # Sud-Est / Sud-Ouest -> 0.55
    south_side = ((aspect >= 135) & (aspect < 160)) | \
                 ((aspect >= 200) & (aspect < 225))
    humidity[south_side] = 0.55

    # Sud (160°-200°) -> 0.4 (herbe dominante)
    south = (aspect >= 160) & (aspect <= 200)
    humidity[south] = 0.4

    safe_print(f"  Aspect: 0-360 degres")
    safe_print(f"  Humidity: min={np.min(humidity):.2f}, max={np.max(humidity):.2f}")

    return aspect, humidity


def calculate_curvature_zt(heightmap, cellsize):
    """
    Calcule courbures profile et plan selon Zevenbergen & Thorne (1987).

    Méthode géomorphologique standard qui distingue:
    - Profile curvature : courbure le long de la pente (accélération/décélération écoulement)
    - Plan curvature : courbure perpendiculaire (convergence/divergence → talwegs/crêtes)

    Args:
        heightmap: array 2D altitudes (float32)
        cellsize: résolution mètres/pixel

    Returns:
        tuple (profile_curvature, plan_curvature) en float32

    Référence:
        Zevenbergen & Thorne (1987), "Quantitative Analysis of Land Surface Topography"

    Plan curvature < 0 : convergence (talwegs, vallées)
    Plan curvature > 0 : divergence (crêtes, bosses)
    """
    safe_print("[3/15] Calcul curvature Zevenbergen & Thorne...")

    # Pad heightmap (1 pixel bordure mode='edge')
    heightmap_pad = np.pad(heightmap, pad_width=1, mode='edge')

    # Extraction stencil 3×3 via slicing
    # Z1 Z2 Z3
    # Z4 Z5 Z6
    # Z7 Z8 Z9
    Z1 = heightmap_pad[:-2, :-2]
    Z2 = heightmap_pad[:-2, 1:-1]
    Z3 = heightmap_pad[:-2, 2:]
    Z4 = heightmap_pad[1:-1, :-2]
    Z5 = heightmap_pad[1:-1, 1:-1]  # = heightmap lui-même
    Z6 = heightmap_pad[1:-1, 2:]
    Z7 = heightmap_pad[2:, :-2]
    Z8 = heightmap_pad[2:, 1:-1]
    Z9 = heightmap_pad[2:, 2:]

    # Coefficients Zevenbergen & Thorne
    L = cellsize
    L2 = L ** 2

    D = ((Z4 + Z6) / 2.0 - Z5) / L2
    E = ((Z2 + Z8) / 2.0 - Z5) / L2
    F = ((-Z1 + Z3 + Z7 - Z9) / 4.0) / L2
    G = ((-Z4 + Z6) / 2.0) / L
    H = ((Z2 - Z8) / 2.0) / L

    # Dénominateur (pente carrée)
    denom = G**2 + H**2

    # Dénominateur safe pour éviter division par zéro (warning numpy)
    denom_safe = np.where(denom > 1e-10, denom, 1.0)

    # Profile curvature (le long de la pente)
    profile_curvature = np.where(
        denom > 1e-10,
        -2.0 * (D * G**2 + E * H**2 + F * G * H) / denom_safe,
        0.0
    ).astype(np.float32)

    # Plan curvature (perpendiculaire à la pente, convergence/divergence)
    plan_curvature = np.where(
        denom > 1e-10,
        2.0 * (D * H**2 + E * G**2 - F * G * H) / denom_safe,
        0.0
    ).astype(np.float32)

    # Stats
    safe_print(f"  Profile curvature: min={np.nanmin(profile_curvature):.4f}, "
               f"max={np.nanmax(profile_curvature):.4f}, "
               f"mean={np.nanmean(profile_curvature):.4f}")
    safe_print(f"  Plan curvature: min={np.nanmin(plan_curvature):.4f}, "
               f"max={np.nanmax(plan_curvature):.4f}, "
               f"mean={np.nanmean(plan_curvature):.4f}")
    safe_print(f"  Methode: Zevenbergen & Thorne (1987)")

    return profile_curvature, plan_curvature


def calculate_tpi(heightmap, cellsize, radius_local_m, radius_macro_m):
    """
    Calcule TPI (Topographic Position Index) local et macro

    TPI = heightmap - moyenne_locale(heightmap, rayon)

    Returns:
        tpi_local: array 2D normalisé [-1, +1] (float32)
        tpi_macro: array 2D normalisé [-1, +1] (float32)
    """
    safe_print("[4/15] Calcul TPI local + macro...")

    # TPI local
    radius_local_px = int(radius_local_m / cellsize)
    mean_local = uniform_filter(heightmap, size=radius_local_px, mode='nearest')
    tpi_local_raw = heightmap - mean_local

    # TPI macro
    radius_macro_px = int(radius_macro_m / cellsize)
    mean_macro = uniform_filter(heightmap, size=radius_macro_px, mode='nearest')
    tpi_macro_raw = heightmap - mean_macro

    # Normaliser chaque TPI entre -1 et +1
    def normalize_tpi(tpi):
        valid = tpi[~np.isnan(tpi)]
        if len(valid) > 0:
            p1 = np.percentile(valid, 1)
            p99 = np.percentile(valid, 99)
            return np.clip((tpi - p1) / (p99 - p1) * 2 - 1, -1.0, 1.0).astype(np.float32)
        return np.zeros_like(tpi, dtype=np.float32)

    tpi_local = normalize_tpi(tpi_local_raw)
    tpi_macro = normalize_tpi(tpi_macro_raw)

    safe_print(f"  TPI local: {radius_local_m}m ({radius_local_px}px)")
    safe_print(f"  TPI macro: {radius_macro_m}m ({radius_macro_px}px)")

    return tpi_local, tpi_macro


def fill_depressions(heightmap):
    """
    Remplissage des dépressions locales via reconstruction morphologique (Soille).

    Élimine les culs-de-sac locaux qui piègent le flux et fragmentent le réseau de drainage.
    Utilise les bords de la carte comme exutoires valides.

    Args:
        heightmap: array 2D altitudes (float32, NaN pour nodata)

    Returns:
        heightmap_filled: array 2D altitudes rehaussées (float32, NaN préservés)
    """
    safe_print("  [FILL] Remplissage depressions (priority-flood)...")

    H, W = heightmap.shape

    # Masquer NaN temporairement
    nan_mask = np.isnan(heightmap)
    valid_data = heightmap[~nan_mask]

    if valid_data.size == 0:
        safe_print("  [FILL] Aucune donnee valide, skip")
        return heightmap.copy()

    # Valeur max (plafond) pour seed
    max_val = np.nanmax(valid_data)

    # Créer seed : max partout sauf bords (exutoires)
    seed = np.full((H, W), max_val, dtype=np.float32)

    # Les 4 bords gardent leur altitude d'origine (exutoires valides)
    seed[0, :]  = np.where(nan_mask[0, :],  max_val, heightmap[0, :])   # haut
    seed[-1, :] = np.where(nan_mask[-1, :], max_val, heightmap[-1, :])  # bas
    seed[:, 0]  = np.where(nan_mask[:, 0],  max_val, heightmap[:, 0])   # gauche
    seed[:, -1] = np.where(nan_mask[:, -1], max_val, heightmap[:, -1])  # droite

    # Mask : remplacer NaN par max_val pour reconstruction (évite blocage)
    mask = np.where(nan_mask, max_val, heightmap)

    # Reconstruction par érosion : seed >= mask partout, érosion jusqu'à mask
    # Résultat : heightmap sans dépressions internes, exutoires préservés
    filled = reconstruction(seed, mask, method='erosion')

    # Restaurer NaN originaux
    filled[nan_mask] = np.nan

    # Stats
    diff = filled - heightmap
    diff_valid = diff[~nan_mask]
    n_raised = int(np.sum(diff_valid > 1e-4))  # Seuil numérique 0.1mm
    pct_raised = (n_raised / valid_data.size) * 100
    max_raise = float(np.nanmax(diff_valid)) if n_raised > 0 else 0.0

    safe_print(f"  [FILL] Pixels rehausses: {n_raised:,} ({pct_raised:.2f}%)")
    safe_print(f"  [FILL] Rehaussement max: {max_raise:.2f}m")

    return filled.astype(np.float32)


def calculate_flow_accumulation(heightmap, cellsize):
    """
    Algorithme D8 pour flow accumulation AVEC remplissage préalable des dépressions.

    1. Remplit dépressions locales (priority-flood) pour éviter piégeage flux
    2. Route flux D8 sur heightmap sans culs-de-sac
    3. Résultat : réseau de drainage continu au lieu de taches isolées

    Args:
        heightmap: array 2D altitudes (float32, NaN pour nodata)
        cellsize: résolution m/pixel

    Returns:
        flow: array 2D normalisé [0, 1] (float32)
    """
    safe_print("[5/15] Calcul flow accumulation (D8 + priority-flood)...")

    # 1. REMPLISSAGE DES DÉPRESSIONS (clé du fix)
    heightmap_filled = fill_depressions(heightmap)

    # 2. ROUTING D8 sur heightmap sans dépressions
    H, W = heightmap_filled.shape
    flow = np.ones((H, W), dtype=np.float32)  # Chaque pixel commence à 1

    # Directions D8 (8 voisins)
    dirs = [(-1,-1), (-1,0), (-1,1), (0,-1), (0,1), (1,-1), (1,0), (1,1)]

    # Trier pixels par altitude décroissante (traiter hauts en premier)
    valid_mask = ~np.isnan(heightmap_filled)
    coords = np.argwhere(valid_mask)
    alts = heightmap_filled[valid_mask]
    sorted_idx = np.argsort(-alts)  # Décroissant

    # Pour chaque pixel (du haut vers le bas)
    for idx in sorted_idx:
        y, x = coords[idx]
        alt = heightmap_filled[y, x]

        # Trouver voisin le plus bas
        lowest_alt = alt
        lowest_pos = None

        for dy, dx in dirs:
            ny, nx = y + dy, x + dx
            if 0 <= ny < H and 0 <= nx < W:
                neighbor_alt = heightmap_filled[ny, nx]
                if not np.isnan(neighbor_alt) and neighbor_alt < lowest_alt:
                    lowest_alt = neighbor_alt
                    lowest_pos = (ny, nx)

        # Si voisin plus bas trouvé, accumuler flow
        if lowest_pos:
            ny, nx = lowest_pos
            flow[ny, nx] += flow[y, x]

    # 3. NORMALISATION finale (identique à avant)
    flow_valid = flow[valid_mask]
    p99 = np.percentile(flow_valid, 99)
    flow = np.clip(flow / p99, 0.0, 1.0).astype(np.float32)

    safe_print(f"  Flow max: {np.nanmax(flow):.3f}")

    return flow


def calculate_coastal_distance(heightmap, cellsize):
    """
    Calcule distance en mètres depuis la ligne de côte

    Returns:
        distance_m: array 2D distance (mètres, float32)
    """
    safe_print("[6/15] Calcul distance cotiere...")

    # Détecter mer (altitude < 0)
    sea_mask = heightmap < 0

    # Distance transform depuis terre
    distance_px = distance_transform_edt(~sea_mask)
    distance_m = (distance_px * cellsize).astype(np.float32)

    safe_print(f"  Distance max: {np.nanmax(distance_m):.0f}m")

    return distance_m


def calculate_roughness(heightmap, cellsize):
    """
    Calcule rugosité locale = écart-type altitude dans rayon 20m

    Différencie terrain accidenté (roche) vs pente lisse

    Returns:
        roughness: array 2D normalisé [0, 1] (float32)
    """
    safe_print("[7/15] Calcul roughness locale...")

    # Rayon 20m en pixels
    radius_px = int(20 / cellsize)

    # Écart-type local
    roughness_raw = generic_filter(heightmap, np.std, size=radius_px, mode='nearest')

    # Normaliser entre 0 et 1
    valid = roughness_raw[~np.isnan(roughness_raw)]
    if len(valid) > 0:
        rmin = np.min(valid)
        rmax = np.max(valid)
        roughness = ((roughness_raw - rmin) / (rmax - rmin)).astype(np.float32)
    else:
        roughness = np.zeros_like(heightmap, dtype=np.float32)

    safe_print(f"  Rayon: {radius_px}px ({radius_px * cellsize:.1f}m)")
    safe_print(f"  Min: {np.nanmin(roughness):.3f}, Max: {np.nanmax(roughness):.3f}")

    return roughness


def auto_calibrate(heightmap, slope, flow, params, curvature=None, roughness=None):
    """
    Calcule valeurs auto pour paramètres None

    Args:
        curvature: optionnel, pour auto-calibrer debris_curvature_max
        roughness: optionnel, pour auto-calibrer rock_roughness_min

    Returns:
        params: dict complété avec valeurs auto
    """
    safe_print("[8/15] Auto-calibration parametres...")

    params_out = params.copy()

    # Terrain émergé
    land_mask = (heightmap > 0) & (~np.isnan(heightmap))
    land_alt = heightmap[land_mask]

    slope_valid = slope[~np.isnan(slope)]
    flow_valid = flow[~np.isnan(flow)]

    if curvature is not None:
        curv_valid = curvature[~np.isnan(curvature)]
    else:
        curv_valid = None

    if roughness is not None:
        rough_valid = roughness[~np.isnan(roughness)]
    else:
        rough_valid = None

    # Altitude
    if params_out['coastal_alt_max_m'] is None:
        params_out['coastal_alt_max_m'] = float(np.percentile(land_alt, 10))
        safe_print(f"  [AUTO] coastal_alt_max_m = {params_out['coastal_alt_max_m']:.1f}m (P10)")
    else:
        safe_print(f"  [USER] coastal_alt_max_m = {params_out['coastal_alt_max_m']:.1f}m")

    if params_out['grass_low_max_m'] is None:
        params_out['grass_low_max_m'] = float(np.percentile(land_alt, 30))
        safe_print(f"  [AUTO] grass_low_max_m = {params_out['grass_low_max_m']:.1f}m (P30)")
    else:
        safe_print(f"  [USER] grass_low_max_m = {params_out['grass_low_max_m']:.1f}m")

    if params_out['grass_mid_max_m'] is None:
        params_out['grass_mid_max_m'] = float(np.percentile(land_alt, 66))
        safe_print(f"  [AUTO] grass_mid_max_m = {params_out['grass_mid_max_m']:.1f}m (P66)")
    else:
        safe_print(f"  [USER] grass_mid_max_m = {params_out['grass_mid_max_m']:.1f}m")

    if params_out['grass_high_max_m'] is None:
        params_out['grass_high_max_m'] = float(np.percentile(land_alt, 80))
        safe_print(f"  [AUTO] grass_high_max_m = {params_out['grass_high_max_m']:.1f}m (P80)")
    else:
        safe_print(f"  [USER] grass_high_max_m = {params_out['grass_high_max_m']:.1f}m")

    # Slope
    if params_out['debris_min_deg'] is None:
        params_out['debris_min_deg'] = float(np.percentile(slope_valid, 65))
        safe_print(f"  [AUTO] debris_min_deg = {params_out['debris_min_deg']:.1f} (P65)")
    else:
        safe_print(f"  [USER] debris_min_deg = {params_out['debris_min_deg']:.1f}")

    if params_out['rock_min_deg'] is None:
        params_out['rock_min_deg'] = float(np.percentile(slope_valid, 85))
        safe_print(f"  [AUTO] rock_min_deg = {params_out['rock_min_deg']:.1f} (P85)")
    else:
        safe_print(f"  [USER] rock_min_deg = {params_out['rock_min_deg']:.1f}")


    # Roughness - deux seuils
    if rough_valid is not None:
        # rock_roughness_min (P70) : rock_walls
        if params_out.get('rock_roughness_min') is None:
            params_out['rock_roughness_min'] = float(np.percentile(rough_valid, 70))
            safe_print(f"  [AUTO] rock_roughness_min = {params_out['rock_roughness_min']:.3f} (P70 rock)")
        else:
            safe_print(f"  [USER] rock_roughness_min = {params_out['rock_roughness_min']:.3f}")

        # debris_roughness_min (P50) : debris_rock
        if params_out.get('debris_roughness_min') is None:
            params_out['debris_roughness_min'] = float(np.percentile(rough_valid, 50))
            safe_print(f"  [AUTO] debris_roughness_min = {params_out['debris_roughness_min']:.3f} (P50 debris)")
        else:
            safe_print(f"  [USER] debris_roughness_min = {params_out['debris_roughness_min']:.3f}")
    else:
        # Fallback si roughness non fournie
        params_out['rock_roughness_min'] = 0.10
        params_out['debris_roughness_min'] = 0.05

    return params_out
