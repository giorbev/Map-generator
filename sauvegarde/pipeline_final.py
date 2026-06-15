"""
Pipeline Final — Corrections Prioritaires Post-Test Reforger
=============================================================

CORRECTIONS INTÉGRÉES:
1. Normalisation pixel par pixel (somme <= 1.0)
2. Exclusions zones strictes (sea/coastal/land)
3. Érosion par curvature INVERSÉE (dirt=concave/talwegs, debris=convexe)
4. Vérifications détaillées par zone

ZONES GÉOGRAPHIQUES:
- zone_sea     : altitude < 0                      -> seul seabed actif
- zone_coastal : altitude >= 0 ET distance < 60m   -> seuls coastal_pebbles/grass actifs
- zone_land    : altitude >= 0 ET distance >= 60m  -> pas de seabed ni coastal

Usage:
    python pipeline_final.py <heightmap.asc> <curvature.png> <curv_min> <curv_max> <output_dir>
"""

import numpy as np
from pathlib import Path
from PIL import Image
from scipy.ndimage import gaussian_filter, distance_transform_edt
import sys


# ══════════════════════════════════════════════════════════════════════════════
# UTILITAIRES CHARGEMENT (identiques)
# ══════════════════════════════════════════════════════════════════════════════

def load_asc(asc_path):
    """Charge heightmap ASC format ArcGIS"""
    print(f"[1/9] Chargement heightmap: {asc_path}")

    with open(asc_path, 'r') as f:
        lines = f.readlines()

    meta = {}
    for i in range(6):
        key, value = lines[i].strip().split()
        meta[key.lower()] = float(value) if '.' in value else int(value)

    data_lines = lines[6:]
    heightmap = np.array([
        [float(val) for val in line.split()]
        for line in data_lines if line.strip()
    ])

    nodata = meta.get('nodata_value', -9999)
    heightmap[heightmap == nodata] = np.nan

    print(f"  Resolution: {heightmap.shape[0]}x{heightmap.shape[1]}")
    print(f"  Cellsize: {meta['cellsize']}m/px")
    print(f"  Altitude: {np.nanmin(heightmap):.1f}m -> {np.nanmax(heightmap):.1f}m")

    return heightmap, meta


def load_curvature_mask(curvature_path, curvature_range):
    """Charge masque curvature depuis Instant Terra"""
    print(f"[2/9] Chargement curvature: {curvature_path}")

    curv_path = Path(curvature_path)
    min_curv, max_curv = curvature_range

    if curv_path.suffix == '.raw':
        file_size = curv_path.stat().st_size
        num_pixels = file_size // 2
        width = height = int(np.sqrt(num_pixels))

        try:
            curv = np.fromfile(curv_path, dtype='>u2').reshape((height, width))
        except:
            curv = np.fromfile(curv_path, dtype='<u2').reshape((height, width))

    elif curv_path.suffix == '.png':
        curv = np.array(Image.open(curv_path), dtype=np.uint16)

    else:
        raise ValueError(f"Format non supporte: {curv_path.suffix}")

    curv_decoded = (curv / 65535.0) * (max_curv - min_curv) + min_curv

    print(f"  Resolution: {curv_decoded.shape[0]}x{curv_decoded.shape[1]}")
    print(f"  Range: {min_curv} -> {max_curv}")
    print(f"  Distribution: min={np.min(curv_decoded):.1f}, max={np.max(curv_decoded):.1f}")

    return curv_decoded


def calculate_slope(heightmap, cellsize):
    """Calcule pente en degres depuis heightmap"""
    print("[3/9] Calcul pentes...")

    gy, gx = np.gradient(heightmap, cellsize)
    slope = np.degrees(np.arctan(np.sqrt(gx**2 + gy**2)))

    print(f"  Distribution: min={np.nanmin(slope):.1f}, max={np.nanmax(slope):.1f}, "
          f"mediane={np.nanmedian(slope):.1f}")

    return slope


def auto_calibrate(heightmap, slope, curvature, cellsize, user_params):
    """Auto-calibration seuils (identique)"""
    print("[4/9] Auto-calibration seuils...")

    params = user_params.copy()

    land_mask = (heightmap > 0) & (~np.isnan(heightmap))
    land_alt = heightmap[land_mask]

    if params['coastal_alt_max_m'] is None:
        params['coastal_alt_max_m'] = float(np.percentile(land_alt, 10))
        print(f"  [AUTO] coastal_alt_max_m = {params['coastal_alt_max_m']:.1f}m (P10)")

    if params['grass_low_max_m'] is None:
        params['grass_low_max_m'] = float(np.percentile(land_alt, 30))
        print(f"  [AUTO] grass_low_max_m = {params['grass_low_max_m']:.1f}m (P30)")

    if params['grass_mid_max_m'] is None:
        params['grass_mid_max_m'] = float(np.percentile(land_alt, 66))
        print(f"  [AUTO] grass_mid_max_m = {params['grass_mid_max_m']:.1f}m (P66)")

    if params['grass_high_max_m'] is None:
        params['grass_high_max_m'] = float(np.percentile(land_alt, 80))
        print(f"  [AUTO] grass_high_max_m = {params['grass_high_max_m']:.1f}m (P80)")

    slope_valid = slope[~np.isnan(slope)]

    if params['debris_min_deg'] is None:
        params['debris_min_deg'] = float(np.percentile(slope_valid, 65))
        print(f"  [AUTO] debris_min_deg = {params['debris_min_deg']:.1f} (P65)")

    if params['rock_min_deg'] is None:
        params['rock_min_deg'] = float(np.percentile(slope_valid, 85))
        print(f"  [AUTO] rock_min_deg = {params['rock_min_deg']:.1f} (P85)")

    if params['curvature_radius_m'] is None:
        params['curvature_radius_m'] = cellsize * 5.0
        print(f"  [AUTO] curvature_radius_m = {params['curvature_radius_m']:.1f}m (cellsize x 5)")

    if params['concave_threshold'] is None and curvature is not None:
        curv_valid = curvature[~np.isnan(curvature)]
        params['concave_threshold'] = float(np.percentile(curv_valid, 25))
        print(f"  [AUTO] concave_threshold = {params['concave_threshold']:.2f} (P25)")

    print(f"\n  Parametres finaux:")
    print(f"    Coastal: distance_max=60m (FIXE), alt_max={params['coastal_alt_max_m']:.1f}m")
    print(f"    Grass: low_max={params['grass_low_max_m']:.1f}m, mid_max={params['grass_mid_max_m']:.1f}m, high_max={params['grass_high_max_m']:.1f}m")
    print(f"    Slope: debris_min={params['debris_min_deg']:.1f}, rock_min={params['rock_min_deg']:.1f}")
    print(f"    Feathering: coastal={params['feather_coastal_m']:.0f}m, grass={params['feather_grass_m']:.0f}m, rock={params['feather_rock_m']:.0f}m")

    return params


# ══════════════════════════════════════════════════════════════════════════════
# GÉNÉRATION MASKS AVEC CORRECTIONS PRIORITAIRES
# ══════════════════════════════════════════════════════════════════════════════

def generate_masks_final(heightmap, slope, curvature, params, cellsize):
    """
    Génération masks avec CORRECTIONS PRIORITAIRES intégrées

    1. Définir zones géographiques strictes
    2. Générer masks de base
    3. Appliquer exclusions zones AVANT normalisation
    4. Normaliser pixel par pixel (somme <= 1.0)
    5. Retourner masks + zones pour vérification
    """
    print("[5/9] Generation masques FINAUX (corrections integrees)...")

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
    print("  [ZONES] Definition zones geographiques strictes...")

    # Calcul distance mer
    sea_mask_bool = heightmap < 0
    distance_px = distance_transform_edt(~sea_mask_bool)
    distance_m = distance_px * cellsize

    COASTAL_DISTANCE_FIXED = 60.0  # CORRECTION: fixe à 60m

    # Zone 1: Mer (altitude < 0)
    zone_sea = heightmap < 0

    # Zone 2: Côtière (altitude >= 0 ET distance < 60m)
    zone_coastal = (heightmap >= 0) & (distance_m < COASTAL_DISTANCE_FIXED)

    # Zone 3: Terre (tout le reste)
    zone_land = (heightmap >= 0) & (distance_m >= COASTAL_DISTANCE_FIXED)

    num_sea = np.sum(zone_sea)
    num_coastal = np.sum(zone_coastal)
    num_land = np.sum(zone_land)
    total = zone_sea.size

    print(f"    Zone mer      : {num_sea:8} px ({num_sea/total*100:5.2f}%)")
    print(f"    Zone cotiere  : {num_coastal:8} px ({num_coastal/total*100:5.2f}%)")
    print(f"    Zone terre    : {num_land:8} px ({num_land/total*100:5.2f}%)")

    # ══════════════════════════════════════════════════════════════════════════
    # 01_SEABED (strictement altitude < 0)
    # ══════════════════════════════════════════════════════════════════════════
    print("  [01] seabed (strict altitude < 0)...")

    # CORRECTION: Mask binaire strict (pas de transition douce)
    masks['01_seabed'] = zone_sea.astype(np.float32)

    # ══════════════════════════════════════════════════════════════════════════
    # 02-03 COASTAL (pebbles convexe + grass concave)
    # ══════════════════════════════════════════════════════════════════════════
    print("  [02-03] coastal pebbles + grass...")

    coastal_alt_max = params['coastal_alt_max_m']
    falloff_coastal = params['feather_coastal_m']

    # Mask altitude côtière (transition douce)
    coastal_alt_mask = np.clip(
        1.0 - (heightmap - coastal_alt_max) / falloff_coastal,
        0.0, 1.0
    ).astype(np.float32)

    # Zone côtière complète (sera forcée plus tard)
    coastal_zone = zone_coastal.astype(np.float32) * coastal_alt_mask

    if curvature is not None:
        concave_thresh = params['concave_threshold']
        falloff_curv = 2.0

        curv_factor = np.clip(
            (curvature - concave_thresh) / falloff_curv,
            -1.0, 1.0
        ).astype(np.float32)

        # Pebbles = coastal × convexe
        masks['02_coastal_pebbles'] = coastal_zone * np.clip(curv_factor, 0.0, 1.0)

        # Grass = coastal × concave
        masks['03_coastal_grass'] = coastal_zone * np.clip(-curv_factor, 0.0, 1.0)
    else:
        masks['02_coastal_pebbles'] = coastal_zone * 0.5
        masks['03_coastal_grass'] = coastal_zone * 0.5

    # ══════════════════════════════════════════════════════════════════════════
    # 04-06 GRASS (low/mid/high par altitude)
    # ══════════════════════════════════════════════════════════════════════════
    print("  [04-06] grass low/mid/high...")

    grass_low_max = params['grass_low_max_m']
    grass_mid_max = params['grass_mid_max_m']
    grass_high_max = params['grass_high_max_m']
    falloff_grass = params['feather_grass_m']

    # grass_low : coastal_alt_max -> grass_low_max
    low_bottom = np.clip((heightmap - coastal_alt_max) / falloff_grass, 0.0, 1.0)
    low_top = np.clip(1.0 - (heightmap - grass_low_max) / falloff_grass, 0.0, 1.0)
    masks['04_grass_low'] = (low_bottom * low_top).astype(np.float32)

    # grass_mid : grass_low_max -> grass_mid_max
    mid_bottom = np.clip((heightmap - grass_low_max) / falloff_grass, 0.0, 1.0)
    mid_top = np.clip(1.0 - (heightmap - grass_mid_max) / falloff_grass, 0.0, 1.0)
    masks['05_grass_mid'] = (mid_bottom * mid_top).astype(np.float32)

    # grass_high : grass_mid_max -> grass_high_max
    high_bottom = np.clip((heightmap - grass_mid_max) / falloff_grass, 0.0, 1.0)
    high_top = np.clip(1.0 - (heightmap - grass_high_max) / falloff_grass, 0.0, 1.0)
    masks['06_grass_high'] = (high_bottom * high_top).astype(np.float32)

    # ══════════════════════════════════════════════════════════════════════════
    # 07-08 MOUNTAIN GRASS (au-dessus grass_high_max)
    # ══════════════════════════════════════════════════════════════════════════
    print("  [07-08] mountain grass low/high...")

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

        masks['07_mountain_grass_low'] = mountain_mask * np.clip(-curv_factor, 0.0, 1.0)
        masks['08_mountain_grass_high'] = mountain_mask * np.clip(curv_factor, 0.0, 1.0)
    else:
        masks['07_mountain_grass_low'] = mountain_mask * 0.5
        masks['08_mountain_grass_high'] = mountain_mask * 0.5

    # ══════════════════════════════════════════════════════════════════════════
    # CORRECTION 3: ÉROSION PAR CURVATURE INVERSÉE
    # dirt_erosion  = pente modérée ET CONCAVE (talwegs/creux)
    # debris_rock   = pente modérée ET CONVEXE (accumulation)
    # ══════════════════════════════════════════════════════════════════════════
    print("  [09-10] dirt erosion (CONCAVE/talwegs) + debris rock (CONVEXE)...")

    debris_min = params['debris_min_deg']
    rock_min = params['rock_min_deg']
    falloff_slope = 5.0

    # Mask pente modérée (debris_min -> rock_min)
    erosion_bottom = np.clip((slope - debris_min) / falloff_slope, 0.0, 1.0)
    erosion_top = np.clip(1.0 - (slope - rock_min) / falloff_slope, 0.0, 1.0)
    moderate_slope_mask = (erosion_bottom * erosion_top).astype(np.float32)

    if curvature is not None:
        concave_thresh = params['concave_threshold']
        falloff_curv = 2.0

        curv_factor = np.clip(
            (curvature - concave_thresh) / falloff_curv,
            -1.0, 1.0
        ).astype(np.float32)

        # CORRECTION: dirt_erosion = pente modérée × CONCAVE (talwegs)
        masks['09_dirt_erosion'] = moderate_slope_mask * np.clip(-curv_factor, 0.0, 1.0)

        # CORRECTION: debris_rock = pente modérée × CONVEXE (accumulation)
        masks['10_debris_rock'] = moderate_slope_mask * np.clip(curv_factor, 0.0, 1.0)
    else:
        # Sans curvature : tout dans dirt_erosion
        masks['09_dirt_erosion'] = moderate_slope_mask
        masks['10_debris_rock'] = np.zeros_like(moderate_slope_mask)

    # ══════════════════════════════════════════════════════════════════════════
    # 11 ROCK WALLS (pente forte, toutes curvatures)
    # ══════════════════════════════════════════════════════════════════════════
    print("  [11] rock walls...")

    rock_threshold = rock_min + 5.0

    masks['11_rock_walls'] = np.clip(
        (slope - rock_threshold) / falloff_slope,
        0.0, 1.0
    ).astype(np.float32)

    # ══════════════════════════════════════════════════════════════════════════
    # FEATHERING (lissage gaussien)
    # ══════════════════════════════════════════════════════════════════════════
    print("  [FEATHERING] Lissage gaussien...")

    sigma_coastal_px = params['feather_coastal_m'] / cellsize
    masks['02_coastal_pebbles'] = gaussian_filter(masks['02_coastal_pebbles'], sigma=sigma_coastal_px)
    masks['03_coastal_grass'] = gaussian_filter(masks['03_coastal_grass'], sigma=sigma_coastal_px)

    sigma_grass_px = params['feather_grass_m'] / cellsize
    masks['04_grass_low'] = gaussian_filter(masks['04_grass_low'], sigma=sigma_grass_px)
    masks['05_grass_mid'] = gaussian_filter(masks['05_grass_mid'], sigma=sigma_grass_px)
    masks['06_grass_high'] = gaussian_filter(masks['06_grass_high'], sigma=sigma_grass_px)
    masks['07_mountain_grass_low'] = gaussian_filter(masks['07_mountain_grass_low'], sigma=sigma_grass_px)
    masks['08_mountain_grass_high'] = gaussian_filter(masks['08_mountain_grass_high'], sigma=sigma_grass_px)

    sigma_rock_px = params['feather_rock_m'] / cellsize
    masks['09_dirt_erosion'] = gaussian_filter(masks['09_dirt_erosion'], sigma=sigma_rock_px)
    masks['10_debris_rock'] = gaussian_filter(masks['10_debris_rock'], sigma=sigma_rock_px)
    masks['11_rock_walls'] = gaussian_filter(masks['11_rock_walls'], sigma=sigma_rock_px)

    # ══════════════════════════════════════════════════════════════════════════
    # CORRECTION 2: APPLIQUER EXCLUSIONS ZONES STRICTES
    # ══════════════════════════════════════════════════════════════════════════
    print("  [EXCLUSIONS] Application zones strictes AVANT normalisation...")

    # Zone MER : seul seabed actif, tout le reste = 0
    for name in masks.keys():
        if name != '01_seabed':
            masks[name][zone_sea] = 0.0

    # Zone CÔTIÈRE : seuls coastal_pebbles + coastal_grass actifs, reste = 0
    coastal_only = ['02_coastal_pebbles', '03_coastal_grass']
    for name in masks.keys():
        if name not in coastal_only and name != '01_seabed':
            masks[name][zone_coastal] = 0.0

    # Zone TERRE : pas de seabed ni coastal, reste = 0
    land_excluded = ['01_seabed', '02_coastal_pebbles', '03_coastal_grass']
    for name in land_excluded:
        masks[name][zone_land] = 0.0

    print(f"    [OK] Exclusions appliquees (sea/coastal/land)")

    # ══════════════════════════════════════════════════════════════════════════
    # CORRECTION 1: NORMALISATION pixel par pixel
    # ══════════════════════════════════════════════════════════════════════════
    print("  [NORMALISATION] Somme masks <= 1.0 pixel par pixel...")

    # Exclure seabed de la normalisation (traité séparément)
    terrain_masks = [name for name in masks.keys() if name != '01_seabed']

    # Calculer somme des masks terrain
    sum_terrain = np.zeros(shape, dtype=np.float32)
    for name in terrain_masks:
        sum_terrain += masks[name]

    # Pixels où somme > 1.0
    overflow_mask = sum_terrain > 1.0
    num_overflow = np.sum(overflow_mask)

    if num_overflow > 0:
        print(f"    {num_overflow} pixels avec somme > 1.0 ({num_overflow/sum_terrain.size*100:.2f}%)")
        print(f"    Normalisation en cours...")

        # Normaliser uniquement les pixels overflow
        for name in terrain_masks:
            masks[name][overflow_mask] /= sum_terrain[overflow_mask]

        # Vérifier après normalisation
        sum_after = np.zeros(shape, dtype=np.float32)
        for name in terrain_masks:
            sum_after += masks[name]

        max_sum = np.max(sum_after)
        print(f"    Somme max apres normalisation: {max_sum:.6f}")

        # ASSERT somme <= 1.0
        assert max_sum <= 1.0001, f"ERREUR: somme max = {max_sum} > 1.0"
        print(f"    [OK] Assert somme <= 1.0 valide")
    else:
        print(f"    [OK] Aucun overflow detecte (somme max={np.max(sum_terrain):.6f})")

    # Retourner masks + zones pour vérification
    zones = {
        'sea': zone_sea,
        'coastal': zone_coastal,
        'land': zone_land
    }

    return masks, zones


# ══════════════════════════════════════════════════════════════════════════════
# DÉTECTION TEXTURE BASE
# ══════════════════════════════════════════════════════════════════════════════

def detect_base_texture(masks):
    """Détecte texture base (identique)"""
    print("[6/9] Detection texture de base...")

    candidates = ['04_grass_low', '05_grass_mid', '06_grass_high']
    coverage = {name: np.mean(masks[name]) for name in candidates}

    base_texture = max(coverage, key=coverage.get)

    print(f"  Couverture grass:")
    for name in candidates:
        print(f"    {name}: {coverage[name]*100:.2f}%")
    print(f"  -> Texture de base recommandee : {base_texture}")

    return base_texture


# ══════════════════════════════════════════════════════════════════════════════
# CORRECTION 4: VÉRIFICATION DÉTAILLÉE PAR ZONE
# ══════════════════════════════════════════════════════════════════════════════

def verify_masks_detailed(masks, heightmap, zones):
    """
    Vérification détaillée avec stats par zone

    Vérifie:
    1. Couverture globale + par zone
    2. Exclusions strictes (seabed, grass, coastal)
    3. Somme <= 1.0 partout
    4. Top 5 zones problématiques
    """
    print("[7/9] Verification detaillee POST-CORRECTIONS...")

    valid_mask = ~np.isnan(heightmap)

    # ── COUVERTURE GLOBALE ──
    print(f"\n  Couverture GLOBALE:")
    for name, mask in masks.items():
        coverage_pct = np.mean(mask[valid_mask]) * 100
        mask_valid = mask[valid_mask]
        min_val = np.min(mask_valid)
        max_val = np.max(mask_valid)

        print(f"    {name:30s}: {coverage_pct:5.2f}% (min={min_val:.3f}, max={max_val:.3f})")

    # ── COUVERTURE PAR ZONE ──
    print(f"\n  Couverture PAR ZONE:")

    for zone_name, zone_mask in zones.items():
        print(f"\n  [{zone_name.upper()}] ({np.sum(zone_mask)} px)")

        for name, mask in masks.items():
            coverage_zone = np.mean(mask[zone_mask]) * 100 if np.any(zone_mask) else 0.0
            if coverage_zone > 0.01:  # Afficher seulement si > 0.01%
                print(f"    {name:30s}: {coverage_zone:5.2f}%")

    # ── VÉRIFICATION EXCLUSIONS ──
    print(f"\n  [CHECK] Exclusions zones strictes:")

    # Check 1: Seabed = 0 sur zone côtière
    seabed_coastal = np.sum(masks['01_seabed'][zones['coastal']])
    status1 = "OK" if seabed_coastal == 0 else "ERREUR"
    print(f"    Seabed zone cotiere : {seabed_coastal:.6f} [{status1}]")

    # Check 2: Grass = 0 sur zone côtière
    grass_coastal = np.sum(
        masks['04_grass_low'][zones['coastal']] +
        masks['05_grass_mid'][zones['coastal']] +
        masks['06_grass_high'][zones['coastal']]
    )
    status2 = "OK" if grass_coastal == 0 else "ERREUR"
    print(f"    Grass zone cotiere  : {grass_coastal:.6f} [{status2}]")

    # Check 3: Coastal = 0 sur zone terre
    coastal_land = np.sum(
        masks['02_coastal_pebbles'][zones['land']] +
        masks['03_coastal_grass'][zones['land']]
    )
    status3 = "OK" if coastal_land == 0 else "ERREUR"
    print(f"    Coastal zone terre  : {coastal_land:.6f} [{status3}]")

    # ── VÉRIFICATION SOMME ──
    print(f"\n  [CHECK] Somme masks <= 1.0:")

    terrain_masks = [name for name in masks.keys() if name != '01_seabed']
    sum_terrain = np.zeros(heightmap.shape, dtype=np.float32)
    for name in terrain_masks:
        sum_terrain += masks[name]

    max_sum = np.max(sum_terrain)
    overflow_pixels = np.sum(sum_terrain > 1.0001)

    print(f"    Somme max: {max_sum:.6f}")
    print(f"    Pixels >1.0: {overflow_pixels}")

    status4 = "OK" if overflow_pixels == 0 else "ERREUR"
    print(f"    [{status4}] Somme <= 1.0 {'partout' if overflow_pixels == 0 else 'VIOLATED'}")

    # ── TOP 5 ZONES PROBLÉMATIQUES ──
    print(f"\n  [CHECK] Top 5 zones haute densite (>3 textures):")

    # Compter textures actives par pixel
    tex_count = np.zeros(heightmap.shape, dtype=np.int32)
    threshold_active = 0.01

    for name in terrain_masks:
        tex_count += (masks[name] > threshold_active).astype(np.int32)

    # Trouver pixels >3 textures
    high_density = tex_count > 3
    num_high = np.sum(high_density)

    if num_high > 0:
        print(f"    {num_high} pixels >3 textures ({num_high/tex_count.size*100:.2f}%)")

        # Top 5 par densité
        indices = np.argwhere(high_density)
        densities = tex_count[high_density]
        sorted_idx = np.argsort(densities)[::-1][:5]

        for i, idx in enumerate(sorted_idx, 1):
            y, x = indices[idx]
            density = densities[idx]
            alt = heightmap[y, x]
            print(f"    #{i}: ({x*4}m, {y*4}m) alt={alt:.1f}m -> {density} textures")
    else:
        print(f"    [OK] Aucun pixel >3 textures")

    print(f"\n  [OK] Verification terminee")


# ══════════════════════════════════════════════════════════════════════════════
# EXPORT
# ══════════════════════════════════════════════════════════════════════════════

def export_masks(masks, output_dir):
    """Export masks PNG 16-bit (identique)"""
    print(f"[8/9] Export masques PNG 16-bit: {output_dir}")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for name, mask in masks.items():
        mask_uint16 = (mask * 65535).astype(np.uint16)

        output_path = output_dir / f"{name}.png"
        Image.fromarray(mask_uint16).save(output_path)
        print(f"  [OK] {output_path.name}")

    print(f"  Total: {len(masks)} masques exportes")


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE COMPLET FINAL
# ══════════════════════════════════════════════════════════════════════════════

def run_pipeline_final(heightmap_path, curvature_path, curvature_range, output_dir, user_params=None):
    """Pipeline complet FINAL avec toutes corrections intégrées"""
    print("="*70)
    print("PIPELINE FINAL — Corrections Prioritaires Post-Test Reforger")
    print("="*70)

    if user_params is None:
        user_params = {
            "coastal_alt_max_m": None,
            "grass_low_max_m": None,
            "grass_mid_max_m": None,
            "grass_high_max_m": None,
            "debris_min_deg": 18.0,  # OPTIMISÉ
            "rock_min_deg": 28.0,    # OPTIMISÉ
            "curvature_radius_m": None,
            "concave_threshold": None,
            "feather_coastal_m": 20.0,
            "feather_grass_m": 20.0,  # OPTIMISÉ
            "feather_rock_m": 10.0,
        }

    # 1. Charger heightmap
    heightmap, meta = load_asc(heightmap_path)
    cellsize = meta['cellsize']

    # 2. Calculer slope
    slope = calculate_slope(heightmap, cellsize)

    # 3. Charger curvature
    curvature = None
    if curvature_path is not None:
        curvature = load_curvature_mask(curvature_path, curvature_range)

    # 4. Auto-calibration
    params = auto_calibrate(heightmap, slope, curvature, cellsize, user_params)

    # 5. Générer masques FINAUX avec corrections
    masks, zones = generate_masks_final(heightmap, slope, curvature, params, cellsize)

    # 6. Détecter texture base
    base_texture = detect_base_texture(masks)

    # 7. Vérifier avec détails par zone
    verify_masks_detailed(masks, heightmap, zones)

    # 8. Exporter
    export_masks(masks, output_dir)

    print("\n[9/9] [OK] Pipeline FINAL termine !")
    print("="*70)

    return {
        'params': params,
        'masks': masks,
        'zones': zones,
        'base_texture': base_texture
    }


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Usage:")
        print("  python pipeline_final.py <heightmap.asc> <curvature.png> <curv_min> <curv_max> <output_dir>")
        print("")
        print("Exemple:")
        print('  python pipeline_final.py data/projects/Zimnitrita/sources/temp_Terrain_modified3.asc '
              'data/projects/Zimnitrita/sources/curvature.png -17 17 output_final')
        sys.exit(1)

    heightmap_path = sys.argv[1]
    curvature_path = sys.argv[2]
    curv_min = float(sys.argv[3])
    curv_max = float(sys.argv[4])
    output_dir = sys.argv[5]

    # Paramètres OPTIMISÉS par défaut
    user_params = {
        "coastal_alt_max_m": None,
        "grass_low_max_m": None,
        "grass_mid_max_m": None,
        "grass_high_max_m": None,
        "debris_min_deg": 18.0,
        "rock_min_deg": 28.0,
        "curvature_radius_m": None,
        "concave_threshold": None,
        "feather_coastal_m": 20.0,
        "feather_grass_m": 20.0,
        "feather_rock_m": 10.0,
    }

    run_pipeline_final(
        heightmap_path,
        curvature_path,
        (curv_min, curv_max),
        output_dir,
        user_params
    )
