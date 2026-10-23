"""
pipeline_v5.py — Pipeline terrain unifié
=========================================
Extension de pipeline_unified.py avec :
  - Mapping masque → texture (configurable)
  - Arbitrage budget par bloc (respect 6 slots max)
  - Préservation Zone B (textures existantes intactes)
  - Gestion blocs frontière Zone A/B
  - Visualisation carte colorisée (satmap-like) avec quadrillage tuiles
  - Export masques PNG

Modules :
  [1] Lecture heightmap .asc
  [2] Calcul terrain (slope, fBm, coastal)
  [3] Masques de base (seabed, coastal, rock, landes, flow, deposit)
  [4] Végétation (prairie, maquis, alpages, forêts)
  [5] Application masque exclusion (Zone B préservée)
  [6] Normalisation exclusive (vectorisée)
  [7] Arbitrage budget par bloc
  [8] Visualisation carte
  [9] Export masques PNG

Usage :
    from pipeline_v5 import run_pipeline
"""

import json
import struct
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter, uniform_filter


# ============================================================================
# CONFIGURATION
# ============================================================================

# Chemins masques Gaea (optionnels, patchés dans run_pipeline)
GAEA_FLOW = None
GAEA_DEPOSIT = None

# Paramètres généraux
CELL_SIZE        = None   # Auto-détecté depuis .asc header
OUTPUT_SIZE      = 4096   # Résolution sortie masques PNG

# Masque exclusion
COASTAL_SEA_LEVEL = 0.0
COASTAL_WIDTH     = 40.0

# Seuils pente
THRESHOLD_GENTLE = None   # Auto p70
THRESHOLD_LANDES = None   # Auto p85
THRESHOLD_ROCK   = 22.0
THRESHOLD_CLIFF  = 26.0
TRANSITION_WIDTH = 5.0

# Roughness
ROUGHNESS_AMPLITUDE = 8.0
ROUGHNESS_SCALE     = 0.008
ROUGHNESS_OCTAVES   = 6
ROUGHNESS_SEED      = 42
ROUGHNESS_MODE      = "slope_perturb"

# Végétation
VEG_MIN_SCORE = 0.15

# Post-processing
STRETCH_AUTO     = True
WEIGHT_MIN       = 0.10
DEPOSIT_CUT_LOW  = 0.30

# (GRID_W et NUM_BLK retirés — passés en paramètres obligatoires)

# ============================================================================
# MAPPING MASQUE → TEXTURE (défauts — modifiable via Streamlit)
# ============================================================================
# Valeurs = ID global matériau dans terrain.terr (index 0-based)

# ============================================================================
# DEFAULT_MASK_CONFIG — Configuration masques par défaut (noms texture)
# ============================================================================
# SURFACES et SURFACES_INV ont été supprimés — utiliser surfaces.json par projet
# Les noms de texture ci-dessous sont résolus dynamiquement via project_manager.py

# Priorité d'application (ordre = priorité décroissante)
DEFAULT_MASK_CONFIG = [
    ("mask_seabed",           "SeaBed_01",                (70,  130, 180)),
    ("mask_coastal",          "BeachGrass_01",             (194, 178, 128)),
    ("mask_alpages",          "zi_MountainGrass_04",       (200, 220, 160)),
    ("mask_landes_rocheuses", "MountainGrass_01",          (143, 143, 120)),
    ("mask_maquis_landes",    "Heather_01",                (160, 120,  80)),
    ("mask_foret_coniferes",  "ForestConiferous_01_Base",  (  0,  60,   0)),
    ("mask_foret_feuillue",   "ForestDeciduous_01_Base",   (  0, 100,   0)),
    ("mask_flow",             "Dirt_03",                   (101,  67,  33)),
    ("mask_landes_plateau",   "MountainGrass_03",          (107, 142,  35)),
    ("mask_rock",             "Rock_01",                   (128, 128, 128)),
    ("mask_deposit",          "Dirt_01",                   (139, 115,  85)),
    ("mask_prairie_seche",    "Grass_02",                  ( 85, 107,  47)),
    ("mask_prairie_humide",   "Grass_03",                  ( 34, 139,  34)),
]

# Couleur de fond (texture par défaut, résolu dynamiquement)
DEFAULT_TEXTURE_NAME = "Grass_03"
DEFAULT_COLOR = (50, 160, 50)

# Seuil de présence d'un masque sur un bloc (% cellules pour compter)
MASK_PRESENCE_THRESH = 0.15  # 15% garantit mathématiquement max 6 masques par bloc 32×32


# ============================================================================
# MODULE 1 — LECTURE HEIGHTMAP
# ============================================================================

def load_heightmap_asc(asc_path: Path) -> Tuple[np.ndarray, float]:
    asc_path = Path(asc_path)
    suffix = asc_path.suffix.lower()

    SUPPORTED = {'.asc', '.tif', '.tiff'}
    if suffix not in SUPPORTED:
        raise ValueError(
            f"Format '{suffix}' non supporté. Formats acceptés : .asc, .tif, .tiff\n"
            f"PNG 16-bit non supporté (pas de métadonnées altitude)."
        )

    # ── GeoTIFF ──────────────────────────────────────────────────────────────
    if suffix in ('.tif', '.tiff'):
        try:
            import rasterio
        except ImportError:
            raise ImportError("rasterio requis pour lire les GeoTIFF : pip install rasterio")

        with rasterio.open(asc_path) as src:
            dem = src.read(1).astype(np.float32)
            cellsize = src.res[0]  # résolution X en mètres
            nodata = src.nodata
            if nodata is not None:
                dem[dem == nodata] = np.nan
            nrows, ncols = dem.shape

        print(f"[1/9] Chargement heightmap (GeoTIFF): {asc_path.name}")
        print(f"       {nrows}×{ncols} px, cellsize={cellsize}m")
        print(f"       Altitude: {np.nanmin(dem):.1f}m -> {np.nanmax(dem):.1f}m")
        return dem, cellsize

    # ── ASC ──────────────────────────────────────────────────────────────────
    with open(asc_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    header = {}
    for line in lines[:10]:
        parts = line.strip().split()
        if len(parts) == 2:
            try:
                header[parts[0].lower()] = float(parts[1])
            except ValueError:
                pass
    ncols    = int(header.get('ncols', 0))
    nrows    = int(header.get('nrows', 0))
    cellsize = header.get('cellsize', 4.0)
    nodata   = header.get('nodata_value', -9999.0)

    dem = np.loadtxt(asc_path, skiprows=6, dtype=np.float32)
    dem[dem == nodata] = np.nan

    print(f"[1/9] Chargement heightmap (ASC): {asc_path.name}")
    print(f"       {nrows}×{ncols} px, cellsize={cellsize}m")
    print(f"       Altitude: {np.nanmin(dem):.1f}m -> {np.nanmax(dem):.1f}m")
    return dem, cellsize


# ============================================================================
# MODULE 2 — CALCUL TERRAIN
# ============================================================================

def compute_slope_aspect(dem, cellsize):
    fy, fx = np.gradient(dem, cellsize)
    slope  = np.degrees(np.arctan(np.sqrt(fx**2 + fy**2)))
    aspect = np.degrees(np.arctan2(-fx, fy))
    return slope, aspect


def enrichissement_slope_fbm(slope, cellsize):
    if not ROUGHNESS_MODE:
        return slope
    np.random.seed(ROUGHNESS_SEED)
    h, w  = slope.shape
    noise = np.zeros((h, w), dtype=np.float32)
    for octave in range(ROUGHNESS_OCTAVES):
        freq = 2 ** octave * ROUGHNESS_SCALE
        amp  = ROUGHNESS_AMPLITUDE / (2 ** octave)
        oct_noise = np.random.randn(h, w).astype(np.float32) * amp
        oct_noise = uniform_filter(oct_noise, size=int(1.0 / freq))
        noise += oct_noise
    return np.clip(slope + noise, 0, 90)


def compute_coastal_distance(dem):
    land = (dem > COASTAL_SEA_LEVEL).astype(np.uint8)
    return cv2.distanceTransform(land, cv2.DIST_L2, 5)


def module_terrain(dem, cellsize):
    print("[2/9] Calcul terrain...")
    slope, aspect = compute_slope_aspect(dem, cellsize)
    slope_e       = enrichissement_slope_fbm(slope, cellsize)
    coastal_dist  = compute_coastal_distance(dem)
    print("       slope enrichi, coastal distance OK")
    return {'slope': slope_e, 'aspect': aspect, 'coastal_distance': coastal_dist}


# ============================================================================
# MODULE 3 — MASQUES DE BASE
# ============================================================================

def apply_output_curve(mask, gamma=1.0):
    if STRETCH_AUTO:
        active = mask[mask > 0]
        if active.size > 0:
            lo, hi = np.percentile(active, 2), np.percentile(mask, 98)
            if hi > lo:
                mask = np.clip((mask - lo) / (hi - lo), 0, 1)
    if gamma != 1.0:
        mask = np.power(np.clip(mask, 0, 1), gamma)
    if mask.max() > 0:
        mask[mask < mask.max() * 0.02] = 0
    if WEIGHT_MIN > 0:
        mask = np.where(mask > 0, WEIGHT_MIN + mask * (1.0 - WEIGHT_MIN), 0.0)
    return np.clip(mask, 0, 1)


def generate_seabed(dem):
    t   = COASTAL_SEA_LEVEL
    tr  = 2.0
    out = np.zeros_like(dem, dtype=np.float32)
    out[dem <= t - tr] = 1.0
    m   = (dem > t - tr) & (dem <= t)
    out[m] = 1.0 - (dem[m] - (t - tr)) / tr
    if WEIGHT_MIN > 0:
        out = np.where(out > 0, WEIGHT_MIN + out * (1 - WEIGHT_MIN), 0.0)
    return np.clip(out, 0, 1)


def generate_coastal(dem, coastal_dist, slope=None):
    """
    Génère masque coastal uniquement sur les pixels connectés à la mer.
    Filtre les lacs intérieurs et zones basses encaissées.
    """
    from scipy.ndimage import label

    # Bande côtière brute
    coastal = np.clip((COASTAL_WIDTH - coastal_dist) / COASTAL_WIDTH, 0, 1)
    coastal = coastal * (dem > COASTAL_SEA_LEVEL).astype(np.float32)

    # Masque mer (pixels sous le niveau de la mer)
    sea_mask = (dem <= COASTAL_SEA_LEVEL)

    # Composantes connexes de la mer
    labeled, n_components = label(sea_mask)

    # Trouver les composantes connectées au bord de l'image (= vraie mer)
    border_labels = set()
    border_labels.update(labeled[0, :].flat)
    border_labels.update(labeled[-1, :].flat)
    border_labels.update(labeled[:, 0].flat)
    border_labels.update(labeled[:, -1].flat)
    border_labels.discard(0)  # ignorer le fond (non-mer)

    # Masque de la vraie mer (connectée au bord)
    true_sea = np.isin(labeled, list(border_labels))

    # Distance depuis la vraie mer (pixels true_sea = source)
    # distanceTransform calcule distance aux pixels=0, donc on inverse
    true_sea_inv = (~true_sea).astype(np.uint8)
    dist_from_true_sea = cv2.distanceTransform(true_sea_inv, cv2.DIST_L2, 5)

    # Coastal = terres à moins de COASTAL_WIDTH de la vraie mer
    coastal_filtered = np.clip((COASTAL_WIDTH - dist_from_true_sea) / COASTAL_WIDTH, 0, 1)
    coastal_filtered = coastal_filtered * (dem > COASTAL_SEA_LEVEL).astype(np.float32)

    # Filtre pente : supprimer coastal sur les zones raides (falaises)
    if slope is not None:
        SLOPE_MAX = 12.0  # degrés max pour avoir du coastal
        slope_factor = np.clip(1.0 - slope / SLOPE_MAX, 0, 1)
        coastal_filtered = coastal_filtered * slope_factor

    return coastal_filtered


def generate_landes_rocheuses(slope, t, maquis_mix=0.35):
    """
    maquis_mix : fraction max de landes_rocheuses atténuée par fBm
                 (0.0 = pas de mélange, 0.5 = jusqu'à 50% de trous)
    """
    GAP        = TRANSITION_WIDTH
    landes_end = max(t['landes'], t['rock'] - GAP / 2)
    out = np.zeros_like(slope, dtype=np.float32)
    m1  = (slope >= t['gentle']) & (slope < t['landes'])
    out[m1] = (slope[m1] - t['gentle']) / (t['landes'] - t['gentle'])
    out[(slope >= t['landes']) & (slope < landes_end)] = 1.0
    m2  = (slope >= landes_end) & (slope < t['rock'])
    out[m2] = 1.0 - (slope[m2] - landes_end) / (t['rock'] - landes_end)
    # Bruit fBm pour créer des trous organiques → maquis_landes s'y glisse
    if maquis_mix > 0:
        h, w = slope.shape
        freq, amp = 0.006, 1.0
        noise = np.zeros((h, w), dtype=np.float32)
        for _ in range(5):
            oct_noise = np.random.randn(h, w).astype(np.float32) * amp
            oct_noise = uniform_filter(oct_noise, size=max(1, int(1.0 / freq)))
            noise += oct_noise
            freq *= 2.0; amp *= 0.5
        noise = (noise - noise.min()) / (noise.max() - noise.min())  # 0→1
        attenuation = 1.0 - maquis_mix * noise
        out = out * attenuation
    return out


def generate_rock(slope, threshold=None):
    start = threshold if threshold is not None else (
        THRESHOLD_ROCK if THRESHOLD_ROCK
        else np.percentile(slope[slope > 0], 90) + TRANSITION_WIDTH / 2
    )
    return np.clip((slope - start) / TRANSITION_WIDTH, 0, 1)


def load_gaea_mask(path, shape):
    if path is None or not path.exists():
        return None
    img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if img is None:
        return None
    if len(img.shape) == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if img.shape != shape:
        img = cv2.resize(img, (shape[1], shape[0]), interpolation=cv2.INTER_LINEAR)
    mask = img.astype(np.float32) / (65535.0 if img.dtype == np.uint16 else 255.0)
    if mask.max() > 0:
        mask[mask < mask.max() * 0.02] = 0
    return mask


def module_masques_base(dem, terrain, calibration=None, gaea_flow=None, gaea_deposit=None):
    print("[3/9] Masques de base...")
    cal = calibration or {}
    threshold_rock = cal.get('threshold_rock', THRESHOLD_ROCK)

    slope  = terrain['slope']
    sa     = slope[slope > 0]
    t = {
        'gentle': THRESHOLD_GENTLE or np.percentile(sa, 70),
        'landes': THRESHOLD_LANDES or np.percentile(sa, 85),
        'rock':   threshold_rock   or np.percentile(sa, 90),
        'cliff':  THRESHOLD_CLIFF  or np.percentile(sa, 95),
    }
    print(f"[SEUILS] gentle={t['gentle']:.1f}° landes={t['landes']:.1f}° rock={t['rock']:.1f}° cliff={t['cliff']:.1f}°")
    m = {}
    m['mask_seabed']          = generate_seabed(dem)

    # Forcer seabed à 0 sur les pixels terrestres (dem > 0m)
    land = (dem > COASTAL_SEA_LEVEL).astype(np.float32)
    land = np.nan_to_num(land, nan=0.0)
    m['mask_seabed'] = np.nan_to_num(m['mask_seabed'] * (1 - land), nan=0.0)

    m['mask_coastal']         = generate_coastal(dem, terrain['coastal_distance'], slope=terrain['slope'])
    m['mask_landes_rocheuses']= generate_landes_rocheuses(terrain['slope'], t)
    print(f"[LANDES_ROCH] max={m['mask_landes_rocheuses'].max():.3f} mean={m['mask_landes_rocheuses'].mean():.4f} nonzero={np.count_nonzero(m['mask_landes_rocheuses'])}")
    m['mask_rock']            = generate_rock(terrain['slope'], threshold=t['rock'])
    print(f"[ROCK_MASK] max={m['mask_rock'].max():.3f} mean={m['mask_rock'].mean():.4f} nonzero={np.count_nonzero(m['mask_rock'])}")
    flow = load_gaea_mask(gaea_flow, dem.shape)
    if flow is not None:
        flow_cut = cal.get('flow_cut', 0.45)
        if flow.max() > 0:
            flow[flow < flow.max() * flow_cut] = 0
        m['mask_flow'] = apply_output_curve(flow, gamma=cal.get('flow_gamma', 0.5))
    dep = load_gaea_mask(gaea_deposit, dem.shape)
    if dep is not None:
        dep_cut = cal.get('dep_cut', DEPOSIT_CUT_LOW)
        if dep.max() > 0:
            dep[dep < dep.max() * dep_cut] = 0
        m['mask_deposit'] = apply_output_curve(dep, gamma=cal.get('dep_gamma', 1.0))
    print(f"       {len(m)} masques actifs")
    return m


# ============================================================================
# MODULE 4 — VÉGÉTATION
# ============================================================================

def generate_alpages(dem, slope):
    land = (dem > 0).astype(np.float32)
    def _bell(arr, lo, hi, s=10.0):
        c, h = (lo + hi) / 2, (hi - lo) / 2 + 1e-6
        return np.clip(1 - (np.abs(arr - c) - h) / (s + 1e-6), 0, 1)
    debris_min, rock_min = 18.0, 28.0
    flat   = np.clip(1 - slope / (debris_min + 1e-9), 0, 1)
    gentle = _bell(slope, 5, debris_min, 5)
    steep  = np.clip((slope - debris_min) / (rock_min - debris_min + 1), 0, 1)
    tpi    = dem - uniform_filter(dem, size=50)
    tpi    = np.clip(tpi / (np.abs(tpi).max() + 1e-9), -1, 1)

    # Bruit fBm pour casser les formes rondes
    np.random.seed(ROUGHNESS_SEED + 1)
    h_dem, w_dem = dem.shape
    noise = np.zeros((h_dem, w_dem), dtype=np.float32)
    for octave in range(4):
        freq = 2 ** octave * 0.004
        amp  = 25.0 / (2 ** octave)  # ±25m de perturbation max
        oct_noise = np.random.randn(h_dem, w_dem).astype(np.float32) * amp
        oct_noise = uniform_filter(oct_noise, size=int(1.0 / freq))
        noise += oct_noise
    dem_noisy = dem + noise  # DEM perturbé pour calcul alpages

    alp = np.clip((dem_noisy - 180) / 80, 0, 1) * (flat * .7 + gentle * .3) * land * (0.7 + np.clip(tpi, 0, 1) * .4 + (1-steep) * .2)
    alp = gaussian_filter(alp.astype(np.float32), sigma=1.0)  # sigma réduit

    # Bruit de forme appliqué APRÈS le gaussian pour préserver les contours irréguliers
    np.random.seed(ROUGHNESS_SEED + 2)
    shape_noise = np.zeros((h_dem, w_dem), dtype=np.float32)
    for octave in range(3):
        freq = 2 ** octave * 0.006
        amp  = 0.15 / (2 ** octave)
        oct_n = np.random.randn(h_dem, w_dem).astype(np.float32) * amp
        oct_n = uniform_filter(oct_n, size=int(1.0 / freq))
        shape_noise += oct_n
    alp = np.clip(alp + shape_noise * (alp > 0).astype(np.float32), 0, 1)

    return np.where(alp >= VEG_MIN_SCORE, alp, 0.0)


def generate_foret_coniferes(dem, slope, aspect, coastal_dist):
    land = (dem > 0).astype(np.float32)
    def _bell(arr, lo, hi, s=10.0):
        c, h = (lo + hi) / 2, (hi - lo) / 2 + 1e-6
        return np.clip(1 - (np.abs(arr - c) - h) / (s + 1e-6), 0, 1)
    debris_min, rock_min = 18.0, 28.0
    alt_pine = _bell(dem, 0, 250, 40)
    flat     = np.clip(1 - slope / (debris_min + 1e-9), 0, 1)
    gentle   = _bell(slope, 5, debris_min, 5)
    rocky    = np.clip((slope - rock_min) / 20, 0, 1)
    north    = np.cos(np.radians(aspect))
    south_f  = np.clip((-north + 1) / 2, 0, 1)
    dist_n   = np.clip(coastal_dist / 500, 0, 1)
    c        = 4.0
    cx = (np.roll(dem, -1, 1) - 2*dem + np.roll(dem, 1, 1)) / c**2
    cy = (np.roll(dem, -1, 0) - 2*dem + np.roll(dem, 1, 0)) / c**2
    curv     = np.clip((cx + cy) / (np.abs(cx + cy).max() + 1e-9), -1, 1)
    flow     = np.clip(-curv * .5 + (1 - slope / (slope.max() + 1e-9)) * .5, 0, 1)
    humid    = np.clip(flow * .6 + (1 - dist_n) * .4, 0, 1)
    dry      = np.clip(1 - humid, 0, 1)
    coastal  = ((coastal_dist < 60) & (dem < 15)).astype(np.float32)
    cz       = np.clip(1 - coastal_dist / 800, 0, 1)
    interior = np.clip((coastal_dist - 600) / 1200, 0, 1)
    fc = alt_pine * (cz * .7 + (1 - interior) * .3) * (1 - coastal) * land * (0.5 + south_f * .3 + dry * .15 + rocky * .1) * (flat * .6 + gentle * .4)
    fc = gaussian_filter(fc.astype(np.float32), sigma=2.5)
    return np.where(np.clip(fc, 0, 1) >= VEG_MIN_SCORE, fc, 0.0)


def module_vegetation(dem, terrain, calibration=None):
    print("[4/9] Masques végétation...")
    cal = calibration or {}
    prairie_alt_max    = cal.get('prairie_alt_max',    80.0)
    prairie_seche_min  = cal.get('prairie_seche_min',  15.0)
    prairie_seche_max  = cal.get('prairie_seche_max',  80.0)
    landes_plateau_min = cal.get('landes_plateau_min', 120.0)
    maquis_alt_min     = cal.get('maquis_alt_min',     30.0)
    maquis_alt_max     = cal.get('maquis_alt_max',     120.0)
    foret_alt_min      = cal.get('foret_alt_min',      30.0)
    gamma_global       = cal.get('gamma_global',       1.0)

    sl = terrain['slope']
    cd = terrain['coastal_distance']
    m  = {}
    m['mask_prairie_humide']  = np.clip((prairie_alt_max - dem) / prairie_alt_max, 0, 1) * np.clip((12 - sl) / 12, 0, 1)
    m['mask_prairie_seche']   = np.clip((dem - prairie_seche_min) / (prairie_seche_max - prairie_seche_min), 0, 1) * np.clip((prairie_seche_max - dem) / 30, 0, 1) * np.clip((15 - sl) / 15, 0, 1)
    m['mask_landes_plateau']  = np.clip((dem - landes_plateau_min) / 40, 0, 1) * np.clip((sl - 12) / 8, 0, 1)
    m['mask_maquis_landes']   = np.clip((dem - maquis_alt_min) / (maquis_alt_max - maquis_alt_min), 0, 1) * np.clip((maquis_alt_max - dem) / 30, 0, 1) * np.clip((sl - 5) / 8, 0, 1) * np.clip((30 - sl) / 10, 0, 1)
    print(f"[MAQUIS] max={m['mask_maquis_landes'].max():.3f} mean={m['mask_maquis_landes'].mean():.4f} nonzero={np.count_nonzero(m['mask_maquis_landes'])}")
    if m['mask_maquis_landes'].max() > 0:
        m['mask_maquis_landes'] = np.clip(m['mask_maquis_landes'] * 2.0, 0, 1)
        threshold = 0.15
        boost     = 0.75
        mask      = m['mask_maquis_landes']
        m['mask_maquis_landes'] = np.where(mask > threshold,
                                            np.maximum(mask, boost),
                                            0.0).astype(np.float32)
        print(f"[MAQUIS_AMP] max={m['mask_maquis_landes'].max():.3f} mean={m['mask_maquis_landes'].mean():.4f} nonzero={np.count_nonzero(m['mask_maquis_landes'])}")
    m['mask_alpages']         = generate_alpages(dem, sl)
    m['mask_foret_feuillue']  = np.clip((dem - foret_alt_min) / 40, 0, 1) * np.clip((18 - sl) / 18, 0, 1) * 0.8
    m['mask_foret_coniferes'] = generate_foret_coniferes(dem, sl, terrain['aspect'], cd)

    # ── Boost gamma global sur tous les masks végétation (renforce les faibles)
    if gamma_global != 1.0:
        _skip = {"mask_seabed", "mask_coastal", "mask_flow", "mask_deposit"}
        for _k in list(m.keys()):
            if _k not in _skip:
                m[_k] = apply_output_curve(m[_k], gamma=gamma_global)

    land_mask = (dem > COASTAL_SEA_LEVEL).astype(np.float32)
    land_mask = np.nan_to_num(land_mask, nan=0.0)
    for key in m:
        m[key] = np.nan_to_num(m[key] * land_mask, nan=0.0)

    print(f"       {len(m)} masques végétation")
    return m


# ============================================================================
# MODULE 5 — MASQUE EXCLUSION
# ============================================================================

def module_exclusion(masques, exclusion_path):
    """Zone blanche = on écrit (Zone A). Zone noire = on préserve (Zone B)."""
    if exclusion_path is None or not exclusion_path.exists():
        print("[5/9] Pas de masque exclusion")
        return masques, None

    print("[5/9] Application masque exclusion...")
    img = cv2.imread(str(exclusion_path), cv2.IMREAD_UNCHANGED)
    if img is None:
        print("       WARN : masque exclusion illisible")
        return masques, None

    if len(img.shape) == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    first = next(iter(masques.values()))
    if img.shape != first.shape:
        img = cv2.resize(img, (first.shape[1], first.shape[0]), interpolation=cv2.INTER_NEAREST)

    # Zone A = pixels blancs (> 128) → masques s'appliquent ici
    zone_a = (img > 128)
    # Zone B = pixels noirs → on ne touche pas
    zone_b = ~zone_a

    for name in masques:
        if name == 'mask_seabed':
            continue  # seabed sur toute la map
        masques[name][zone_b] = 0.0

    pct_a = zone_a.sum() / zone_a.size * 100
    print(f"       Zone A = {pct_a:.1f}%, Zone B préservée")
    return masques, zone_a  # retourne aussi le masque Zone A pour le module 7


# ============================================================================
# MODULE 6 — NORMALISATION EXCLUSIVE (vectorisée)
# ============================================================================

def module_normalize(masques, mask_config):
    """
    Normalisation par soustraction progressive.

    Les masques s'appliquent dans l'ordre de priorité.
    Chaque masque ne prend que les pixels non encore attribués par les masques précédents.
    → Budget 6 slots garanti par construction (un pixel = un seul masque).
    """
    print("[6/9] Normalisation par soustraction...")
    priority_names = [cfg[0] for cfg in mask_config if cfg[0] in masques]

    first = next(iter(masques.values()))
    h, w  = first.shape

    # Masque des pixels déjà attribués
    attribue = np.zeros((h, w), dtype=bool)

    normalized = {}
    for name in priority_names:
        raw = masques[name].copy()
        # N'activer que les pixels non encore attribués
        raw[attribue] = 0.0
        # Marquer les pixels actifs de ce masque comme attribués
        actif = raw > 0
        attribue |= actif
        normalized[name] = raw

    # Conserver les masques hors priorité inchangés (ne participent pas à la soustraction)
    for name in masques:
        if name not in normalized:
            normalized[name] = masques[name]

    n_attribues = int(attribue.sum())
    pct = n_attribues / (h * w) * 100
    print(f"       Soustraction : {len(priority_names)} masques, {n_attribues:,} px attribués ({pct:.1f}%)")
    return normalized


# ============================================================================
# MODULE 7 — ARBITRAGE BUDGET PAR BLOC (nouveau)
# ============================================================================

def _read_zone_b_slots(data_dir, bx, by, grid_w, num_blk, tile_prefix):
    """
    Lit le nombre de slots Zone B déjà utilisés pour le bloc (bx,by).
    Retourne (n_slots_zone_b, mat_ids_zone_b).
    """
    try:
        from clean_weights import compute_lrs2_shift

        tile_id = (by // num_blk) * grid_w + (bx // num_blk)
        path    = data_dir / f"{tile_prefix}{tile_id}.ttile"
        if not path.exists():
            return 0, []
        data     = path.read_bytes()
        lrs2_pos = data.find(b'LRS2')
        if lrs2_pos < 0:
            return 0, []
        lrs2_sz  = struct.unpack_from('>I', data, lrs2_pos + 4)[0]
        lrs2_raw = data[lrs2_pos + 8: lrs2_pos + 8 + lrs2_sz]

        shift = compute_lrs2_shift(grid_w, num_blk)
        mask = (1 << shift) - 1

        pos = 0
        while pos < len(lrs2_raw) - 6:
            idx = struct.unpack_from('<I', lrs2_raw, pos)[0]
            cnt = struct.unpack_from('<H', lrs2_raw, pos + 4)[0]
            mats = list(struct.unpack_from(f'<{cnt}H', lrs2_raw, pos + 6))
            if (idx & mask) == bx and ((idx >> shift) & mask) == by:
                return len(mats), mats
            pos += 6 + cnt * 2
        return 0, []
    except Exception:
        return 0, []


def module_budget(masques, mask_config, zone_a_mask, budget_pipeline, grid_w, num_blk, tile_prefix, data_dir=None):
    """
    Module 7 : Analyse budget par bloc depuis les masques normalisés.

    Après soustraction, un pixel = un seul masque → pas de dépassement possible.
    Ce module calcule la carte des masques actifs par bloc pour la visualisation.
    """
    print("[7/9] Analyse budget par bloc...")

    priority_names = [cfg[0] for cfg in mask_config]
    color_map      = {cfg[0]: cfg[2] for cfg in mask_config}

    first = next(iter(masques.values()))
    h, w  = first.shape

    blocs_per_axis = grid_w * num_blk
    bloc_px        = OUTPUT_SIZE // blocs_per_axis

    bloc_map   = {}
    n_over     = 0
    n_ok       = 0
    n_frontier = 0

    for by_bloc in range(blocs_per_axis):
        for bx_bloc in range(blocs_per_axis):
            py  = (blocs_per_axis - 1 - by_bloc) * bloc_px
            px  = bx_bloc * bloc_px
            py2 = min(py + bloc_px, OUTPUT_SIZE)
            px2 = min(px + bloc_px, OUTPUT_SIZE)
            n_px = (py2 - py) * (px2 - px)
            if n_px == 0:
                continue

            # Compter les masques distincts actifs sur ce bloc (après soustraction)
            active_masks = []
            for name in priority_names:
                if name not in masques:
                    continue
                region   = masques[name][py:py2, px:px2]
                n_active_px = int((region > 0).sum())
                if n_active_px > 0:
                    strength = float(region.sum())  # force totale
                    active_masks.append((name, strength, n_active_px))

            # Trier par force décroissante
            active_masks.sort(key=lambda x: -x[1])

            # Limiter strictement à budget_pipeline masques (top-N par force)
            selected = active_masks[:budget_pipeline]
            n_active = len(selected)

            # Lire slots Zone B si data_dir fourni
            slots_zone_b = 0
            if data_dir and data_dir.exists():
                slots_zone_b, _ = _read_zone_b_slots(data_dir, bx_bloc, by_bloc, grid_w, num_blk, tile_prefix)
                if slots_zone_b > 0:
                    n_frontier += 1

            total_slots = n_active + slots_zone_b

            if total_slots > budget_pipeline:
                n_over += 1
            else:
                n_ok += 1

            # Couleur dominante = premier masque actif (ordre priorité)
            dominant_color = DEFAULT_COLOR
            if active_masks:
                dominant_name  = active_masks[0][0]
                dominant_color = color_map.get(dominant_name, DEFAULT_COLOR)

            bloc_map[(bx_bloc, by_bloc)] = {
                'color':     dominant_color,
                'n_active':  n_active,
                'n_zone_b':  slots_zone_b,
                'frontier':  slots_zone_b > 0,
                'total':     total_slots,
            }

    stats = {
        'n_ok':       n_ok,
        'n_over':     n_over,
        'n_frontier': n_frontier,
        'total':      blocs_per_axis ** 2,
    }
    print(f"       OK={n_ok}, dépassement={n_over}, frontière={n_frontier}")
    return masques, bloc_map, stats


# ============================================================================
# MODULE 8 — VISUALISATION CARTE
# ============================================================================

def build_zone_b_colormap(data_dir: Path, mask_config: List, surfaces: Dict,
                           grid_w: int, num_blk: int, tile_prefix: str,
                           catalog_path: Optional[Path] = None) -> Dict:
    """
    Lit le matériau dominant de chaque bloc Zone B depuis les .ttile.
    Couleurs depuis catalog.json (avg_color) si fourni, sinon couleurs génériques.
    """
    # Charger catalog
    catalog = {}
    if catalog_path and catalog_path.exists():
        with open(catalog_path, encoding='utf-8') as f:
            catalog = json.load(f)

    def get_color(mat_id: int) -> Tuple[int, int, int]:
        name = surfaces.get(mat_id, '')
        # Chercher dans catalog
        entry = catalog.get(name) or catalog.get(name + '.emat')
        if entry:
            avg = entry.get('avg_color')
            if avg and avg != [0, 0, 0]:
                # Éclaircir légèrement pour la lisibilité
                r = min(255, int(avg[0] * 1.4))
                g = min(255, int(avg[1] * 1.4))
                b = min(255, int(avg[2] * 1.4))
                return (r, g, b)
        # Fallback couleurs depuis mask_config
        for _, mid, color in mask_config:
            if mid == mat_id:
                return color
        return DEFAULT_COLOR

    print(f"       Lecture Zone B depuis {data_dir}...")
    from clean_weights import compute_lrs2_shift

    tile_ids = []
    for f in data_dir.glob(f'{tile_prefix}*.ttile'):
        try:
            # Extraire l'ID après le préfixe
            tile_ids.append(int(f.stem[len(tile_prefix):]))
        except (ValueError, IndexError):
            pass

    shift = compute_lrs2_shift(grid_w, num_blk)
    mask = (1 << shift) - 1

    colormap = {}
    for tile_id in sorted(tile_ids):
        path = data_dir / f'{tile_prefix}{tile_id}.ttile'
        try:
            raw = path.read_bytes()
            lrs2_pos = raw.find(b'LRS2')
            if lrs2_pos < 0:
                continue
            lrs2_sz  = struct.unpack_from('>I', raw, lrs2_pos + 4)[0]
            lrs2_raw = raw[lrs2_pos + 8: lrs2_pos + 8 + lrs2_sz]
            pos = 0
            while pos < len(lrs2_raw) - 6:
                idx  = struct.unpack_from('<I', lrs2_raw, pos)[0]
                cnt  = struct.unpack_from('<H', lrs2_raw, pos + 4)[0]
                mats = list(struct.unpack_from(f'<{cnt}H', lrs2_raw, pos + 6))
                bx   = idx & mask
                by   = (idx >> shift) & mask
                if mats:
                    colormap[(bx, by)] = get_color(mats[0])
                pos += 6 + cnt * 2
        except Exception:
            continue

    print(f"       {len(colormap)} blocs Zone B lus")
    return colormap


def module_visualize(masques_normalized, mask_config, output_path,
                     budget_pipeline, grid_w, num_blk,
                     zone_a_mask=None, bloc_budget_map=None,
                     zone_b_colormap=None, satmap_path=None,
                     surfaces_map=None,
                     tile_grid=True, img_size=4096):
    """
    Génère une image de visualisation pixel par pixel depuis les masques normalisés.

    Zone B : satmap_path si fourni (meilleur rendu), sinon zone_b_colormap par bloc,
             sinon DEFAULT_COLOR uniforme.
    """
    print("[8/9] Génération carte de visualisation (pixel par pixel)...")

    # Fallback surfaces_map vide si non fourni
    if surfaces_map is None:
        surfaces_map = {}

    priority_names = [cfg[0] for cfg in mask_config if cfg[0] in masques_normalized]
    color_map      = {cfg[0]: cfg[2] for cfg in mask_config}

    # ── Stack des masques dans l'ordre de priorité ─────────────────────────
    first  = next(iter(masques_normalized.values()))
    h, w   = first.shape

    stack  = np.stack([masques_normalized[name] for name in priority_names], axis=0)  # (N, H, W)
    winner = np.argmax(stack, axis=0)   # (H, W) — index du masque gagnant
    maxval = np.max(stack, axis=0)      # (H, W) — valeur max

    # ── Construction image couleur pixel par pixel ─────────────────────────
    img_rgb = np.zeros((h, w, 3), dtype=np.uint8)

    for i, name in enumerate(priority_names):
        r, g, b = color_map.get(name, DEFAULT_COLOR)
        mask_px = (winner == i) & (maxval > 0)
        img_rgb[mask_px] = [r, g, b]

    # Pixels sans masque actif → couleur par défaut (Grass_03)
    no_mask = maxval == 0
    img_rgb[no_mask] = DEFAULT_COLOR

    # Pas de flip Y — les masques sont déjà dans l'orientation correcte (nord en haut)
    # depuis le DEM .asc (Y=0 = nord)

    # ── Zone B → satmap / colormap par bloc / neutre ──────────────────────
    if zone_a_mask is not None:
        zm = cv2.resize(
            zone_a_mask.astype(np.uint8),
            (w, h), interpolation=cv2.INTER_NEAREST
        )
        zone_b_px = zm == 0

        if satmap_path and Path(str(satmap_path)).exists():
            # Satmap comme fond Zone B — rendu le plus fidèle
            sat = cv2.imread(str(satmap_path))
            if sat is not None:
                sat = cv2.resize(sat, (w, h), interpolation=cv2.INTER_AREA)
                sat_rgb = cv2.cvtColor(sat, cv2.COLOR_BGR2RGB)
                # La satmap a Y=0 en haut comme numpy → pas de flip nécessaire
                img_rgb[zone_b_px] = sat_rgb[zone_b_px]

        elif zone_b_colormap:
            # Couleurs par bloc depuis catalog.json + .ttile
            blocs_per_axis = grid_w * num_blk
            bloc_px_h = h // blocs_per_axis
            bloc_px_w = w // blocs_per_axis
            color_layer = np.full((h, w, 3), DEFAULT_COLOR, dtype=np.uint8)
            for (bx, by), (r, g, b) in zone_b_colormap.items():
                py0 = (blocs_per_axis - 1 - by) * bloc_px_h
                px0 = bx * bloc_px_w
                py1 = min(py0 + bloc_px_h, h)
                px1 = min(px0 + bloc_px_w, w)
                color_layer[py0:py1, px0:px1] = [r, g, b]
            img_rgb[zone_b_px] = color_layer[zone_b_px]

        else:
            # Phase 1 — couleur neutre uniforme Grass_03
            img_rgb[zone_b_px] = DEFAULT_COLOR

    # ── Resize à img_size ──────────────────────────────────────────────────
    if h != img_size or w != img_size:
        img_rgb = cv2.resize(img_rgb, (img_size, img_size), interpolation=cv2.INTER_NEAREST)

    # BGR pour cv2
    img = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)

    # ── Quadrillage tuiles ─────────────────────────────────────────────────
    if tile_grid:
        blocs_per_axis = grid_w * num_blk
        bloc_px        = img_size // blocs_per_axis  # px par bloc dans l'image finale
        tile_px        = num_blk * bloc_px   # px par tuile

        # Lignes de tuiles (blanc semi-transparent)
        for i in range(0, img_size, tile_px):
            cv2.line(img, (i, 0), (i, img_size - 1), (220, 220, 220), 1)
            cv2.line(img, (0, i), (img_size - 1, i), (220, 220, 220), 1)

        # Lignes de blocs (gris très discret)
        for i in range(0, img_size, bloc_px):
            if i % tile_px != 0:
                cv2.line(img, (i, 0), (i, img_size - 1), (60, 60, 60), 1)
                cv2.line(img, (0, i), (img_size - 1, i), (60, 60, 60), 1)

        # Numéros de tuiles
        font = cv2.FONT_HERSHEY_SIMPLEX
        for ty in range(grid_w):
            for tx in range(grid_w):
                tile_id = ty * grid_w + tx
                px_x    = tx * tile_px + 2
                px_y    = (grid_w - 1 - ty) * tile_px + 11  # flip Y
                cv2.putText(img, str(tile_id), (px_x, px_y),
                            font, 0.22, (200, 200, 200), 1, cv2.LINE_AA)

    # ── Marquage blocs dépassement budget ──────────────────────────────────
    if bloc_budget_map:
        blocs_per_axis = grid_w * num_blk
        bloc_px        = img_size // blocs_per_axis
        for (bx, by), n in bloc_budget_map.items():
            if n > budget_pipeline:
                px_x0 = bx * bloc_px
                px_y0 = (blocs_per_axis - 1 - by) * bloc_px
                cv2.rectangle(img,
                              (px_x0, px_y0),
                              (px_x0 + bloc_px - 1, px_y0 + bloc_px - 1),
                              (0, 0, 255), 1)  # contour rouge

    # ── Légende ────────────────────────────────────────────────────────────
    legend_h = 180
    legend   = np.zeros((legend_h, img_size, 3), dtype=np.uint8)
    font     = cv2.FONT_HERSHEY_SIMPLEX
    x_leg, y_leg = 10, 20

    for cfg in mask_config:
        name, mat_id, (r, g, b) = cfg
        if name not in masques_normalized:
            continue
        label = f"{name.replace('mask_', '')} → {surfaces_map.get(mat_id, f'ID{mat_id}')}"
        cv2.rectangle(legend, (x_leg, y_leg - 11), (x_leg + 14, y_leg + 3), (b, g, r), -1)
        cv2.putText(legend, label, (x_leg + 17, y_leg), font, 0.32, (210, 210, 210), 1)
        x_leg += 270
        if x_leg > img_size - 270:
            x_leg = 10
            y_leg += 16

    # Légende dépassement budget
    cv2.rectangle(legend, (x_leg, y_leg - 11), (x_leg + 14, y_leg + 3), (0, 0, 255), -1)
    cv2.putText(legend, "> 6 textures (dépassement)", (x_leg + 17, y_leg),
                font, 0.32, (210, 210, 210), 1)

    # Carte seule 4096×4096
    cv2.imwrite(str(output_path), img)
    print(f"       Carte sauvegardée : {output_path} ({img.shape[1]}×{img.shape[0]})")
    # Légende séparée
    legend_path = output_path.parent / (output_path.stem + "_legend.png")
    cv2.imwrite(str(legend_path), legend)
    print(f"       Légende sauvegardée : {legend_path}")
    return output_path


# ============================================================================
# MODULE 9A — EXPORT MASQUES PNG
# ============================================================================

def module_export_masks(masques, mask_config, output_dir):
    """Export masques PNG 16 bits dans output_dir."""
    print("[9/9] Export masques PNG...")
    output_dir.mkdir(parents=True, exist_ok=True)

    priority_names = [cfg[0] for cfg in mask_config]
    order_map      = {name: i + 1 for i, name in enumerate(priority_names)}

    for name, mask in masques.items():
        # Resize à OUTPUT_SIZE
        if mask.shape[0] != OUTPUT_SIZE or mask.shape[1] != OUTPUT_SIZE:
            mask = cv2.resize(mask, (OUTPUT_SIZE, OUTPUT_SIZE), interpolation=cv2.INTER_AREA)
        # Seuillage final
        if mask.max() > 0:
            mask[mask < mask.max() * 0.01] = 0
        # Uint16
        mask_u16 = (mask * 65535).astype(np.uint16)
        idx  = order_map.get(name, 99)
        fname = output_dir / f"{idx:02d}_{name}.png"
        cv2.imwrite(str(fname), mask_u16)
        print(f"       {fname.name}")

    print(f"       {len(masques)} masques exportés → {output_dir}")


# ============================================================================
# MODULE 9B — ÉCRITURE DIRECTE .TTILE
# ============================================================================

def _find_gctd_sections(gctd, lrs2_entries):
    sections, pos = [], 2
    while pos < len(gctd) - 4:
        fx = struct.unpack_from('<H', gctd, pos)[0]
        fy = struct.unpack_from('<H', gctd, pos + 2)[0]
        if (fx, fy) in lrs2_entries and fx < 128 and fy < 128:
            next_off = len(gctd)
            probe    = pos + 4
            while probe < len(gctd) - 4:
                nx = struct.unpack_from('<H', gctd, probe)[0]
                ny = struct.unpack_from('<H', gctd, probe + 2)[0]
                if (nx, ny) in lrs2_entries and nx < 128 and ny < 128 and (nx, ny) != (fx, fy):
                    next_off = probe
                    break
                probe += 1
            sections.append({'bx': fx, 'by': fy, 'hdr_off': pos,
                              'data_off': pos + 4, 'data_size': next_off - pos - 4})
            pos += 2030
        else:
            pos += 1
    return sections


def _detect_gctd_payload_size(data_dir: Path, ttile_prefix: str) -> int:
    """Auto-détecte la taille du payload GCTD par bloc depuis le premier .ttile."""
    ttiles = list(data_dir.glob(f"{ttile_prefix}*.ttile"))
    if not ttiles:
        return 2025
    with open(ttiles[0], 'rb') as f:
        raw = f.read()
    pos = 12
    gctd_size = None
    lrs2_payload = None
    while pos < len(raw) - 8:
        tag = bytes(raw[pos:pos+4])
        size = struct.unpack_from('>I', raw, pos+4)[0]
        if tag == b'GCTD':
            gctd_size = size
        if tag == b'LRS2':
            lrs2_payload = raw[pos+8:pos+8+size]
        next_pos = pos + 8 + size
        if size % 2: next_pos += 1
        pos = next_pos
    if not gctd_size or not lrs2_payload:
        return 2025
    p = 0
    n = 0
    while p < len(lrs2_payload) - 6:
        count = struct.unpack_from('<H', lrs2_payload, p+4)[0]
        p += 6 + count * 2
        n += 1
    if n == 0:
        return 2025
    section_size = (gctd_size - 2) // n
    payload_size = section_size - 4
    print(f"[AUTO-GCTD] {n} blocs, section={section_size}b, payload={payload_size}b")
    return payload_size


def _detect_lrs2_shift(data_dir, ttile_prefix, num_blk):
    ttiles = list(data_dir.glob(f"{ttile_prefix}*.ttile"))
    if not ttiles:
        return 7

    with open(ttiles[0], 'rb') as f:
        raw = f.read()

    pos = raw.find(b'LRS2')
    if pos < 0:
        return 7

    size = struct.unpack_from('>I', raw, pos + 4)[0]
    payload = raw[pos + 8: pos + 8 + size]

    # Collecter tous les index
    indices = []
    p = 0
    while p < len(payload) - 6:
        index = struct.unpack_from('<I', payload, p)[0]
        count = struct.unpack_from('<H', payload, p + 4)[0]
        indices.append(index)
        p += 6 + count * 2

    if not indices:
        return 7

    max_index = max(indices)
    # Avec shift=7 : index_max = bx_max | (by_max << 7)
    #   bx_max = num_blk-1, by_max = num_blk-1
    #   max_index_shift7 = (num_blk-1) | ((num_blk-1) << 7)
    # Avec shift=8 : max_index = (num_blk-1) | ((num_blk-1) << 8)
    threshold = (num_blk - 1) | ((num_blk - 1) << 7)
    # Si max_index > threshold → shift=8 obligatoire
    if max_index > threshold:
        return 8
    return 7


def _parse_lrs2(raw, lrs2_shift=7):
    entries, pos = {}, 0
    mask = (1 << lrs2_shift) - 1
    while pos < len(raw) - 6:
        idx  = struct.unpack_from('<I', raw, pos)[0]
        cnt  = struct.unpack_from('<H', raw, pos + 4)[0]
        mats = list(struct.unpack_from(f'<{cnt}H', raw, pos + 6))
        entries[(idx & mask, (idx >> lrs2_shift) & mask)] = mats
        pos += 6 + cnt * 2
    return entries


def _build_lrs2(entries, lrs2_shift=7):
    parts = []
    for (bx, by), mats in sorted(entries.items()):
        parts.append(struct.pack('<IH', bx | (by << lrs2_shift), len(mats)))
        parts.append(struct.pack(f'<{len(mats)}H', *mats))
    return b''.join(parts)






def _weight_to_sub(weight: float) -> int:
    if   weight >= 1.00: return 3
    elif weight >= 0.75: return 2
    elif weight >= 0.50: return 1
    else:                return 0





def _build_calibration(dem: np.ndarray, cellsize: float,
                       slope: np.ndarray) -> dict:
    """
    Calcule les seuils de calibrage depuis la heightmap.
    Appelé une seule fois après load_heightmap_asc() et module_terrain().
    """
    valid = dem[dem > -9000]
    alt_min_raw = float(np.nanmin(valid))
    alt_min     = max(0.0, alt_min_raw)  # Plancher au niveau de la mer
    alt_max     = float(np.nanmax(valid))
    alt_range   = alt_max - alt_min

    sp70 = float(np.percentile(slope, 70))
    sp85 = float(np.percentile(slope, 85))
    sp90 = float(np.percentile(slope, 90))

    return {
        # Métadonnées
        'alt_min'  : alt_min,
        'alt_max'  : alt_max,
        'alt_range': alt_range,
        'cellsize' : cellsize,
        'slope_p70': sp70,
        'slope_p85': sp85,
        'slope_p90': sp90,
        # Seuils masques — proportionnels à alt_range
        'coastal_width'     : 40.0,
        'threshold_rock'    : sp90,
        'prairie_alt_max'   : alt_min + alt_range * 0.25,
        'prairie_seche_min' : alt_min + alt_range * 0.05,
        'prairie_seche_max' : alt_min + alt_range * 0.25,
        'landes_plateau_min': alt_min + alt_range * 0.35,
        'maquis_alt_min'    : alt_min + alt_range * 0.08,
        'maquis_alt_max'    : alt_min + alt_range * 0.35,
        'foret_alt_min'     : alt_min + alt_range * 0.08,
        'alpages_alt_min'   : alt_min + alt_range * 0.50,
    }


# ============================================================================
# FONCTION PRINCIPALE — Appelable depuis Streamlit ou en standalone
# ============================================================================

def run_pipeline(
    asc_path: Path,
    output_dir: Path,
    grid_w: int,
    num_blk: int,
    tile_prefix: str,
    block_budget: int,
    exclusion_path: Optional[Path] = None,
    gaea_flow: Optional[Path] = None,
    gaea_deposit: Optional[Path] = None,
    data_dir: Optional[Path] = None,
    catalog_path: Optional[Path] = None,
    satmap_path: Optional[Path] = None,
    mask_config: Optional[List] = None,
    surfaces_map: Optional[Dict] = None,
    default_mat_name: str = "default",
    mode: str = 'masks',
    dry_run: bool = True,
    progress_cb=None,
    calibration: Optional[Dict] = None,
    **kwargs,
) -> Dict:
    """
    Point d'entrée principal du pipeline v5.

    Args:
        asc_path       : Chemin heightmap .asc
        output_dir     : Dossier de sortie
        grid_w         : Nombre de tuiles par axe (obligatoire)
        num_blk        : Nombre de blocs par tuile par axe (obligatoire)
        tile_prefix    : Préfixe des tuiles (ex: "Terrain_", "ZBK_terrain_")
        block_budget   : Budget Reforger par bloc (5 ou 7, obligatoire)
        exclusion_path : Masque exclusion PNG (Zone B = noir, optionnel)
        gaea_flow      : Masque flow Gaea (optionnel)
        gaea_deposit   : Masque deposit Gaea (optionnel)
        data_dir       : Dossier .Data Reforger (pour lecture Zone B)
        mask_config    : Liste [(nom_masque, mat_id, color_rgb), ...]
        surfaces_map   : Dict {mat_id: nom_texture} pour affichage
        mode           : 'masks' = export PNG, 'preview' = visualisation seule
        dry_run        : Si True, pas d'écriture réelle
        progress_cb    : Callback de progression (optionnel)
        calibration    : Dict calibrations (optionnel)

    Returns:
        dict avec résultats et chemins de sortie
    """
    # Validation budget
    if not isinstance(block_budget, int) or block_budget < 2:
        raise ValueError(f"block_budget doit être un entier ≥ 2 (reçu: {block_budget})")

    budget_pipeline = block_budget - 1
    print(f"[BUDGET] projet = {block_budget}, pipeline = {budget_pipeline}")

    # Fallback surfaces_map vide si non fourni
    if surfaces_map is None:
        surfaces_map = {}

    cfg = mask_config or DEFAULT_MASK_CONFIG

    # Modules 1-4
    dem, cellsize  = load_heightmap_asc(asc_path)
    terrain        = module_terrain(dem, cellsize)
    calibration_auto = _build_calibration(dem, cellsize, terrain['slope'])
    calibration_final = {**calibration_auto, **(calibration or {})}
    print(f"[CALIB] alt={calibration_auto['alt_min']:.1f}→{calibration_auto['alt_max']:.1f}m | "
          f"slope p70/85/90={calibration_auto['slope_p70']:.1f}°/{calibration_auto['slope_p85']:.1f}°/{calibration_auto['slope_p90']:.1f}°")

    masques        = module_masques_base(dem, terrain, calibration_final, gaea_flow, gaea_deposit)
    masques.update(module_vegetation(dem, terrain, calibration_final))

    # Module 5
    masques, zone_a = module_exclusion(masques, exclusion_path)

    # Module 6
    masques = module_normalize(masques, cfg)

    # Module 7
    masques, bloc_map, stats = module_budget(masques, cfg, zone_a, budget_pipeline, grid_w, num_blk, tile_prefix, data_dir)

    # Module 8 — Visualisation
    output_dir.mkdir(parents=True, exist_ok=True)
    visu_path = output_dir / 'pipeline_preview.png'
    bloc_budget_map = {k: v["n_active"] for k, v in bloc_map.items()}  # Zone A uniquement

    # Phase 2 : lire Zone B depuis .ttile si data_dir fourni
    zone_b_colormap = None
    if data_dir and data_dir.exists():
        zone_b_colormap = build_zone_b_colormap(data_dir, cfg, surfaces_map, grid_w, num_blk, tile_prefix, catalog_path)

    module_visualize(masques, cfg, visu_path, budget_pipeline, grid_w, num_blk, zone_a, bloc_budget_map, zone_b_colormap, satmap_path, surfaces_map)

    # Module 9
    result = {
        'bloc_map':  bloc_map,
        'stats':     stats,
        'visu_path': visu_path,
        'masks':     {},
    }

    if mode == 'masks' or mode == 'preview':
        if mode == 'masks':
            module_export_masks(masques, cfg, output_dir / 'masks')
        result['masks'] = {name: output_dir / 'masks' / f"{i+1:02d}_{name}.png"
                           for i, (name, _, _) in enumerate(cfg)}

        if mode == 'preview':
            result['masques'] = masques
            result['dem'] = dem
            result['cfg'] = cfg
            result['calibration_auto'] = calibration_auto
            result['calibration'] = calibration  # valeurs actives (auto + overrides UI)

    return result


# ============================================================================
# MAIN STANDALONE


