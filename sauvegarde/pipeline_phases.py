"""
Pipeline Phases — Système 11 Masks Continus
============================================

Architecture valeurs continues 0.0-1.0 (pas de binarisation)
Transitions douces (falloff) aux bordures de chaque condition
Paramètres utilisateur en mètres réels avec auto-calibration sur valeurs None

11 masks cibles :
01_seabed
02_coastal_pebbles
03_coastal_grass
04_grass_low
05_grass_mid
06_grass_high
07_mountain_grass_low
08_mountain_grass_high
09_dirt_erosion
10_debris_rock
11_rock_walls

Usage:
    python pipeline_phases.py <heightmap.asc> <curvature.raw> <curv_min> <curv_max> <output_dir>
"""

import numpy as np
from pathlib import Path
from PIL import Image
from scipy.ndimage import gaussian_filter, distance_transform_edt
import sys


# ══════════════════════════════════════════════════════════════════════════════
# UTILITAIRES CHARGEMENT
# ══════════════════════════════════════════════════════════════════════════════

def load_asc(asc_path):
    """
    Charge heightmap ASC format ArcGIS

    Returns:
        heightmap: array 2D altitudes
        meta: dict (ncols, nrows, cellsize, nodata)
    """
    print(f"[1/8] Chargement heightmap: {asc_path}")

    with open(asc_path, 'r') as f:
        lines = f.readlines()

    # Parser header (6 lignes)
    meta = {}
    for i in range(6):
        key, value = lines[i].strip().split()
        meta[key.lower()] = float(value) if '.' in value else int(value)

    # Parser données
    data_lines = lines[6:]
    heightmap = np.array([
        [float(val) for val in line.split()]
        for line in data_lines if line.strip()
    ])

    # Remplacer nodata par NaN
    nodata = meta.get('nodata_value', -9999)
    heightmap[heightmap == nodata] = np.nan

    print(f"  Résolution: {heightmap.shape[0]}×{heightmap.shape[1]}")
    print(f"  Cellsize: {meta['cellsize']}m/px")
    print(f"  Altitude: {np.nanmin(heightmap):.1f}m -> {np.nanmax(heightmap):.1f}m")

    return heightmap, meta


def load_curvature_mask(curvature_path, curvature_range):
    """
    Charge masque curvature depuis Instant Terra (16-bit raw ou png)

    Args:
        curvature_path: chemin fichier .raw ou .png
        curvature_range: tuple (min_curv, max_curv) utilisé dans IT

    Returns:
        curvature: array 2D décodé en valeurs réelles
    """
    print(f"[2/8] Chargement curvature: {curvature_path}")

    curv_path = Path(curvature_path)
    min_curv, max_curv = curvature_range

    if curv_path.suffix == '.raw':
        # Auto-détecter taille
        file_size = curv_path.stat().st_size
        num_pixels = file_size // 2  # 16-bit = 2 bytes/pixel
        width = height = int(np.sqrt(num_pixels))

        # Essayer big-endian puis little-endian
        try:
            curv = np.fromfile(curv_path, dtype='>u2').reshape((height, width))
        except:
            curv = np.fromfile(curv_path, dtype='<u2').reshape((height, width))

    elif curv_path.suffix == '.png':
        curv = np.array(Image.open(curv_path), dtype=np.uint16)

    else:
        raise ValueError(f"Format non supporté: {curv_path.suffix}")

    # Décoder : [0, 65535] -> [min_curv, max_curv]
    curv_decoded = (curv / 65535.0) * (max_curv - min_curv) + min_curv

    print(f"  Résolution: {curv_decoded.shape[0]}×{curv_decoded.shape[1]}")
    print(f"  Range: {min_curv} -> {max_curv}")
    print(f"  Distribution: min={np.min(curv_decoded):.1f}, max={np.max(curv_decoded):.1f}")

    return curv_decoded


def calculate_slope(heightmap, cellsize):
    """
    Calcule pente en degrés depuis heightmap

    Args:
        heightmap: array 2D altitudes (m)
        cellsize: résolution m/px

    Returns:
        slope: array 2D pentes (degrés)
    """
    print("[3/8] Calcul pentes...")

    # Gradients X et Y
    gy, gx = np.gradient(heightmap, cellsize)

    # Pente = arctan(sqrt(gx² + gy²))
    slope = np.degrees(np.arctan(np.sqrt(gx**2 + gy**2)))

    print(f"  Distribution: min={np.nanmin(slope):.1f}°, max={np.nanmax(slope):.1f}°, "
          f"médiane={np.nanmedian(slope):.1f}°")

    return slope


# ══════════════════════════════════════════════════════════════════════════════
# AUTO-CALIBRATION
# ══════════════════════════════════════════════════════════════════════════════

def auto_calibrate(heightmap, slope, curvature, cellsize, user_params):
    """
    Auto-calibration seuils altitude/slope/curvature
    Calcule UNIQUEMENT les valeurs None dans user_params

    Args:
        heightmap: array 2D altitudes
        slope: array 2D pentes
        curvature: array 2D curvature
        cellsize: résolution m/px
        user_params: dict paramètres utilisateur

    Returns:
        dict: paramètres finaux (user + auto)
    """
    print("[4/8] Auto-calibration seuils...")

    # Copie pour ne pas modifier l'original
    params = user_params.copy()

    # Filtrer terrain émergé (>0)
    land_mask = (heightmap > 0) & (~np.isnan(heightmap))
    land_alt = heightmap[land_mask]

    # ── COASTAL ──
    if params['coastal_alt_max_m'] is None:
        params['coastal_alt_max_m'] = float(np.percentile(land_alt, 10))
        print(f"  [AUTO] coastal_alt_max_m = {params['coastal_alt_max_m']:.1f}m (P10)")

    # ── GRASS ALTITUDE ──
    if params['grass_low_max_m'] is None:
        params['grass_low_max_m'] = float(np.percentile(land_alt, 30))
        print(f"  [AUTO] grass_low_max_m = {params['grass_low_max_m']:.1f}m (P30)")

    if params['grass_mid_max_m'] is None:
        params['grass_mid_max_m'] = float(np.percentile(land_alt, 66))
        print(f"  [AUTO] grass_mid_max_m = {params['grass_mid_max_m']:.1f}m (P66)")

    if params['grass_high_max_m'] is None:
        params['grass_high_max_m'] = float(np.percentile(land_alt, 80))
        print(f"  [AUTO] grass_high_max_m = {params['grass_high_max_m']:.1f}m (P80)")

    # ── SLOPE (debris/rock) ──
    slope_valid = slope[~np.isnan(slope)]

    if params['debris_min_deg'] is None:
        params['debris_min_deg'] = float(np.percentile(slope_valid, 65))
        print(f"  [AUTO] debris_min_deg = {params['debris_min_deg']:.1f}° (P65)")

    if params['rock_min_deg'] is None:
        params['rock_min_deg'] = float(np.percentile(slope_valid, 85))
        print(f"  [AUTO] rock_min_deg = {params['rock_min_deg']:.1f}° (P85)")

    # ── CURVATURE ──
    if params['curvature_radius_m'] is None:
        params['curvature_radius_m'] = cellsize * 5.0
        print(f"  [AUTO] curvature_radius_m = {params['curvature_radius_m']:.1f}m (cellsize × 5)")

    if params['concave_threshold'] is None and curvature is not None:
        curv_valid = curvature[~np.isnan(curvature)]
        params['concave_threshold'] = float(np.percentile(curv_valid, 25))
        print(f"  [AUTO] concave_threshold = {params['concave_threshold']:.2f} (P25)")

    print(f"\n  Paramètres finaux:")
    print(f"    Coastal: distance_max={params['coastal_distance_max_m']:.0f}m, alt_max={params['coastal_alt_max_m']:.1f}m")
    print(f"    Grass: low_max={params['grass_low_max_m']:.1f}m, mid_max={params['grass_mid_max_m']:.1f}m, high_max={params['grass_high_max_m']:.1f}m")
    print(f"    Slope: debris_min={params['debris_min_deg']:.1f}°, rock_min={params['rock_min_deg']:.1f}°")
    print(f"    Feathering: coastal={params['feather_coastal_m']:.0f}m, grass={params['feather_grass_m']:.0f}m, rock={params['feather_rock_m']:.0f}m")

    return params


# ══════════════════════════════════════════════════════════════════════════════
# GÉNÉRATION MASQUES CONTINUS
# ══════════════════════════════════════════════════════════════════════════════

def generate_continuous_masks(heightmap, slope, curvature, params, cellsize):
    """
    Génère 11 masques continus (float32 0.0-1.0) avec transitions douces

    CORRECTIONS PRIORITAIRES:
    1. Normalisation pixel par pixel (somme <= 1.0)
    2. Exclusions zones strictes (sea/coastal/land)
    3. Érosion par curvature (dirt=concave/talwegs, debris=convexe)
    4. Vérification détaillée par zone

    Args:
        heightmap: array 2D altitudes
        slope: array 2D pentes
        curvature: array 2D curvature (redimensionné si nécessaire)
        params: dict paramètres calibrés
        cellsize: résolution m/px

    Returns:
        dict: {mask_name: float32_array}
    """
    print("[5/8] Generation masques continus (CORRIGES)...")

    # Initialiser tous les masks à 0.0
    shape = heightmap.shape
    masks = {name: np.zeros(shape, dtype=np.float32) for name in [
        '01_seabed',
        '02_coastal_pebbles',
        '03_coastal_grass',
        '04_grass_low',
        '05_grass_mid',
        '06_grass_high',
        '07_mountain_grass_low',
        '08_mountain_grass_high',
        '09_dirt_erosion',
        '10_debris_rock',
        '11_rock_walls'
    ]}

    # ══════════════════════════════════════════════════════════════════════════
    # CORRECTION 2: DÉFINIR ZONES GÉOGRAPHIQUES STRICTES
    # ══════════════════════════════════════════════════════════════════════════
    print("  [ZONES] Definition zones geographiques...")

    # Distance mer
    sea_mask_bool = heightmap < 0
    distance_px = distance_transform_edt(~sea_mask_bool)
    distance_m = distance_px * cellsize

    coastal_distance_max = params['coastal_distance_max_m']

    # Zone 1: Mer (altitude < 0)
    zone_sea = heightmap < 0

    # Zone 2: Côtière (altitude >= 0 ET distance < 60m)
    zone_coastal = (heightmap >= 0) & (distance_m < coastal_distance_max)

    # Zone 3: Terre (tout le reste)
    zone_land = (heightmap >= 0) & (distance_m >= coastal_distance_max)

    num_sea = np.sum(zone_sea)
    num_coastal = np.sum(zone_coastal)
    num_land = np.sum(zone_land)
    total = zone_sea.size

    print(f"    Zone mer      : {num_sea:8} px ({num_sea/total*100:5.2f}%)")
    print(f"    Zone cotiere  : {num_coastal:8} px ({num_coastal/total*100:5.2f}%)")
    print(f"    Zone terre    : {num_land:8} px ({num_land/total*100:5.2f}%)")

    # ══════════════════════════════════════════════════════════════════════════
    # 01_SEABED (altitude < 0)
    # ══════════════════════════════════════════════════════════════════════════
    print("  [01] seabed...")
    falloff_m = params['feather_coastal_m']
    # Transition douce de 0m vers -falloff_m
    masks['01_seabed'] = np.clip(
        -heightmap / falloff_m,
        0.0, 1.0
    ).astype(np.float32)

    # ══════════════════════════════════════════════════════════════════════════
    # DISTANCE MER (pour coastal)
    # ══════════════════════════════════════════════════════════════════════════
    print("  [DISTANCE MER] Calcul distance transform...")
    sea_mask = heightmap <= 0
    distance_px = distance_transform_edt(~sea_mask)
    distance_m = distance_px * cellsize

    coastal_distance_max = params['coastal_distance_max_m']
    coastal_alt_max = params['coastal_alt_max_m']
    falloff_coastal = params['feather_coastal_m']

    # Mask distance côtière (transition douce)
    coastal_distance_mask = np.clip(
        1.0 - (distance_m - coastal_distance_max) / falloff_coastal,
        0.0, 1.0
    ).astype(np.float32)

    # Mask altitude côtière (transition douce)
    coastal_alt_mask = np.clip(
        1.0 - (heightmap - coastal_alt_max) / falloff_coastal,
        0.0, 1.0
    ).astype(np.float32)

    # Coastal global = intersection distance ET altitude
    coastal_zone = coastal_distance_mask * coastal_alt_mask

    # ══════════════════════════════════════════════════════════════════════════
    # 02_COASTAL_PEBBLES (convexe) + 03_COASTAL_GRASS (concave)
    # ══════════════════════════════════════════════════════════════════════════
    print("  [02-03] coastal pebbles + grass...")

    if curvature is not None:
        concave_thresh = params['concave_threshold']
        falloff_curv = 2.0  # transition sur 2 unités de curvature

        # Curvature mask (>0 = convexe, <0 = concave)
        # Transition douce autour du seuil
        curv_factor = np.clip(
            (curvature - concave_thresh) / falloff_curv,
            -1.0, 1.0
        ).astype(np.float32)

        # Pebbles = coastal × convexe
        masks['02_coastal_pebbles'] = coastal_zone * np.clip(curv_factor, 0.0, 1.0)

        # Grass = coastal × concave
        masks['03_coastal_grass'] = coastal_zone * np.clip(-curv_factor, 0.0, 1.0)
    else:
        # Sans curvature : 50/50
        masks['02_coastal_pebbles'] = coastal_zone * 0.5
        masks['03_coastal_grass'] = coastal_zone * 0.5

    # ══════════════════════════════════════════════════════════════════════════
    # 04_GRASS_LOW, 05_GRASS_MID, 06_GRASS_HIGH (altitudes successives)
    # ══════════════════════════════════════════════════════════════════════════
    print("  [04-06] grass low/mid/high...")

    grass_low_max = params['grass_low_max_m']
    grass_mid_max = params['grass_mid_max_m']
    grass_high_max = params['grass_high_max_m']
    falloff_grass = params['feather_grass_m']

    # grass_low : coastal_alt_max -> grass_low_max
    # Transition basse (au-dessus de coastal)
    low_bottom = np.clip(
        (heightmap - coastal_alt_max) / falloff_grass,
        0.0, 1.0
    )
    # Transition haute (en dessous de grass_low_max)
    low_top = np.clip(
        1.0 - (heightmap - grass_low_max) / falloff_grass,
        0.0, 1.0
    )
    masks['04_grass_low'] = (low_bottom * low_top).astype(np.float32)

    # grass_mid : grass_low_max -> grass_mid_max
    mid_bottom = np.clip(
        (heightmap - grass_low_max) / falloff_grass,
        0.0, 1.0
    )
    mid_top = np.clip(
        1.0 - (heightmap - grass_mid_max) / falloff_grass,
        0.0, 1.0
    )
    masks['05_grass_mid'] = (mid_bottom * mid_top).astype(np.float32)

    # grass_high : grass_mid_max -> grass_high_max
    high_bottom = np.clip(
        (heightmap - grass_mid_max) / falloff_grass,
        0.0, 1.0
    )
    high_top = np.clip(
        1.0 - (heightmap - grass_high_max) / falloff_grass,
        0.0, 1.0
    )
    masks['06_grass_high'] = (high_bottom * high_top).astype(np.float32)

    # ══════════════════════════════════════════════════════════════════════════
    # 07_MOUNTAIN_GRASS_LOW + 08_MOUNTAIN_GRASS_HIGH (au-dessus de grass_high_max)
    # ══════════════════════════════════════════════════════════════════════════
    print("  [07-08] mountain grass low/high...")

    # Zone montagne = au-dessus de grass_high_max
    mountain_mask = np.clip(
        (heightmap - grass_high_max) / falloff_grass,
        0.0, 1.0
    ).astype(np.float32)

    if curvature is not None:
        concave_thresh = params['concave_threshold']
        falloff_curv = 2.0

        curv_factor = np.clip(
            (curvature - concave_thresh) / falloff_curv,
            -1.0, 1.0
        ).astype(np.float32)

        # mountain_grass_low = concave (vallées)
        masks['07_mountain_grass_low'] = mountain_mask * np.clip(-curv_factor, 0.0, 1.0)

        # mountain_grass_high = convexe (crêtes)
        masks['08_mountain_grass_high'] = mountain_mask * np.clip(curv_factor, 0.0, 1.0)
    else:
        # Sans curvature : 50/50
        masks['07_mountain_grass_low'] = mountain_mask * 0.5
        masks['08_mountain_grass_high'] = mountain_mask * 0.5

    # ══════════════════════════════════════════════════════════════════════════
    # 09_DIRT_EROSION (pente modérée)
    # ══════════════════════════════════════════════════════════════════════════
    print("  [09] dirt erosion...")

    debris_min = params['debris_min_deg']
    rock_min = params['rock_min_deg']
    falloff_slope = 5.0  # transition sur 5 degrés

    # Transition basse (au-dessus de debris_min)
    erosion_bottom = np.clip(
        (slope - debris_min) / falloff_slope,
        0.0, 1.0
    )
    # Transition haute (en dessous de rock_min)
    erosion_top = np.clip(
        1.0 - (slope - rock_min) / falloff_slope,
        0.0, 1.0
    )
    masks['09_dirt_erosion'] = (erosion_bottom * erosion_top).astype(np.float32)

    # ══════════════════════════════════════════════════════════════════════════
    # 10_DEBRIS_ROCK (pente forte - transition vers rock)
    # ══════════════════════════════════════════════════════════════════════════
    print("  [10] debris rock...")

    # Autour de rock_min : transition avant rock_walls
    rock_threshold = rock_min + 5.0  # décalage pour éviter superposition totale

    debris_bottom = np.clip(
        (slope - rock_min) / falloff_slope,
        0.0, 1.0
    )
    debris_top = np.clip(
        1.0 - (slope - rock_threshold) / falloff_slope,
        0.0, 1.0
    )
    masks['10_debris_rock'] = (debris_bottom * debris_top).astype(np.float32)

    # ══════════════════════════════════════════════════════════════════════════
    # 11_ROCK_WALLS (pente très forte)
    # ══════════════════════════════════════════════════════════════════════════
    print("  [11] rock walls...")

    masks['11_rock_walls'] = np.clip(
        (slope - rock_threshold) / falloff_slope,
        0.0, 1.0
    ).astype(np.float32)

    # ══════════════════════════════════════════════════════════════════════════
    # FEATHERING (lissage gaussien en mètres réels)
    # ══════════════════════════════════════════════════════════════════════════
    print("  [FEATHERING] Lissage gaussien...")

    # Coastal
    sigma_coastal_px = params['feather_coastal_m'] / cellsize
    masks['02_coastal_pebbles'] = gaussian_filter(masks['02_coastal_pebbles'], sigma=sigma_coastal_px)
    masks['03_coastal_grass'] = gaussian_filter(masks['03_coastal_grass'], sigma=sigma_coastal_px)

    # Grass
    sigma_grass_px = params['feather_grass_m'] / cellsize
    masks['04_grass_low'] = gaussian_filter(masks['04_grass_low'], sigma=sigma_grass_px)
    masks['05_grass_mid'] = gaussian_filter(masks['05_grass_mid'], sigma=sigma_grass_px)
    masks['06_grass_high'] = gaussian_filter(masks['06_grass_high'], sigma=sigma_grass_px)
    masks['07_mountain_grass_low'] = gaussian_filter(masks['07_mountain_grass_low'], sigma=sigma_grass_px)
    masks['08_mountain_grass_high'] = gaussian_filter(masks['08_mountain_grass_high'], sigma=sigma_grass_px)

    # Rock/debris
    sigma_rock_px = params['feather_rock_m'] / cellsize
    masks['09_dirt_erosion'] = gaussian_filter(masks['09_dirt_erosion'], sigma=sigma_rock_px)
    masks['10_debris_rock'] = gaussian_filter(masks['10_debris_rock'], sigma=sigma_rock_px)
    masks['11_rock_walls'] = gaussian_filter(masks['11_rock_walls'], sigma=sigma_rock_px)

    return masks


# ══════════════════════════════════════════════════════════════════════════════
# DÉTECTION TEXTURE DE BASE
# ══════════════════════════════════════════════════════════════════════════════

def detect_base_texture(masks):
    """
    Détecte la texture de base dominante parmi grass_low/mid/high

    Args:
        masks: dict {name: float32_array}

    Returns:
        str: nom de la texture de base
    """
    print("[6/8] Détection texture de base...")

    candidates = ['04_grass_low', '05_grass_mid', '06_grass_high']
    coverage = {name: np.mean(masks[name]) for name in candidates}

    base_texture = max(coverage, key=coverage.get)

    print(f"  Couverture grass:")
    for name in candidates:
        print(f"    {name}: {coverage[name]*100:.2f}%")
    print(f"  -> Texture de base recommandee : {base_texture}")

    return base_texture


# ══════════════════════════════════════════════════════════════════════════════
# VÉRIFICATION FINALE
# ══════════════════════════════════════════════════════════════════════════════

def verify_masks(masks, heightmap):
    """
    Vérifie la qualité des masks générés

    Args:
        masks: dict {name: float32_array}
        heightmap: array 2D altitudes
    """
    print("[7/8] Vérification finale...")

    # Pixels valides (hors NaN)
    valid_mask = ~np.isnan(heightmap)

    print(f"\n  Couverture par mask (sur terrain valide):")
    for name, mask in masks.items():
        # Couverture moyenne
        coverage_pct = np.mean(mask[valid_mask]) * 100

        # Stats valeurs
        mask_valid = mask[valid_mask]
        min_val = np.min(mask_valid)
        max_val = np.max(mask_valid)
        mean_val = np.mean(mask_valid)

        print(f"    {name:30s}: couv={coverage_pct:5.2f}%, min={min_val:.3f}, max={max_val:.3f}, moy={mean_val:.3f}")

        # Vérifier qu'il n'est pas binaire (sauf seabed qui peut l'être)
        unique_vals = len(np.unique(mask_valid[mask_valid > 0]))
        if unique_vals <= 2 and name != '01_seabed':
            print(f"      [WARNING] Mask quasi-binaire detecte ({unique_vals} valeurs uniques)")

        # Vérifier qu'il existe des valeurs intermédiaires
        mid_range = mask_valid[(mask_valid > 0.1) & (mask_valid < 0.9)]
        if len(mid_range) == 0 and coverage_pct > 1.0:
            print(f"      [WARNING] Aucune valeur intermediaire detectee (pas de transition douce)")

    print(f"\n  [OK] Verification terminee")


# ══════════════════════════════════════════════════════════════════════════════
# EXPORT
# ══════════════════════════════════════════════════════════════════════════════

def export_masks(masks, output_dir):
    """
    Exporte masques PNG 16-bit (valeurs continues)

    Args:
        masks: dict {name: float32_array}
        output_dir: dossier output
    """
    print(f"[8/8] Export masques PNG 16-bit: {output_dir}")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for name, mask in masks.items():
        # Convertir float32 [0.0-1.0] -> uint16 [0-65535] SANS binarisation
        mask_uint16 = (mask * 65535).astype(np.uint16)

        # Sauvegarder PNG
        output_path = output_dir / f"{name}.png"
        Image.fromarray(mask_uint16).save(output_path)
        print(f"  [OK] {output_path.name}")

    print(f"  Total: {len(masks)} masques exportés")


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE COMPLET
# ══════════════════════════════════════════════════════════════════════════════

def run_pipeline_continuous(heightmap_path, curvature_path, curvature_range, output_dir, user_params=None):
    """
    Pipeline complet 11 masks continus

    Args:
        heightmap_path: chemin heightmap.asc
        curvature_path: chemin curvature.raw ou .png (ou None)
        curvature_range: tuple (min, max) utilisé dans Instant Terra
        output_dir: dossier output masques
        user_params: dict paramètres utilisateur (ou None pour défauts)

    Returns:
        dict: {
            'params': dict paramètres calibrés,
            'masks': dict masques générés,
            'base_texture': str nom texture de base
        }
    """
    print("="*70)
    print("PIPELINE CONTINU — 11 Masks")
    print("="*70)

    # Paramètres par défaut (None = auto-calibration)
    if user_params is None:
        user_params = {
            # Coastal
            "coastal_distance_max_m": 100.0,
            "coastal_alt_max_m": None,

            # Altitude herbe
            "grass_low_max_m": None,
            "grass_mid_max_m": None,
            "grass_high_max_m": None,

            # Slope
            "debris_min_deg": None,
            "rock_min_deg": None,

            # Curvature
            "curvature_radius_m": None,
            "concave_threshold": None,

            # Feathering
            "feather_coastal_m": 20.0,
            "feather_grass_m": 40.0,
            "feather_rock_m": 10.0,
        }

    # 1. Charger heightmap
    heightmap, meta = load_asc(heightmap_path)
    cellsize = meta['cellsize']

    # 2. Calculer slope
    slope = calculate_slope(heightmap, cellsize)

    # 3. Charger curvature (optionnel)
    curvature = None
    if curvature_path is not None:
        curvature = load_curvature_mask(curvature_path, curvature_range)

    # 4. Auto-calibration
    params = auto_calibrate(heightmap, slope, curvature, cellsize, user_params)

    # 5. Générer masques continus
    masks = generate_continuous_masks(heightmap, slope, curvature, params, cellsize)

    # 6. Détecter texture de base
    base_texture = detect_base_texture(masks)

    # 7. Vérifier
    verify_masks(masks, heightmap)

    # 8. Exporter
    export_masks(masks, output_dir)

    print("="*70)
    print("[OK] Pipeline termine !")
    print("="*70)

    return {
        'params': params,
        'masks': masks,
        'base_texture': base_texture
    }


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Usage:")
        print("  python pipeline_phases.py <heightmap.asc> <curvature.raw> <curv_min> <curv_max> <output_dir>")
        print("")
        print("Exemple:")
        print('  python pipeline_phases.py data/zbk/heightmap.asc data/zbk/curvature.raw -15 15 output_zbk')
        sys.exit(1)

    heightmap_path = sys.argv[1]
    curvature_path = sys.argv[2]
    curv_min = float(sys.argv[3])
    curv_max = float(sys.argv[4])
    output_dir = sys.argv[5]

    # Paramètres utilisateur par défaut (tout en auto)
    user_params = {
        "coastal_distance_max_m": 100.0,
        "coastal_alt_max_m": None,
        "grass_low_max_m": None,
        "grass_mid_max_m": None,
        "grass_high_max_m": None,
        "debris_min_deg": None,
        "rock_min_deg": None,
        "curvature_radius_m": None,
        "concave_threshold": None,
        "feather_coastal_m": 20.0,
        "feather_grass_m": 40.0,
        "feather_rock_m": 10.0,
    }

    run_pipeline_continuous(
        heightmap_path,
        curvature_path,
        (curv_min, curv_max),
        output_dir,
        user_params
    )
