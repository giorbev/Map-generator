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
# MAIN
# ============================================================================

def main():
    OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

    print("=" * 70)
    print("PIPELINE V3 — Masques terrain Reforger")
    print(f"  Roughness : {ROUGHNESS_MODE or 'désactivé'}")
    print(f"  Stretch   : {STRETCH_AUTO}   Weight_min : {WEIGHT_MIN}")
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
        excl_raw   = load_and_normalize_mask(EXCLUSION_MASK, OUTPUT_SIZE)
        exclusion  = (excl_raw > 0.5).astype(np.uint8)
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

    # [7] Masques Gaea
    if GAEA_MASKS:
        print(f"\n[GAEA] {len(GAEA_MASKS)} masque(s)...")
        process_gaea_masks(GAEA_MASKS, exclusion, OUTPUT_SIZE, OUTPUT_DIR)

    print(f"\n{'='*70}")
    print(f"✅ Pipeline v3 terminé → {OUTPUT_DIR}")
    print(f"   Seuils : gentle={t['gentle']}°  landes={t['landes']}°  "
          f"rock={t['rock']}°  cliff={t['cliff']}°")
    print(f"   Roughness : {ROUGHNESS_MODE or 'None'}  "
          f"amplitude={ROUGHNESS_AMPLITUDE}  scale={ROUGHNESS_SCALE}")


if __name__ == '__main__':
    main()
