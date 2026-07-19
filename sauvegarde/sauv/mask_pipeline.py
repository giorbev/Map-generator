#!/usr/bin/env python3
"""
mask_pipeline.py - Pipeline unifié de génération de masques terrain
pour Arma Reforger / Enfusion (Zimnitrita)

Génère des masques PNG 16 bits mutuellement exclusifs avec :
  - Hiérarchie de priorité stricte
  - Transitions douces entre zones adjacentes
  - Worley noise pour les zones herbeuses
  - Masque côtier (distance + altitude + pente)
  - Intégration masques Gaea (flow, deposit)

Usage:
    python mask_pipeline.py
"""

import numpy as np
import cv2
from pathlib import Path
from scipy.ndimage import gaussian_filter
from scipy.spatial import cKDTree

# ============================================================================
# CONFIG
# ============================================================================

ASC_PATH        = Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\sources\Terrain_modified5.asc")
EXCLUSION_MASK  = Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\masks\masque exclusion.png")
OUTPUT_DIR      = Path(r"H:\logiciel perso\Map generator\masks_output")
OUTPUT_SIZE     = 4097

# Masques Gaea externes
GAEA_FLOW    = Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\masks\flow.png")
GAEA_DEPOSIT = Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\masks\deposit.png")

# Seuils de pente (None = auto percentiles)
THRESHOLD_GENTLE = None   # p70
THRESHOLD_LANDES = None   # p85
THRESHOLD_ROCK   = None   # p90
THRESHOLD_CLIFF  = None   # p95

# Largeur transitions (degrés pour pente, mètres pour distance)
TRANS_SLOPE = 2.5   # étroit = 2-3°
TRANS_DIST  = 25.0  # étroit = 20-30m

# Masque côtier
COASTAL_ALT_MAX  = 15.0   # m
COASTAL_DIST_MAX = 100.0  # m
COASTAL_SLOPE_MAX = 8.0   # ° (plages = pente douce)

# Worley noise
NOISE_SCALE      = 0.003   # fréquence spatiale
NOISE_AMPLITUDE  = 0.18    # amplitude (0=pas de bruit)
NOISE_SEED       = 42

# ============================================================================
# LECTURE DU HEIGHTMAP
# ============================================================================

def read_asc(path: Path) -> tuple:
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
    print(f"  → {ncols}×{nrows}, cellsize={cellsize}m, alt [{np.nanmin(dem):.0f}m, {np.nanmax(dem):.0f}m]")
    return dem, cellsize

# ============================================================================
# SIGNAUX TERRAIN
# ============================================================================

def compute_slope(dem: np.ndarray, cellsize: float) -> np.ndarray:
    print("[SLOPE] Calcul des pentes...")
    dz_dx = (np.roll(dem, -1, axis=1) - np.roll(dem, 1, axis=1)) / (2 * cellsize)
    dz_dy = (np.roll(dem, -1, axis=0) - np.roll(dem, 1, axis=0)) / (2 * cellsize)
    dz_dx[:, 0]  = (dem[:, 1]  - dem[:, 0])  / cellsize
    dz_dx[:, -1] = (dem[:, -1] - dem[:, -2]) / cellsize
    dz_dy[0, :]  = (dem[1, :]  - dem[0, :])  / cellsize
    dz_dy[-1, :] = (dem[-1, :] - dem[-2, :]) / cellsize
    slope = np.degrees(np.arctan(np.sqrt(dz_dx**2 + dz_dy**2)))
    print(f"  → min={np.nanmin(slope):.1f}° max={np.nanmax(slope):.1f}°")
    return slope

def compute_distance_to_coast(dem: np.ndarray, cellsize: float) -> np.ndarray:
    print("[COAST] Calcul distance à la côte...")
    land = (dem > 0) & ~np.isnan(dem)
    water = ~land
    # Distance transform depuis les pixels eau
    from scipy.ndimage import distance_transform_edt
    dist_pixels = distance_transform_edt(land)  # distance depuis le bord terre→eau
    dist_m = dist_pixels * cellsize
    dist_m[water] = 0
    print(f"  → max distance côtière: {dist_m.max():.0f}m")
    return dist_m.astype(np.float32)

def compute_thresholds(slope: np.ndarray) -> dict:
    global THRESHOLD_GENTLE, THRESHOLD_LANDES, THRESHOLD_ROCK, THRESHOLD_CLIFF
    p = {pct: round(float(np.nanpercentile(slope, pct)), 1) for pct in [70, 85, 90, 95]}
    if THRESHOLD_GENTLE is None: THRESHOLD_GENTLE = p[70]
    if THRESHOLD_LANDES is None: THRESHOLD_LANDES = p[85]
    if THRESHOLD_ROCK   is None: THRESHOLD_ROCK   = p[90]
    if THRESHOLD_CLIFF  is None: THRESHOLD_CLIFF  = p[95]
    t = dict(gentle=THRESHOLD_GENTLE, landes=THRESHOLD_LANDES,
             rock=THRESHOLD_ROCK, cliff=THRESHOLD_CLIFF)
    print(f"[SEUILS] gentle={t['gentle']}° landes={t['landes']}° rock={t['rock']}° cliff={t['cliff']}°")
    return t

# ============================================================================
# WORLEY NOISE
# ============================================================================

def worley_noise_2d(shape: tuple, scale: float, seed: int = 42) -> np.ndarray:
    """Génère un Worley noise 2D normalisé [0..1]."""
    print(f"[NOISE] Génération Worley noise ({shape[0]}×{shape[1]})...")
    rng = np.random.default_rng(seed)
    H, W = shape

    # Points aléatoires dans l'espace normalisé
    n_points = max(100, int(H * W * scale * scale * 4))
    n_points = min(n_points, 5000)
    pts = rng.random((n_points, 2))
    pts[:, 0] *= H
    pts[:, 1] *= W

    # Distance au plus proche voisin
    tree = cKDTree(pts)
    yy, xx = np.mgrid[0:H, 0:W]
    coords = np.column_stack([yy.ravel(), xx.ravel()])
    dists, _ = tree.query(coords, k=1)
    dists = dists.reshape(H, W).astype(np.float32)

    # Normaliser [0..1]
    dists = (dists - dists.min()) / (dists.max() - dists.min() + 1e-6)
    print(f"  → {n_points} points, noise généré")
    return dists

# ============================================================================
# UTILITAIRES MASQUES
# ============================================================================

def load_mask(path: Path, out_size: int) -> np.ndarray:
    """Charge un masque PNG (any depth) → float32 [0..1] à out_size."""
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
    if m.shape[0] != out_size:
        m = cv2.resize(m, (out_size, out_size), interpolation=cv2.INTER_LINEAR)
    return np.clip(m, 0, 1)

def save_16bit(mask: np.ndarray, path: Path):
    """Sauvegarde float32 [0..1] → PNG 16 bits."""
    out = (np.clip(mask, 0, 1) * 65535).astype(np.uint16)
    cv2.imwrite(str(path), out)

def smooth_ramp(arr: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """Rampe linéaire : 0 sous lo, 1 au-dessus de hi."""
    out = np.zeros_like(arr, dtype=np.float32)
    in_range = (arr > lo) & (arr < hi)
    out[in_range] = (arr[in_range] - lo) / (hi - lo)
    out[arr >= hi] = 1.0
    return out

def apply_noise(mask: np.ndarray, noise: np.ndarray, amplitude: float) -> np.ndarray:
    """Applique le Worley noise pour varier les bords du masque."""
    # Noise affecte surtout les zones de transition (pas les zones pures)
    edge = 1.0 - np.abs(mask * 2 - 1)  # max aux bords (mask≈0.5)
    perturb = (noise - 0.5) * amplitude * edge
    return np.clip(mask + perturb, 0, 1)

# ============================================================================
# PIPELINE PRINCIPAL
# ============================================================================

def generate_all_masks(dem, slope, dist_coast, t, exclusion, noise,
                       flow_raw, deposit_raw, out_size, output_dir):
    """
    Génère tous les masques avec hiérarchie stricte et transitions douces.

    Hiérarchie (priorité décroissante) :
    1. Seabed   — sous-marin
    2. Coastal  — côtier (plages)
    3. Rock     — pentes très fortes
    4. Landes   — pentes fortes
    5. Flow     — talwegs
    6. Deposit  — sédiments
    7. Végétation (depuis vegetation_map.py — à intégrer)
    8. Grass    — fond par défaut

    Principe mutuellement exclusif :
    - Chaque masque est calculé dans sa zone brute
    - On soustrait les zones déjà prises par les masques de priorité supérieure
    - Somme totale ≤ 1.0 à tout moment
    """
    T = TRANS_SLOPE

    # Resize signaux à out_size si nécessaire
    def resize(arr):
        if arr is None: return None
        if arr.shape[0] != out_size:
            return cv2.resize(arr.astype(np.float32), (out_size, out_size),
                            interpolation=cv2.INTER_LINEAR)
        return arr.astype(np.float32)

    slope_r      = resize(slope)
    dem_r        = resize(dem)
    dist_r       = resize(dist_coast)
    flow_r       = resize(flow_raw)
    deposit_r    = resize(deposit_raw)

    # Budget disponible (commence à 1.0, décroît à chaque masque)
    budget = np.ones((out_size, out_size), dtype=np.float32)
    budget[exclusion == 0] = 0.0  # zones protégées

    masks = {}

    # ── 1. SEABED ─────────────────────────────────────────────────────────
    print("  [1] Seabed...")
    water = (dem_r < 0) | np.isnan(dem_r)
    seabed = np.where(water, 1.0, 0.0).astype(np.float32)
    # Transition douce à la surface (0→-2m)
    near_surface = (dem_r >= -3) & (dem_r < 0)
    seabed[near_surface] = smooth_ramp(-dem_r[near_surface], 0, 3)
    seabed = np.minimum(seabed, budget)
    budget -= seabed
    budget = np.clip(budget, 0, 1)
    masks['seabed'] = seabed

    # ── 2. COASTAL ────────────────────────────────────────────────────────
    print("  [2] Coastal...")
    # Distance + altitude + pente douce
    dist_factor  = smooth_ramp(COASTAL_DIST_MAX - dist_r, 0, COASTAL_DIST_MAX)
    alt_factor   = smooth_ramp(COASTAL_ALT_MAX - dem_r, 0, COASTAL_ALT_MAX)
    slope_factor = smooth_ramp(COASTAL_SLOPE_MAX - slope_r, 0, COASTAL_SLOPE_MAX)
    coastal_raw  = dist_factor * alt_factor * slope_factor
    coastal_raw  = apply_noise(coastal_raw, noise, NOISE_AMPLITUDE * 0.5)
    coastal      = np.minimum(coastal_raw, budget)
    budget -= coastal
    budget = np.clip(budget, 0, 1)
    masks['coastal'] = coastal

    # ── 3. ROCK ───────────────────────────────────────────────────────────
    print("  [3] Rock...")
    # Montée : rock+T/2 → cliff, plein au-delà
    rock_start = t['rock'] + T / 2
    rock_raw   = smooth_ramp(slope_r, rock_start, t['cliff'])
    rock_raw   = apply_noise(rock_raw, noise, NOISE_AMPLITUDE * 0.3)
    rock       = np.minimum(rock_raw, budget)
    budget -= rock
    budget = np.clip(budget, 0, 1)
    masks['rock'] = rock

    # ── 4. LANDES ROCHEUSES ───────────────────────────────────────────────
    print("  [4] Landes rocheuses...")
    # Zone : gentle → rock-T/2, puis redescend
    landes_end = t['rock'] - T / 2
    landes_raw = smooth_ramp(slope_r, t['gentle'], t['landes'])
    # Descente avant la zone rock
    fall_mask  = slope_r > landes_end
    fall_val   = 1.0 - smooth_ramp(slope_r, landes_end, t['rock'] + T / 2)
    landes_raw = np.where(fall_mask, landes_raw * fall_val, landes_raw)
    landes_raw = apply_noise(landes_raw, noise, NOISE_AMPLITUDE * 0.4)
    landes     = np.minimum(landes_raw, budget)
    budget -= landes
    budget = np.clip(budget, 0, 1)
    masks['landes_rocheuses'] = landes

    # ── 5. FLOW ───────────────────────────────────────────────────────────
    print("  [5] Flow...")
    if flow_r is not None:
        flow_raw2  = gaussian_filter(flow_r, sigma=1.5)
        flow_raw2  = apply_noise(flow_raw2, noise, NOISE_AMPLITUDE * 0.6)
        flow_mask  = np.minimum(flow_raw2, budget)
        budget -= flow_mask
        budget = np.clip(budget, 0, 1)
        masks['flow'] = flow_mask
    else:
        masks['flow'] = np.zeros((out_size, out_size), dtype=np.float32)

    # ── 6. DEPOSIT ────────────────────────────────────────────────────────
    print("  [6] Deposit...")
    if deposit_r is not None:
        dep_raw2   = gaussian_filter(deposit_r, sigma=1.5)
        dep_raw2   = apply_noise(dep_raw2, noise, NOISE_AMPLITUDE * 0.6)
        dep_mask   = np.minimum(dep_raw2, budget)
        budget -= dep_mask
        budget = np.clip(budget, 0, 1)
        masks['deposit'] = dep_mask
    else:
        masks['deposit'] = np.zeros((out_size, out_size), dtype=np.float32)

    # ── 7. GRASS (fond par défaut) ────────────────────────────────────────
    print("  [7] Grass (fond)...")
    # Le budget restant = zones non couvertes → Grass_03
    grass_raw = budget.copy()
    grass_raw = apply_noise(grass_raw, noise, NOISE_AMPLITUDE * 0.8)
    grass     = np.clip(grass_raw, 0, 1)
    masks['grass_default'] = grass

    return masks

# ============================================================================
# VALIDATION VISUELLE
# ============================================================================

def generate_validation_map(masks: dict, satmap_path: Path,
                             out_size: int, output_dir: Path):
    """Génère une carte de validation avec tous les masques superposés."""
    print("[VIZ] Génération carte de validation...")

    if satmap_path and satmap_path.exists():
        satmap = cv2.imread(str(satmap_path))
        if satmap.shape[0] != out_size:
            satmap = cv2.resize(satmap, (out_size, out_size))
        result = satmap.astype(np.float32)
    else:
        result = np.full((out_size, out_size, 3), 40, dtype=np.float32)

    colors = {
        'seabed':          (200, 100, 0),    # bleu foncé
        'coastal':         (200, 200, 0),    # cyan
        'rock':            (0, 0, 200),      # rouge
        'landes_rocheuses':(0, 130, 200),    # orange
        'flow':            (255, 200, 0),    # cyan vif
        'deposit':         (0, 165, 255),    # orange vif
        'grass_default':   (0, 180, 0),      # vert (transparent)
    }

    alphas = {
        'seabed': 0.7, 'coastal': 0.65, 'rock': 0.7,
        'landes_rocheuses': 0.6, 'flow': 0.65, 'deposit': 0.6,
        'grass_default': 0.0,  # fond invisible
    }

    for name, mask in masks.items():
        if name not in colors or alphas.get(name, 0) == 0:
            continue
        color = colors[name]
        alpha = alphas[name] * mask
        for c, col in enumerate(color):
            result[:,:,c] = result[:,:,c] * (1 - alpha) + col * alpha

    # Grille tiles
    tile_pix = out_size // 32
    for i in range(33):
        p = i * tile_pix
        if p < out_size:
            result[p,:,:] = result[p,:,:] * 0.4 + 160 * 0.6
            result[:,p,:] = result[:,p,:] * 0.4 + 160 * 0.6

    result = np.clip(result, 0, 255).astype(np.uint8)

    # Légende
    LEG_W = 300
    legend = np.full((out_size, LEG_W, 3), 20, dtype=np.uint8)
    cv2.putText(legend, "PIPELINE MASQUES", (10, 30),
               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 2)
    items = [(c, n) for n, c in colors.items() if n != 'grass_default']
    for i, (color, name) in enumerate(items):
        y = 65 + i * 38
        cv2.rectangle(legend, (10,y-14),(32,y+8), color, -1)
        cv2.putText(legend, name, (40,y),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255,255,255), 1)

    final = np.hstack([result, legend])
    cv2.imwrite(str(output_dir / "pipeline_validation.png"), final)
    print(f"  → pipeline_validation.png")

# ============================================================================
# MAIN
# ============================================================================

def main():
    OUTPUT_DIR.mkdir(exist_ok=True, parents=True)
    print("=" * 70)
    print("MASK PIPELINE — Génération unifiée masques terrain Reforger")
    print("=" * 70)

    # 1. Heightmap + signaux
    dem, cellsize = read_asc(ASC_PATH)
    slope    = compute_slope(dem, cellsize)
    dist_coast = compute_distance_to_coast(dem, cellsize)
    t        = compute_thresholds(slope)

    # 2. Exclusion
    if EXCLUSION_MASK and EXCLUSION_MASK.exists():
        excl_raw   = load_mask(EXCLUSION_MASK, OUTPUT_SIZE)
        exclusion  = (excl_raw > 0.5).astype(np.uint8)
        print(f"[EXCL] Zone active: {exclusion.mean()*100:.1f}%")
    else:
        exclusion = np.ones((OUTPUT_SIZE, OUTPUT_SIZE), dtype=np.uint8)
        print("[EXCL] Toute la carte active")

    # 3. Masques Gaea
    flow_raw    = load_mask(GAEA_FLOW,    OUTPUT_SIZE) if GAEA_FLOW.exists()    else None
    deposit_raw = load_mask(GAEA_DEPOSIT, OUTPUT_SIZE) if GAEA_DEPOSIT.exists() else None
    print(f"[GAEA] Flow: {'OK' if flow_raw is not None else 'absent'}  "
          f"Deposit: {'OK' if deposit_raw is not None else 'absent'}")

    # 4. Worley noise
    noise = worley_noise_2d((OUTPUT_SIZE, OUTPUT_SIZE),
                             scale=NOISE_SCALE, seed=NOISE_SEED)
    # Redimensionner si nécessaire (le noise est généré à OUTPUT_SIZE)

    # 5. Génération des masques
    print(f"\n[MASKS] Génération avec hiérarchie stricte...")
    masks = generate_all_masks(dem, slope, dist_coast, t, exclusion,
                                noise, flow_raw, deposit_raw,
                                OUTPUT_SIZE, OUTPUT_DIR)

    # 6. Sauvegarde
    print(f"\n[SAVE] Export PNG 16 bits...")
    for name, mask in masks.items():
        path = OUTPUT_DIR / f"mask_{name}.png"
        save_16bit(mask, path)
        pct = (mask > 0.01).sum() / mask.size * 100
        print(f"  [OK] mask_{name}.png — {pct:.1f}% actif")

    # 7. Validation visuelle
    satmap_path = Path(r"H:\logiciel perso\Map generator\satmap_v2_textured_4097__13_.png")
    generate_validation_map(masks, satmap_path, OUTPUT_SIZE, OUTPUT_DIR)

    print(f"\n✅ Terminé ! {OUTPUT_DIR}")
    print(f"   {len(masks)} masques générés, résolution {OUTPUT_SIZE}×{OUTPUT_SIZE} px")

if __name__ == '__main__':
    main()
