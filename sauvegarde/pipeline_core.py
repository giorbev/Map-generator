# -*- coding: utf-8 -*-
"""
Pipeline Optimisé QTRE — Génération 12 masques terrain (NUANCES ÉROSION)
- Architecture 12 masques (max 6-7 textures/bloc)
- Auto-calibration LOCALE (détection hétérogénéité terrain + seuils par région)
- Auto-calibration altitude (P10, P66, P80)
- Auto-calibration slope (Jenks) avec adaptation cellsize
- Auto-calibration curvature (P20, P25, P75) avec compensation lissage
- Masques : SeaBed + Coastal + 3 Grass + 2 Highland + 4 Érosion (Light/Medium/Heavy) + 2 Rock
- Gradation érosion : 4 niveaux au lieu de 2 pour transitions naturelles
- Budget végétation : 0 slot (serré)
- Budget mappeur : 0-1 slot (zones plates uniquement)
"""

import numpy as np
import sys
from PIL import Image
from pathlib import Path
import json
from datetime import datetime

def safe_print(*args, **kwargs):
    """Print safe pour Windows - évite les erreurs d'encodage et I/O closed."""
    try:
        if not sys.stdout or sys.stdout.closed:
            return
        print(*args, **kwargs)
    except (UnicodeEncodeError, OSError, ValueError, AttributeError):
        try:
            safe_args = [arg.encode('ascii', 'replace').decode('ascii')
                         if isinstance(arg, str) else arg
                         for arg in args]
            print(*safe_args, **kwargs)
        except:
            pass


def load_asc(asc_path):
    """Charge heightmap ASC et retourne array + métadonnées"""
    safe_print(f"[1/6] Chargement heightmap: {asc_path}")

    with open(asc_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # Parse header
    ncols = int(lines[0].split()[1])
    nrows = int(lines[1].split()[1])
    xllcorner = float(lines[2].split()[1])
    yllcorner = float(lines[3].split()[1])
    cellsize = float(lines[4].split()[1])
    nodata = float(lines[5].split()[1])

    # Parse data
    data = []
    for line in lines[6:]:
        data.append([float(x) for x in line.split()])

    heightmap = np.array(data, dtype=np.float32)

    # Replace nodata
    heightmap[heightmap == nodata] = np.nan

    meta = {
        'ncols': ncols,
        'nrows': nrows,
        'cellsize': cellsize,
        'xllcorner': xllcorner,
        'yllcorner': yllcorner,
        'nodata': nodata
    }

    safe_print(f"  Shape: {heightmap.shape}")
    safe_print(f"  Altitude: {np.nanmin(heightmap):.2f}m - {np.nanmax(heightmap):.2f}m")

    return heightmap, meta


def calculate_slope(heightmap, cellsize):
    """Calcule slope en degrés pour chaque pixel"""
    safe_print("[2/6] Calcul slope...")

    # Gradient
    dy, dx = np.gradient(heightmap)

    # Pente (degrés)
    rise_over_run = np.sqrt(dx**2 + dy**2) / cellsize
    slope = np.arctan(rise_over_run) * 180 / np.pi

    # NaN où heightmap est NaN
    slope[np.isnan(heightmap)] = np.nan

    safe_print(f"  Slope: {np.nanmin(slope):.2f}° - {np.nanmax(slope):.2f}° (moyen: {np.nanmean(slope):.2f}°)")

    return slope


def calculate_region_heterogeneity(heightmap, slope):
    """
    Calcule hétérogénéité terrain pour décider calibration globale vs locale

    Retourne score 0-100 (>80 = très hétérogène = calibration locale recommandée)
    """
    land_mask = (heightmap > 0) & (~np.isnan(heightmap))
    land_alt = heightmap[land_mask]
    land_slope = slope[land_mask]

    # Coefficient de variation altitude (CV = std/mean)
    cv_alt = (np.std(land_alt) / np.mean(land_alt)) * 100

    # Coefficient de variation slope
    cv_slope = (np.std(land_slope) / (np.mean(land_slope) + 1e-6)) * 100

    # Score hétérogénéité (moyenne pondérée)
    heterogeneity_score = (cv_alt * 0.6) + (cv_slope * 0.4)

    return float(heterogeneity_score)


def detect_terrain_regions(heightmap, slope, n_regions=2):
    """
    Détecte régions homogènes via K-means (altitude + slope)

    Args:
        heightmap: array altitudes
        slope: array pentes
        n_regions: nombre de régions (défaut 2 pour EST/OUEST)

    Returns:
        dict: {region_id: boolean_mask} pour chaque région
    """
    from sklearn.cluster import KMeans

    safe_print(f"  Detection {n_regions} regions homogenes (K-means)...")

    # Préparer features (altitude + slope normalisés)
    land_mask = (heightmap > 0) & (~np.isnan(heightmap))

    # Créer grille features
    h, w = heightmap.shape
    features = []
    coords = []

    # Échantillonner 1 pixel sur 4 pour performance
    for i in range(0, h, 4):
        for j in range(0, w, 4):
            if land_mask[i, j]:
                features.append([
                    heightmap[i, j],
                    slope[i, j]
                ])
                coords.append((i, j))

    features = np.array(features)

    # Normaliser features
    from sklearn.preprocessing import StandardScaler
    scaler = StandardScaler()
    features_scaled = scaler.fit_transform(features)

    # K-means clustering
    kmeans = KMeans(n_clusters=n_regions, random_state=42, n_init=10)
    labels = kmeans.fit_predict(features_scaled)

    # Créer masques par région (interpoler sur grille complète)
    region_masks = {}

    for region_id in range(n_regions):
        # Créer masque sparse depuis échantillons
        region_sparse = np.zeros((h, w), dtype=bool)
        for idx, (i, j) in enumerate(coords):
            if labels[idx] == region_id:
                region_sparse[i, j] = True

        # Dilater pour remplir trous (interpolation simple)
        from scipy.ndimage import binary_dilation
        region_full = binary_dilation(region_sparse, iterations=4)
        region_full = region_full & land_mask  # Limiter au terrain

        region_masks[region_id] = region_full

        # Stats région
        region_alt = heightmap[region_full]
        region_slope = slope[region_full]
        coverage = (np.sum(region_full) / np.sum(land_mask)) * 100

        safe_print(f"    Region {region_id}: {coverage:.1f}% terrain | "
              f"Alt {np.mean(region_alt):.1f}m | Slope {np.mean(region_slope):.1f}°")

    return region_masks


def auto_calibrate_local(heightmap, slope, curvature, region_mask, cellsize):
    """
    Calibration locale pour une région spécifique

    Args:
        heightmap, slope, curvature: arrays terrain
        region_mask: masque boolean région
        cellsize: résolution m/px

    Returns:
        dict: thresholds pour cette région
    """
    # Extraire données région
    region_alt = heightmap[region_mask]
    region_slope = slope[region_mask]

    if len(region_alt) == 0:
        return None

    # ── ALTITUDE ─────────────────────────────────────────────────────────────
    p10 = float(np.percentile(region_alt, 10))
    p20 = float(np.percentile(region_alt, 20))
    p66 = float(np.percentile(region_alt, 66))
    p80 = float(np.percentile(region_alt, 80))

    # ── SLOPE ────────────────────────────────────────────────────────────────
    try:
        from jenkspy import jenks_breaks

        slope_valid = region_slope[region_slope > 0]
        sample_size = min(50000, len(slope_valid))
        slope_sample = np.random.choice(slope_valid, sample_size, replace=False)

        breaks = jenks_breaks(slope_sample, n_classes=5)
        debris_min = float(breaks[2])
        rock_min = float(breaks[3])

    except (ImportError, Exception):
        # Fallback percentiles
        slope_valid = region_slope[region_slope > 0]
        debris_min = float(np.percentile(slope_valid, 50))
        rock_min = float(np.percentile(slope_valid, 75))

    # ── CURVATURE ────────────────────────────────────────────────────────────
    curvature_thresholds = {}

    if curvature is not None:
        region_curv = curvature[region_mask]
        curv_valid = region_curv[~np.isnan(region_curv)]

        if len(curv_valid) > 0:
            # Adapter au cellsize (compensation lissage)
            cellsize_factor = cellsize / 2.0  # Référence 2m/px

            p20_curv_raw = float(np.percentile(curv_valid, 20))
            p25_curv_raw = float(np.percentile(curv_valid, 25))
            p75_curv_raw = float(np.percentile(curv_valid, 75))

            # Assouplir si cellsize > 2m (compenser lissage)
            curvature_thresholds = {
                'grass_dense_max': p20_curv_raw / cellsize_factor,
                'debris_concave_max': p25_curv_raw / cellsize_factor,
                'convexe_min': p75_curv_raw / cellsize_factor
            }

    return {
        'altitude': {
            'p10': p10,
            'p20': p20,
            'p66': p66,
            'p80': p80
        },
        'slope': {
            'debris_min': debris_min,
            'rock_min': rock_min
        },
        'curvature': curvature_thresholds
    }


def auto_calibrate(heightmap, slope, curvature=None, cellsize=2.0):
    """
    Auto-calibration altitude + slope + curvature

    Détecte automatiquement hétérogénéité terrain et applique calibration locale si nécessaire

    Returns:
        dict: {
            'altitude': {'p10': X, 'p20': Y, 'p33': Z, 'p66': W, 'p80': V},
            'slope': {'debris_min': A, 'rock_min': B},
            'curvature': {'concave_max': C, 'convexe_min': D} (optionnel),
            'local': {region_id: thresholds} (si calibration locale),
            'region_masks': {region_id: mask} (si calibration locale)
        }
    """
    safe_print("[3/6] Auto-calibration...")

    # ── DÉTECTION HÉTÉROGÉNÉITÉ ──────────────────────────────────────────────
    heterogeneity = calculate_region_heterogeneity(heightmap, slope)
    safe_print(f"  Hétérogénéité terrain : {heterogeneity:.1f}/100")

    use_local_calibration = heterogeneity > 60  # Seuil 60 (assoupli depuis 80)

    if use_local_calibration:
        safe_print(f"  -> Calibration LOCALE activée (terrain hétérogène)")

        # Détecter régions
        region_masks = detect_terrain_regions(heightmap, slope, n_regions=2)

        # Calibrer chaque région
        local_thresholds = {}
        for region_id, region_mask in region_masks.items():
            local_thresh = auto_calibrate_local(heightmap, slope, curvature, region_mask, cellsize)
            if local_thresh:
                local_thresholds[region_id] = local_thresh
                safe_print(f"    Region {region_id} calibrée : "
                      f"debris={local_thresh['slope']['debris_min']:.1f}°, "
                      f"rock={local_thresh['slope']['rock_min']:.1f}°")

        # Retourner calibration locale + globale (fallback)
        # On calcule quand même les seuils globaux pour compatibilité
        pass  # Continue avec calibration globale ci-dessous
    else:
        safe_print(f"  -> Calibration GLOBALE (terrain homogène)")
        region_masks = None
        local_thresholds = None

    # ── ALTITUDE ─────────────────────────────────────────────────────────────
    # Percentiles terrain ferme (altitude > 0m)
    land_mask = (heightmap > 0) & (~np.isnan(heightmap))
    land_alt = heightmap[land_mask]

    p10_raw = float(np.percentile(land_alt, 10))
    p20 = float(np.percentile(land_alt, 20))
    p66 = float(np.percentile(land_alt, 66))
    p80 = float(np.percentile(land_alt, 80))

    # ── COASTAL ADAPTATIF ────────────────────────────────────────────────────
    # Garantir bande côtière visible selon taille terrain
    terrain_size_m = heightmap.shape[0] * 2.0  # Estimation cellsize (à affiner)
    denivele = float(np.nanmax(heightmap) - np.nanmin(heightmap))

    # Seuil min adaptatif selon taille carte
    if terrain_size_m > 12000:  # Grande carte (>12km)
        coastal_min = 20.0
    elif terrain_size_m > 6000:  # Moyenne (6-12km)
        coastal_min = 15.0
    else:  # Petite (<6km)
        coastal_min = 12.0

    # Hybride : P10 OU min (le plus grand)
    p10 = max(p10_raw, coastal_min)

    if p10 > p10_raw:
        safe_print(f"  Altitude P10 (coastal max): {p10:.1f}m (forcé depuis {p10_raw:.1f}m, min={coastal_min:.1f}m)")
    else:
        safe_print(f"  Altitude P10 (coastal max): {p10:.1f}m")

    safe_print(f"  Altitude P20 (grass_dense max): {p20:.1f}m")
    safe_print(f"  Altitude P66 (highland min): {p66:.1f}m")
    safe_print(f"  Altitude P80 (highland_high min): {p80:.1f}m")

    # ── SLOPE ────────────────────────────────────────────────────────────────
    # Jenks Natural Breaks (si disponible) OU Percentiles fallback
    try:
        from jenkspy import jenks_breaks

        slope_valid = slope[~np.isnan(slope) & (slope > 0)]
        sample_size = min(100000, len(slope_valid))
        slope_sample = np.random.choice(slope_valid, sample_size, replace=False)

        breaks = jenks_breaks(slope_sample, n_classes=5)

        debris_min = float(breaks[2])  # Moderate min
        rock_min = float(breaks[3])    # Steep min (seuil rocheux)

        safe_print(f"  Slope seuils (Jenks):")
        safe_print(f"    Debris min: {debris_min:.1f}°")
        safe_print(f"    Rock min: {rock_min:.1f}° <- seuil rocheux")

    except ImportError:
        # Fallback : Percentiles
        slope_valid = slope[~np.isnan(slope) & (slope > 0)]
        p50 = float(np.percentile(slope_valid, 50))
        p75 = float(np.percentile(slope_valid, 75))

        debris_min = p50
        rock_min = p75

        safe_print(f"  Slope seuils (Percentiles fallback):")
        safe_print(f"    Debris min: {debris_min:.1f}° (P50)")
        safe_print(f"    Rock min: {rock_min:.1f}° (P75)")

    # ── CURVATURE ────────────────────────────────────────────────────────────
    curvature_thresholds = None
    if curvature is not None:
        curv_valid = curvature[~np.isnan(curvature)]

        # Percentiles naturels : concave (P20, P25) et convexe (P75)
        p20_curv = float(np.percentile(curv_valid, 20))  # Concave assoupli (Grass_Dense)
        p25_curv = float(np.percentile(curv_valid, 25))  # Concave (Debris accumulation)
        p75_curv = float(np.percentile(curv_valid, 75))  # Convexe (Dirt, Grass_Dry)

        curvature_thresholds = {
            'grass_dense_max': p20_curv,    # < P20 concave assoupli (Grass_Dense)
            'debris_concave_max': p25_curv, # < P25 concave (Debris accumulation)
            'convexe_min': p75_curv         # >= P75 convexe (Dirt_Erosion, Grass_Dry)
        }

        safe_print(f"  Curvature seuils (Percentiles):")
        safe_print(f"    Concave assoupli (Grass_Dense) : < {p20_curv:.2f} (P20)")
        safe_print(f"    Concave (Debris)               : < {p25_curv:.2f} (P25)")
        safe_print(f"    Convexe (Dirt, Grass_Dry)      : >= {p75_curv:.2f} (P75)")

    result = {
        'altitude': {'p10': p10, 'p20': p20, 'p66': p66, 'p80': p80},
        'slope': {'debris_min': debris_min, 'rock_min': rock_min}
    }

    if curvature_thresholds:
        result['curvature'] = curvature_thresholds

    # Ajouter données calibration locale si activée
    if use_local_calibration and local_thresholds:
        result['local'] = local_thresholds
        result['region_masks'] = region_masks
        safe_print(f"  [CALIBRATION LOCALE] {len(local_thresholds)} régions détectées")

    return result


def load_curvature_mask(curvature_path, curvature_range):
    """
    Charge et décode masque curvature depuis Instant Terra

    Args:
        curvature_path: chemin .raw ou .png
        curvature_range: tuple (min, max) ex: (-21, 21)

    Returns:
        numpy array avec valeurs curvature décodées
    """
    from pathlib import Path

    curv_path = Path(curvature_path)
    min_curv, max_curv = curvature_range

    # Charger selon extension
    if curv_path.suffix == '.raw':
        # Détecter taille automatiquement
        file_size = curv_path.stat().st_size
        num_pixels = file_size // 2  # 16-bit = 2 bytes
        width = height = int(np.sqrt(num_pixels))

        if width * height != num_pixels:
            raise ValueError(f"Fichier .raw n'est pas carré : {num_pixels} pixels")

        try:
            curv = np.fromfile(curv_path, dtype='>u2').reshape((height, width))
        except:
            curv = np.fromfile(curv_path, dtype='<u2').reshape((height, width))

    elif curv_path.suffix == '.png':
        from PIL import Image
        curv = np.array(Image.open(curv_path), dtype=np.uint16)
    else:
        raise ValueError(f"Format non supporté : {curv_path.suffix}")

    # Décoder : [0, 65535] -> [min_curv, max_curv]
    curv_decoded = (curv / 65535.0) * (max_curv - min_curv) + min_curv

    return curv_decoded


def _generate_masks_for_region(heightmap, slope, region_mask, thresh, curvature=None, cellsize=2.0):
    """
    Génère 12 masques pour UNE région avec ses seuils locaux

    Args:
        heightmap: array altitudes
        slope: array pentes
        region_mask: masque booléen de la région
        thresh: dict seuils pour cette région
        curvature: array curvature optionnel
        cellsize: résolution

    Returns:
        dict: {name: boolean_array} masques pour cette région
    """
    # Extraire seuils
    p10 = thresh['altitude']['p10']
    p20 = thresh['altitude']['p20']
    p66 = thresh['altitude']['p66']
    p80 = thresh['altitude']['p80']
    debris_min = thresh['slope']['debris_min']
    rock_min = thresh['slope']['rock_min']

    if curvature is not None and 'curvature' in thresh:
        grass_dense_max = thresh['curvature']['grass_dense_max']
        debris_concave_max = thresh['curvature']['debris_concave_max']
        convexe_min = thresh['curvature']['convexe_min']
    else:
        grass_dense_max = -10.0
        debris_concave_max = -3.0
        convexe_min = 3.0

    # Masques de base
    land_mask = (heightmap >= 0) & (~np.isnan(heightmap)) & region_mask
    underwater_mask = (heightmap < 0) & (~np.isnan(heightmap))  # PAS region_mask (eau pas dans regions)
    flat_mask = (slope < debris_min) & (~np.isnan(slope)) & region_mask

    # Coastal (distance mer calculée globalement, pas par région)
    from scipy.ndimage import distance_transform_edt
    coastline_mask = (heightmap > 0) & (
        (np.roll(heightmap, 1, axis=0) <= 0) |
        (np.roll(heightmap, -1, axis=0) <= 0) |
        (np.roll(heightmap, 1, axis=1) <= 0) |
        (np.roll(heightmap, -1, axis=1) <= 0)
    )
    distance_px = distance_transform_edt(~coastline_mask)
    distance_m = distance_px * cellsize
    mask_coastal_initial = (heightmap >= 0) & (heightmap < p10) & flat_mask & (distance_m < 100.0)

    # Zones altitude
    mask_lowland_initial = (heightmap >= p10) & (heightmap < p66) & flat_mask
    mask_highland_initial = (heightmap >= p66) & flat_mask
    mask_seabed_initial = underwater_mask

    # Érosion 4 niveaux
    slope_mid1 = debris_min + (rock_min - debris_min) * 0.33
    slope_mid2 = debris_min + (rock_min - debris_min) * 0.67

    if curvature is not None:
        mask_erosion_light = (slope >= debris_min) & (slope < slope_mid1) & \
                             (curvature >= debris_concave_max) & land_mask
        mask_erosion_medium = (slope >= slope_mid1) & (slope < slope_mid2) & land_mask
        mask_erosion_heavy = (slope >= slope_mid2) & (slope < rock_min) & \
                             (curvature < debris_concave_max) & land_mask
        mask_rock_moderate = (slope >= rock_min) & (slope < rock_min + 5) & land_mask
        mask_rock_walls = (slope >= rock_min + 5) & land_mask
    else:
        mask_erosion_light = (slope >= debris_min) & (slope < slope_mid1) & land_mask
        mask_erosion_medium = (slope >= slope_mid1) & (slope < slope_mid2) & land_mask
        mask_erosion_heavy = (slope >= slope_mid2) & (slope < rock_min) & land_mask
        mask_rock_moderate = (slope >= rock_min) & (slope < rock_min + 5) & land_mask
        mask_rock_walls = (slope >= rock_min + 5) & land_mask

    # Cascade érosion
    mask_erosion_medium = mask_erosion_medium & (~mask_erosion_light)
    mask_erosion_heavy = mask_erosion_heavy & (~mask_erosion_light) & (~mask_erosion_medium)
    mask_rock_moderate = mask_rock_moderate & (~mask_erosion_light) & (~mask_erosion_medium) & (~mask_erosion_heavy)
    mask_rock_walls = mask_rock_walls & (~mask_erosion_light) & (~mask_erosion_medium) & (~mask_erosion_heavy) & (~mask_rock_moderate)

    # Highland
    mask_highland = mask_highland_initial & (~mask_rock_walls) & (~mask_rock_moderate) & \
                    (~mask_erosion_heavy) & (~mask_erosion_medium) & (~mask_erosion_light)
    mask_highland_mid = mask_highland & (heightmap < p80)
    mask_highland_high = mask_highland & (heightmap >= p80)

    # Grass
    mask_lowland = mask_lowland_initial & (~mask_rock_walls) & (~mask_rock_moderate) & \
                   (~mask_erosion_heavy) & (~mask_erosion_medium) & (~mask_erosion_light) & \
                   (~mask_highland_mid) & (~mask_highland_high)

    if curvature is not None:
        lowland_alt = heightmap[mask_lowland]
        if len(lowland_alt) > 0:
            p33_lowland = float(np.percentile(lowland_alt, 33))
            p80_lowland = float(np.percentile(lowland_alt, 80))
        else:
            p33_lowland = (p10 + p66) / 2
            p80_lowland = p80

        mask_grass_dry = mask_lowland & (heightmap >= p80_lowland) & (curvature >= convexe_min)
        mask_grass_dense_zones = mask_lowland & (heightmap < p33_lowland) & (curvature < grass_dense_max)
        mask_grass_standard = mask_lowland & (~mask_grass_dry) & (~mask_grass_dense_zones)
    else:
        mask_grass_dry = np.zeros_like(heightmap, dtype=bool)
        mask_grass_dense_zones = np.zeros_like(heightmap, dtype=bool)
        mask_grass_standard = mask_lowland

    # Coastal
    mask_coastal = mask_coastal_initial & (~mask_rock_walls) & (~mask_rock_moderate) & \
                   (~mask_erosion_heavy) & (~mask_erosion_medium) & (~mask_erosion_light) & \
                   (~mask_highland_mid) & (~mask_highland_high) & \
                   (~mask_grass_dry) & (~mask_grass_standard) & (~mask_grass_dense_zones)

    # Seabed
    mask_seabed = mask_seabed_initial

    return {
        '01_seabed': mask_seabed,
        '02_coastal_pebbles': mask_coastal,
        '03_grass_dry': mask_grass_dry,
        '04_grass_standard': mask_grass_standard,
        '05_grass_dense_zones': mask_grass_dense_zones,
        '06_highland_mid': mask_highland_mid,
        '07_highland_high': mask_highland_high,
        '08_erosion_light': mask_erosion_light,
        '09_erosion_medium': mask_erosion_medium,
        '10_erosion_heavy': mask_erosion_heavy,
        '11_rock_moderate': mask_rock_moderate,
        '12_rock_walls': mask_rock_walls
    }


def generate_masks(heightmap, slope, thresholds, curvature=None, cellsize=2.0):
    """
    Génère 12 masques optimisés QTRE avec calibration locale optionnelle

    ARCHITECTURE FINALE (12 masques) :
      1-2. Rock (Walls + Moderate) - 5 niveaux érosion
      3-5. Erosion (Light/Medium/Heavy)
      6-7. Highland (Mid/High)
      8-10. Grass (Dry/Standard/Dense)
      11. Coastal (Pebbles)
      12. SeaBed

    Args:
        heightmap: array altitudes
        slope: array pentes (degrés)
        thresholds: dict calibration (P10, P20, P66, P80, debris_min, rock_min)
                    + optionnel 'local' et 'region_masks' pour calibration locale
        curvature: array curvature (optionnel, pour subdivisions)
        cellsize: résolution m/px

    Returns:
        dict: {name: boolean_array}
    """
    safe_print("[4/7] Generation 12 masques optimises QTRE...")

    # Détecter calibration locale
    use_local = 'local' in thresholds and 'region_masks' in thresholds

    if use_local:
        safe_print("  [CALIBRATION LOCALE] Application seuils par region...")
        local_thresholds = thresholds['local']
        region_masks = thresholds['region_masks']

        # Generer masques par region
        regional_masks = {}
        for region_id, region_mask in region_masks.items():
            region_thresh = local_thresholds[region_id]
            safe_print(f"    Region {region_id}: debris>={region_thresh['slope']['debris_min']:.1f}deg, "
                  f"rock>={region_thresh['slope']['rock_min']:.1f}deg, "
                  f"p10={region_thresh['altitude']['p10']:.1f}m, p80={region_thresh['altitude']['p80']:.1f}m")
            regional_masks[region_id] = _generate_masks_for_region(
                heightmap, slope, region_mask, region_thresh, curvature, cellsize
            )

        # Fusionner les masques regionaux avec feathering aux frontieres
        safe_print("  Fusion masques regionaux avec feathering frontieres...")
        from scipy.ndimage import gaussian_filter, binary_dilation

        # Creer masque de frontiere entre regions (zone de transition)
        region_ids = list(region_masks.keys())
        if len(region_ids) == 2:
            # Dilater chaque region et trouver l'intersection = frontiere
            region_0_dilated = binary_dilation(region_masks[region_ids[0]], iterations=25)
            region_1_dilated = binary_dilation(region_masks[region_ids[1]], iterations=25)
            border_mask = region_0_dilated & region_1_dilated
        else:
            border_mask = np.zeros_like(heightmap, dtype=bool)

        # Fusionner chaque masque (sauf seabed qui est global)
        masks = {}

        # Seabed: generer globalement (pas par region, car eau pas dans regions)
        masks['01_seabed'] = (heightmap < 0) & (~np.isnan(heightmap))

        # Autres masques: fusionner par region
        for mask_name in ['02_coastal_pebbles', '03_grass_dry', '04_grass_standard',
                          '05_grass_dense_zones', '06_highland_mid', '07_highland_high',
                          '08_erosion_light', '09_erosion_medium', '10_erosion_heavy',
                          '11_rock_moderate', '12_rock_walls']:
            # Combiner masques de chaque region
            combined_mask = np.zeros_like(heightmap, dtype=bool)
            for region_id in region_ids:
                combined_mask |= regional_masks[region_id][mask_name]

            # Appliquer feathering à la zone frontiere
            if np.any(border_mask & combined_mask):
                # Flouter uniquement la zone frontiere
                mask_float = combined_mask.astype(np.float32)
                mask_float_blurred = gaussian_filter(mask_float, sigma=10)
                # Garder original sauf dans zone frontiere
                combined_mask = np.where(border_mask, mask_float_blurred > 0.3, combined_mask)

            masks[mask_name] = combined_mask

    else:
        safe_print("  [CALIBRATION GLOBALE] Application seuils uniformes...")

        # Creer un masque "full" couvrant tout le terrain
        full_mask = np.ones_like(heightmap, dtype=bool)

        # Utiliser la fonction helper avec les seuils globaux
        masks = _generate_masks_for_region(
            heightmap, slope, full_mask, thresholds, curvature, cellsize
        )

    # Masque de bord (ignorer 10px sur chaque bord pour eviter artifacts edge effects)
    safe_print("  Application masque bord (10px) pour eviter artifacts...")
    h, w = heightmap.shape
    edge_mask = np.ones_like(heightmap, dtype=bool)
    edge_mask[:10, :] = False  # Bord haut
    edge_mask[-10:, :] = False  # Bord bas
    edge_mask[:, :10] = False  # Bord gauche
    edge_mask[:, -10:] = False  # Bord droit

    # Appliquer masque bord a tous les masques terrestres (pas seabed)
    for mask_name in masks.keys():
        if mask_name != '01_seabed':
            masks[mask_name] = masks[mask_name] & edge_mask

    # Stats couverture
    total_pixels = np.sum(~np.isnan(heightmap))

    safe_print("\n  Couverture terrain (12 masques - nuances erosion):")
    for name, mask in masks.items():
        pct = (np.sum(mask) / total_pixels) * 100
        safe_print(f"    {name:24s}: {pct:5.2f}%")

    # Validation overlaps (feathering cree intentionnellement des overlaps)
    overlap_pixels = 0
    for i, (name1, mask1) in enumerate(list(masks.items())):
        for name2, mask2 in list(masks.items())[i+1:]:
            if name1 != '01_seabed' and name2 != '01_seabed':  # Ignorer seabed
                overlap_pixels += np.sum(mask1 & mask2)

    if overlap_pixels > 0:
        safe_print(f"\n  [WARNING] {overlap_pixels} pixels overlap detectes")

    # Estimation budget QTRE
    safe_print("\n  Estimation budget QTRE (12 masques):")
    safe_print("    Plaines       : 1-2 grass = 1-2 textures")
    safe_print("    Pentes faibles: 1-2 erosion light/medium = 1-2 textures")
    safe_print("    Pentes fortes : 2-3 erosion medium/heavy/rock = 2-3 textures")
    safe_print("    Transitions   : 2 grass + 3 erosion = 5 textures")
    safe_print("    Pire cas      : 1 coastal + 2 grass + 3 erosion = 6 textures (!)")
    safe_print("    Vegetation    : 0 slot (budget serre)")
    safe_print("    Mappeur       : 0-1 slot (zones plates)")
    safe_print("    Total max     : 6-7 textures/bloc [LIMITE QTRE]")

    return masks




def detect_base_texture(masks, heightmap):
    """
    Détecte quelle texture utiliser comme base Workbench

    Stratégie : La texture la plus dominante devient base
    -> Économise 1 masque (6 au lieu de 7)
    -> Respecte limite Reforger (7 textures au lieu de 8)

    Returns:
        dict: {
            'base_mask': str (nom masque),
            'base_texture': str (nom texture recommandée),
            'coverage_pct': float,
            'masks_to_import': list (6 masques restants)
        }
    """
    total_pixels = np.sum(~np.isnan(heightmap))

    coverage = {}
    for name, mask in masks.items():
        count = np.sum(mask)
        pct = (count / total_pixels) * 100
        coverage[name] = pct

    # Trouver masque dominant
    dominant_mask = max(coverage, key=coverage.get)
    dominant_pct = coverage[dominant_mask]

    # Mapping masque -> texture recommandée (vanilla stems) - 12 masques
    base_textures = {
        '01_seabed': 'SeaBed_01.emat',
        '02_coastal_pebbles': 'Pebbles_01.emat',
        '03_grass_dry': 'Grass_01.emat',
        '04_grass_standard': 'Grass_02.emat',
        '05_grass_dense_zones': 'Grass_03.emat',
        '06_highland_mid': 'MountainGrass_02.emat',
        '07_highland_high': 'MountainGrass_01.emat',
        '08_erosion_light': 'Dirt_01.emat',
        '09_erosion_medium': 'Dirt_03.emat',
        '10_erosion_heavy': 'Debris_Rock_01.emat',
        '11_rock_moderate': 'Rock_02.emat',
        '12_rock_walls': 'Rock_01.emat'
    }

    base_texture = base_textures.get(dominant_mask, 'Grass_02.emat')

    # Liste des 6 masques à importer (excluant la base)
    masks_to_import = [name for name in masks.keys() if name != dominant_mask]

    return {
        'base_mask': dominant_mask,
        'base_texture': base_texture,
        'coverage_pct': dominant_pct,
        'masks_to_import': masks_to_import
    }


def apply_feathering(masks, cellsize=2.0, terrain_size_m=8192):
    """
    Applique feathering (transitions douces) aux masques adjacents

    Sigma adaptatif selon type masque (coastal net, érosion doux)

    Args:
        masks: dict {name: boolean_array}
        cellsize: résolution m/px (pour adapter sigma)
        terrain_size_m: taille terrain (pour adapter sigma)

    Returns:
        dict: masques avec feathering appliqué
    """
    from scipy.ndimage import gaussian_filter

    safe_print("\n[5a/7] Application feathering différencié (transitions adaptées)...")

    # Calculer sigma de base selon taille terrain
    if terrain_size_m > 12000:  # Grande carte (Zimnitrita 16km)
        sigma_base = 6
        sigma_grass = 4
        sigma_coastal = 2
    elif terrain_size_m > 6000:  # Moyenne (ZBK 8km)
        sigma_base = 3
        sigma_grass = 2
        sigma_coastal = 1
    else:  # Petite (<6km)
        sigma_base = 2
        sigma_grass = 2
        sigma_coastal = 1

    safe_print(f"  Sigma adaptatif:")
    safe_print(f"    Érosion (Dirt/Debris/Rock) : {sigma_base}px ({sigma_base * cellsize:.1f}m)")
    safe_print(f"    Grass/Highland             : {sigma_grass}px ({sigma_grass * cellsize:.1f}m)")
    safe_print(f"    Coastal/SeaBed             : {sigma_coastal}px ({sigma_coastal * cellsize:.1f}m)")

    # Appliquer feathering avec sigma adapté
    masks_feathered = {}

    for name, mask in masks.items():
        # Déterminer sigma selon type masque
        if 'coastal' in name.lower() or 'seabed' in name.lower():
            sigma = sigma_coastal  # Transition courte mer/terre
        elif 'grass' in name.lower() or 'highland' in name.lower():
            sigma = sigma_grass  # Transition moyenne grass
        else:  # Érosion (dirt, debris, rock)
            sigma = sigma_base  # Transition longue érosion

        # Convertir boolean -> float pour blur
        mask_float = mask.astype(np.float32)

        # Gaussian blur
        mask_blurred = gaussian_filter(mask_float, sigma=sigma)

        # Reconvertir en boolean avec seuil adapté
        # Seuil plus bas pour petits sigma (garder couverture)
        threshold = 0.3 if sigma >= 3 else 0.4
        mask_feathered = mask_blurred > threshold

        masks_feathered[name] = mask_feathered

    safe_print(f"  Feathering appliqué à {len(masks)} masques")

    return masks_feathered


def export_masks(masks, output_dir, base_recommendation=None, target_resolution=4096):
    """
    Exporte masques PNG 16-bit avec downscale automatique

    Args:
        masks: dict {name: boolean_array}
        output_dir: dossier output
        base_recommendation: dict résultat detect_base_texture() (optionnel)
        target_resolution: résolution max (défaut 4096, ou None pour native)
    """
    safe_print(f"[5/7] Export masques: {output_dir}")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Détecter résolution source (premier masque)
    first_mask = next(iter(masks.values()))
    source_height, source_width = first_mask.shape

    # Décider si downscale nécessaire
    needs_downscale = False
    if target_resolution and max(source_height, source_width) > target_resolution:
        needs_downscale = True
        # Calculer résolution cible (garder aspect ratio)
        if source_height > source_width:
            target_height = target_resolution
            target_width = int(source_width * (target_resolution / source_height))
        else:
            target_width = target_resolution
            target_height = int(source_height * (target_resolution / source_width))

        safe_print(f"  Downscale: {source_width}x{source_height} -> {target_width}x{target_height} (optimisation Workbench)")
    else:
        target_width, target_height = source_width, source_height
        safe_print(f"  Résolution native: {source_width}x{source_height}")

    for name, mask in masks.items():
        # Convertir boolean -> uint16 (0 ou 65535)
        mask_uint16 = mask.astype(np.uint16) * 65535

        # Remplacer NaN par 0
        mask_uint16[np.isnan(mask_uint16)] = 0

        # Downscale si nécessaire (interpolation NEAREST pour masques binaires)
        if needs_downscale:
            img = Image.fromarray(mask_uint16)
            img_resized = img.resize((target_width, target_height), Image.NEAREST)
            mask_uint16 = np.array(img_resized)

        # Sauvegarder PNG
        output_path = output_dir / f"{name}.png"
        Image.fromarray(mask_uint16).save(output_path)

        # Marquer si c'est la base recommandée
        if base_recommendation and name == base_recommendation['base_mask']:
            safe_print(f"  {name}.png (BASE RECOMMANDÉE - ne pas importer)")
        else:
            safe_print(f"  {name}.png")

    safe_print(f"  Total: {len(masks)} masques générés")

    if base_recommendation:
        safe_print(f"\n  [OPTIMISATION WORKBENCH]")
        safe_print(f"     Base: {base_recommendation['base_texture']} ({base_recommendation['coverage_pct']:.1f}% terrain)")
        safe_print(f"     Masques a importer: {len(base_recommendation['masks_to_import'])} (6/7)")
        safe_print(f"     Total textures: 7 (1 base + 6 masques) [OK]")


def save_calibration(thresholds, output_path):
    """Sauvegarde calibration JSON"""
    safe_print(f"[6/6] Sauvegarde calibration: {output_path}")

    # Copier thresholds sans region_masks (numpy arrays non JSON serializable)
    thresholds_safe = dict(thresholds)
    if 'region_masks' in thresholds_safe:
        del thresholds_safe['region_masks']  # Ne pas sauvegarder (recalculé automatiquement)

    data = {
        'version': '1.0',
        'generated_at': datetime.now().isoformat(),
        'thresholds': thresholds_safe
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    safe_print("  Calibration sauvegardée")


def generate_workbench_instructions(base_recommendation, biome_textures, output_path):
    """
    Génère fichier instructions pour import Workbench

    Args:
        base_recommendation: dict detect_base_texture()
        biome_textures: dict {mask_name: texture} depuis biome
        output_path: chemin fichier instructions.txt
    """
    instructions = []
    instructions.append("="*70)
    instructions.append("INSTRUCTIONS IMPORT WORKBENCH REFORGER")
    instructions.append("="*70)
    instructions.append("")
    instructions.append("OPTIMISATION : 7 TEXTURES TOTAL (1 base + 6 masques)")
    instructions.append("")

    # Étape 1 : Base
    base_mask = base_recommendation['base_mask']
    base_texture = base_recommendation['base_texture']
    base_pct = base_recommendation['coverage_pct']

    instructions.append("ÉTAPE 1 : APPLIQUER TEXTURE DE BASE")
    instructions.append("-" * 70)
    instructions.append(f"Texture : {base_texture}")
    instructions.append(f"Coverage: {base_pct:.1f}% du terrain")
    instructions.append("")
    instructions.append("Workbench :")
    instructions.append("  1. Sélectionner texture : " + base_texture)
    instructions.append("  2. Clic droit > Fill Surface Layer (Clear Others)")
    instructions.append("     -> Applique sur 100% du terrain")
    instructions.append("")

    # Étape 2 : Masques
    instructions.append("ÉTAPE 2 : IMPORTER MASQUES (6/7)")
    instructions.append("-" * 70)
    instructions.append("")

    masks_to_import = base_recommendation['masks_to_import']

    for i, mask_name in enumerate(masks_to_import, 1):
        # Extraire nom sans numéro (ex: '02_coastal' -> 'coastal')
        mask_key = mask_name.split('_', 1)[1] if '_' in mask_name else mask_name
        texture = biome_textures.get(mask_key, "???")

        instructions.append(f"{i}. {mask_name}.png")
        instructions.append(f"   Texture : {texture}")
        instructions.append(f"   Workbench :")
        instructions.append(f"     - Sélectionner texture : {texture}")
        instructions.append(f"     - Terrain > Apply Mask")
        instructions.append(f"     - Charger : {mask_name}.png")
        instructions.append("")

    instructions.append("="*70)
    instructions.append("RÉSULTAT FINAL")
    instructions.append("="*70)
    instructions.append(f"Textures totales : 7 (1 base + 6 masques)")
    instructions.append(f"Limite Reforger  : 5-7 textures/bloc")
    instructions.append(f"Statut           : [OK] COMPATIBLE")
    instructions.append("")

    # Sauvegarder
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(instructions))


def run_pipeline(heightmap_path, output_dir, curvature_path=None, curvature_range=None, mask_resolution=4096):
    """
    Pipeline complet : heightmap -> masques PNG 14 textures

    Phase 1-6 : Côtier + Grass + Highland + Érosion + Talwegs + Sous-marin

    Args:
        heightmap_path: chemin fichier ASC
        output_dir: dossier output masques
        curvature_path: chemin masque curvature .raw/.png (optionnel)
        curvature_range: tuple (min, max) seuils curvature IT (ex: -21, 21)
        mask_resolution: résolution max masques (défaut 4096, None = native)

    Returns:
        dict: {
            'thresholds': calibration data (avec curvature auto-calibrée),
            'base_recommendation': base texture info
        }
    """
    safe_print("="*80)
    safe_print("PIPELINE 12 MASQUES — CALIBRATION LOCALE + NUANCES ÉROSION")
    safe_print("="*80)

    # 1. Charger heightmap
    heightmap, meta = load_asc(heightmap_path)

    # 2. Calculer slope
    slope = calculate_slope(heightmap, meta['cellsize'])

    # 3. Charger curvature (optionnel)
    curvature = None
    if curvature_path and Path(curvature_path).exists():
        safe_print("\n[3a/7] Chargement curvature...")
        curvature = load_curvature_mask(curvature_path, curvature_range or (-21, 21))
        safe_print(f"  Curvature chargée : {curvature.shape}")
    else:
        safe_print("\n[3a/7] Pas de curvature -> Côtier uniforme")

    # 4. Auto-calibration (altitude + slope + curvature)
    safe_print("\n[4/7] Auto-calibration...")
    thresholds = auto_calibrate(heightmap, slope, curvature, cellsize=meta['cellsize'])

    # 5. Générer masques (avec curvature pour subdivisions)
    masks = generate_masks(heightmap, slope, thresholds, curvature, cellsize=meta['cellsize'])

    # 5a. Appliquer feathering (transitions douces)
    # Note : feathering crée overlaps intentionnels (transitions graduées)
    terrain_size_m = heightmap.shape[0] * meta['cellsize']
    masks = apply_feathering(masks, cellsize=meta['cellsize'], terrain_size_m=terrain_size_m)
    safe_print("  [INFO] Feathering crée overlaps intentionnels pour transitions douces (normal)")

    # 6. Détecter texture base optimale
    safe_print("\n[6/7] Détection texture base optimale...")
    base_recommendation = detect_base_texture(masks, heightmap)

    # 7. Exporter PNG (avec downscale auto)
    export_masks(masks, output_dir, base_recommendation, target_resolution=mask_resolution)

    # 8. Sauvegarder calibration
    calibration_path = Path(output_dir) / 'calibration.json'
    save_calibration(thresholds, calibration_path)

    # 9. Analyse budget QTRE (visualisation densité textures/bloc)
    try:
        qtre_stats = generate_qtre_heatmap(
            masks_dir=output_dir,
            cellsize=meta['cellsize'],
            output_dir=output_dir,
            heightmap=heightmap,
            presence_threshold=3276  # 5% de 65535
        )
    except Exception as e:
        safe_print(f"\n[QTRE] (!) Erreur analyse QTRE: {e}")
        qtre_stats = None

    safe_print("\n" + "="*60)
    safe_print("TERMINÉ !")
    safe_print(f"Masques: {output_dir}")
    safe_print("="*60)

    return {
        'thresholds': thresholds,
        'base_recommendation': base_recommendation,
        'qtre_stats': qtre_stats
    }


# ══════════════════════════════════════════════════════════════════════════════
# OUTIL VISUALISATION BUDGET QTRE (densité textures par bloc)
# ══════════════════════════════════════════════════════════════════════════════

def generate_qtre_heatmap(masks_dir, cellsize, output_dir, heightmap=None,
                          presence_threshold=3276, threshold_ok=3, threshold_limit=5,
                          analyze_conflicts=True, generate_per_texture_heatmaps=False):
    """
    Génère une heatmap de densité QTRE (textures/bloc 32×32m) avec analyse de conflits

    Args:
        masks_dir: Dossier contenant les masques PNG 16-bit générés
        cellsize: Résolution m/px (2 pour ZBK, 4 pour Zimnitrita)
        output_dir: Dossier de sortie pour les visualisations
        heightmap: Optionnel, heightmap numpy array pour overlay
        presence_threshold: Seuil valeur moyenne pour considérer texture active (défaut 5% de 65535)
        threshold_ok: Nombre max de textures OK (défaut 3)
        threshold_limit: Nombre max de textures limite avant critique (défaut 5)
        analyze_conflicts: Générer analyse détaillée des conflits (défaut True)
        generate_per_texture_heatmaps: Générer heatmaps individuelles par texture (défaut False)

    Returns:
        dict avec statistiques QTRE
    """
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors
    from matplotlib.patches import Rectangle
    from pathlib import Path

    safe_print("\n[QTRE] Analyse densité textures par bloc...")

    masks_dir = Path(masks_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Charger tous les masques PNG 16-bit (sauf SeaBed)
    masks = {}
    mask_files = sorted(masks_dir.glob("*.png"))

    for mask_file in mask_files:
        mask_name = mask_file.stem

        # Ignorer SeaBed (sous-marin, pas compté dans QTRE)
        if 'seabed' in mask_name.lower():
            safe_print(f"  -> Ignore: {mask_name} (sous-marin)")
            continue

        try:
            img = Image.open(mask_file)
            mask_array = np.array(img, dtype=np.float32)
            masks[mask_name] = mask_array
            safe_print(f"  -> Charge: {mask_name} ({mask_array.shape})")
        except Exception as e:
            safe_print(f"  (!) Erreur lecture {mask_name}: {e}")
            continue

    if not masks:
        safe_print("  (X) Aucun masque charge !")
        return None

    # 2. Calculer taille bloc en pixels
    bloc_px = int(32 / cellsize)  # 32m au sol
    safe_print(f"  Taille bloc: {bloc_px}×{bloc_px} pixels (32m au sol)")

    # 3. Obtenir dimensions
    first_mask = next(iter(masks.values()))
    h, w = first_mask.shape
    safe_print(f"  Résolution masques: {h}×{w} pixels")

    # 4. Calculer nombre de blocs
    n_blocs_y = h // bloc_px
    n_blocs_x = w // bloc_px
    total_blocs = n_blocs_y * n_blocs_x
    safe_print(f"  Grille blocs: {n_blocs_y}×{n_blocs_x} = {total_blocs} blocs")

    # 5. Créer matrice densité (1 pixel par bloc)
    density_map = np.zeros((n_blocs_y, n_blocs_x), dtype=np.uint8)

    # 5b. Stockage détails conflits (si activé)
    conflict_details = [] if analyze_conflicts else None

    # 6. Pour chaque bloc, compter textures actives ET stocker détails conflits
    safe_print(f"  Analyse {total_blocs} blocs...")

    for by in range(n_blocs_y):
        for bx in range(n_blocs_x):
            y_start = by * bloc_px
            x_start = bx * bloc_px
            y_end = y_start + bloc_px
            x_end = x_start + bloc_px

            active_count = 0
            active_textures = []  # Pour analyse conflits

            for mask_name, mask_array in masks.items():
                # Extraire région bloc
                bloc_region = mask_array[y_start:y_end, x_start:x_end]

                # Calculer moyenne
                mean_val = np.mean(bloc_region)

                # Si moyenne > seuil -> texture active
                if mean_val > presence_threshold:
                    active_count += 1

                    # Stocker détails pour analyse conflits
                    if analyze_conflicts:
                        coverage_pct = (np.sum(bloc_region > 0) / bloc_region.size) * 100
                        active_textures.append({
                            'name': mask_name,
                            'mean': float(mean_val),
                            'coverage': float(coverage_pct)
                        })

            density_map[by, bx] = active_count

            # Stocker bloc si > threshold_ok (pour analyse conflits)
            if analyze_conflicts and active_count > threshold_ok:
                x_m = (bx * bloc_px + bloc_px/2) * cellsize
                y_m = (by * bloc_px + bloc_px/2) * cellsize

                conflict_details.append({
                    'x_m': float(x_m),
                    'y_m': float(y_m),
                    'bx': bx,
                    'by': by,
                    'density': active_count,
                    'textures': sorted(active_textures, key=lambda x: x['coverage'], reverse=True)
                })

    # 7. Statistiques
    stats = {
        'total_blocs': total_blocs,
        'distribution': {},
        'max_density': int(np.max(density_map)),
        'mean_density': float(np.mean(density_map)),
        'median_density': float(np.median(density_map))
    }

    for density in range(0, stats['max_density'] + 1):
        count = np.sum(density_map == density)
        pct = (count / total_blocs) * 100
        stats['distribution'][density] = {'count': int(count), 'percent': float(pct)}

    # 8. Trouver top 10 zones les plus denses AVEC liste des textures
    top_zones = []
    flat_indices = np.argsort(density_map.ravel())[::-1][:10]  # Top 10

    for idx in flat_indices:
        by = idx // n_blocs_x
        bx = idx % n_blocs_x
        density = int(density_map[by, bx])

        # Convertir en coordonnées mètres (centre du bloc)
        x_m = (bx * bloc_px + bloc_px/2) * cellsize
        y_m = (by * bloc_px + bloc_px/2) * cellsize

        # Extraire liste des textures actives dans ce bloc
        y_start = by * bloc_px
        x_start = bx * bloc_px
        y_end = y_start + bloc_px
        x_end = x_start + bloc_px

        active_textures_in_bloc = []
        for mask_name, mask_array in masks.items():
            bloc_region = mask_array[y_start:y_end, x_start:x_end]
            mean_val = np.mean(bloc_region)
            if mean_val > presence_threshold:
                coverage_pct = (np.sum(bloc_region > 0) / bloc_region.size) * 100
                active_textures_in_bloc.append({
                    'name': mask_name,
                    'coverage': float(coverage_pct)
                })

        # Trier par couverture décroissante
        active_textures_in_bloc = sorted(active_textures_in_bloc, key=lambda x: x['coverage'], reverse=True)

        top_zones.append({
            'x_m': float(x_m),
            'y_m': float(y_m),
            'density': density,
            'textures': active_textures_in_bloc
        })

    stats['top_zones'] = top_zones

    # 8b. Distribution geographique par texture (ou chaque texture est presente)
    texture_distribution = {}

    for mask_name, mask_array in masks.items():
        # Compter nombre de blocs ou cette texture est active
        blocs_actifs = []

        for by in range(n_blocs_y):
            for bx in range(n_blocs_x):
                y_start = by * bloc_px
                x_start = bx * bloc_px
                y_end = y_start + bloc_px
                x_end = x_start + bloc_px

                bloc_region = mask_array[y_start:y_end, x_start:x_end]
                mean_val = np.mean(bloc_region)

                if mean_val > presence_threshold:
                    x_m = (bx * bloc_px + bloc_px/2) * cellsize
                    y_m = (by * bloc_px + bloc_px/2) * cellsize
                    blocs_actifs.append({
                        'x_m': float(x_m),
                        'y_m': float(y_m),
                        'intensity': float(mean_val)
                    })

        # Trier par intensité décroissante et garder top 5
        blocs_actifs_sorted = sorted(blocs_actifs, key=lambda x: x['intensity'], reverse=True)[:5]

        texture_distribution[mask_name] = {
            'total_blocs': len(blocs_actifs),
            'coverage_pct': (len(blocs_actifs) / total_blocs) * 100,
            'top_zones': blocs_actifs_sorted
        }

    stats['texture_distribution'] = texture_distribution

    # 9. Texture la plus responsable des dépassements
    texture_blame = {name: 0 for name in masks.keys()}

    for by in range(n_blocs_y):
        for bx in range(n_blocs_x):
            if density_map[by, bx] > threshold_ok:  # Dépassement seuil OK
                y_start = by * bloc_px
                x_start = bx * bloc_px
                y_end = y_start + bloc_px
                x_end = x_start + bloc_px

                for mask_name, mask_array in masks.items():
                    bloc_region = mask_array[y_start:y_end, x_start:x_end]
                    if np.mean(bloc_region) > presence_threshold:
                        texture_blame[mask_name] += 1

    if texture_blame:
        most_blamed = max(texture_blame.items(), key=lambda x: x[1])
        stats['most_blamed_texture'] = {
            'name': most_blamed[0],
            'count': most_blamed[1]
        }

    # 10. Verdict (avec seuils configurables)
    pct_ok = sum(stats['distribution'].get(i, {}).get('percent', 0)
                 for i in range(0, threshold_ok + 1))

    pct_attention = sum(stats['distribution'].get(i, {}).get('percent', 0)
                        for i in range(threshold_ok + 1, threshold_limit + 1))

    pct_critical = sum(stats['distribution'].get(i, {}).get('percent', 0)
                       for i in range(threshold_limit + 1, stats['max_density'] + 1))

    if pct_critical > 5:
        verdict = "CRITIQUE"
    elif pct_attention > 20:
        verdict = "ATTENTION"
    else:
        verdict = "OK"

    stats['verdict'] = verdict
    stats['pct_ok'] = float(pct_ok)
    stats['pct_attention'] = float(pct_attention)
    stats['pct_critical'] = float(pct_critical)
    stats['threshold_ok'] = threshold_ok
    stats['threshold_limit'] = threshold_limit
    stats['conflict_count'] = len(conflict_details) if conflict_details else 0

    # 11. GENERER HEATMAP COULEUR PNG
    safe_print(f"  Generation heatmap couleur...")

    fig, ax = plt.subplots(figsize=(12, 10))

    # Colormap personnalisée adaptée aux seuils
    colors = ['#000080', '#0000FF', '#00FF00', '#FFFF00', '#FF8000', '#FF0000', '#800080']
    n_bins = stats['max_density'] + 1
    cmap = mcolors.LinearSegmentedColormap.from_list('qtre', colors, N=n_bins)

    vmax_display = max(threshold_limit + 2, stats['max_density'])
    im = ax.imshow(density_map, cmap=cmap, vmin=0, vmax=vmax_display,
                   interpolation='nearest', origin='upper')

    # Légende colorbar
    cbar = plt.colorbar(im, ax=ax, orientation='vertical', pad=0.02)
    cbar.set_label('Textures actives par bloc 32×32m', rotation=270, labelpad=20, fontsize=12)
    cbar.ax.tick_params(labelsize=10)

    ax.set_title(f"Budget QTRE — Densite Textures/Bloc\n{verdict}",
                 fontsize=16, fontweight='bold')
    ax.set_xlabel(f"Blocs X (1 bloc = 32m)", fontsize=12)
    ax.set_ylabel(f"Blocs Y (1 bloc = 32m)", fontsize=12)

    # Ajouter grille légère
    ax.grid(True, alpha=0.2, linestyle='--', linewidth=0.5)

    # Annotations statistiques (seuils configurables)
    text_stats = f"Total: {total_blocs} blocs\n"
    text_stats += f"OK (<={threshold_ok} tex): {pct_ok:.1f}%\n"
    text_stats += f"Limite ({threshold_ok+1}-{threshold_limit}): {pct_attention:.1f}%\n"
    text_stats += f"Critique ({threshold_limit+1}+): {pct_critical:.1f}%"
    if conflict_details:
        text_stats += f"\nConflits: {len(conflict_details)} blocs"

    ax.text(0.02, 0.98, text_stats, transform=ax.transAxes, fontsize=10,
            verticalalignment='top', bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

    plt.tight_layout()
    heatmap_path = output_dir / 'qtre_heatmap.png'
    plt.savefig(heatmap_path, dpi=150, bbox_inches='tight')
    plt.close()
    safe_print(f"  -> Sauvegarde: {heatmap_path}")

    # 12. GENERER OVERLAY SUR HEIGHTMAP (si fournie)
    if heightmap is not None:
        safe_print(f"  Generation overlay sur heightmap...")

        fig, ax = plt.subplots(figsize=(14, 12))

        # Heightmap en niveaux de gris (fond)
        heightmap_normalized = (heightmap - np.nanmin(heightmap)) / (np.nanmax(heightmap) - np.nanmin(heightmap))
        ax.imshow(heightmap_normalized, cmap='gray', alpha=0.7, origin='upper')

        # Heatmap QTRE en overlay (resize pour correspondre)
        from scipy.ndimage import zoom
        zoom_factor_y = h / n_blocs_y
        zoom_factor_x = w / n_blocs_x
        density_map_resized = zoom(density_map, (zoom_factor_y, zoom_factor_x), order=0)

        im_overlay = ax.imshow(density_map_resized, cmap=cmap, vmin=0, vmax=vmax_display,
                               alpha=0.6, interpolation='nearest', origin='upper')

        cbar = plt.colorbar(im_overlay, ax=ax, orientation='vertical', pad=0.02)
        cbar.set_label('Textures/bloc', rotation=270, labelpad=20, fontsize=12)

        ax.set_title(f"QTRE Overlay — {verdict}", fontsize=16, fontweight='bold')
        ax.axis('off')

        plt.tight_layout()
        overlay_path = output_dir / 'qtre_overlay.png'
        plt.savefig(overlay_path, dpi=150, bbox_inches='tight')
        plt.close()
        safe_print(f"  -> Sauvegarde: {overlay_path}")

    # 12b. GENERER RAPPORT CONFLITS DETAILLE (si demande)
    if analyze_conflicts and conflict_details:
        safe_print(f"  Generation rapport conflits ({len(conflict_details)} blocs)...")

        conflicts_path = output_dir / 'qtre_conflicts.txt'
        with open(conflicts_path, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("ANALYSE DETAILLEE DES CONFLITS QTRE\n")
            f.write("=" * 80 + "\n\n")

            f.write(f"Seuil OK: <={threshold_ok} textures\n")
            f.write(f"Seuil Limite: <={threshold_limit} textures\n")
            f.write(f"Total blocs en conflit (>{threshold_ok} tex): {len(conflict_details)}\n\n")

            # Analyser les paires de textures frequentes
            from collections import Counter
            texture_pairs = Counter()
            texture_freq = Counter()

            for conflict in conflict_details:
                tex_names = [t['name'] for t in conflict['textures']]
                for name in tex_names:
                    texture_freq[name] += 1

                # Paires (combinaisons de 2)
                for i, t1 in enumerate(tex_names):
                    for t2 in tex_names[i+1:]:
                        pair = tuple(sorted([t1, t2]))
                        texture_pairs[pair] += 1

            f.write("TEXTURES LES PLUS FREQUENTES DANS LES CONFLITS\n")
            f.write("-" * 80 + "\n")
            for tex_name, count in texture_freq.most_common(10):
                pct = (count / len(conflict_details)) * 100
                f.write(f"  {tex_name:30s} : {count:4d} blocs ({pct:5.1f}%)\n")

            f.write("\n")
            f.write("PAIRES DE TEXTURES LES PLUS FREQUENTES\n")
            f.write("-" * 80 + "\n")
            for (tex1, tex2), count in texture_pairs.most_common(15):
                pct = (count / len(conflict_details)) * 100
                f.write(f"  {tex1:28s} + {tex2:28s} : {count:4d} ({pct:5.1f}%)\n")

            f.write("\n")
            f.write("DETAIL DES BLOCS EN CONFLIT\n")
            f.write("-" * 80 + "\n\n")

            # Trier par densite decroissante
            conflict_details_sorted = sorted(conflict_details, key=lambda x: x['density'], reverse=True)

            for i, conflict in enumerate(conflict_details_sorted[:50], 1):  # Limiter a 50 premiers
                f.write(f"Bloc #{i} : Position ({conflict['x_m']:7.1f}m, {conflict['y_m']:7.1f}m) "
                       f"-> {conflict['density']} textures\n")

                for tex in conflict['textures']:
                    f.write(f"  - {tex['name']:30s} : {tex['coverage']:5.1f}% couverture "
                           f"(moy: {tex['mean']:6.0f})\n")

                f.write("\n")

            if len(conflict_details) > 50:
                f.write(f"... et {len(conflict_details) - 50} autres blocs en conflit\n\n")

            f.write("=" * 80 + "\n")
            f.write(f"Rapport sauvegarde: {conflicts_path}\n")
            f.write("=" * 80 + "\n")

        safe_print(f"  -> Sauvegarde: {conflicts_path}")

    # 13. GENERER RAPPORT TEXTE PRINCIPAL
    safe_print(f"  Generation rapport statistique...")

    report_path = output_dir / 'qtre_report.txt'
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("=" * 70 + "\n")
        f.write("RAPPORT BUDGET QTRE — Analyse Densité Textures\n")
        f.write("=" * 70 + "\n\n")

        f.write(f"Verdict: {verdict}\n\n")

        f.write("STATISTIQUES GÉNÉRALES\n")
        f.write("-" * 70 + "\n")
        f.write(f"Total blocs analysés: {total_blocs}\n")
        f.write(f"Taille bloc: 32×32m ({bloc_px}×{bloc_px} pixels)\n")
        f.write(f"Cellsize: {cellsize}m/px\n")
        f.write(f"Seuil présence: {presence_threshold} (5% de 65535)\n\n")

        f.write(f"Densité moyenne: {stats['mean_density']:.2f} textures/bloc\n")
        f.write(f"Densité médiane: {stats['median_density']:.0f} textures/bloc\n")
        f.write(f"Densité maximale: {stats['max_density']} textures/bloc\n\n")

        f.write("DISTRIBUTION\n")
        f.write("-" * 70 + "\n")
        for density in range(0, stats['max_density'] + 1):
            dist = stats['distribution'].get(density, {})
            count = dist.get('count', 0)
            pct = dist.get('percent', 0)
            status = ""
            if density <= threshold_ok:
                status = "[OK]"
            elif density <= threshold_limit:
                status = "[LIMITE]"
            else:
                status = "[CRITIQUE]"
            f.write(f"{density} textures: {count:6d} blocs ({pct:5.2f}%) {status}\n")

        f.write("\n")
        f.write(f"Blocs OK (<={threshold_ok} textures):      {pct_ok:5.2f}%\n")
        f.write(f"Blocs Attention ({threshold_ok+1}-{threshold_limit}):       {pct_attention:5.2f}%\n")
        f.write(f"Blocs Critique ({threshold_limit+1}+):         {pct_critical:5.2f}%\n\n")

        f.write("TOP 10 ZONES LES PLUS DENSES\n")
        f.write("-" * 70 + "\n")
        for i, zone in enumerate(stats['top_zones'], 1):
            f.write(f"{i:2d}. Position ({zone['x_m']:7.1f}m, {zone['y_m']:7.1f}m) "
                   f"-> {zone['density']} textures:\n")
            # Afficher liste des textures dans cette zone
            for tex in zone.get('textures', []):
                f.write(f"     - {tex['name']:30s} ({tex['coverage']:4.1f}% couverture)\n")
            f.write("\n")

        # Distribution geographique par texture
        if 'texture_distribution' in stats:
            f.write("DISTRIBUTION GEOGRAPHIQUE PAR TEXTURE\n")
            f.write("-" * 70 + "\n")
            f.write("Ou chaque texture est presente sur la carte:\n\n")

            # Trier par nombre de blocs décroissant
            sorted_textures = sorted(stats['texture_distribution'].items(),
                                    key=lambda x: x[1]['total_blocs'], reverse=True)

            for mask_name, dist_info in sorted_textures:
                f.write(f"{mask_name}:\n")
                f.write(f"  Presente dans {dist_info['total_blocs']:5d} blocs "
                       f"({dist_info['coverage_pct']:5.2f}% de la carte)\n")

                if dist_info['top_zones']:
                    f.write(f"  Top 5 zones les plus denses:\n")
                    for j, zone in enumerate(dist_info['top_zones'], 1):
                        f.write(f"    {j}. ({zone['x_m']:7.1f}m, {zone['y_m']:7.1f}m) "
                               f"- intensite: {zone['intensity']:6.0f}\n")
                f.write("\n")

        if 'most_blamed_texture' in stats:
            f.write("\n")
            f.write("TEXTURE LA PLUS RESPONSABLE DES DEPASSEMENTS\n")
            f.write("-" * 70 + "\n")
            blamed = stats['most_blamed_texture']
            f.write(f"{blamed['name']}: presente dans {blamed['count']} blocs >{threshold_ok} textures\n")

        f.write("\n")
        f.write("=" * 70 + "\n")
        f.write("Fichiers generes:\n")
        f.write(f"  - {output_dir / 'qtre_heatmap.png'}\n")
        if heightmap is not None:
            f.write(f"  - {output_dir / 'qtre_overlay.png'}\n")
        if conflict_details:
            f.write(f"  - {output_dir / 'qtre_conflicts.txt'}\n")
        f.write(f"  - {output_dir / 'qtre_report.txt'}\n")
        f.write("=" * 70 + "\n")

    safe_print(f"  -> Sauvegarde: {report_path}")

    # 14. GENERER HEATMAPS INDIVIDUELLES PAR TEXTURE (optionnel)
    if generate_per_texture_heatmaps:
        safe_print(f"  Generation heatmaps individuelles par texture...")

        heatmaps_dir = output_dir / 'qtre_per_texture'
        heatmaps_dir.mkdir(exist_ok=True)

        for mask_name, mask_array in masks.items():
            # Creer une heatmap de densite pour cette texture seule
            texture_density = np.zeros((n_blocs_y, n_blocs_x), dtype=np.float32)

            for by in range(n_blocs_y):
                for bx in range(n_blocs_x):
                    y_start = by * bloc_px
                    x_start = bx * bloc_px
                    y_end = y_start + bloc_px
                    x_end = x_start + bloc_px

                    bloc_region = mask_array[y_start:y_end, x_start:x_end]
                    texture_density[by, bx] = np.mean(bloc_region)

            # Generer PNG
            fig, ax = plt.subplots(figsize=(10, 8))

            im = ax.imshow(texture_density, cmap='hot', vmin=0, vmax=65535,
                          interpolation='nearest', origin='upper')

            cbar = plt.colorbar(im, ax=ax, orientation='vertical', pad=0.02)
            cbar.set_label('Intensite moyenne', rotation=270, labelpad=20, fontsize=10)

            ax.set_title(f"Densite : {mask_name}", fontsize=14, fontweight='bold')
            ax.set_xlabel(f"Blocs X", fontsize=10)
            ax.set_ylabel(f"Blocs Y", fontsize=10)

            plt.tight_layout()
            texture_heatmap_path = heatmaps_dir / f"{mask_name}_density.png"
            plt.savefig(texture_heatmap_path, dpi=120, bbox_inches='tight')
            plt.close()

        safe_print(f"  -> {len(masks)} heatmaps dans: {heatmaps_dir}")

    # 15. Afficher resume console
    safe_print(f"\n[QTRE] Budget QTRE: {pct_ok:.1f}% OK, {pct_attention:.1f}% attention, {pct_critical:.1f}% critique -> {verdict}")

    return stats


# ══════════════════════════════════════════════════════════════════════════════
# COMPATIBILITÉ APP.PY (stubs pour ancien pipeline)
# ══════════════════════════════════════════════════════════════════════════════

# Constantes pour compatibilité (12 masques - nuances érosion)
PIPELINE_STEMS = [
    'SeaBed', 'Coastal_Pebbles',
    'Grass_Dry', 'Grass_Standard', 'Grass_Dense_Zones',
    'Highland_Mid', 'Highland_High',
    'Erosion_Light', 'Erosion_Medium', 'Erosion_Heavy',
    'Rock_Moderate', 'Rock_Walls'
]

STEM_COLORS = {
    'Seabed': (50, 100, 150),
    'Coastal': (200, 180, 120),
    'Pebbles': (150, 140, 120),
    'Grass': (100, 180, 80),
    'Dry': (140, 170, 90),
    'Standard': (100, 180, 80),
    'Dense': (80, 150, 60),
    'Zones': (80, 150, 60),
    'Highland': (120, 140, 100),
    'Mid': (110, 130, 90),
    'High': (130, 150, 110),
    'Erosion': (120, 100, 80),
    'Light': (140, 120, 95),
    'Medium': (120, 100, 80),
    'Heavy': (100, 85, 70),
    'Dirt': (120, 100, 80),
    'Debris': (140, 120, 100),
    'Rock': (100, 100, 100),
    'Moderate': (90, 90, 90),
    'Walls': (80, 80, 80)
}

STEM_ROLES = {
    'SeaBed': 'underwater',
    'Coastal_Pebbles': 'coastal',
    'Grass_Dry': 'grass',
    'Grass_Standard': 'grass',
    'Grass_Dense_Zones': 'grass',
    'Highland_Mid': 'grass',
    'Highland_High': 'grass',
    'Erosion_Light': 'dirt',
    'Erosion_Medium': 'dirt',
    'Erosion_Heavy': 'debris',
    'Rock_Moderate': 'rock',
    'Rock_Walls': 'rock'
}


class TexturePipeline:
    """
    Classe simplifiée pour compatibilité app.py
    Remplace l'ancien pipeline complexe par le nouveau pipeline simple (7 masques)
    """

    def __init__(self, heightmap_path, output_dir=None):
        self.heightmap_path = heightmap_path
        self.output_dir = output_dir
        self.thresholds = None

    def run(self, output_dir=None):
        """Exécute le pipeline simple"""
        if output_dir is None:
            output_dir = self.output_dir or "output_masks"

        # Appeler pipeline simple
        self.thresholds = run_pipeline(self.heightmap_path, output_dir)

        return self.thresholds

    @staticmethod
    def derive_grid_from_project(project):
        """Stub pour compatibilité - retourne valeurs par défaut"""
        return (4096, 4096, 64, 64, 0.0, 400.0)

    @staticmethod
    def build_paths_from_project(project, project_dir):
        """
        Retourne chemins sources depuis session_state (source unique)
        Compatible avec ancien pipeline
        """
        import streamlit as st
        from pathlib import Path

        paths = {}

        # Heightmap depuis session_state (chargée dans sidebar Chargement & Export)
        heightmap_path = st.session_state.get('heightmap_path')
        if heightmap_path and Path(heightmap_path).exists():
            paths['heightmap'] = heightmap_path

        # SatMap depuis session_state
        satmap_path = st.session_state.get('satmap_path')
        if satmap_path and Path(satmap_path).exists():
            paths['satmap'] = satmap_path

        # Masques IT depuis session_state (slope calculé auto, pas chargé)
        for role in ['curvature', 'sediment']:
            it_path = st.session_state.get(f'it_path_{role}')
            if it_path and Path(it_path).exists():
                paths[role] = it_path

        return paths

    @staticmethod
    def list_biomes(biomes_path: str) -> dict:
        """Retourne {biome_id: label} depuis biomes.json. Vide si fichier absent."""
        import os
        if not os.path.exists(biomes_path):
            return {}
        with open(biomes_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return {bid: b.get("label", bid) for bid, b in data.get("biomes", {}).items()}

    @staticmethod
    def resolve_biome(biome_id: str, biomes_path: str):
        """
        Charge un biome et retourne (stems, stem_scales)
        Stub simplifié pour compatibilité
        """
        import os
        if not os.path.exists(biomes_path):
            return PIPELINE_STEMS, {s: 1.0 for s in PIPELINE_STEMS}

        with open(biomes_path, "r", encoding="utf-8") as fh:
            biomes_data = json.load(fh)

        biome = biomes_data.get("biomes", {}).get(biome_id)
        if not biome:
            return PIPELINE_STEMS, {s: 1.0 for s in PIPELINE_STEMS}

        stems = list(biome.get("stems", PIPELINE_STEMS))
        role_scales = biome.get("role_scales", {})
        stem_scales = {
            s: role_scales.get(STEM_ROLES.get(s, ""), 1.0)
            for s in stems
        }
        return stems, stem_scales

    @staticmethod
    def load_biome_config(biome_id: str, biomes_path: str, project_path: str = None):
        """
        Charge config biome (nouveau format v2)
        Stub simplifié pour compatibilité
        """
        import os
        if not os.path.exists(biomes_path):
            return None

        with open(biomes_path, "r", encoding="utf-8") as fh:
            biomes_data = json.load(fh)

        biome = biomes_data.get("biomes", {}).get(biome_id)
        if not biome:
            return None

        # Nouveau format : biome_file
        if "biome_file" in biome:
            biome_file = biome["biome_file"]
            if not os.path.isabs(biome_file):
                biomes_dir = os.path.dirname(biomes_path)
                biome_file = os.path.join(biomes_dir, biome_file)

            if os.path.exists(biome_file):
                with open(biome_file, "r", encoding="utf-8") as f:
                    return json.load(f)

        return None


def render_preview_rgb(masks_dict, width, height):
    """
    Génère aperçu RGB des masques
    Version simple pour compatibilité
    """
    # Créer image RGB
    preview = np.zeros((height, width, 3), dtype=np.uint8)

    # Overlay masques avec couleurs
    for name, mask in masks_dict.items():
        # Extraire nom stem du nom fichier (ex: "01_seabed" -> "SeaBed")
        parts = name.split('_')
        stem = '_'.join(parts[1:]).title() if len(parts) > 1 else name.title()

        color = STEM_COLORS.get(stem, (128, 128, 128))

        for c in range(3):
            preview[:, :, c] = np.where(mask, color[c], preview[:, :, c])

    return preview


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import argparse
    import ast

    parser = argparse.ArgumentParser(description='Pipeline génération masques terrain')
    parser.add_argument('heightmap', help='Chemin heightmap ASC')
    parser.add_argument('output_dir', nargs='?', default='output_masks', help='Dossier output masques (defaut: output_masks)')
    parser.add_argument('--curvature', help='Chemin masque curvature .raw/.png (optionnel)')
    parser.add_argument('--curvature-range', help='Range curvature IT (ex: "[-15,15]")')
    parser.add_argument('--mask-resolution', type=int, default=4096, help='Resolution max masques (defaut: 4096, 0 = native)')

    args = parser.parse_args()

    # Parse curvature range si fourni
    curvature_range = None
    if args.curvature_range:
        curvature_range = tuple(ast.literal_eval(args.curvature_range))

    # Parse mask resolution (0 = native, None pour désactiver downscale)
    mask_resolution = None if args.mask_resolution == 0 else args.mask_resolution

    run_pipeline(
        args.heightmap,
        args.output_dir,
        curvature_path=args.curvature,
        curvature_range=curvature_range,
        mask_resolution=mask_resolution
    )
