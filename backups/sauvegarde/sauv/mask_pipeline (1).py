#!/usr/bin/env python3
"""
mask_pipeline.py - Pipeline unifié de génération de masques terrain
pour Arma Reforger / Enfusion (Zimnitrita)

Génère des masques PNG 16 bits mutuellement exclusifs avec :
  - Hiérarchie de priorité stricte (budget décroissant)
  - Transitions étroites (2-3°) entre zones adjacentes
  - Worley noise pour les bords organiques
  - Masque côtier (distance + altitude + pente douce)
  - 16 types de végétation depuis vegetation_map.py
  - Signaux terrain depuis pipeline_v2.py

Usage:
    python mask_pipeline.py
"""

import sys
import numpy as np
import cv2
from pathlib import Path
from scipy.ndimage import gaussian_filter
from scipy.spatial import cKDTree

# ============================================================================
# CONFIG
# ============================================================================

SCRIPTS_DIR = Path(r"H:\logiciel perso\Map generator\scripts")
sys.path.insert(0, str(SCRIPTS_DIR))

ASC_PATH        = Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\sources\Terrain_modified5.asc")
EXCLUSION_MASK  = Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\masks\masque exclusion.png")
OUTPUT_DIR      = Path(r"H:\logiciel perso\Map generator\masks_output")
SATMAP_PATH     = Path(r"H:\logiciel perso\Map generator\satmap_v2_textured_4097__13_.png")
OUTPUT_SIZE     = 4097

# Masques Gaea
GAEA_FLOW    = Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\masks\flow.png")
GAEA_DEPOSIT = Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\masks\deposit.png")

# Seuils pente (None = auto percentiles)
THRESHOLD_GENTLE = None
THRESHOLD_LANDES = None
THRESHOLD_ROCK   = None
THRESHOLD_CLIFF  = None

# Transitions étroites
TRANS_SLOPE = 2.5   # degrés
TRANS_DIST  = 25.0  # mètres

# Masque côtier
COASTAL_ALT_MAX   = 15.0
COASTAL_DIST_MAX  = 100.0
COASTAL_SLOPE_MAX = 8.0

# Worley noise
NOISE_SCALE     = 0.003
NOISE_AMPLITUDE = 0.18
NOISE_SEED      = 42

# TPI rayons
TPI_LOCAL_M = 200
TPI_MACRO_M = 1500

# ============================================================================
# IMPORTS PIPELINE
# ============================================================================

def import_pipeline_functions():
    """Importe les fonctions depuis pipeline_v2.py et vegetation_map.py."""
    try:
        from pipeline_v2 import (
            load_asc,
            calculate_slope,
            calculate_aspect,
            calculate_curvature_zt,
            calculate_tpi,
            calculate_flow_accumulation,
            calculate_coastal_distance,
            fill_depressions,
        )
        print("[IMPORT] pipeline_v2.py ✅")
    except ImportError as e:
        print(f"[WARN] pipeline_v2.py non disponible: {e}")
        load_asc = calculate_slope = calculate_aspect = None
        calculate_curvature_zt = calculate_tpi = None
        calculate_flow_accumulation = calculate_coastal_distance = None
        fill_depressions = None

    try:
        from vegetation_map import compute_vegetation_scores
        print("[IMPORT] vegetation_map.py ✅")
    except ImportError as e:
        print(f"[WARN] vegetation_map.py non disponible: {e}")
        compute_vegetation_scores = None

    return {
        'load_asc': load_asc,
        'calculate_slope': calculate_slope,
        'calculate_aspect': calculate_aspect,
        'calculate_curvature_zt': calculate_curvature_zt,
        'calculate_tpi': calculate_tpi,
        'calculate_flow_accumulation': calculate_flow_accumulation,
        'calculate_coastal_distance': calculate_coastal_distance,
        'fill_depressions': fill_depressions,
        'compute_vegetation_scores': compute_vegetation_scores,
    }

# ============================================================================
# FALLBACK ASC READER (si pipeline_v2 non dispo)
# ============================================================================

def read_asc_fallback(path: Path) -> tuple:
    print(f"[ASC] Lecture {path.name}...")
    with open(path, 'r') as f:
        ncols    = int(f.readline().split()[1])
        nrows    = int(f.readline().split()[1])
        xll      = float(f.readline().split()[1])
        yll      = float(f.readline().split()[1])
        cellsize = float(f.readline().split()[1])
        nodata   = float(f.readline().split()[1])
        data = [float(x) for line in f for x in line.split()]
    dem = np.array(data, dtype=np.float32).reshape(nrows, ncols)
    dem[dem == nodata] = np.nan
    print(f"  → {ncols}×{nrows}, cellsize={cellsize}m")
    return dem, cellsize, nodata

# ============================================================================
# SEUILS AUTOMATIQUES
# ============================================================================

def compute_thresholds(slope: np.ndarray) -> dict:
    global THRESHOLD_GENTLE, THRESHOLD_LANDES, THRESHOLD_ROCK, THRESHOLD_CLIFF
    p = {pct: round(float(np.nanpercentile(slope, pct)), 1) for pct in [70, 85, 90, 95]}
    if THRESHOLD_GENTLE is None: THRESHOLD_GENTLE = p[70]
    if THRESHOLD_LANDES is None: THRESHOLD_LANDES = p[85]
    if THRESHOLD_ROCK   is None: THRESHOLD_ROCK   = p[90]
    if THRESHOLD_CLIFF  is None: THRESHOLD_CLIFF  = p[95]
    t = dict(gentle=THRESHOLD_GENTLE, landes=THRESHOLD_LANDES,
             rock=THRESHOLD_ROCK, cliff=THRESHOLD_CLIFF)
    print(f"[SEUILS] gentle={t['gentle']}° landes={t['landes']}° "
          f"rock={t['rock']}° cliff={t['cliff']}°")
    return t

# ============================================================================
# WORLEY NOISE
# ============================================================================

def worley_noise_2d(shape: tuple, scale: float, seed: int = 42) -> np.ndarray:
    print(f"[NOISE] Worley noise ({shape[0]}×{shape[1]})...")
    rng = np.random.default_rng(seed)
    H, W = shape
    n_points = min(max(200, int(H * W * scale * scale * 4)), 5000)
    pts = rng.random((n_points, 2))
    pts[:, 0] *= H
    pts[:, 1] *= W
    tree = cKDTree(pts)
    yy, xx = np.mgrid[0:H, 0:W]
    coords = np.column_stack([yy.ravel(), xx.ravel()])
    dists, _ = tree.query(coords, k=1)
    dists = dists.reshape(H, W).astype(np.float32)
    dists = (dists - dists.min()) / (dists.max() - dists.min() + 1e-6)
    print(f"  → {n_points} points générés")
    return dists

# ============================================================================
# UTILITAIRES
# ============================================================================

def load_mask(path: Path, out_size: int) -> np.ndarray:
    raw = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if raw is None:
        return np.zeros((out_size, out_size), dtype=np.float32)
    if raw.ndim == 3:
        raw = cv2.cvtColor(raw, cv2.COLOR_BGR2GRAY)
    if raw.dtype == np.uint8:
        m = raw.astype(np.float32) / 255.0
    elif raw.dtype == np.uint16:
        m = raw.astype(np.float32) / 65535.0
    else:
        m = raw.astype(np.float32)
        m = np.clip(m / max(m.max(), 1.0), 0, 1)
    if m.shape[0] != out_size or m.shape[1] != out_size:
        m = cv2.resize(m, (out_size, out_size), interpolation=cv2.INTER_LINEAR)
    return np.clip(m, 0, 1)

def save_16bit(mask: np.ndarray, path: Path):
    out = (np.clip(mask, 0, 1) * 65535).astype(np.uint16)
    cv2.imwrite(str(path), out)

def resize_to(arr: np.ndarray, size: int) -> np.ndarray:
    if arr is None: return None
    if arr.shape[0] == size and arr.shape[1] == size:
        return arr.astype(np.float32)
    return cv2.resize(arr.astype(np.float32), (size, size),
                      interpolation=cv2.INTER_LINEAR)

def smooth_ramp(arr: np.ndarray, lo: float, hi: float) -> np.ndarray:
    out = np.zeros_like(arr, dtype=np.float32)
    in_range = (arr > lo) & (arr < hi)
    out[in_range] = (arr[in_range] - lo) / (hi - lo)
    out[arr >= hi] = 1.0
    return out

def apply_noise(mask: np.ndarray, noise: np.ndarray, amplitude: float) -> np.ndarray:
    edge = 1.0 - np.abs(mask * 2 - 1)
    perturb = (noise - 0.5) * amplitude * edge
    return np.clip(mask + perturb, 0, 1)

def take_from_budget(raw: np.ndarray, budget: np.ndarray) -> tuple:
    """Prend ce qui est disponible dans le budget, retourne (mask, budget_restant)."""
    taken = np.minimum(raw, budget)
    return taken, np.clip(budget - taken, 0, 1)

# ============================================================================
# GÉNÉRATION DES MASQUES
# ============================================================================

def generate_all_masks(signals: dict, t: dict, exclusion: np.ndarray,
                       noise: np.ndarray, fns: dict, out_size: int) -> dict:
    """
    Génère tous les masques avec budget décroissant (priorité stricte).
    Chaque masque ne peut prendre que ce que les masques supérieurs n'ont pas pris.
    """
    T = TRANS_SLOPE

    # Signaux redimensionnés
    slope   = resize_to(signals['slope'], out_size)
    dem     = resize_to(signals['dem'], out_size)
    dist    = resize_to(signals['dist_coast'], out_size)
    flow    = resize_to(signals.get('flow'), out_size)
    deposit = resize_to(signals.get('deposit'), out_size)
    aspect  = resize_to(signals.get('aspect'), out_size)
    curv    = resize_to(signals.get('curvature'), out_size)
    tpi_l   = resize_to(signals.get('tpi_local'), out_size)
    tpi_m   = resize_to(signals.get('tpi_macro'), out_size)
    flow_n  = resize_to(signals.get('flow_norm'), out_size)

    # Budget global
    budget = np.ones((out_size, out_size), dtype=np.float32)
    budget[exclusion == 0] = 0.0
    budget[np.isnan(dem)] = 0.0

    masks = {}

    # ── 1. SEABED ─────────────────────────────────────────────────────────
    print("  [1/8] Seabed...")
    water    = (dem < 0) | np.isnan(dem)
    seabed   = np.where(water, 1.0, 0.0).astype(np.float32)
    near_sfc = (dem >= -3) & (dem < 0)
    seabed[near_sfc] = smooth_ramp(-dem[near_sfc], 0, 3)
    seabed, budget = take_from_budget(seabed, budget)
    masks['seabed'] = seabed

    # ── 2. COASTAL ────────────────────────────────────────────────────────
    print("  [2/8] Coastal...")
    d_factor = smooth_ramp(COASTAL_DIST_MAX - dist, 0, COASTAL_DIST_MAX)
    a_factor = smooth_ramp(COASTAL_ALT_MAX  - dem,  0, COASTAL_ALT_MAX)
    s_factor = smooth_ramp(COASTAL_SLOPE_MAX - slope, 0, COASTAL_SLOPE_MAX)
    coastal_raw = d_factor * a_factor * s_factor
    coastal_raw = apply_noise(coastal_raw, noise, NOISE_AMPLITUDE * 0.5)
    coastal_raw = gaussian_filter(coastal_raw, sigma=2.0)
    coastal, budget = take_from_budget(coastal_raw, budget)
    masks['coastal'] = coastal

    # ── 3. ROCK ───────────────────────────────────────────────────────────
    print("  [3/8] Rock...")
    rock_start = t['rock'] + T / 2
    rock_raw   = smooth_ramp(slope, rock_start, t['cliff'])
    rock_raw   = apply_noise(rock_raw, noise, NOISE_AMPLITUDE * 0.3)
    rock, budget = take_from_budget(rock_raw, budget)
    masks['rock'] = rock

    # ── 4. LANDES ROCHEUSES ───────────────────────────────────────────────
    print("  [4/8] Landes rocheuses...")
    landes_end = t['rock'] - T / 2
    landes_raw = smooth_ramp(slope, t['gentle'], t['landes'])
    fall_mask  = slope > landes_end
    fall_val   = 1.0 - smooth_ramp(slope, landes_end, t['rock'] + T / 2)
    landes_raw = np.where(fall_mask, landes_raw * fall_val, landes_raw)
    landes_raw = apply_noise(landes_raw, noise, NOISE_AMPLITUDE * 0.4)
    landes, budget = take_from_budget(landes_raw, budget)
    masks['landes_rocheuses'] = landes

    # ── 5. FLOW ───────────────────────────────────────────────────────────
    print("  [5/8] Flow...")
    if flow is not None:
        flow_s = gaussian_filter(flow, sigma=1.5)
        flow_s = apply_noise(flow_s, noise, NOISE_AMPLITUDE * 0.6)
        flow_m, budget = take_from_budget(flow_s, budget)
    else:
        flow_m = np.zeros((out_size, out_size), dtype=np.float32)
    masks['flow'] = flow_m

    # ── 6. DEPOSIT ────────────────────────────────────────────────────────
    print("  [6/8] Deposit...")
    if deposit is not None:
        dep_s = gaussian_filter(deposit, sigma=1.5)
        dep_s = apply_noise(dep_s, noise, NOISE_AMPLITUDE * 0.6)
        dep_m, budget = take_from_budget(dep_s, budget)
    else:
        dep_m = np.zeros((out_size, out_size), dtype=np.float32)
    masks['deposit'] = dep_m

    # ── 7. VÉGÉTATION ─────────────────────────────────────────────────────
    print("  [7/8] Végétation (16 types)...")
    compute_veg = fns.get('compute_vegetation_scores')
    if compute_veg is not None and tpi_l is not None:
        # Préparer les paramètres pour vegetation_map
        params = {
            'grass_low_max_m': 40,
            'grass_mid_max_m': 100,
            'grass_high_max_m': 170,
            'debris_min_deg': t['gentle'],
            'rock_min_deg': t['rock'],
            'coastal_alt_max_m': COASTAL_ALT_MAX,
            'coastal_distance_max_m': COASTAL_DIST_MAX,
        }
        dem_small = dem
        cellsize_approx = 16384 / out_size  # estimation

        veg_scores = compute_veg(
            heightmap=dem_small,
            slope=slope,
            curvature=curv if curv is not None else np.zeros_like(slope),
            tpi_local=tpi_l,
            tpi_macro=tpi_m if tpi_m is not None else np.zeros_like(slope),
            flow=flow_n if flow_n is not None else np.zeros_like(slope),
            aspect=aspect if aspect is not None else np.zeros_like(slope),
            distance_cote=dist,
            params=params,
            cellsize=cellsize_approx,
        )

        # Appliquer les scores de végétation dans le budget restant
        # Winner-takes-all puis allocation proportionnelle
        veg_types = list(veg_scores.keys())
        veg_arrays = [resize_to(veg_scores[k], out_size) for k in veg_types]

        # Stack des scores
        stack = np.stack(veg_arrays, axis=0)  # (N, H, W)
        stack = np.clip(stack, 0, 1)

        # Normaliser pour que la somme ≤ 1
        total = stack.sum(axis=0) + 1e-6
        stack_norm = stack / np.maximum(total, 1.0)

        # Chaque type prend sa part du budget restant
        for i, veg_type in enumerate(veg_types):
            veg_raw = stack_norm[i] * budget
            veg_raw = apply_noise(veg_raw, noise, NOISE_AMPLITUDE * 0.7)
            veg_raw = gaussian_filter(veg_raw, sigma=1.0)
            veg_taken, budget = take_from_budget(veg_raw, budget)
            masks[veg_type] = veg_taken
    else:
        print("    [SKIP] vegetation_map.py non disponible ou TPI manquant")

    # ── 8. GRASS DEFAULT ──────────────────────────────────────────────────
    print("  [8/8] Grass default (budget restant)...")
    grass_raw = apply_noise(budget.copy(), noise, NOISE_AMPLITUDE * 0.5)
    grass = np.clip(grass_raw, 0, 1)
    masks['grass_default'] = grass

    return masks

# ============================================================================
# VALIDATION VISUELLE
# ============================================================================

def generate_validation_map(masks: dict, out_size: int, output_dir: Path):
    print("\n[VIZ] Génération carte de validation...")

    if SATMAP_PATH.exists():
        result = cv2.imread(str(SATMAP_PATH)).astype(np.float32)
        if result.shape[0] != out_size:
            result = cv2.resize(result, (out_size, out_size))
    else:
        result = np.full((out_size, out_size, 3), 40, dtype=np.float32)

    # Couleurs BGR par masque (les plus importants)
    colors = {
        'seabed':              (180, 80,  0),
        'coastal':             (220, 200, 0),
        'rock':                (0,   0,   220),
        'landes_rocheuses':    (0,   130, 220),
        'flow':                (255, 210, 0),
        'deposit':             (0,   165, 255),
        'foret_feuillue':      (0,   90,  0),
        'foret_coniferes':     (0,   60,  40),
        'maquis_landes':       (60,  90,  120),
        'landes_plateau':      (70,  110, 140),
        'prairie_humide':      (50,  180, 80),
        'prairie_seche':       (80,  160, 180),
        'prairie_plateau':     (90,  190, 180),
        'alpages':             (120, 210, 200),
        'ripisylve':           (100, 200, 140),
        'roseaux_marais':      (90,  160, 120),
        'veg_rupestre':        (130, 150, 140),
        'haies_lisieres':      (60,  140, 100),
    }
    alphas = {k: 0.65 for k in colors}
    alphas['grass_default'] = 0.0

    for name, mask in masks.items():
        if name not in colors:
            continue
        alpha = alphas.get(name, 0.5) * mask
        color = colors[name]
        for c, col in enumerate(color):
            result[:,:,c] = result[:,:,c] * (1-alpha) + col * alpha

    # Grille tiles
    tile_pix = out_size // 32
    for i in range(33):
        p = i * tile_pix
        if p < out_size:
            result[p,:,:] = result[p,:,:] * 0.4 + 160 * 0.6
            result[:,p,:] = result[:,p,:] * 0.4 + 160 * 0.6

    result = np.clip(result, 0, 255).astype(np.uint8)

    # Légende
    LEG_W = 320
    legend = np.full((out_size, LEG_W, 3), 20, dtype=np.uint8)
    cv2.putText(legend, "PIPELINE MASQUES", (10, 30),
               cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255,255,255), 2)
    y = 65
    for name, color in colors.items():
        if name in masks and (masks[name] > 0.01).any():
            pct = (masks[name] > 0.01).sum() / masks[name].size * 100
            cv2.rectangle(legend, (10,y-14),(32,y+8), color, -1)
            label = f"{name[:22]} {pct:.0f}%"
            cv2.putText(legend, label, (38,y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.30, (255,255,255), 1)
            y += 30

    final = np.hstack([result, legend])
    cv2.imwrite(str(output_dir / "pipeline_validation.png"), final)
    print(f"  → pipeline_validation.png ({len(masks)} masques)")

# ============================================================================
# MAIN
# ============================================================================

def main():
    OUTPUT_DIR.mkdir(exist_ok=True, parents=True)
    print("=" * 70)
    print("MASK PIPELINE — Pipeline unifié masques terrain Reforger")
    print("=" * 70)

    # 1. Imports
    fns = import_pipeline_functions()

    # 2. Heightmap
    if fns['load_asc']:
        dem, cellsize, _ = fns['load_asc'](str(ASC_PATH))
        dem = np.array(dem, dtype=np.float32)
    else:
        dem, cellsize, _ = read_asc_fallback(ASC_PATH)
    print(f"[DEM] {dem.shape}, cellsize={cellsize}m")

    # 3. Calcul des signaux
    print("\n[SIGNALS] Calcul des signaux terrain...")

    if fns['calculate_slope']:
        slope = fns['calculate_slope'](dem, cellsize)
    else:
        from mask_generator import compute_slope
        slope = compute_slope(dem, cellsize)

    t = compute_thresholds(slope)

    signals = {'dem': dem, 'slope': slope}

    if fns['calculate_aspect']:
        print("  → Aspect...")
        signals['aspect'] = fns['calculate_aspect'](dem, cellsize)

    if fns['calculate_curvature_zt']:
        print("  → Courbure...")
        signals['curvature'] = fns['calculate_curvature_zt'](dem, cellsize)

    if fns['calculate_tpi']:
        print("  → TPI local + macro...")
        tpi_l, tpi_m = fns['calculate_tpi'](dem, cellsize, TPI_LOCAL_M, TPI_MACRO_M)
        signals['tpi_local'] = tpi_l
        signals['tpi_macro'] = tpi_m

    if fns['calculate_coastal_distance']:
        print("  → Distance côtière...")
        signals['dist_coast'] = fns['calculate_coastal_distance'](dem, cellsize)
    else:
        from scipy.ndimage import distance_transform_edt
        land = (dem > 0) & ~np.isnan(dem)
        dist_px = distance_transform_edt(land)
        signals['dist_coast'] = (dist_px * cellsize).astype(np.float32)

    if fns['calculate_flow_accumulation']:
        print("  → Flow accumulation...")
        dem_filled = fns['fill_depressions'](dem) if fns['fill_depressions'] else dem
        flow_raw = fns['calculate_flow_accumulation'](dem_filled, cellsize)
        # Normaliser [0..1]
        flow_max = np.nanpercentile(flow_raw, 99)
        signals['flow_norm'] = np.clip(flow_raw / (flow_max + 1e-6), 0, 1).astype(np.float32)

    # 4. Masques Gaea
    signals['flow']    = load_mask(GAEA_FLOW,    OUTPUT_SIZE) if GAEA_FLOW.exists()    else None
    signals['deposit'] = load_mask(GAEA_DEPOSIT, OUTPUT_SIZE) if GAEA_DEPOSIT.exists() else None
    print(f"[GAEA] Flow: {'OK' if signals['flow'] is not None else 'absent'}  "
          f"Deposit: {'OK' if signals['deposit'] is not None else 'absent'}")

    # 5. Exclusion
    if EXCLUSION_MASK.exists():
        excl = load_mask(EXCLUSION_MASK, OUTPUT_SIZE)
        exclusion = (excl > 0.5).astype(np.uint8)
        print(f"[EXCL] Zone active: {exclusion.mean()*100:.1f}%")
    else:
        exclusion = np.ones((OUTPUT_SIZE, OUTPUT_SIZE), dtype=np.uint8)

    # 6. Worley noise
    noise = worley_noise_2d((OUTPUT_SIZE, OUTPUT_SIZE), NOISE_SCALE, NOISE_SEED)

    # 7. Génération masques
    print(f"\n[MASKS] Génération hiérarchie stricte...")
    masks = generate_all_masks(signals, t, exclusion, noise, fns, OUTPUT_SIZE)

    # 8. Export
    print(f"\n[SAVE] Export PNG 16 bits...")
    for name, mask in masks.items():
        path = OUTPUT_DIR / f"mask_{name}.png"
        save_16bit(mask, path)
        pct = (mask > 0.01).sum() / mask.size * 100
        print(f"  [OK] mask_{name}.png — {pct:.1f}% actif")

    # 9. Validation
    generate_validation_map(masks, OUTPUT_SIZE, OUTPUT_DIR)

    print(f"\n✅ Terminé ! {len(masks)} masques dans {OUTPUT_DIR}")


if __name__ == '__main__':
    main()
