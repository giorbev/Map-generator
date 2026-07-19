#!/usr/bin/env python3
"""
pipeline_v3.py — Pipeline unifié de génération de masques terrain
==================================================================
Fusionne mask_generator.py + heightmap_roughness.py

Ordre d'exécution :
  [1] Lecture heightmap .asc
  [2] Enrichissement slope via fBm (SlopeRoughnessProcessor)
  [3] Seuils automatiques depuis percentiles
  [4] Génération masques pente : landes_rocheuses + rock
  [5] Normalisation masques Gaea : flow + deposit + autres
  [6] Post-processing universel (stretch, gamma, weight_min)

Usage:
    python pipeline_v3.py
"""

import numpy as np
import cv2
from pathlib import Path
from scipy.ndimage import uniform_filter

# ============================================================================
# CONFIG — À ADAPTER
# ============================================================================

# --- Chemins ---
ASC_PATH = Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\sources\Terrain_modified5.asc")
EXCLUSION_MASK = Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\masks\masque exclusion.png")
OUTPUT_DIR = Path(r"H:\logiciel perso\Map generator\masks_output")

# --- Résolution de sortie ---
OUTPUT_SIZE = 4097  # pixels (Reforger attend 4097×4097)

# --- Roughness (enrichissement slope) ---
ROUGHNESS_MODE      = "slope_perturb"  # "slope_perturb" | "domain_warp" | "additive" | None
ROUGHNESS_AMPLITUDE = 8.0    # degrés de perturbation max (slope_perturb)
ROUGHNESS_SCALE     = 0.008  # fréquence spatiale du bruit (plus bas = plus large)
ROUGHNESS_OCTAVES   = 6
ROUGHNESS_SEED      = 42
CELL_SIZE           = 4.0    # mètres par pixel (Zimnitrita)

# --- Seuils de pente (None = auto depuis percentiles) ---
THRESHOLD_GENTLE = None   # p70 — début pentes notables
THRESHOLD_LANDES = None   # p85 — landes rocheuses
THRESHOLD_ROCK   = 22.0   # fixe — rock (None = p90)
THRESHOLD_CLIFF  = 26.0   # fixe — falaise (None = p95)

# --- Transitions ---
TRANSITION_WIDTH = 5.0  # largeur zone neutre entre landes et rock (degrés)

# --- Post-processing universel ---
STRETCH_AUTO = True   # étirement percentile [p2..p98]
WEIGHT_MIN   = 0.10   # poids minimum visible Workbench (0.0 = désactivé)

# --- Masques Gaea ---
# Format : (chemin_source, nom_sortie, gamma, cut_low)
# cut_low : percentile de coupure basse [0..1] — met à 0 tout ce qui est
#           en dessous de ce seuil avant le stretch (0.0 = désactivé)
GAEA_MASKS = [
    (Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\masks\flow.png"),    "mask_flow",    0.5, 0.30),
    (Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\masks\deposit.png"), "mask_deposit", 1.0, 0.15),
]
APPLY_EXCLUSION_TO_GAEA = True

# --- Végétation ---
ENABLE_VEGETATION = True   # Active la génération des masques végétation
VEG_MIN_SCORE     = 0.15   # Score minimum pour qu'un pixel soit actif

# --- Normalisation exclusive ---
# Ordre de priorité strict (index 0 = priorité maximale)
# Les masques en tête écrasent les suivants dans les zones de chevauchement
MASK_PRIORITY = [
    "mask_seabed",
    "mask_coastal_flat",
    "mask_coastal_slope",
    "mask_flow",
    "mask_deposit",
    "mask_landes_rocheuses",
    "mask_rock",
    "mask_prairie_humide",
    "mask_prairie_seche",
    "mask_landes_plateau",
    "mask_maquis_landes",
    "mask_alpages",
    "mask_foret_feuillue",
    "mask_foret_coniferes",
]

# --- QTRE ---
QTRE_BLOC_SIZE        = 32    # mètres par bloc LRS2
QTRE_PRESENCE_THRESH  = 0.05  # coverage minimale pour compter un masque actif dans un bloc

# --- Masques côtiers ---
# Bande calculée depuis le trait de côte (dem=0) vers l'intérieur des terres
# La largeur en mètres est convertie en pixels via CELL_SIZE
COASTAL_SEA_LEVEL      = 0.0   # altitude du trait de côte (m)
COASTAL_FLAT_WIDTH     = 40.0  # largeur bande flat (m) — galets/sable
COASTAL_SLOPE_WIDTH    = 60.0  # largeur bande slope (m) — falaises côtières
COASTAL_FLAT_MAX_SLOPE = 10.0  # pente max pour flat (°)
COASTAL_SLOPE_MIN_SLOPE= 15.0  # pente min pour slope (°)

# ============================================================================
# FBM — Fractal Brownian Motion
# ============================================================================

try:
    from noise import pnoise2
    _HAS_PNOISE = True
except ImportError:
    _HAS_PNOISE = False


def _fbm_pnoise(h, w, scale, octaves, seed):
    ox, oy = seed * 1000.17, seed * 999.31
    out = np.empty((h, w), dtype=np.float32)
    for y in range(h):
        for x in range(w):
            out[y, x] = pnoise2(x * scale + ox, y * scale + oy,
                                 octaves=octaves, persistence=0.5, lacunarity=2.0)
    return out


def _fbm_scipy(h, w, scale, octaves, seed):
    rng = np.random.default_rng(seed)
    out = np.zeros((h, w), dtype=np.float32)
    amplitude, frequency = 1.0, 1.0
    sigma_base = max(1, int(1.0 / (scale * max(h, w))))
    for _ in range(octaves):
        layer = rng.standard_normal((h, w)).astype(np.float32)
        sigma = max(0.5, sigma_base / frequency)
        layer = uniform_filter(layer, size=int(sigma * 3) | 1)
        mx = np.abs(layer).max()
        if mx > 0:
            layer /= mx
        out += layer * amplitude
        amplitude *= 0.5
        frequency *= 2.0
    mx = np.abs(out).max()
    return out / mx if mx > 0 else out


def generate_fbm(h, w, scale=0.005, octaves=6, seed=0):
    """Retourne un tableau fBm dans [-1, 1], shape (h, w)."""
    if _HAS_PNOISE:
        return _fbm_pnoise(h, w, scale, octaves, seed)
    return _fbm_scipy(h, w, scale, octaves, seed)


# ============================================================================
# ÉTAPE 1 — LECTURE HEIGHTMAP
# ============================================================================

def read_asc(path: Path) -> tuple:
    print(f"[ASC] Lecture {path.name}...")
    with open(path, 'r') as f:
        ncols    = int(f.readline().split()[1])
        nrows    = int(f.readline().split()[1])
        _xll     = float(f.readline().split()[1])
        _yll     = float(f.readline().split()[1])
        cellsize = float(f.readline().split()[1])
        nodata   = float(f.readline().split()[1])
        data     = [float(x) for line in f for x in line.split()]
    dem = np.array(data, dtype=np.float32).reshape(nrows, ncols)
    dem[dem == nodata] = np.nan
    print(f"  → {ncols}×{nrows}, cellsize={cellsize}m")
    return dem, cellsize


# ============================================================================
# ÉTAPE 2 — SLOPE ENRICHIE
# ============================================================================

def compute_slope_raw(dem: np.ndarray, cellsize: float) -> np.ndarray:
    """Slope brute Zevenbergen & Thorne en degrés."""
    dy, dx = np.gradient(dem.astype(np.float32), cellsize)
    return np.degrees(np.arctan(np.sqrt(dx**2 + dy**2)))


def compute_slope_enriched(dem: np.ndarray, cellsize: float) -> np.ndarray:
    """
    Slope enrichie selon ROUGHNESS_MODE.
    - slope_perturb : slope + bruit fBm (heightmap inchangé)
    - domain_warp   : heightmap déformé avant calcul slope
    - additive      : heightmap + déplacement fBm avant calcul slope
    - None          : slope brute
    """
    if ROUGHNESS_MODE is None:
        slope = compute_slope_raw(dem, cellsize)
        print(f"[SLOPE] Brute — min={np.nanmin(slope):.1f}° max={np.nanmax(slope):.1f}°")
        return slope

    h, w = dem.shape

    if ROUGHNESS_MODE == "slope_perturb":
        print(f"[SLOPE] Enrichissement slope_perturb (amplitude={ROUGHNESS_AMPLITUDE}°)...")
        slope = compute_slope_raw(dem, cellsize)
        noise = generate_fbm(h, w, scale=ROUGHNESS_SCALE,
                              octaves=ROUGHNESS_OCTAVES, seed=ROUGHNESS_SEED)
        slope = slope + noise * ROUGHNESS_AMPLITUDE

    elif ROUGHNESS_MODE == "domain_warp":
        print(f"[SLOPE] Enrichissement domain_warp (strength={ROUGHNESS_AMPLITUDE}px)...")
        from scipy.ndimage import map_coordinates
        ys, xs = np.mgrid[0:h, 0:w]
        wx = generate_fbm(h, w, scale=ROUGHNESS_SCALE,
                          octaves=ROUGHNESS_OCTAVES, seed=ROUGHNESS_SEED)
        wy = generate_fbm(h, w, scale=ROUGHNESS_SCALE,
                          octaves=ROUGHNESS_OCTAVES, seed=ROUGHNESS_SEED + 99)
        src_x = np.clip(xs + wx * ROUGHNESS_AMPLITUDE, 0, w - 1)
        src_y = np.clip(ys + wy * ROUGHNESS_AMPLITUDE, 0, h - 1)
        dem_w = map_coordinates(dem.astype(np.float64),
                                [src_y.ravel(), src_x.ravel()],
                                order=1, mode="nearest").reshape(h, w)
        slope = compute_slope_raw(dem_w.astype(np.float32), cellsize)

    elif ROUGHNESS_MODE == "additive":
        print(f"[SLOPE] Enrichissement additive (amplitude={ROUGHNESS_AMPLITUDE}m)...")
        noise = generate_fbm(h, w, scale=ROUGHNESS_SCALE,
                              octaves=ROUGHNESS_OCTAVES, seed=ROUGHNESS_SEED)
        slope_norm = compute_slope_raw(dem, cellsize)
        slope_norm = slope_norm / max(slope_norm.max(), 1e-9)
        noise = noise * (slope_norm ** 1.5)
        dem_r = dem.astype(np.float32) + noise * ROUGHNESS_AMPLITUDE
        slope = compute_slope_raw(dem_r, cellsize)

    else:
        raise ValueError(f"ROUGHNESS_MODE inconnu : {ROUGHNESS_MODE!r}")

    print(f"  → min={np.nanmin(slope):.1f}° max={np.nanmax(slope):.1f}° "
          f"moy={np.nanmean(slope):.1f}°")
    return slope


# ============================================================================
# ÉTAPE 3 — SEUILS AUTOMATIQUES
# ============================================================================

def compute_thresholds(slope: np.ndarray) -> dict:
    global THRESHOLD_GENTLE, THRESHOLD_LANDES, THRESHOLD_ROCK, THRESHOLD_CLIFF

    p = {pct: round(float(np.nanpercentile(slope, pct)), 1)
         for pct in [70, 85, 90, 95]}

    if THRESHOLD_GENTLE is None: THRESHOLD_GENTLE = p[70]
    if THRESHOLD_LANDES is None: THRESHOLD_LANDES = p[85]
    if THRESHOLD_ROCK   is None: THRESHOLD_ROCK   = p[90]
    if THRESHOLD_CLIFF  is None: THRESHOLD_CLIFF  = p[95]

    t = dict(gentle=THRESHOLD_GENTLE, landes=THRESHOLD_LANDES,
             rock=THRESHOLD_ROCK, cliff=THRESHOLD_CLIFF)

    print(f"[SEUILS] gentle={t['gentle']}° (p70)  landes={t['landes']}° (p85)"
          f"  rock={t['rock']}° (p90)  cliff={t['cliff']}° (p95)")
    return t


# ============================================================================
# UTILITAIRES
# ============================================================================

def load_and_normalize_mask(path: Path, out_size: int) -> np.ndarray:
    """Charge un masque PNG (8/16/float32) → float32 [0..1], redimensionné."""
    raw = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if raw is None:
        raise FileNotFoundError(f"Masque introuvable: {path}")
    if raw.ndim == 3:
        raw = cv2.cvtColor(raw, cv2.COLOR_BGR2GRAY)
    if raw.dtype == np.uint8:
        mask = raw.astype(np.float32) / 255.0
    elif raw.dtype == np.uint16:
        mask = raw.astype(np.float32) / 65535.0
    elif raw.dtype == np.float32:
        mask = raw.copy()
        if mask.max() > 1.0:
            mask /= mask.max()
    else:
        mask = raw.astype(np.float32) / max(raw.max(), 1.0)
    if mask.shape[0] != out_size or mask.shape[1] != out_size:
        mask = cv2.resize(mask, (out_size, out_size), interpolation=cv2.INTER_LINEAR)
    return np.clip(mask, 0, 1)


def save_mask_16bit(mask_f32: np.ndarray, path: Path):
    """Sauvegarde float32 [0..1] → PNG 16 bits."""
    mask_16 = (np.clip(mask_f32, 0, 1) * 65535).astype(np.uint16)
    cv2.imwrite(str(path), mask_16)
    print(f"  [OK] {path.name:<40} — {(mask_f32 > 0).sum() / mask_f32.size * 100:.1f}% actif")


def apply_output_curve(mask: np.ndarray, gamma: float = 1.0,
                       cut_low: float = 0.0) -> np.ndarray:
    """Post-processing universel : cut_low → stretch percentile → gamma → weight_min."""
    # 0. Coupure basse — met à 0 tout ce qui est sous le seuil
    if cut_low > 0:
        threshold = np.percentile(mask[mask > 0], cut_low * 100) if (mask > 0).any() else 0
        mask = np.where(mask >= threshold, mask, 0.0)

    if STRETCH_AUTO:
        active = mask[mask > 0]
        if active.size > 0:
            lo = np.percentile(active, 2)
            hi = np.percentile(mask, 98)
            if hi > lo:
                mask = np.clip((mask - lo) / (hi - lo), 0, 1)

    if gamma != 1.0:
        mask = np.power(np.clip(mask, 0, 1), gamma)

    if WEIGHT_MIN > 0:
        mask = np.where(mask > 0, WEIGHT_MIN + mask * (1.0 - WEIGHT_MIN), 0.0)

    return np.clip(mask, 0, 1)


def resize_if_needed(arr: np.ndarray, out_size: int) -> np.ndarray:
    if arr.shape[0] != out_size or arr.shape[1] != out_size:
        return cv2.resize(arr, (out_size, out_size), interpolation=cv2.INTER_LINEAR)
    return arr


# ============================================================================
# ÉTAPE 4 — MASQUES DE PENTE
# ============================================================================

def generate_slope_masks(slope: np.ndarray, t: dict,
                          exclusion: np.ndarray, out_size: int,
                          output_dir: Path):
    """Génère mask_landes_rocheuses.png + mask_rock.png."""

    slope = resize_if_needed(slope, out_size)

    GAP         = TRANSITION_WIDTH
    landes_end  = max(t['landes'], t['rock'] - GAP / 2)
    rock_start  = t['rock'] + GAP / 2

    # --- LANDES ROCHEUSES ---
    landes = np.zeros((out_size, out_size), dtype=np.float32)
    m_rise = (slope >= t['gentle']) & (slope < t['landes'])
    landes[m_rise] = (slope[m_rise] - t['gentle']) / (t['landes'] - t['gentle'])
    landes[(slope >= t['landes']) & (slope < landes_end)] = 1.0
    m_fall = (slope >= landes_end) & (slope < t['rock'])
    landes[m_fall] = 1.0 - (slope[m_fall] - landes_end) / (t['rock'] - landes_end)
    landes[exclusion == 0] = 0.0
    landes = apply_output_curve(landes)
    save_mask_16bit(landes, output_dir / "mask_landes_rocheuses.png")
    print(f"       gentle({t['gentle']}°) → plein({t['landes']}°) → neutre({landes_end:.1f}°)")

    # --- ROCK ---
    rock = np.zeros((out_size, out_size), dtype=np.float32)
    m_rise_r = (slope >= rock_start) & (slope < t['cliff'])
    rock[m_rise_r] = (slope[m_rise_r] - rock_start) / (t['cliff'] - rock_start)
    rock[slope >= t['cliff']] = 1.0
    rock[exclusion == 0] = 0.0
    rock = apply_output_curve(rock)
    save_mask_16bit(rock, output_dir / "mask_rock.png")
    print(f"       neutre → montée({rock_start:.1f}°) → plein({t['cliff']}°)")


# ============================================================================
# ÉTAPE 4b — MASQUE SEABED
# ============================================================================

def generate_seabed_mask(dem: np.ndarray, out_size: int, output_dir: Path,
                          sea_level: float = 0.0, transition: float = 2.0):
    """
    Génère mask_seabed.png — zones sous le niveau de la mer.

    dem <= sea_level - transition : 1.0 (plein fond marin)
    sea_level - transition → sea_level : transition douce 1→0
    dem > sea_level : 0.0

    Pas de masque d'exclusion — couvre toute la carte.
    Pas d'apply_output_curve — masque binaire/semi-binaire brut.
    """
    dem_r = resize_if_needed(dem, out_size)

    seabed = np.zeros((out_size, out_size), dtype=np.float32)

    # Zone pleine : sous sea_level - transition
    seabed[dem_r <= sea_level - transition] = 1.0

    # Transition douce : [sea_level - transition .. sea_level]
    if transition > 0:
        m_trans = (dem_r > sea_level - transition) & (dem_r <= sea_level)
        seabed[m_trans] = 1.0 - (dem_r[m_trans] - (sea_level - transition)) / transition

    # Appliquer weight_min sur les pixels actifs
    if WEIGHT_MIN > 0:
        seabed = np.where(seabed > 0, WEIGHT_MIN + seabed * (1.0 - WEIGHT_MIN), 0.0)

    seabed = np.clip(seabed, 0, 1)
    save_mask_16bit(seabed, output_dir / "mask_seabed.png")
    pct_full = (dem_r <= sea_level - transition).sum() / dem_r.size * 100
    pct_trans = ((dem_r > sea_level - transition) & (dem_r <= sea_level)).sum() / dem_r.size * 100
    print(f"       plein={pct_full:.1f}%  transition={pct_trans:.1f}%  "
          f"(sea_level={sea_level}m  transition={transition}m)")



# ============================================================================
# ÉTAPE 4c — MASQUES CÔTIERS
# ============================================================================

def generate_coastal_masks(dem: np.ndarray, slope: np.ndarray,
                            out_size: int, output_dir: Path):
    """
    Génère deux masques côtiers depuis le trait de côte (dem=COASTAL_SEA_LEVEL)
    vers l'intérieur des terres :

      mask_coastal_flat  — zones plates  (slope < COASTAL_FLAT_MAX_SLOPE)
      mask_coastal_slope — zones pentues (slope > COASTAL_SLOPE_MIN_SLOPE)

    Transition douce sur toute la largeur de la bande.
    Pas de masque d'exclusion — couvre toute la carte.
    """
    from scipy.ndimage import distance_transform_edt

    dem_r   = resize_if_needed(dem,   out_size)
    slope_r = resize_if_needed(slope, out_size)

    # Distance en pixels de chaque pixel terrestre au pixel marin le plus proche
    land_mask = (dem_r > COASTAL_SEA_LEVEL).astype(np.uint8)
    dist_px   = distance_transform_edt(land_mask)

    # --- COASTAL FLAT ---
    flat_w_px  = COASTAL_FLAT_WIDTH / CELL_SIZE
    band_flat  = np.zeros((out_size, out_size), dtype=np.float32)
    in_band_f  = (dist_px > 0) & (dist_px <= flat_w_px)
    band_flat[in_band_f] = 1.0 - (dist_px[in_band_f] / flat_w_px)
    # Gate slope : actif seulement là où slope < COASTAL_FLAT_MAX_SLOPE
    flat_gate     = (slope_r < COASTAL_FLAT_MAX_SLOPE).astype(np.float32)
    coastal_flat  = band_flat * flat_gate
    if WEIGHT_MIN > 0:
        coastal_flat = np.where(coastal_flat > 0,
                                WEIGHT_MIN + coastal_flat * (1.0 - WEIGHT_MIN), 0.0)
    save_mask_16bit(np.clip(coastal_flat, 0, 1), output_dir / "mask_coastal_flat.png")
    print(f"       flat  : largeur={COASTAL_FLAT_WIDTH}m  slope<{COASTAL_FLAT_MAX_SLOPE}°  "
          f"{(coastal_flat > 0).sum() / coastal_flat.size * 100:.1f}% actif")

    # --- COASTAL SLOPE ---
    slope_w_px    = COASTAL_SLOPE_WIDTH / CELL_SIZE
    band_slope    = np.zeros((out_size, out_size), dtype=np.float32)
    in_band_s     = (dist_px > 0) & (dist_px <= slope_w_px)
    band_slope[in_band_s] = 1.0 - (dist_px[in_band_s] / slope_w_px)
    # Gate slope : transition douce au-dessus de COASTAL_SLOPE_MIN_SLOPE
    slope_gate    = np.clip((slope_r - COASTAL_SLOPE_MIN_SLOPE) / 5.0, 0, 1)
    coastal_slope = band_slope * slope_gate
    if WEIGHT_MIN > 0:
        coastal_slope = np.where(coastal_slope > 0,
                                 WEIGHT_MIN + coastal_slope * (1.0 - WEIGHT_MIN), 0.0)
    save_mask_16bit(np.clip(coastal_slope, 0, 1), output_dir / "mask_coastal_slope.png")
    print(f"       slope : largeur={COASTAL_SLOPE_WIDTH}m  slope>{COASTAL_SLOPE_MIN_SLOPE}°  "
          f"{(coastal_slope > 0).sum() / coastal_slope.size * 100:.1f}% actif")


def process_gaea_masks(gaea_masks: list, exclusion: np.ndarray,
                        out_size: int, output_dir: Path):
    """Charge, normalise et sauvegarde les masques Gaea en 16 bits."""
    for entry in gaea_masks:
        if len(entry) == 4:
            src_path, out_name, gamma, cut_low = entry
        elif len(entry) == 3:
            src_path, out_name, gamma = entry
            cut_low = 0.0
        else:
            src_path, out_name = entry
            gamma, cut_low = 1.0, 0.0

        if not src_path.exists():
            print(f"  [SKIP] {src_path.name} introuvable")
            continue
        mask = load_and_normalize_mask(src_path, out_size)
        if APPLY_EXCLUSION_TO_GAEA:
            mask[exclusion == 0] = 0.0
        mask = apply_output_curve(mask, gamma=gamma, cut_low=cut_low)
        save_mask_16bit(mask, output_dir / f"{out_name}.png")
        print(f"       gamma={gamma}  cut_low={cut_low}  stretch={STRETCH_AUTO}  weight_min={WEIGHT_MIN}")


# ============================================================================
# ÉTAPE 6 — MASQUES VÉGÉTATION (depuis vegetation_map.py)
# ============================================================================

def generate_vegetation_masks(dem: np.ndarray, slope: np.ndarray,
                               exclusion: np.ndarray, cellsize: float,
                               out_size: int, output_dir: Path) -> dict:
    """
    Génère les masques de végétation depuis les signaux terrain.
    Retourne un dict {nom_masque: array_float32} pour la normalisation.

    Masques générés :
        mask_foret_feuillue, mask_foret_coniferes,
        mask_maquis_landes, mask_landes_plateau,
        mask_prairie_humide, mask_prairie_seche, mask_alpages
    """
    from scipy.ndimage import gaussian_filter

    print("[VEG] Calcul signaux terrain...")
    dem_r   = resize_if_needed(dem,   out_size).astype(np.float32)
    slope_r = resize_if_needed(slope, out_size).astype(np.float32)

    # --- Signaux dérivés ---
    dy, dx = np.gradient(dem_r, cellsize)
    aspect = np.degrees(np.arctan2(-dy, dx)) % 360

    # Curvature simple
    c = cellsize
    curv_x = (np.roll(dem_r, -1, axis=1) - 2*dem_r + np.roll(dem_r, 1, axis=1)) / c**2
    curv_y = (np.roll(dem_r, -1, axis=0) - 2*dem_r + np.roll(dem_r, 1, axis=0)) / c**2
    curvature = np.clip((curv_x + curv_y) / (np.abs(curv_x + curv_y).max() + 1e-9), -1, 1)

    # TPI local (rayon 5px) et macro (rayon 25px)
    from scipy.ndimage import uniform_filter as uf
    tpi_local = dem_r - uf(dem_r, size=10)
    tpi_macro = dem_r - uf(dem_r, size=50)
    tpi_local = np.clip(tpi_local / (np.abs(tpi_local).max() + 1e-9), -1, 1)
    tpi_macro = np.clip(tpi_macro / (np.abs(tpi_macro).max() + 1e-9), -1, 1)

    # Flow proxy depuis curvature concave + slope
    flow = np.clip(-curvature * 0.5 + (1 - slope_r / (slope_r.max() + 1e-9)) * 0.5, 0, 1)

    # Distance côte (proxy : distance aux zones < 0)
    from scipy.ndimage import distance_transform_edt
    sea = (dem_r <= 0).astype(np.uint8)
    land_px = distance_transform_edt(1 - sea)
    distance_cote = land_px * cellsize

    # Params auto-calibrés depuis le DEM
    land_mask = dem_r > 0
    alt_min = float(np.nanmin(dem_r[land_mask])) if land_mask.any() else 0
    alt_max = float(np.nanmax(dem_r[land_mask])) if land_mask.any() else 500
    params = {
        'grass_low_max_m':      min(40,  alt_max * 0.15),
        'grass_mid_max_m':      min(100, alt_max * 0.35),
        'grass_high_max_m':     min(170, alt_max * 0.60),
        'debris_min_deg':       18.0,
        'rock_min_deg':         28.0,
        'coastal_alt_max_m':    15.0,
        'coastal_distance_max_m': 60.0,
    }

    # --- Facteurs de base ---
    def _bell(arr, lo, hi, slope=10.0):
        center = (lo + hi) / 2.0
        half = (hi - lo) / 2.0 + 1e-6
        dist = np.abs(arr - center) - half
        return np.clip(1.0 - dist / (slope + 1e-6), 0.0, 1.0)

    debris_min = params['debris_min_deg']
    rock_min   = params['rock_min_deg']
    g_low      = params['grass_low_max_m']
    g_mid      = params['grass_mid_max_m']
    g_high     = params['grass_high_max_m']

    alt_pine      = _bell(dem_r, 0, 250, slope=40)
    alt_deciduous = _bell(dem_r, 150, 400, slope=50)
    alt_low       = np.clip(1 - (dem_r - alt_min) / (g_low - alt_min + 1), 0, 1)
    alt_mid       = _bell(dem_r, g_low, g_mid, slope=20)
    alt_high      = _bell(dem_r, g_mid, g_high, slope=30)

    flat   = np.clip(1 - slope_r / (debris_min + 1e-9), 0, 1)
    gentle = _bell(slope_r, 5, debris_min, slope=5)
    steep  = np.clip((slope_r - debris_min) / (rock_min - debris_min + 1), 0, 1)
    rocky  = np.clip((slope_r - rock_min) / 20, 0, 1)

    north   = np.cos(np.radians(aspect))
    north_f = np.clip((north + 1) / 2, 0, 1)
    south_f = np.clip((-north + 1) / 2, 0, 1)

    dist_w_norm = np.clip(distance_cote / 500, 0, 1)
    humid = np.clip(flow * 0.6 + (1 - dist_w_norm) * 0.4, 0, 1)
    dry   = np.clip(1 - humid, 0, 1)

    tpi_neg     = np.clip(-tpi_local, 0, 1)
    tpi_pos     = np.clip(tpi_local,  0, 1)
    tpi_mac_pos = np.clip(tpi_macro,  0, 1)

    coastal     = ((distance_cote < params['coastal_distance_max_m']) &
                   (dem_r < params['coastal_alt_max_m'])).astype(np.float32)
    non_coastal = 1 - coastal
    land        = land_mask.astype(np.float32)

    coastal_zone = np.clip(1 - distance_cote / 800, 0, 1)
    interior     = np.clip((distance_cote - 600) / 1200, 0, 1)

    # --- Scores végétation ---
    VEG_ACTIVE = {
        "foret_coniferes": (
            alt_pine * (coastal_zone * 0.7 + (1 - interior) * 0.3) * non_coastal * land
            * (0.5 + south_f * 0.30 + dry * 0.15 + rocky * 0.10)
            * (flat * 0.6 + gentle * 0.4)
        ),
        "foret_feuillue": (
            alt_deciduous * (interior * 0.7 + (1 - coastal_zone) * 0.3) * non_coastal * land
            * (0.5 + north_f * 0.30 + humid * 0.15 + (1 - rocky) * 0.10)
            * (flat * 0.6 + gentle * 0.4)
        ),
        "maquis_landes": (
            alt_mid * south_f * dry * gentle
            * np.clip(1 - tpi_mac_pos * 0.3, 0.5, 1.0)
            * non_coastal * land
        ),
        "landes_plateau": (
            alt_mid * (0.5 + 0.5 * tpi_mac_pos) * (0.5 + 0.5 * dry)
            * (flat * 0.8 + gentle * 0.2) * non_coastal * land
        ),
        "prairie_humide": (
            alt_low * flat * non_coastal * land
            * (0.6 + humid * 0.8 + flow * 0.3 + tpi_neg * 0.2)
        ),
        "prairie_seche": (
            ((alt_low + alt_mid) * 0.5) * flat * non_coastal * land
            * (0.5 + dry * 0.6 + tpi_pos * 0.3 + south_f * 0.2)
        ),
        "alpages": (
            np.clip((dem_r - 180) / 80, 0, 1) * (flat * 0.7 + gentle * 0.3) * land
            * (0.7 + tpi_mac_pos * 0.4 + (1 - steep) * 0.2)
        ),
    }

    # Lissage spatial
    SIGMA = {"foret_coniferes": 2.5, "foret_feuillue": 2.5,
             "maquis_landes": 2.0, "landes_plateau": 2.0,
             "prairie_humide": 2.0, "prairie_seche": 2.0, "alpages": 2.5}

    results = {}
    print("[VEG] Génération masques végétation...")
    for name, arr in VEG_ACTIVE.items():
        arr = gaussian_filter(arr.astype(np.float32), sigma=SIGMA.get(name, 2.0))
        arr = np.clip(arr, 0, 1)
        arr[exclusion == 0] = 0.0
        # Appliquer seuil min score
        arr = np.where(arr >= VEG_MIN_SCORE, arr, 0.0)
        results[f"mask_{name}"] = arr

    return results


# ============================================================================
# ÉTAPE 7 — NORMALISATION EXCLUSIVE (blend avec transitions douces)
# ============================================================================

def normalize_exclusive(all_masks: dict, priority: list,
                         out_size: int, output_dir: Path):
    """
    Normalise tous les masques pour qu'ils ne se superposent pas,
    tout en conservant des transitions douces.

    Algorithme :
      Pour chaque pixel, calculer la somme des scores actifs.
      Redistribuer proportionnellement mais en respectant la priorité :
      les masques prioritaires conservent leur score, les suivants
      sont réduits de ce qui a déjà été alloué.

    Sauvegarde les masques normalisés (écrase les fichiers générés).
    """
    print("\n[NORM] Normalisation exclusive des masques...")

    # Charger tous les masques dans l'ordre de priorité
    loaded = {}
    for name in priority:
        path = output_dir / f"{name}.png"
        if path.exists():
            raw = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
            if raw is not None:
                loaded[name] = raw.astype(np.float32) / 65535.0
        elif name in all_masks:
            loaded[name] = all_masks[name]

    if not loaded:
        print("  [SKIP] Aucun masque trouvé")
        return

    # Passe de normalisation : budget restant par pixel
    budget = np.ones((out_size, out_size), dtype=np.float32)
    normalized = {}

    for name in priority:
        if name not in loaded:
            continue
        mask = loaded[name].copy()
        # Appliquer le budget restant
        mask_out = np.minimum(mask, budget)
        budget   = np.maximum(budget - mask_out, 0.0)
        normalized[name] = mask_out

    # Sauvegarder les masques normalisés
    for name, mask in normalized.items():
        pct = (mask > 0).sum() / mask.size * 100
        save_mask_16bit(mask, output_dir / f"{name}.png")
        print(f"  [NORM] {name:<35} — {pct:.1f}% actif")


# ============================================================================
# ÉTAPE 8 — VÉRIFICATION BUDGET QTRE
# ============================================================================

def check_qtre(output_dir: Path, priority: list, cellsize: float):
    """
    Analyse le budget QTRE par bloc LRS2 (32×32m).
    Compte le nombre de masques actifs par bloc et signale les dépassements.
    """
    print("\n[QTRE] Analyse budget par bloc...")

    bloc_px = max(1, int(QTRE_BLOC_SIZE / cellsize))

    # Charger tous les masques normalisés
    masks = {}
    for name in priority:
        path = output_dir / f"{name}.png"
        if path.exists():
            raw = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
            if raw is not None:
                masks[name] = raw.astype(np.float32) / 65535.0

    if not masks:
        print("  [SKIP] Aucun masque trouvé")
        return

    first = next(iter(masks.values()))
    H, W = first.shape
    n_blocs_y = H // bloc_px
    n_blocs_x = W // bloc_px
    total_blocs = n_blocs_y * n_blocs_x

    print(f"  Bloc: {bloc_px}×{bloc_px}px ({QTRE_BLOC_SIZE}m)  "
          f"Grille: {n_blocs_y}×{n_blocs_x} = {total_blocs} blocs")

    density_map = np.zeros((n_blocs_y, n_blocs_x), dtype=np.uint8)

    for by in range(n_blocs_y):
        for bx in range(n_blocs_x):
            y0, x0 = by * bloc_px, bx * bloc_px
            y1, x1 = y0 + bloc_px, x0 + bloc_px
            active = 0
            for name, mask in masks.items():
                if name == "mask_seabed":
                    continue
                if np.mean(mask[y0:y1, x0:x1]) > QTRE_PRESENCE_THRESH:
                    active += 1
            density_map[by, bx] = active

    # Distribution
    max_d = int(density_map.max())
    print(f"\n  Distribution (w0 implicite non compté) :")
    blocs_ok = blocs_lim = blocs_crit = 0
    for d in range(max_d + 1):
        count = int((density_map == d).sum())
        pct   = count / total_blocs * 100
        if d <= 3:
            status = "[OK]"
            blocs_ok += count
        elif d <= 5:
            status = "[LIMITE]"
            blocs_lim += count
        else:
            status = "[CRITIQUE]"
            blocs_crit += count
        print(f"    {d} tex/bloc: {count:6} blocs ({pct:5.1f}%) {status}")

    pct_ok   = blocs_ok   / total_blocs * 100
    pct_crit = blocs_crit / total_blocs * 100
    verdict  = ("OK"       if pct_ok >= 85 and pct_crit < 1 else
                "ATTENTION" if pct_ok >= 70 else "CRITIQUE")

    print(f"\n  Budget QTRE :")
    print(f"    OK (≤3)      : {blocs_ok:6} ({pct_ok:.1f}%)")
    print(f"    Limite (4-5) : {blocs_lim:6} ({blocs_lim/total_blocs*100:.1f}%)")
    print(f"    Critique (6+): {blocs_crit:6} ({pct_crit:.1f}%)")
    print(f"    → Verdict : {verdict}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

    print("=" * 70)
    print("PIPELINE V3 — Masques terrain Reforger")
    print(f"  Roughness : {ROUGHNESS_MODE or 'désactivé'}")
    print(f"  Stretch   : {STRETCH_AUTO}   Weight_min : {WEIGHT_MIN}")
    print(f"  Végétation: {'activée' if ENABLE_VEGETATION else 'désactivée'}")
    print(f"  Sortie    : {OUTPUT_SIZE}×{OUTPUT_SIZE} px  →  {OUTPUT_DIR}")
    print("=" * 70)

    # [1] Heightmap
    dem, cellsize = read_asc(ASC_PATH)

    # [2] Slope enrichie
    slope = compute_slope_enriched(dem, cellsize)

    # [3] Seuils
    t = compute_thresholds(slope)

    # [4] Masque d'exclusion
    if EXCLUSION_MASK and EXCLUSION_MASK.exists():
        excl_raw  = load_and_normalize_mask(EXCLUSION_MASK, OUTPUT_SIZE)
        exclusion = (excl_raw > 0.5).astype(np.uint8)
        print(f"[EXCL] {exclusion.mean()*100:.1f}% actif")
    else:
        exclusion = np.ones((OUTPUT_SIZE, OUTPUT_SIZE), dtype=np.uint8)
        print("[EXCL] Pas de masque d'exclusion — toute la carte active")

    # [5] Masques pente
    print(f"\n[PENTE] Génération landes + rock...")
    generate_slope_masks(slope, t, exclusion, OUTPUT_SIZE, OUTPUT_DIR)

    # [6] Masque seabed
    print(f"\n[SEABED] Génération masque fond marin...")
    generate_seabed_mask(dem, OUTPUT_SIZE, OUTPUT_DIR, sea_level=0.0, transition=2.0)

    # [7] Masques côtiers
    print(f"\n[COASTAL] Génération masques côtiers...")
    generate_coastal_masks(dem, slope, OUTPUT_SIZE, OUTPUT_DIR)

    # [8] Masques Gaea
    if GAEA_MASKS:
        print(f"\n[GAEA] {len(GAEA_MASKS)} masque(s)...")
        process_gaea_masks(GAEA_MASKS, exclusion, OUTPUT_SIZE, OUTPUT_DIR)

    # [9] Masques végétation
    veg_masks = {}
    if ENABLE_VEGETATION:
        veg_masks = generate_vegetation_masks(
            dem, slope, exclusion, cellsize, OUTPUT_SIZE, OUTPUT_DIR)
        # Sauvegarder avant normalisation
        for name, mask in veg_masks.items():
            mask = apply_output_curve(mask)
            save_mask_16bit(mask, OUTPUT_DIR / f"{name}.png")

    # [10] Normalisation exclusive
    normalize_exclusive(veg_masks, MASK_PRIORITY, OUTPUT_SIZE, OUTPUT_DIR)

    # [11] QTRE
    check_qtre(OUTPUT_DIR, MASK_PRIORITY, cellsize)

    print(f"\n{'='*70}")
    print(f"✅ Pipeline v3 terminé → {OUTPUT_DIR}")
    print(f"   Seuils : gentle={t['gentle']}°  landes={t['landes']}°  "
          f"rock={t['rock']}°  cliff={t['cliff']}°")
    print(f"   Roughness : {ROUGHNESS_MODE or 'None'}  "
          f"amplitude={ROUGHNESS_AMPLITUDE}  scale={ROUGHNESS_SCALE}")


if __name__ == '__main__':
    main()
