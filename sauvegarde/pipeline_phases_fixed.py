"""
Pipeline Phases CORRIGÉ — Après test Reforger
==============================================

Corrections appliquées:
1. SEABED : strictement altitude < 0, exclusion avec coastal
2. COASTAL : réduit à 60m, exclusion grass_low/mid/high
3. ÉROSION : utilise curvature (dirt_erosion = convexe, debris_rock = concave)
4. NORMALISATION : somme masks <= 1.0 par pixel
5. VÉRIFICATION : seabed absent côtier, max 3 tex coastal

Usage:
    python pipeline_phases_fixed.py <heightmap.asc> <curvature.raw> <curv_min> <curv_max> <output_dir>
"""

import numpy as np
from pathlib import Path
from PIL import Image
from scipy.ndimage import gaussian_filter, distance_transform_edt
import sys


# Copie des fonctions load_asc, load_curvature_mask, calculate_slope
# (identiques à pipeline_phases.py)

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
    """Auto-calibration seuils (identique à version précédente)"""
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
    print(f"    Coastal: distance_max={params['coastal_distance_max_m']:.0f}m, alt_max={params['coastal_alt_max_m']:.1f}m")
    print(f"    Grass: low_max={params['grass_low_max_m']:.1f}m, mid_max={params['grass_mid_max_m']:.1f}m, high_max={params['grass_high_max_m']:.1f}m")
    print(f"    Slope: debris_min={params['debris_min_deg']:.1f}, rock_min={params['rock_min_deg']:.1f}")
    print(f"    Feathering: coastal={params['feather_coastal_m']:.0f}m, grass={params['feather_grass_m']:.0f}m, rock={params['feather_rock_m']:.0f}m")

    return params


def generate_continuous_masks_fixed(heightmap, slope, curvature, params, cellsize):
    """
    GÉNÉRATION MASKS CORRIGÉS POST-TEST REFORGER

    Corrections:
    1. Seabed strictement < 0 + exclusion coastal
    2. Coastal 60m + exclusion grass
    3. Érosion + curvature (dirt=convexe, debris=concave)
    4. Normalisation finale somme <= 1.0
    """
    print("[5/9] Generation masques continus CORRIGES...")

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
    # CORRECTION 1 : SEABED strictement altitude < 0
    # ══════════════════════════════════════════════════════════════════════════
    print("  [01] seabed (strictement < 0)...")

    # Mask binaire strict : altitude < 0
    seabed_strict = heightmap < 0

    # Pas de transition douce pour seabed
    masks['01_seabed'] = seabed_strict.astype(np.float32)

    # ══════════════════════════════════════════════════════════════════════════
    # CORRECTION 2 : DISTANCE MER + COASTAL réduit à 60m
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

    # Coastal global = intersection distance ET altitude ET terre émergée (pas seabed)
    coastal_zone = coastal_distance_mask * coastal_alt_mask * (~seabed_strict).astype(np.float32)

    # ══════════════════════════════════════════════════════════════════════════
    # 02_COASTAL_PEBBLES (convexe) + 03_COASTAL_GRASS (concave)
    # ══════════════════════════════════════════════════════════════════════════
    print("  [02-03] coastal pebbles + grass (exclusion seabed)...")

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
    # CORRECTION 2 : GRASS_LOW/MID/HIGH — exclusion zone coastal
    # ══════════════════════════════════════════════════════════════════════════
    print("  [04-06] grass low/mid/high (exclusion coastal)...")

    grass_low_max = params['grass_low_max_m']
    grass_mid_max = params['grass_mid_max_m']
    grass_high_max = params['grass_high_max_m']
    falloff_grass = params['feather_grass_m']

    # Mask exclusion coastal (distance > coastal_distance_max)
    non_coastal_mask = (distance_m > coastal_distance_max).astype(np.float32)

    # grass_low : coastal_alt_max -> grass_low_max, HORS zone coastal
    low_bottom = np.clip(
        (heightmap - coastal_alt_max) / falloff_grass,
        0.0, 1.0
    )
    low_top = np.clip(
        1.0 - (heightmap - grass_low_max) / falloff_grass,
        0.0, 1.0
    )
    masks['04_grass_low'] = (low_bottom * low_top * non_coastal_mask).astype(np.float32)

    # grass_mid : grass_low_max -> grass_mid_max, HORS zone coastal
    mid_bottom = np.clip(
        (heightmap - grass_low_max) / falloff_grass,
        0.0, 1.0
    )
    mid_top = np.clip(
        1.0 - (heightmap - grass_mid_max) / falloff_grass,
        0.0, 1.0
    )
    masks['05_grass_mid'] = (mid_bottom * mid_top * non_coastal_mask).astype(np.float32)

    # grass_high : grass_mid_max -> grass_high_max, HORS zone coastal
    high_bottom = np.clip(
        (heightmap - grass_mid_max) / falloff_grass,
        0.0, 1.0
    )
    high_top = np.clip(
        1.0 - (heightmap - grass_high_max) / falloff_grass,
        0.0, 1.0
    )
    masks['06_grass_high'] = (high_bottom * high_top * non_coastal_mask).astype(np.float32)

    # ══════════════════════════════════════════════════════════════════════════
    # 07_MOUNTAIN_GRASS_LOW + 08_MOUNTAIN_GRASS_HIGH (au-dessus grass_high_max)
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
    # CORRECTION 3 : ÉROSION utilise CURVATURE
    # dirt_erosion = pente modérée ET convexe (érosion active)
    # debris_rock = pente modérée ET concave (accumulation débris)
    # ══════════════════════════════════════════════════════════════════════════
    print("  [09-10] dirt erosion + debris rock (avec curvature)...")

    debris_min = params['debris_min_deg']
    rock_min = params['rock_min_deg']
    falloff_slope = 5.0

    # Mask pente modérée (debris_min -> rock_min)
    erosion_bottom = np.clip(
        (slope - debris_min) / falloff_slope,
        0.0, 1.0
    )
    erosion_top = np.clip(
        1.0 - (slope - rock_min) / falloff_slope,
        0.0, 1.0
    )
    moderate_slope_mask = (erosion_bottom * erosion_top).astype(np.float32)

    if curvature is not None:
        concave_thresh = params['concave_threshold']
        falloff_curv = 2.0

        curv_factor = np.clip(
            (curvature - concave_thresh) / falloff_curv,
            -1.0, 1.0
        ).astype(np.float32)

        # dirt_erosion = pente modérée × convexe (érosion active)
        masks['09_dirt_erosion'] = moderate_slope_mask * np.clip(curv_factor, 0.0, 1.0)

        # debris_rock = pente modérée × concave (accumulation débris)
        masks['10_debris_rock'] = moderate_slope_mask * np.clip(-curv_factor, 0.0, 1.0)
    else:
        # Sans curvature : tout dans dirt_erosion
        masks['09_dirt_erosion'] = moderate_slope_mask
        masks['10_debris_rock'] = np.zeros_like(moderate_slope_mask)

    # ══════════════════════════════════════════════════════════════════════════
    # 11_ROCK_WALLS (pente très forte)
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
    # CORRECTION 4 : NORMALISATION — somme <= 1.0 par pixel
    # ══════════════════════════════════════════════════════════════════════════
    print("  [NORMALISATION] Somme masks <= 1.0 par pixel...")

    # Exclure seabed de la normalisation (traitement séparé)
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
    else:
        print(f"    [OK] Aucun overflow detecte (somme max={np.max(sum_terrain):.6f})")

    # ══════════════════════════════════════════════════════════════════════════
    # CORRECTION 1 : FORCER seabed = 0 si coastal > 0
    # ══════════════════════════════════════════════════════════════════════════
    print("  [SEABED] Exclusion zone cotiere...")

    coastal_total = masks['02_coastal_pebbles'] + masks['03_coastal_grass']
    seabed_coastal_conflict = (masks['01_seabed'] > 0) & (coastal_total > 0)
    num_conflicts = np.sum(seabed_coastal_conflict)

    if num_conflicts > 0:
        print(f"    {num_conflicts} pixels seabed/coastal conflict detectes")
        print(f"    Forcer seabed = 0 dans zone coastal...")
        masks['01_seabed'][seabed_coastal_conflict] = 0.0

    return masks


def detect_base_texture(masks):
    """Détecte texture de base (identique)"""
    print("[6/9] Detection texture de base...")

    candidates = ['04_grass_low', '05_grass_mid', '06_grass_high']
    coverage = {name: np.mean(masks[name]) for name in candidates}

    base_texture = max(coverage, key=coverage.get)

    print(f"  Couverture grass:")
    for name in candidates:
        print(f"    {name}: {coverage[name]*100:.2f}%")
    print(f"  -> Texture de base recommandee : {base_texture}")

    return base_texture


def verify_masks_fixed(masks, heightmap, params):
    """
    VÉRIFICATION POST-CORRECTIONS

    Vérifie:
    1. Seabed absent zone côtière
    2. Max 3 textures zone côtière
    3. dirt_erosion + debris_rock bien subdivisés
    4. Somme <= 1.0 partout
    """
    print("[7/9] Verification finale POST-CORRECTIONS...")

    valid_mask = ~np.isnan(heightmap)

    print(f"\n  Couverture par mask:")
    for name, mask in masks.items():
        coverage_pct = np.mean(mask[valid_mask]) * 100
        mask_valid = mask[valid_mask]
        min_val = np.min(mask_valid)
        max_val = np.max(mask_valid)
        mean_val = np.mean(mask_valid)

        print(f"    {name:30s}: couv={coverage_pct:5.2f}%, min={min_val:.3f}, max={max_val:.3f}, moy={mean_val:.3f}")

    # ── VÉRIFICATION 1 : Seabed absent zone côtière ──
    print(f"\n  [CHECK 1] Seabed absent zone cotiere...")

    coastal_total = masks['02_coastal_pebbles'] + masks['03_coastal_grass']
    seabed_coastal = (masks['01_seabed'] > 0) & (coastal_total > 0)
    num_conflicts = np.sum(seabed_coastal)

    if num_conflicts == 0:
        print(f"    [OK] Aucun conflit seabed/coastal")
    else:
        print(f"    [WARNING] {num_conflicts} pixels seabed/coastal detectes !")

    # ── VÉRIFICATION 2 : Max 3 textures zone côtière ──
    print(f"\n  [CHECK 2] Max textures zone cotiere...")

    # Définir zone côtière (distance < coastal_distance_max + altitude < coastal_alt_max)
    sea_mask = heightmap <= 0
    distance_px = distance_transform_edt(~sea_mask)
    distance_m = distance_px * params['cellsize']

    coastal_zone_mask = (distance_m < params['coastal_distance_max_m']) & (heightmap < params['coastal_alt_max_m'])

    # Compter textures actives par pixel dans zone côtière
    coastal_tex_count = np.zeros(heightmap.shape, dtype=np.int32)
    for name in ['02_coastal_pebbles', '03_coastal_grass', '04_grass_low', '05_grass_mid', '06_grass_high']:
        coastal_tex_count[coastal_zone_mask] += (masks[name][coastal_zone_mask] > 0.01).astype(np.int32)

    max_coastal_tex = np.max(coastal_tex_count) if np.any(coastal_zone_mask) else 0
    print(f"    Max textures zone cotiere: {max_coastal_tex}")

    if max_coastal_tex <= 3:
        print(f"    [OK] Zone cotiere <= 3 textures")
    else:
        num_exceed = np.sum(coastal_tex_count > 3)
        print(f"    [WARNING] {num_exceed} pixels zone cotiere >3 textures !")

    # ── VÉRIFICATION 3 : dirt_erosion + debris_rock subdivisés ──
    print(f"\n  [CHECK 3] Subdivision erosion/debris...")

    dirt_coverage = np.mean(masks['09_dirt_erosion'])
    debris_coverage = np.mean(masks['10_debris_rock'])
    ratio = dirt_coverage / (debris_coverage + 1e-9)

    print(f"    dirt_erosion: {dirt_coverage*100:.2f}%")
    print(f"    debris_rock: {debris_coverage*100:.2f}%")
    print(f"    Ratio: {ratio:.2f}:1")

    if debris_coverage > 0.01:
        print(f"    [OK] Subdivision erosion/debris active")
    else:
        print(f"    [WARNING] debris_rock quasi-nul (curvature non utilisee ?)")

    # ── VÉRIFICATION 4 : Somme <= 1.0 ──
    print(f"\n  [CHECK 4] Somme masks <= 1.0...")

    terrain_masks = [name for name in masks.keys() if name != '01_seabed']
    sum_terrain = np.zeros(heightmap.shape, dtype=np.float32)
    for name in terrain_masks:
        sum_terrain += masks[name]

    max_sum = np.max(sum_terrain)
    overflow_pixels = np.sum(sum_terrain > 1.0001)  # tolérance arrondi

    print(f"    Somme max: {max_sum:.6f}")
    print(f"    Pixels >1.0: {overflow_pixels}")

    if overflow_pixels == 0:
        print(f"    [OK] Somme <= 1.0 partout")
    else:
        print(f"    [WARNING] {overflow_pixels} pixels somme >1.0 !")

    print(f"\n  [OK] Verification terminee")


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


def run_pipeline_fixed(heightmap_path, curvature_path, curvature_range, output_dir, user_params=None):
    """Pipeline complet CORRIGÉ post-test Reforger"""
    print("="*70)
    print("PIPELINE CORRIGE POST-TEST REFORGER")
    print("="*70)

    if user_params is None:
        user_params = {
            "coastal_distance_max_m": 60.0,  # CORRIGÉ: réduit de 100m
            "coastal_alt_max_m": None,
            "grass_low_max_m": None,
            "grass_mid_max_m": None,
            "grass_high_max_m": None,
            "debris_min_deg": None,
            "rock_min_deg": None,
            "curvature_radius_m": None,
            "concave_threshold": None,
            "feather_coastal_m": 20.0,
            "feather_grass_m": 20.0,
            "feather_rock_m": 10.0,
        }

    # 1. Charger heightmap
    heightmap, meta = load_asc(heightmap_path)
    cellsize = meta['cellsize']

    # Ajouter cellsize aux params pour vérifications
    user_params['cellsize'] = cellsize

    # 2. Calculer slope
    slope = calculate_slope(heightmap, cellsize)

    # 3. Charger curvature
    curvature = None
    if curvature_path is not None:
        curvature = load_curvature_mask(curvature_path, curvature_range)

    # 4. Auto-calibration
    params = auto_calibrate(heightmap, slope, curvature, cellsize, user_params)

    # 5. Générer masques CORRIGÉS
    masks = generate_continuous_masks_fixed(heightmap, slope, curvature, params, cellsize)

    # 6. Détecter texture base
    base_texture = detect_base_texture(masks)

    # 7. Vérifier POST-CORRECTIONS
    verify_masks_fixed(masks, heightmap, params)

    # 8. Exporter
    export_masks(masks, output_dir)

    print("\n[9/9] [OK] Pipeline termine !")
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
        print("  python pipeline_phases_fixed.py <heightmap.asc> <curvature.raw> <curv_min> <curv_max> <output_dir>")
        print("")
        print("Exemple:")
        print('  python pipeline_phases_fixed.py data/projects/Zimnitrita/sources/temp_Terrain_modified3.asc '
              'data/projects/Zimnitrita/sources/curvature.png -17 17 output_fixed')
        sys.exit(1)

    heightmap_path = sys.argv[1]
    curvature_path = sys.argv[2]
    curv_min = float(sys.argv[3])
    curv_max = float(sys.argv[4])
    output_dir = sys.argv[5]

    # Paramètres OPTIMISÉS + CORRIGÉS
    user_params = {
        "coastal_distance_max_m": 60.0,  # CORRIGÉ: 60m au lieu de 100m
        "coastal_alt_max_m": None,
        "grass_low_max_m": None,
        "grass_mid_max_m": None,
        "grass_high_max_m": None,
        "debris_min_deg": 18.0,          # OPTIMISÉ
        "rock_min_deg": 28.0,            # OPTIMISÉ
        "curvature_radius_m": None,
        "concave_threshold": None,
        "feather_coastal_m": 20.0,
        "feather_grass_m": 20.0,         # OPTIMISÉ
        "feather_rock_m": 10.0,
    }

    run_pipeline_fixed(
        heightmap_path,
        curvature_path,
        (curv_min, curv_max),
        output_dir,
        user_params
    )
