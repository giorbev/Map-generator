"""
Pipeline V2 — Génération Masks Terrain Reforger
================================================

Nouveau système complet :
- Calcul curvature, TPI, flow depuis heightmap
- Classification unique par pixel (priorités strictes)
- Feathering slope-aware
- 13 masks : +mud_river, +forest_floor

Usage:
    python pipeline_v2.py <heightmap.asc> <output_dir>
    python pipeline_v2.py heightmap.asc output/ --params params.json
"""

import numpy as np
from pathlib import Path
from PIL import Image
from scipy.ndimage import gaussian_filter, uniform_filter, distance_transform_edt
import matplotlib.pyplot as plt
import cv2
import sys
import json
import time
from datetime import datetime

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
        log_file = Path("pipeline_v2.log")
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(' '.join(str(a) for a in args) + '\n')
    except:
        pass  # Silence complet si tout échoue


# ══════════════════════════════════════════════════════════════════════════════
# 1. LOAD ASC
# ══════════════════════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════════════════════
# 1B. LOAD VEGETATION MAP (MODE 2)
# ══════════════════════════════════════════════════════════════════════════════

def load_vegetation_map(veg_png_path, target_shape):
    """
    Charge carte végétation PNG colorée et extrait 7 zones par couleur dominante.

    Args:
        veg_png_path: Chemin vers PNG coloré
        target_shape: (H, W) shape heightmap cible

    Returns:
        dict {zone_name: mask_float32_0-1}
    """
    safe_print(f"[MODE 2] Chargement carte vegetation: {veg_png_path}")

    img = cv2.imread(str(veg_png_path), cv2.IMREAD_COLOR)
    if img is None:
        safe_print(f"  [ERREUR] Impossible de charger {veg_png_path}")
        return {}

    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    # Redimensionner vers target_shape
    if img.shape[:2] != target_shape:
        img = cv2.resize(img,
                        (target_shape[1], target_shape[0]),
                        interpolation=cv2.INTER_NEAREST)

    img_f = img.astype(np.float32) / 255.0

    # Couleurs de référence des 7 zones (Zimnitrita)
    ZONE_COLORS = {
        "eau"             : np.array([0.20, 0.40, 0.70]),
        "plateau_herbeux" : np.array([0.55, 0.67, 0.43]),
        "prairie_seche"   : np.array([0.71, 0.77, 0.35]),
        "foret_mixte"     : np.array([0.26, 0.47, 0.21]),
        "foret_coniferes" : np.array([0.14, 0.34, 0.12]),
        "veg_rupestre"    : np.array([0.54, 0.61, 0.55]),
        "non_attribue"    : np.array([0.78, 0.76, 0.72]),
    }

    masks = {}
    for zone_name, ref_color in ZONE_COLORS.items():
        # Distance euclidienne par pixel
        diff = np.linalg.norm(img_f - ref_color, axis=2)
        # Score de proximité normalisé
        score = np.clip(1.0 - diff / 0.3, 0.0, 1.0)
        masks[zone_name] = score.astype(np.float32)

        px_count = int(np.sum(score > 0.3))
        safe_print(f"  Zone '{zone_name}': {px_count} pixels detectes")

    return masks


def load_vegetation_masks_from_dir(veg_dir, target_shape):
    """
    Charge 7 masks PNG végétation déjà extraits depuis dossier (cas Zimnitrita).

    Args:
        veg_dir: Dossier contenant masks PNG
        target_shape: (H, W) shape heightmap cible

    Returns:
        dict {zone_name: mask_float32_0-1}
    """
    safe_print(f"[MODE 2] Chargement masks vegetation: {veg_dir}")

    veg_names = [
        "eau", "plateau_herbeux", "prairie_seche",
        "foret_mixte", "foret_coniferes",
        "veg_rupestre", "non_attribue"
    ]

    masks = {}
    veg_path = Path(veg_dir)

    for name in veg_names:
        matches = list(veg_path.glob(f"*{name}*.png"))
        if not matches:
            safe_print(f"  [SKIP] Zone '{name}': fichier non trouve")
            continue

        arr = cv2.imread(str(matches[0]), cv2.IMREAD_UNCHANGED)
        if arr is None:
            safe_print(f"  [ERREUR] Impossible de lire {matches[0]}")
            continue

        # Redimensionner si nécessaire
        if arr.shape[:2] != target_shape:
            arr = cv2.resize(arr,
                           (target_shape[1], target_shape[0]),
                           interpolation=cv2.INTER_LINEAR)

        # Normaliser 0-1
        if arr.dtype == np.uint16:
            masks[name] = arr.astype(np.float32) / 65535.0
        elif arr.dtype == np.uint8:
            masks[name] = arr.astype(np.float32) / 255.0
        else:
            masks[name] = arr.astype(np.float32)

        px_count = int(np.sum(masks[name] > 0.3))
        safe_print(f"  Zone '{name}': {px_count} pixels charges")

    return masks


# ══════════════════════════════════════════════════════════════════════════════
# 2. CALCULATE SLOPE
# ══════════════════════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════════════════════
# 3. CALCULATE ASPECT
# ══════════════════════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════════════════════
# 4. CALCULATE CURVATURE
# ══════════════════════════════════════════════════════════════════════════════

def calculate_curvature(heightmap, cellsize):
    """
    Calcule curvature via DoG SANS normalisation
    Les valeurs brutes sont conservées pour permettre
    des seuils en percentile (comme slope, flow, etc.)

    Valeurs négatives = concave (creux, vallées)
    Valeurs positives = convexe (crêtes, bosses)

    Returns:
        curvature: array 2D valeurs brutes (float32)
    """
    safe_print("[3/15] Calcul curvature DoG...")

    # DoG = différence entre flou fin et flou grossier
    # sigma=2 → détails locaux (micro-relief)
    # sigma=8 → tendance générale (vallées larges)
    curv_fine   = gaussian_filter(heightmap.astype(np.float32), sigma=2)
    curv_coarse = gaussian_filter(heightmap.astype(np.float32), sigma=8)
    curvature   = curv_fine - curv_coarse

    safe_print(f"  Min: {np.nanmin(curvature):.4f}, "
               f"Max: {np.nanmax(curvature):.4f}, "
               f"Moy: {np.nanmean(curvature):.4f}")
    safe_print(f"  DoG sigma: 2 (fin) vs 8 (grossier)")

    return curvature.astype(np.float32)


# ══════════════════════════════════════════════════════════════════════════════
# 4. CALCULATE TPI
# ══════════════════════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════════════════════
# 5. CALCULATE FLOW ACCUMULATION
# ══════════════════════════════════════════════════════════════════════════════

def calculate_flow_accumulation(heightmap, cellsize):
    """
    Algorithme D8 simplifié pour flow accumulation

    Pour chaque pixel, compte combien de pixels drainent vers lui

    Returns:
        flow: array 2D normalisé [0, 1] (float32)
    """
    safe_print("[5/15] Calcul flow accumulation (D8)...")

    H, W = heightmap.shape
    flow = np.ones((H, W), dtype=np.float32)  # Chaque pixel commence à 1

    # Directions D8 (8 voisins)
    dirs = [(-1,-1), (-1,0), (-1,1), (0,-1), (0,1), (1,-1), (1,0), (1,1)]

    # Trier pixels par altitude décroissante (traiter hauts en premier)
    valid_mask = ~np.isnan(heightmap)
    coords = np.argwhere(valid_mask)
    alts = heightmap[valid_mask]
    sorted_idx = np.argsort(-alts)  # Décroissant

    # Pour chaque pixel (du haut vers le bas)
    for idx in sorted_idx:
        y, x = coords[idx]
        alt = heightmap[y, x]

        # Trouver voisin le plus bas
        lowest_alt = alt
        lowest_pos = None

        for dy, dx in dirs:
            ny, nx = y + dy, x + dx
            if 0 <= ny < H and 0 <= nx < W:
                neighbor_alt = heightmap[ny, nx]
                if not np.isnan(neighbor_alt) and neighbor_alt < lowest_alt:
                    lowest_alt = neighbor_alt
                    lowest_pos = (ny, nx)

        # Si voisin plus bas trouvé, accumuler flow
        if lowest_pos:
            ny, nx = lowest_pos
            flow[ny, nx] += flow[y, x]

    # Normaliser entre 0 et 1
    flow_valid = flow[valid_mask]
    p99 = np.percentile(flow_valid, 99)
    flow = np.clip(flow / p99, 0.0, 1.0).astype(np.float32)

    safe_print(f"  Flow max: {np.nanmax(flow):.3f}")

    return flow


# ══════════════════════════════════════════════════════════════════════════════
# 6. CALCULATE COASTAL DISTANCE
# ══════════════════════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════════════════════
# 7. CALCULATE ROUGHNESS
# ══════════════════════════════════════════════════════════════════════════════

def calculate_roughness(heightmap, cellsize):
    """
    Calcule rugosité locale = écart-type altitude dans rayon 20m

    Différencie terrain accidenté (roche) vs pente lisse

    Returns:
        roughness: array 2D normalisé [0, 1] (float32)
    """
    safe_print("[7/15] Calcul roughness locale...")

    from scipy.ndimage import generic_filter

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


# ══════════════════════════════════════════════════════════════════════════════
# 8. AUTO-CALIBRATE
# ══════════════════════════════════════════════════════════════════════════════

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

    # Flow - trois seuils
    # flow_mud_threshold (P95) : fonds de vallée/mud_river
    if params_out.get('flow_mud_threshold') is None:
        params_out['flow_mud_threshold'] = float(np.percentile(flow_valid, 95))
        safe_print(f"  [AUTO] flow_mud_threshold = {params_out['flow_mud_threshold']:.3f} (P95 fonds vallée)")
    else:
        safe_print(f"  [USER] flow_mud_threshold = {params_out['flow_mud_threshold']:.3f}")

    # flow_debris_threshold (P90) : ravines/debris_rock (restrictif)
    if params_out.get('flow_debris_threshold') is None:
        params_out['flow_debris_threshold'] = float(np.percentile(flow_valid, 90))
        safe_print(f"  [AUTO] flow_debris_threshold = {params_out['flow_debris_threshold']:.3f} (P90 ravines)")
    else:
        safe_print(f"  [USER] flow_debris_threshold = {params_out['flow_debris_threshold']:.3f}")

    # flow_dirt_threshold (P75) : dirt_erosion (creux doux)
    if params_out.get('flow_dirt_threshold') is None:
        params_out['flow_dirt_threshold'] = float(np.percentile(flow_valid, 75))
        safe_print(f"  [AUTO] flow_dirt_threshold = {params_out['flow_dirt_threshold']:.3f} (P75 creux doux)")
    else:
        safe_print(f"  [USER] flow_dirt_threshold = {params_out['flow_dirt_threshold']:.3f}")

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


# ══════════════════════════════════════════════════════════════════════════════
# 8. CLASSIFY PIXELS
# ══════════════════════════════════════════════════════════════════════════════

def classify_pixels(heightmap, slope, curvature, tpi_local, tpi_macro,
                     flow, distance_coastal, roughness, humidity, params,
                     vegetation_masks=None):
    """
    Classification unique par pixel selon priorités strictes

    MODE 1 (vegetation_masks=None):
        classification: array 2D int8 (0-12)
            0=seabed, 1=coastal_pebbles, 2=coastal_grass,
            3=rock_walls, 4=debris_rock, 5=dirt_erosion,
            6=mud_river, 7=grass_low, 8=grass_mid, 9=grass_high,
            10=mountain_grass_low, 11=mountain_grass_high,
            12=forest_floor

    MODE 2 (vegetation_masks fourni):
        classification: array 2D int8 (0-15)
            0=seabed, 1=coastal_pebbles, 2=coastal_grass,
            3=rock_coastal, 4=rock_alpine,
            5=debris_rock, 6=dirt_erosion, 7=mud_river,
            8=grass_low, 9=grass_mid, 10=grass_high,
            11=mountain_grass_low, 12=mountain_grass_high,
            13=heather, 14=forest_floor_deciduous, 15=forest_floor_coniferous
    """
    safe_print("[9/15] Classification pixels (priorites strictes)...")

    H, W = heightmap.shape
    classification = np.full((H, W), -1, dtype=np.int8)  # -1 = non classé

    # Extraire paramètres
    coastal_dist = params['coastal_distance_max_m']
    coastal_alt = params['coastal_alt_max_m']
    grass_low = params['grass_low_max_m']
    grass_mid = params['grass_mid_max_m']
    grass_high = params['grass_high_max_m']
    debris_min = params['debris_min_deg']
    rock_min = params['rock_min_deg']
    flow_thresh = params['flow_threshold']

    # Priorité 1 — Seabed
    seabed_mask = heightmap < 0
    classification[seabed_mask] = 0

    # Priorité 2 — Roche/Érosion (AVANT coastal)
    # Split rock en 2 : coastal (proche mer) vs alpine (montagne)
    rough_rock = params.get('rock_roughness_min', 0.10)
    rock_coastal_dist = params.get('rock_coastal_distance_m', 500.0)

    # Rock coastal : pente forte + rugueuse + proche mer
    rock_coastal_mask = (
        (slope > rock_min) &
        (roughness > rough_rock) &
        (distance_coastal < rock_coastal_dist) &  # Proche côte (<500m)
        (classification == -1)
    )
    classification[rock_coastal_mask] = 3

    # Rock alpine : pente forte + rugueuse + loin mer
    rock_alpine_mask = (
        (slope > rock_min) &
        (roughness > rough_rock) &
        (distance_coastal >= rock_coastal_dist) &  # Loin côte (>500m)
        (classification == -1)
    )
    classification[rock_alpine_mask] = 4  # Index 4 (après rock_coastal 3)

    # Pentes fortes MAIS lisses → herbe alpine raide (MountainGrass_02)
    steep_grass_mask = (
        (slope > rock_min) &
        (roughness <= rough_rock) &
        (classification == -1)  # Pas rock (ni coastal ni alpine)
    )
    classification[steep_grass_mask] = 9  # mountain_grass_high

    # Seuils curvature auto-calibrés par percentile (valeurs brutes)
    # Lecture depuis project.json (Debug) ou valeurs par défaut
    curv_pcts = params.get('curvature_percentiles', {})
    pct_deep    = curv_pcts.get('debris_deep', 15)     # Défaut 15%
    pct_concave = curv_pcts.get('dirt_concave', 25)    # Défaut 25%

    curv_valid = curvature[~np.isnan(curvature)]
    curv_deep    = float(np.percentile(curv_valid, pct_deep))
    curv_concave = float(np.percentile(curv_valid, pct_concave))

    safe_print(f"  [CURV] Percentiles: P{pct_deep} (debris) / P{pct_concave} (dirt)")

    # Debris rock : ravines/ravins profonds (pente forte + creux profond)
    debris_mask = (
        (slope > debris_min) &
        (slope <= rock_min) &
        (curvature < curv_deep) &      # P10 - creux profonds (suffit pour ravins)
        (classification == -1)
    )
    classification[debris_mask] = 5  # Index 5 (après rock_alpine 4)

    # Dirt erosion : talus érodés (creux légers, EXCLUT debris)
    dirt_slope_min = params.get('dirt_slope_min_deg', debris_min * 0.5)  # Par défaut debris_min * 0.5
    dirt_mask = (
        (slope > dirt_slope_min) &     # Pente légère (ajustable via slider)
        (slope <= rock_min) &
        (curvature >= curv_deep) &     # EXCLUSION : >= P10 (pas debris)
        (curvature < curv_concave) &   # < P25 (creux légers)
        (classification == -1)
    )
    classification[dirt_mask] = 6  # Index 6

    # Priorité 3 — Coastal (APRÈS pentes)
    coastal_zone = (
        (distance_coastal < coastal_dist) &
        (heightmap >= -0.5) &   # Descend jusqu'à -0.5m pour coller au bord de l'eau
        (heightmap < coastal_alt) &
        (slope < debris_min) &  # exclure pentes fortes
        (classification == -1)
    )

    coastal_pebbles = coastal_zone & (tpi_local >= 0)
    coastal_grass = coastal_zone & (tpi_local < 0)

    classification[coastal_pebbles] = 1
    classification[coastal_grass] = 2

    # Priorité 4 — Mud River : lignes d'écoulement + fonds de ravins
    flow_valid = flow[~np.isnan(flow)]
    flow_mud_pct = params.get('flow_mud_percentile', 85)  # Ajustable via slider
    flow_river = float(np.percentile(flow_valid, flow_mud_pct))

    # Seuil TPI pour fonds de ravins/vallées
    tpi_valid = tpi_local[~np.isnan(tpi_local)]
    tpi_mud_pct = params.get('tpi_mud_percentile', 40)  # Ajustable via slider
    tpi_ravin = float(np.percentile(tpi_valid, tpi_mud_pct))

    # Condition 1 : Écoulement fort (rivières, ruisseaux)
    river_flow = (
        (slope < debris_min) &
        (flow > flow_river) &
        (tpi_local < 0) &          # Position basse (fond de vallée)
        (classification == -1)
    )

    # Condition 2 : Fonds de ravins profonds (creux + position basse)
    river_creux = (
        (slope < debris_min) &
        (curvature < curv_deep) &   # P10 - creux profonds
        (tpi_local < tpi_ravin) &   # P40 - position basse (fond de ravin)
        (classification == -1)
    )

    # Mud = écoulement OU fonds de ravins
    river_mask = river_flow | river_creux
    classification[river_mask] = 7  # Index 7

    # Priorité 5 — Forest Floor (creux + versants nord)
    # Condition 1: Creux (existant)
    forest_creux = (
        (tpi_local < -0.15) &
        (slope < 15.0) &
        (heightmap < grass_mid) &
        (~coastal_zone) &
        (classification == -1)
    )

    # Condition 2: Versants nord restrictif (nouveau)
    north_facing = humidity > 0.9  # 0.8 -> 0.9 (nord franc uniquement)
    forest_north = (
        north_facing &
        (slope > 5.0) &
        (slope < 15.0) &              # 20.0 -> 15.0 (pentes modérées)
        (heightmap > coastal_alt) &   # pas la côte
        (heightmap < grass_mid) &     # grass_high -> grass_mid (max ~100m)
        (tpi_local < 0.0) &           # 0.2 -> 0.0 (creux/flancs uniquement)
        (classification == -1)
    )

    # Union des deux conditions
    # NOTE: Forest placé en dernier (14) pour layering Reforger (écrase herbe)
    # En MODE 2, vegetation_masks peut affiner en deciduous (14) ou coniferous (15)
    forest_mask = forest_creux | forest_north
    classification[forest_mask] = 14  # Forest en dernier

    # Priorité 6 — Mountain Grass (ordre par altitude croissante)
    mountain_low_mask = (
        (heightmap > grass_mid) &
        (heightmap <= grass_high) &
        (
            (slope < debris_min) |  # pente faible classique
            ((slope < rock_min) & (curvature > 0.0) & (tpi_local > 0.0))  # crête convexe
        ) &
        (tpi_macro > 0.1) &  # versants montagne
        (classification == -1)
    )
    classification[mountain_low_mask] = 11  # Index 11

    mountain_high_mask = (
        (heightmap > grass_high) &
        (
            (slope < debris_min) |  # pente faible classique
            ((slope < rock_min) & (curvature > 0.0) & (tpi_local > 0.0))  # crête convexe
        ) &
        (tpi_macro > 0.1) &
        (classification == -1)
    )
    classification[mountain_high_mask] = 12  # Index 12

    # Priorité 7 — Grass (ordre par altitude croissante)
    grass_low_mask = (
        (heightmap >= coastal_alt) &
        (heightmap <= grass_low) &
        (
            (slope < debris_min) |  # pente faible classique
            ((slope < rock_min) & (curvature > 0.0))  # crête convexe
        ) &
        (classification == -1)
    )
    classification[grass_low_mask] = 8  # Index 8

    grass_mid_mask = (
        (heightmap > grass_low) &
        (heightmap <= grass_mid) &
        (
            (slope < debris_min) |  # pente faible classique
            ((slope < rock_min) & (curvature > 0.0))  # crête convexe
        ) &
        (classification == -1)
    )
    classification[grass_mid_mask] = 9  # Index 9

    grass_high_mask = (
        (heightmap > grass_mid) &
        (heightmap <= grass_high) &
        (
            (slope < debris_min) |  # pente faible classique
            ((slope < rock_min) & (curvature > 0.0))  # crête convexe
        ) &
        (tpi_macro <= 0.1) &
        (classification == -1)
    )
    classification[grass_high_mask] = 10  # Index 10

    # Défaut : grass_mid
    unclassified = classification == -1
    classification[unclassified] = 9  # grass_mid (index 9)

    # ═══════════════════════════════════════════════════════════════════════════
    # MODE 2 : INJECTION VÉGÉTATION
    # ═══════════════════════════════════════════════════════════════════════════

    if vegetation_masks is not None:
        safe_print("[MODE 2] Application carte vegetation...")

        VEG_THRESHOLD = 0.3

        # Zones intouchables (jamais modifiées par végétation)
        INTOUCHABLE = np.isin(classification, [0, 1, 3, 4, 7])  # seabed, coastal_pebbles, rocks, mud_river

        # Zones herbeuses (redistribuables)
        HERBEUX = np.isin(classification, [2, 8, 9, 10, 11, 12])  # coastal_grass, grass_*, mountain_grass_*

        # ── FORÊT MIXTE (feuillus) → forest_floor_deciduous (index 14) ──
        if "foret_mixte" in vegetation_masks:
            veg = vegetation_masks["foret_mixte"] > VEG_THRESHOLD

            # Sur herbe → forest_floor_deciduous
            classification = np.where(
                veg & HERBEUX & ~INTOUCHABLE,
                14, classification
            )

            # Sur érosion (dirt) → forêt stabilise
            classification = np.where(
                veg & (classification == 6) & ~INTOUCHABLE,
                14, classification
            )

            # Sur debris + slope faible → forêt possible
            classification = np.where(
                veg & (classification == 5) & (slope < params['debris_min_deg']) & ~INTOUCHABLE,
                14, classification
            )

            px = int(np.sum(veg))
            safe_print(f"  [VEG] foret_mixte: {px} px traites")

        # ── FORÊT CONIFÈRES → forest_floor_coniferous (index 15) ──
        if "foret_coniferes" in vegetation_masks:
            veg = vegetation_masks["foret_coniferes"] > VEG_THRESHOLD

            # Sur herbe → forest_floor_coniferous
            classification = np.where(
                veg & HERBEUX & ~INTOUCHABLE,
                15, classification
            )

            # Sur érosion → forêt stabilise
            classification = np.where(
                veg & (classification == 6) & ~INTOUCHABLE,
                15, classification
            )

            # Sur debris + slope faible → forêt possible
            classification = np.where(
                veg & (classification == 5) & (slope < params['debris_min_deg']) & ~INTOUCHABLE,
                15, classification
            )

            px = int(np.sum(veg))
            safe_print(f"  [VEG] foret_coniferes: {px} px traites")

        # ── PLATEAU HERBEUX (continent ouest) ──
        if "plateau_herbeux" in vegetation_masks:
            veg = vegetation_masks["plateau_herbeux"] > VEG_THRESHOLD

            # Crêtes exposées → heather dominant (index 13)
            crete = tpi_local > 0.2
            classification = np.where(
                veg & crete & ~INTOUCHABLE,
                13, classification
            )

            # Creux abrités → mountain_grass_low (index 11)
            creux = tpi_local < -0.1
            classification = np.where(
                veg & creux & ~INTOUCHABLE,
                11, classification
            )

            # Reste → mountain_grass_high (index 12)
            autre = ~crete & ~creux
            classification = np.where(
                veg & autre & HERBEUX & ~INTOUCHABLE,
                12, classification
            )

            px = int(np.sum(veg))
            safe_print(f"  [VEG] plateau_herbeux: {px} px traites")

        # ── PRAIRIE SÈCHE ──
        if "prairie_seche" in vegetation_masks:
            veg = vegetation_masks["prairie_seche"] > VEG_THRESHOLD

            # Sur forest_floor → grass_low (index 8)
            classification = np.where(
                veg & np.isin(classification, [14, 15]) & ~INTOUCHABLE,
                8, classification
            )

            # Sur mountain_grass → grass_mid (index 9)
            classification = np.where(
                veg & np.isin(classification, [11, 12]) & ~INTOUCHABLE,
                9, classification
            )

            px = int(np.sum(veg))
            safe_print(f"  [VEG] prairie_seche: {px} px traites")

        # ── VÉGÉTATION RUPESTRE ──
        if "veg_rupestre" in vegetation_masks:
            veg = vegetation_masks["veg_rupestre"] > VEG_THRESHOLD

            # Sur herbe → grass_low (herbe rase rocailleuse) (index 8)
            classification = np.where(
                veg & HERBEUX & ~INTOUCHABLE,
                8, classification
            )

            px = int(np.sum(veg))
            safe_print(f"  [VEG] veg_rupestre: {px} px traites")

        # ── NON ATTRIBUÉ — Option C ──
        if "non_attribue" in vegetation_masks:
            veg = vegetation_masks["non_attribue"] > VEG_THRESHOLD

            crete = tpi_local > 0.3

            # Très plat + pas crête → grass_low (index 13)
            classification = np.where(
                veg & (slope < 10) & ~crete & ~INTOUCHABLE,
                13, classification
            )

            # Pente modérée OU crête → debris_rock (index 4)
            classification = np.where(
                veg & ((slope >= 10) | crete) & (slope < params['rock_min_deg']) & ~INTOUCHABLE,
                4, classification
            )

            # Pente forte → rock_walls (index 3)
            classification = np.where(
                veg & (slope >= params['rock_min_deg']) & ~INTOUCHABLE,
                3, classification
            )

            px = int(np.sum(veg))
            safe_print(f"  [VEG] non_attribue: {px} px traites")

        # ── EAU intérieure ──
        if "eau" in vegetation_masks:
            veg = vegetation_masks["eau"] > VEG_THRESHOLD

            non_sea = classification != 0
            classification = np.where(
                veg & non_sea & ~INTOUCHABLE,
                6, classification
            )

            px = int(np.sum(veg))
            safe_print(f"  [VEG] eau: {px} px traites")

    # Stats
    if vegetation_masks is not None:
        # MODE 2 : 16 masks (ordre layering)
        names = [
            'seabed', 'coastal_pebbles', 'coastal_grass',
            'rock_coastal', 'rock_alpine',
            'debris_rock', 'dirt_erosion', 'mud_river',
            'grass_low', 'grass_mid', 'grass_high',
            'mountain_grass_low', 'mountain_grass_high',
            'heather',
            'forest_floor_deciduous', 'forest_floor_coniferous'
        ]
    else:
        # MODE 1 : 13 masks
        names = [
            'seabed', 'coastal_pebbles', 'coastal_grass',
            'rock_walls', 'debris_rock', 'dirt_erosion',
            'mud_river', 'forest_floor',
            'mountain_grass_high', 'mountain_grass_low',
            'grass_high', 'grass_mid', 'grass_low'
        ]

    safe_print(f"  Distribution:")
    for i, name in enumerate(names):
        count = np.sum(classification == i)
        pct = count / classification.size * 100
        if pct > 0.01:
            safe_print(f"    {i:2d} {name:25s}: {pct:5.2f}%")

    return classification


# ══════════════════════════════════════════════════════════════════════════════
# 9. GENERATE MASKS FROM CLASSIFICATION
# ══════════════════════════════════════════════════════════════════════════════

def generate_masks_from_classification(classification, tpi_local, humidity, mode=1):
    """
    Génère masks float32 depuis classification unique

    MODE 1 (13 masks) : Terrain pur
    MODE 2 (16 masks) : Terrain + Végétation (forest_floor divisé, heather ajouté, rock splitté)

    Applique intensités variables :
    - dirt_erosion : basée sur TPI (profondeur creux)
    - forest_floor / forest_floor_deciduous / forest_floor_coniferous : basée sur humidity
    - grass_low/mid : favorisées sur versants sud

    Returns:
        dict: {nom_mask: array_float32}
    """
    safe_print(f"[10/15] Generation masks depuis classification (MODE {mode})...")

    if mode == 1:
        # MODE 1 : 13 masks (rétrocompatibilité)
        names = [
            '01_seabed', '02_coastal_pebbles', '03_coastal_grass',
            '04_rock_walls', '05_debris_rock', '06_dirt_erosion',
            '07_mud_river', '08_forest_floor',
            '09_mountain_grass_high', '10_mountain_grass_low',
            '11_grass_high', '12_grass_mid', '13_grass_low'
        ]
    else:
        # MODE 2 : 16 masks (ordre layering Reforger : base → rock → érosion → grass → forest)
        names = [
            '01_seabed', '02_coastal_pebbles', '03_coastal_grass',
            '04_rock_coastal', '05_rock_alpine',
            '06_debris_rock', '07_dirt_erosion', '08_mud_river',
            '09_grass_low', '10_grass_mid', '11_grass_high',
            '12_mountain_grass_low', '13_mountain_grass_high',
            '14_heather',
            '15_forest_floor_deciduous', '16_forest_floor_coniferous'
        ]

    masks = {}
    for i, name in enumerate(names):
        mask = (classification == i).astype(np.float32)

        # Intensité variable pour dirt_erosion basée sur profondeur TPI
        if name == '06_dirt_erosion':
            dirt_zone = mask > 0
            # Intensité douce : base 70%, varie entre 50% et 100%
            dirt_intensity = np.clip(0.7 - tpi_local * 0.3, 0.5, 1.0)
            mask[dirt_zone] = dirt_intensity[dirt_zone]

        # Modulation forest_floor par humidity (versants nord denses)
        if name in ['08_forest_floor', '08_forest_floor_deciduous', '09_forest_floor_coniferous']:
            mask = mask * humidity

        # Favoriser grass sur versants sud
        if name in ['13_grass_low', '14_grass_low']:
            south_facing = humidity < 0.6
            mask = np.where(south_facing, np.minimum(mask * 1.2, 1.0), mask)

        if name in ['12_grass_mid', '13_grass_mid']:
            south_facing = humidity < 0.6
            mask = np.where(south_facing, np.minimum(mask * 1.1, 1.0), mask)

        masks[name] = mask
        coverage = np.mean(mask) * 100
        if coverage > 0.01:
            safe_print(f"  {name}: {coverage:.2f}%")

    return masks


# ══════════════════════════════════════════════════════════════════════════════
# 10. APPLY FEATHERING (SLOPE-AWARE)
# ══════════════════════════════════════════════════════════════════════════════

def apply_directional_gradient_debris(masks, classification, cellsize, params):
    """
    Applique gradient directionnel sur debris_rock :
    - Intensité 100% proche de rock_walls
    - Intensité décroissante avec la distance

    Simule l'érosion naturelle : débris concentrés au pied de la roche,
    dispersés progressivement vers le bas.
    """
    if '05_debris_rock' not in masks:
        return

    from scipy.ndimage import distance_transform_edt

    # Distance max pour gradient (en mètres)
    gradient_distance_m = params.get('debris_gradient_distance_m', 100.0)
    gradient_distance_px = int(gradient_distance_m / cellsize)

    # Identifier TOUTES les roches (coastal index 3 + alpine index 4)
    rock_mask = (classification == 3) | (classification == 4)

    if not np.any(rock_mask):
        safe_print("  [GRADIENT] Pas de roches, gradient debris non appliqué")
        return

    # Calculer distance depuis rock_walls (en pixels)
    distance_from_rock = distance_transform_edt(~rock_mask)

    # Normaliser distance (0 = proche rock, 1 = loin)
    distance_normalized = np.clip(distance_from_rock / gradient_distance_px, 0.0, 1.0)

    # Gradient d'intensité (1.0 proche, 0.0 loin)
    intensity = 1.0 - distance_normalized

    # Appliquer gradient sur masque debris existant
    debris_mask = masks['05_debris_rock']
    masks['05_debris_rock'] = debris_mask * intensity.astype(np.float32)

    # Stats
    debris_with_gradient = np.sum(masks['05_debris_rock'] > 0.1)
    safe_print(f"  [GRADIENT] Debris distance max : {gradient_distance_m}m")
    safe_print(f"  [GRADIENT] Pixels debris (>10%) : {int(debris_with_gradient):,}")


def apply_feathering(masks, classification, slope, cellsize, params):
    """
    Feathering slope-aware : pente forte = net, pente faible = doux

    sigma_final = sigma_px * (1.0 - slope_normalized)
    """
    safe_print("[11/15] Application feathering slope-aware...")

    # Mapping feathering par mask (ordre layering Reforger)
    feather_map = {
        '02_coastal_pebbles': params['feather_coastal_m'],
        '03_coastal_grass': params['feather_coastal_m'],
        '04_rock_coastal': params['feather_rock_m'],
        '05_rock_alpine': params['feather_rock_m'],
        '06_debris_rock': params.get('feather_debris_m', params['feather_rock_m']),
        '07_dirt_erosion': params.get('feather_dirt_m', 20.0),
        '08_mud_river': params.get('feather_mud_m', 15.0),
        '09_grass_low': params['feather_grass_m'],
        '10_grass_mid': params['feather_grass_m'],
        '11_grass_high': params['feather_grass_m'],
        '12_mountain_grass_low': params['feather_grass_m'],
        '13_mountain_grass_high': params['feather_grass_m'],
        '14_heather': params['feather_grass_m'],
        '15_forest_floor_deciduous': params['feather_forest_m'],
        '16_forest_floor_coniferous': params['feather_forest_m'],
    }

    # Normaliser slope pour modulation
    rock_min = params['rock_min_deg']
    slope_norm = np.clip(slope / rock_min, 0.0, 1.0)

    for name, feather_m in feather_map.items():
        if name not in masks:
            continue

        sigma_px = feather_m / cellsize

        # Modulation slope-aware : réduire sigma sur pentes fortes
        sigma_modulated = sigma_px * (1.0 - slope_norm * 0.7)  # Max 70% réduction

        # Appliquer gaussian filter avec sigma variable (approximation)
        # Utiliser sigma moyen pour simplification
        sigma_avg = float(np.mean(sigma_modulated))

        masks[name] = gaussian_filter(masks[name], sigma=sigma_avg).astype(np.float32)

        # Éliminer valeurs insignifiantes (<5%)
        masks[name] = np.where(masks[name] < 0.05, 0.0, masks[name])

    # Seabed non featheré
    safe_print(f"  Feathering applique (sauf seabed)")

    return masks


# ══════════════════════════════════════════════════════════════════════════════
# 11. APPLY DEPTH GRADIENT
# ══════════════════════════════════════════════════════════════════════════════

def apply_depth_gradient(masks, tpi_local):
    """
    Dégradé vertical debris/dirt basé sur profondeur du creux

    Fond de creux (TPI très négatif) -> dirt dominant
    Flancs (TPI moins négatif) -> debris dominant
    """
    safe_print("[12/17] Application degrade vertical debris/dirt...")

    if '05_debris_rock' not in masks or '06_dirt_erosion' not in masks:
        safe_print("  [SKIP] debris_rock ou dirt_erosion manquant")
        return masks

    # Calculer profondeur relative dans le creux
    # tpi_local négatif = creux, plus négatif = plus profond
    depth = np.clip(-tpi_local, 0, 1)  # 0=surface, 1=fond

    # Zone de base érosion (là où debris/dirt sont actifs)
    erosion_zone = (masks['05_debris_rock'] + masks['06_dirt_erosion'])
    erosion_zone = np.clip(erosion_zone, 0, 1)

    # Sauvegarder intensité totale avant redistribution
    total_erosion = erosion_zone.copy()

    # Redistribuer selon profondeur
    # Fond -> dirt dominant
    # Flancs -> debris_rock dominant
    masks['06_dirt_erosion'] = total_erosion * depth * 0.8
    masks['05_debris_rock'] = total_erosion * (1 - depth) * 0.8

    # Garder une base minimale des deux pour éviter les zones vides
    masks['06_dirt_erosion'] = np.maximum(masks['06_dirt_erosion'], total_erosion * 0.1)
    masks['05_debris_rock'] = np.maximum(masks['05_debris_rock'], total_erosion * 0.1)

    # Stats
    num_modified = np.sum(total_erosion > 0.01)
    debris_pct = np.mean(masks['05_debris_rock']) * 100
    dirt_pct = np.mean(masks['06_dirt_erosion']) * 100

    safe_print(f"  {num_modified} pixels modifies")
    safe_print(f"  debris_rock: {debris_pct:.2f}%, dirt_erosion: {dirt_pct:.2f}%")

    return masks


# ══════════════════════════════════════════════════════════════════════════════
# 12. APPLY EXCLUSIONS
# ══════════════════════════════════════════════════════════════════════════════

def apply_exclusions(masks):
    """
    Force exclusions mutuelles post-feathering

    Regles:
    1. forest_floor vs grass_low/grass_mid : exclusion mutuelle
    2. debris_rock vs dirt_erosion : separation stricte par curvature
    """
    safe_print("[12/16] Application exclusions mutuelles...")

    # Regle 1: forest_floor exclut grass_low et grass_mid
    if '08_forest_floor' in masks and '13_grass_low' in masks and '12_grass_mid' in masks:
        forest_zone = masks['08_forest_floor'] > 0.3
        num_conflicts = np.sum(forest_zone & ((masks['13_grass_low'] > 0.01) | (masks['12_grass_mid'] > 0.01)))

        masks['13_grass_low'][forest_zone] = 0.0
        masks['12_grass_mid'][forest_zone] = 0.0

        safe_print(f"  [1] forest_floor vs grass : {num_conflicts} pixels corriges")

    # Regle 2: debris_rock vs dirt_erosion : chevauchement autorisé avec réduction debris
    if '05_debris_rock' in masks and '06_dirt_erosion' in masks:
        debris = masks['05_debris_rock']
        dirt = masks['06_dirt_erosion']

        # Zone de chevauchement : les deux > 0.01
        overlap = (debris > 0.01) & (dirt > 0.01)
        num_overlap = np.sum(overlap)

        # Dans zone chevauchement : dirt pleine intensité, debris réduit
        masks['06_dirt_erosion'][overlap] *= 1.0  # pleine intensité (couche basse)
        masks['05_debris_rock'][overlap] *= 0.6   # réduit de 40% (par dessus)

        safe_print(f"  [2] debris + dirt chevauchement : {num_overlap} pixels (debris reduit 60%)")

    return masks


# ══════════════════════════════════════════════════════════════════════════════
# 12. NORMALIZE MASKS
# ══════════════════════════════════════════════════════════════════════════════

def normalize_masks(masks):
    """
    Normalise somme <= 1.0 par pixel (sauf seabed)
    """
    safe_print("[13/16] Normalisation masks (somme <= 1.0)...")

    # Calculer somme sans seabed
    terrain_names = [name for name in masks.keys() if name != '01_seabed']

    sum_terrain = np.zeros_like(next(iter(masks.values())), dtype=np.float32)
    for name in terrain_names:
        sum_terrain += masks[name]

    # Pixels où somme > 1.0
    overflow = sum_terrain > 1.0
    num_overflow = np.sum(overflow)

    if num_overflow > 0:
        safe_print(f"  {num_overflow} pixels overflow ({num_overflow/sum_terrain.size*100:.2f}%)")

        # Normaliser
        for name in terrain_names:
            masks[name][overflow] /= sum_terrain[overflow]

        # Vérifier
        sum_after = np.zeros_like(sum_terrain)
        for name in terrain_names:
            sum_after += masks[name]

        max_sum = np.max(sum_after)
        safe_print(f"  Somme max apres: {max_sum:.6f}")

        assert max_sum <= 1.0001, f"ERREUR: somme = {max_sum}"
    else:
        safe_print(f"  [OK] Aucun overflow (somme max={np.max(sum_terrain):.6f})")

    return masks


# ══════════════════════════════════════════════════════════════════════════════
# 12. EXPORT MASKS 16-BIT
# ══════════════════════════════════════════════════════════════════════════════

def export_masks_16bit(masks, output_dir):
    """
    Export masks PNG 16-bit (JAMAIS de binarisation)
    """
    safe_print(f"[14/16] Export masks PNG 16-bit: {output_dir}")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for name, mask in masks.items():
        # Float32 [0,1] -> uint16 [0,65535]
        mask_uint16 = (mask * 65535).astype(np.uint16)

        # Vérifier continuité
        unique_vals = len(np.unique(mask_uint16))
        min_val = np.min(mask_uint16)
        max_val = np.max(mask_uint16)

        # Sauvegarder
        output_path = output_dir / f"{name}.png"
        Image.fromarray(mask_uint16).save(output_path)

        safe_print(f"  [OK] {name:30s}: {unique_vals:5d} valeurs (min={min_val}, max={max_val})")

    safe_print(f"  Total: {len(masks)} masks exportes")


# ══════════════════════════════════════════════════════════════════════════════
# 13. DETECT BASE TEXTURE
# ══════════════════════════════════════════════════════════════════════════════

def detect_base_texture(masks):
    """
    Détecte texture base parmi grass_low/mid/high
    """
    safe_print("[15/16] Detection texture de base...")

    candidates = {
        '13_grass_low': np.mean(masks.get('13_grass_low', 0)),
        '12_grass_mid': np.mean(masks.get('12_grass_mid', 0)),
        '11_grass_high': np.mean(masks.get('11_grass_high', 0))
    }

    base = max(candidates, key=candidates.get)

    for name, cov in candidates.items():
        safe_print(f"  {name}: {cov*100:.2f}%")

    safe_print(f"  -> Texture de base: {base}")

    return base


# ══════════════════════════════════════════════════════════════════════════════
# 14. CHECK QTRE
# ══════════════════════════════════════════════════════════════════════════════

def check_qtre(masks, cellsize, presence_threshold=0.05):
    """
    Analyse budget QTRE par bloc 32x32m
    """
    safe_print("[16/16] Analyse budget QTRE...")

    # Taille bloc en pixels
    bloc_px = int(32 / cellsize)

    # Dimensions
    first_mask = next(iter(masks.values()))
    H, W = first_mask.shape

    n_blocs_y = H // bloc_px
    n_blocs_x = W // bloc_px
    total_blocs = n_blocs_y * n_blocs_x

    safe_print(f"  Bloc: {bloc_px}x{bloc_px}px (32m)")
    safe_print(f"  Grille: {n_blocs_y}x{n_blocs_x} = {total_blocs} blocs")

    # Heatmap densité
    density_map = np.zeros((n_blocs_y, n_blocs_x), dtype=np.uint8)

    # Analyser chaque bloc
    for by in range(n_blocs_y):
        for bx in range(n_blocs_x):
            y0 = by * bloc_px
            x0 = bx * bloc_px
            y1 = y0 + bloc_px
            x1 = x0 + bloc_px

            active_count = 0
            for name, mask in masks.items():
                if name == '01_seabed':
                    continue

                bloc = mask[y0:y1, x0:x1]
                if np.mean(bloc) > presence_threshold:
                    active_count += 1

            density_map[by, bx] = active_count

    # Distribution
    distribution = {}
    for density in range(0, np.max(density_map) + 1):
        count = np.sum(density_map == density)
        pct = count / total_blocs * 100
        distribution[density] = {'count': count, 'pct': pct}

    safe_print(f"\n  Distribution:")
    for density in sorted(distribution.keys()):
        info = distribution[density]
        status = "[OK]" if density <= 3 else "[LIMITE]" if density <= 5 else "[CRITIQUE]"
        safe_print(f"    {density} tex/bloc: {info['count']:6} blocs ({info['pct']:5.2f}%) {status}")

    # Verdict
    blocs_ok = sum(d['count'] for k, d in distribution.items() if k <= 3)
    blocs_limite = sum(d['count'] for k, d in distribution.items() if 4 <= k <= 5)
    blocs_critique = sum(d['count'] for k, d in distribution.items() if k >= 6)

    pct_ok = blocs_ok / total_blocs * 100
    pct_critique = blocs_critique / total_blocs * 100

    verdict = "OK" if pct_ok >= 85 and pct_critique < 1 else "ATTENTION" if pct_ok >= 70 else "CRITIQUE"

    safe_print(f"\n  Budget QTRE:")
    safe_print(f"    OK (<=3):      {blocs_ok:6} ({pct_ok:.2f}%)")
    safe_print(f"    Limite (4-5):  {blocs_limite:6} ({blocs_limite/total_blocs*100:.2f}%)")
    safe_print(f"    Critique (6+): {blocs_critique:6} ({pct_critique:.2f}%)")
    safe_print(f"    -> Verdict: {verdict}")

    return density_map, distribution, verdict


# ══════════════════════════════════════════════════════════════════════════════
# 15. RUN PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

def run_pipeline(heightmap_path, output_dir, params=None, terrain_data=None, vegetation_map=None):
    """
    Orchestre toutes les fonctions du pipeline V2

    Args:
        heightmap_path: chemin vers .asc
        output_dir: dossier de sortie
        params: dict paramètres (optionnel)
        terrain_data: dict données terrain pré-calculées (optionnel)
                      Si fourni, évite recalcul (performance)
        vegetation_map: None (MODE 1) ou chemin/dict (MODE 2)
                       - None : 13 masks terrain pur
                       - str (chemin PNG coloré) : extraction auto 7 zones
                       - str (dossier masks PNG) : chargement direct
                       - dict : masks déjà chargés
    """
    start_time = time.time()

    mode = 2 if vegetation_map is not None else 1

    safe_print("="*80)
    safe_print(f"PIPELINE V2 — Generation Masks Terrain Reforger — MODE {mode}")
    safe_print("="*80)
    safe_print(f"Debut: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Paramètres par défaut
    if params is None:
        params = {
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
            "debris_gradient_distance_m": 100.0,  # Distance max gradient debris depuis rock
            "rock_coastal_distance_m": 500.0,      # Distance max pour rock coastal vs alpine
        }

    # 1-6: Charger et calculer (ou utiliser terrain_data si fourni)
    if terrain_data is not None:
        # Utiliser données pré-calculées (ZÉRO recalcul)
        safe_print("  [OPTIMISATION] Utilisation terrain_data pre-calcule\n")
        heightmap = terrain_data['heightmap']
        heightmap_smooth = terrain_data['heightmap_smooth']
        cellsize = terrain_data['cellsize']
        slope = terrain_data['slope']
        aspect = terrain_data['aspect']
        curvature = terrain_data['curvature']
        tpi_local = terrain_data['tpi_local']
        tpi_macro = terrain_data['tpi_macro']
        flow = terrain_data['flow']
        distance_coastal = terrain_data['distance_cote']
        roughness = terrain_data['roughness']

        # Humidity depuis aspect (nord=humide)
        humidity = np.clip((np.cos(np.radians(aspect)) + 1) / 2, 0, 1).astype(np.float32)

        # Merge params avec params auto-calibrés de terrain_data
        params_auto = terrain_data.get('params', {})
        params = {**params, **params_auto}

        safe_print(f"  Temps calculs: 0.0s (skip)\n")
    else:
        # Calcul classique (rétrocompatibilité)
        t0 = time.time()
        heightmap, meta = load_asc(heightmap_path)
        cellsize = meta['cellsize']

        # Pre-lissage pour reduire bruit curvature/TPI/flow
        sigma = max(2, int(12 / cellsize))
        heightmap_smooth = gaussian_filter(heightmap, sigma=sigma)
        safe_print(f"  Heightmap lisse: sigma={sigma}px ({sigma*cellsize:.1f}m)\n")

        slope = calculate_slope(heightmap, cellsize)  # original
        aspect, humidity = calculate_aspect(heightmap_smooth, cellsize)  # smooth
        curvature = calculate_curvature(heightmap_smooth, cellsize)  # smooth
        tpi_local, tpi_macro = calculate_tpi(heightmap_smooth, cellsize,  # smooth
                                              params['tpi_local_radius_m'],
                                              params['tpi_macro_radius_m'])
        flow = calculate_flow_accumulation(heightmap_smooth, cellsize)  # smooth
        distance_coastal = calculate_coastal_distance(heightmap, cellsize)  # original
        roughness = calculate_roughness(heightmap_smooth, cellsize)  # smooth

        safe_print(f"\n  Temps calculs: {time.time()-t0:.1f}s\n")

    # 9: Auto-calibration (skip si déjà dans terrain_data)
    if terrain_data is None:
        params_final = auto_calibrate(heightmap, slope, flow, params,
                                      curvature=curvature, roughness=roughness)
    else:
        params_final = params

    # 9B: Charger carte végétation si MODE 2
    vegetation_masks = None
    if mode == 2:
        target_shape = heightmap.shape

        if isinstance(vegetation_map, dict):
            # Masks déjà chargés (cas Zimnitrita)
            vegetation_masks = vegetation_map
            safe_print("[MODE 2] Masks vegetation pre-charges (dict)\n")

        elif Path(vegetation_map).is_dir():
            # Dossier de masks PNG extraits
            vegetation_masks = load_vegetation_masks_from_dir(vegetation_map, target_shape)
            safe_print(f"[MODE 2] {len(vegetation_masks)} zones chargees depuis dossier\n")

        else:
            # PNG unique → extraction par couleur
            vegetation_masks = load_vegetation_map(vegetation_map, target_shape)
            safe_print(f"[MODE 2] {len(vegetation_masks)} zones extraites depuis PNG\n")

    # 10-15: Classification et génération
    classification = classify_pixels(heightmap, slope, curvature, tpi_local,
                                      tpi_macro, flow, distance_coastal, roughness, humidity, params_final,
                                      vegetation_masks=vegetation_masks)

    masks = generate_masks_from_classification(classification, tpi_local, humidity, mode=mode)
    apply_directional_gradient_debris(masks, classification, cellsize, params_final)
    masks = apply_feathering(masks, classification, slope, cellsize, params_final)
    # apply_depth_gradient SUPPRIMÉ — logique séparée debris/dirt
    masks = apply_exclusions(masks)
    masks = normalize_masks(masks)

    # 14-16: Export et analyse
    export_masks_16bit(masks, output_dir)
    base_texture = detect_base_texture(masks)
    density_map, distribution, verdict = check_qtre(masks, cellsize)

    # Résumé final
    total_time = time.time() - start_time

    safe_print("\n" + "="*80)
    safe_print("RESUME FINAL")
    safe_print("="*80)
    safe_print(f"\nTemps total: {total_time:.1f}s")
    safe_print(f"Texture de base: {base_texture}")
    safe_print(f"Verdict QTRE: {verdict}")
    safe_print(f"Output: {output_dir}")
    safe_print(f"\nFin: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    safe_print("="*80)

    return {
        'params': params_final,
        'masks': masks,
        'classification': classification,
        'base_texture': base_texture,
        'qtre_verdict': verdict,
        'total_time': total_time,
        'mode': mode,
        'n_masks': len(masks),
        'output_dir': str(output_dir)
    }


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if len(sys.argv) < 3:
        safe_print("Usage:")
        safe_print("  python pipeline_v2.py <heightmap.asc> <output_dir>")
        safe_print("  python pipeline_v2.py heightmap.asc output/ --params params.json")
        sys.exit(1)

    heightmap_path = sys.argv[1]
    output_dir = sys.argv[2]

    # Charger params optionnels
    params = None
    if len(sys.argv) > 3 and sys.argv[3] == '--params':
        params_path = sys.argv[4]
        with open(params_path, 'r') as f:
            params = json.load(f)
        safe_print(f"Parametres charges depuis: {params_path}\n")

    run_pipeline(heightmap_path, output_dir, params)
