"""
pipeline_v5.py — Pipeline terrain unifié avec écriture directe .ttile
======================================================================
Extension de pipeline_unified.py avec :
  - Mapping masque → texture (configurable)
  - Arbitrage budget par bloc (respect 6 slots max)
  - Préservation Zone B (textures existantes intactes)
  - Gestion blocs frontière Zone A/B
  - Visualisation carte colorisée (satmap-like) avec quadrillage tuiles
  - Mode sortie : masques PNG ou écriture directe .ttile

Modules :
  [1] Lecture heightmap .asc
  [2] Calcul terrain (slope, fBm, coastal)
  [3] Masques de base (seabed, coastal, rock, landes, flow, deposit)
  [4] Végétation (prairie, maquis, alpages, forêts)
  [5] Application masque exclusion (Zone B préservée)
  [6] Normalisation exclusive (vectorisée)
  [7] Arbitrage budget par bloc (nouveau)
  [8] Visualisation carte
  [9] Export masques PNG ou écriture .ttile

Usage standalone :
    python pipeline_v5.py

Usage depuis Streamlit (import) :
    from pipeline_v5 import run_pipeline, MASK_TEXTURE_MAP, DEFAULT_PRIORITIES
"""

import json
import shutil
import struct
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter, uniform_filter


# ============================================================================
# CONFIGURATION — À modifier selon le projet
# ============================================================================

# Chemins (obligatoires)
ASC_PATH   = Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\sources\Terrain_modified5.asc")
OUTPUT_DIR = Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\outputs\latest")

# Chemins optionnels (None = désactivé)
EXCLUSION_MASK = Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\inputs\masks\new_exclusion4.png")
GAEA_FLOW      = Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\inputs\masks\flow_uint16.png")
GAEA_DEPOSIT   = Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\inputs\masks\sediment_uint16.png")

# Terrain Reforger
TERRAIN_ROOT   = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain")
DATA_DIR       = TERRAIN_ROOT / ".Data"
TERR_PATH      = TERRAIN_ROOT / "Terrain.terr"

# Paramètres généraux
CELL_SIZE        = None   # Auto-détecté depuis .asc header
BUDGET_MAX       = 6      # Slots max par bloc (w0..w6, 7 total mais on réserve 1)
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

# GCTD
GCTD_GRID = 45    # cellules par axe dans le payload GCTD
GCTD_SIZE = 2026  # bytes par section (45×45 + 1 padding)
GRID_W    = 32    # tuiles par axe
NUM_BLK   = 4     # blocs par tuile par axe
DEFAULT_MAT_ID = 0  # matériau fallback si aucun masque actif

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
    # (nom_masque,            texture_name,            couleur_visu_RGB)
    # Ordre géographique : eau → côte → roche → hydro → végétation altitude → végétation plaine
    ("mask_seabed",           "SeaBed_01",             (70,  130, 180)),   # bleu acier
    ("mask_coastal",          "BeachGrass_01",         (194, 178, 128)),   # sable
    ("mask_rock",             "Rock_01",               (128, 128, 128)),   # gris
    ("mask_landes_rocheuses", "MountainGrass_01",      (143, 143, 120)),   # gris-vert
    ("mask_flow",             "Dirt_03",               (101,  67,  33)),   # brun foncé — perce roche et végétation si fort
    ("mask_deposit",          "Dirt_01",               (139, 115,  85)),   # brun clair — idem
    ("mask_alpages",          "zi_MountainGrass_04",   (200, 220, 160)),   # vert pâle — altitude
    ("mask_landes_plateau",   "MountainGrass_03",      (107, 142,  35)),   # vert jaune
    ("mask_maquis_landes",    "Heather_01",            (160, 120,  80)),   # heather brun
    ("mask_foret_coniferes",  "ForestConiferous_01_Base", (0,    60,   0)),   # vert très foncé
    ("mask_foret_feuillue",   "ForestDeciduous_01_Base",  (0,   100,   0)),   # vert foncé
    ("mask_prairie_humide",   "Grass_03",              (34,  139,  34)),   # vert moyen
    ("mask_prairie_seche",    "Grass_02",              (85,  107,  47)),   # vert olive
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
    print(f"       slope enrichi, coastal distance OK")
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


def generate_coastal(dem, coastal_dist):
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

    return coastal_filtered


def generate_landes_rocheuses(slope, t):
    GAP       = TRANSITION_WIDTH
    landes_end = max(t['landes'], t['rock'] - GAP / 2)
    out = np.zeros_like(slope, dtype=np.float32)
    m1  = (slope >= t['gentle']) & (slope < t['landes'])
    out[m1] = (slope[m1] - t['gentle']) / (t['landes'] - t['gentle'])
    out[(slope >= t['landes']) & (slope < landes_end)] = 1.0
    m2  = (slope >= landes_end) & (slope < t['rock'])
    out[m2] = 1.0 - (slope[m2] - landes_end) / (t['rock'] - landes_end)
    return out


def generate_rock(slope):
    start = THRESHOLD_ROCK if THRESHOLD_ROCK else np.percentile(slope[slope > 0], 90) + TRANSITION_WIDTH / 2
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


def module_masques_base(dem, terrain, calibration=None):
    print("[3/9] Masques de base...")
    cal = calibration or {}
    coastal_width  = cal.get('coastal_width',  40.0)
    threshold_rock = cal.get('threshold_rock', THRESHOLD_ROCK)

    slope  = terrain['slope']
    sa     = slope[slope > 0]
    t = {
        'gentle': THRESHOLD_GENTLE or np.percentile(sa, 70),
        'landes': THRESHOLD_LANDES or np.percentile(sa, 85),
        'rock':   threshold_rock   or np.percentile(sa, 90),
        'cliff':  THRESHOLD_CLIFF  or np.percentile(sa, 95),
    }
    m = {}
    m['mask_seabed']          = generate_seabed(dem)
    m['mask_coastal']         = generate_coastal(dem, terrain['coastal_distance'])
    m['mask_landes_rocheuses']= generate_landes_rocheuses(terrain['slope'], t)
    m['mask_rock']            = generate_rock(terrain['slope'])
    flow = load_gaea_mask(GAEA_FLOW, dem.shape)
    if flow is not None:
        m['mask_flow'] = apply_output_curve(flow, gamma=0.5)
    dep = load_gaea_mask(GAEA_DEPOSIT, dem.shape)
    if dep is not None:
        if dep.max() > 0:
            dep[dep < dep.max() * DEPOSIT_CUT_LOW] = 0
        m['mask_deposit'] = apply_output_curve(dep, gamma=1.0)
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
    alpages_alt_min    = cal.get('alpages_alt_min',    180.0)

    sl = terrain['slope']
    cd = terrain['coastal_distance']
    m  = {}
    m['mask_prairie_humide']  = np.clip((prairie_alt_max - dem) / prairie_alt_max, 0, 1) * np.clip((12 - sl) / 12, 0, 1)
    m['mask_prairie_seche']   = np.clip((dem - prairie_seche_min) / (prairie_seche_max - prairie_seche_min), 0, 1) * np.clip((prairie_seche_max - dem) / 30, 0, 1) * np.clip((15 - sl) / 15, 0, 1)
    m['mask_landes_plateau']  = np.clip((dem - landes_plateau_min) / 40, 0, 1) * np.clip((sl - 12) / 8, 0, 1)
    m['mask_maquis_landes']   = np.clip((dem - maquis_alt_min) / (maquis_alt_max - maquis_alt_min), 0, 1) * np.clip((maquis_alt_max - dem) / 60, 0, 1) * np.clip((sl - 10) / 8, 0, 1) * np.clip((25 - sl) / 10, 0, 1)
    m['mask_alpages']         = generate_alpages(dem, sl)
    m['mask_foret_feuillue']  = np.clip((dem - foret_alt_min) / 40, 0, 1) * np.clip((18 - sl) / 18, 0, 1) * 0.8
    m['mask_foret_coniferes'] = generate_foret_coniferes(dem, sl, terrain['aspect'], cd)
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

def _read_zone_b_slots(data_dir, bx, by):
    """
    Lit le nombre de slots Zone B déjà utilisés pour le bloc (bx,by).
    Retourne (n_slots_zone_b, mat_ids_zone_b).
    """
    try:
        tile_id = (by // NUM_BLK) * GRID_W + (bx // NUM_BLK)
        path    = data_dir / f"Terrain_{tile_id}.ttile"
        if not path.exists():
            return 0, []
        data     = path.read_bytes()
        lrs2_pos = data.find(b'LRS2')
        if lrs2_pos < 0:
            return 0, []
        lrs2_sz  = struct.unpack_from('>I', data, lrs2_pos + 4)[0]
        lrs2_raw = data[lrs2_pos + 8: lrs2_pos + 8 + lrs2_sz]
        pos = 0
        while pos < len(lrs2_raw) - 6:
            idx = struct.unpack_from('<I', lrs2_raw, pos)[0]
            cnt = struct.unpack_from('<H', lrs2_raw, pos + 4)[0]
            mats = list(struct.unpack_from(f'<{cnt}H', lrs2_raw, pos + 6))
            if (idx & 0x7F) == bx and ((idx >> 7) & 0x7F) == by:
                return len(mats), mats
            pos += 6 + cnt * 2
        return 0, []
    except Exception:
        return 0, []


def module_budget(masques, mask_config, zone_a_mask, data_dir=None):
    """
    Module 7 : Analyse budget par bloc depuis les masques normalisés.

    Après soustraction, un pixel = un seul masque → pas de dépassement possible.
    Ce module calcule la carte des masques actifs par bloc pour la visualisation.
    """
    print("[7/9] Analyse budget par bloc...")

    priority_names = [cfg[0] for cfg in mask_config]
    mat_map        = {cfg[0]: cfg[1] for cfg in mask_config}
    color_map      = {cfg[0]: cfg[2] for cfg in mask_config}

    first = next(iter(masques.values()))
    h, w  = first.shape

    blocs_per_axis = GRID_W * NUM_BLK   # 128
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

            # Limiter strictement à BUDGET_MAX masques (top-N par force)
            selected = active_masks[:BUDGET_MAX]
            n_active = len(selected)

            # Lire slots Zone B si data_dir fourni
            slots_zone_b = 0
            if data_dir and data_dir.exists():
                slots_zone_b, _ = _read_zone_b_slots(data_dir, bx_bloc, by_bloc)
                if slots_zone_b > 0:
                    n_frontier += 1

            total_slots = n_active + slots_zone_b

            if total_slots > BUDGET_MAX:
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
    tile_ids = []
    for f in data_dir.glob('Terrain_*.ttile'):
        try:
            tile_ids.append(int(f.stem.split('_')[1]))
        except (ValueError, IndexError):
            pass

    colormap = {}
    for tile_id in sorted(tile_ids):
        path = data_dir / f'Terrain_{tile_id}.ttile'
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
                bx   = idx & 0x7F
                by   = (idx >> 7) & 0x7F
                if mats:
                    colormap[(bx, by)] = get_color(mats[0])
                pos += 6 + cnt * 2
        except Exception:
            continue

    print(f"       {len(colormap)} blocs Zone B lus")
    return colormap


def module_visualize(masques_normalized, mask_config, output_path,
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
            blocs_per_axis = GRID_W * NUM_BLK
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
        blocs_per_axis = GRID_W * NUM_BLK   # 128
        bloc_px        = img_size // blocs_per_axis  # px par bloc dans l'image finale
        tile_px        = NUM_BLK * bloc_px   # px par tuile

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
        for ty in range(GRID_W):
            for tx in range(GRID_W):
                tile_id = ty * GRID_W + tx
                px_x    = tx * tile_px + 2
                px_y    = (GRID_W - 1 - ty) * tile_px + 11  # flip Y
                cv2.putText(img, str(tile_id), (px_x, px_y),
                            font, 0.22, (200, 200, 200), 1, cv2.LINE_AA)

    # ── Marquage blocs >6 textures ─────────────────────────────────────────
    if bloc_budget_map:
        blocs_per_axis = GRID_W * NUM_BLK
        bloc_px        = img_size // blocs_per_axis
        for (bx, by), n in bloc_budget_map.items():
            if n > BUDGET_MAX:
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

    final = np.vstack([img, legend])
    cv2.imwrite(str(output_path), final)
    print(f"       Carte sauvegardée : {output_path} ({final.shape[1]}×{final.shape[0]})")
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


def _replace_chunks(data: bytearray, replacements: dict) -> bytearray:
    """Reconstruit le fichier IFF avec les chunks remplacés."""
    # Parcourir et collecter tous les chunks
    all_chunks = []
    pos = 12
    while pos < len(data) - 8:
        tag = bytes(data[pos:pos+4])
        size = struct.unpack_from('>I', data, pos + 4)[0]
        if size > len(data):
            break
        payload = bytes(data[pos+8:pos+8+size])
        all_chunks.append((tag, payload))
        next_pos = pos + 8 + size
        if size % 2:
            next_pos += 1
        pos = next_pos

    # Reconstruire avec les remplacements
    out = bytearray()
    out += data[0:4]   # FORM tag
    out += b'\x00\x00\x00\x00'  # taille placeholder
    out += data[8:12]  # type TERR

    for tag, payload in all_chunks:
        new_payload = replacements.get(tag, payload)
        out += tag
        out += struct.pack('>I', len(new_payload))
        out += new_payload
        if len(new_payload) % 2:
            out += b'\x00'  # padding

    # Mettre à jour la taille FORM
    struct.pack_into('>I', out, 4, len(out) - 8)
    return out


def _write_bloc_to_ttile(ttile_path, bx, by, new_mats, new_payload, backup=True):
    """Écrit LRS2 + GCTD pour un bloc dans un .ttile."""
    raw = bytearray(ttile_path.read_bytes())

    # Backup
    if backup:
        bak = ttile_path.with_suffix('.ttile.bak')
        if not bak.exists():
            shutil.copy2(ttile_path, bak)

    # LRS2
    lrs2_pos = raw.find(b'LRS2')
    lrs2_sz  = struct.unpack_from('>I', raw, lrs2_pos + 4)[0]
    lrs2_raw = bytes(raw[lrs2_pos + 8: lrs2_pos + 8 + lrs2_sz])
    entries  = _parse_lrs2(lrs2_raw)
    entries[(bx, by)] = new_mats

    # GCTD
    gctd_pos = raw.find(b'GCTD')
    gctd_sz  = struct.unpack_from('>I', raw, gctd_pos + 4)[0]
    gctd     = bytearray(raw[gctd_pos + 8: gctd_pos + 8 + gctd_sz])
    entries2 = _parse_lrs2(bytes(raw[raw.find(b'LRS2') + 8:]))
    secs     = _find_gctd_sections(bytes(gctd), entries2)
    for sec in secs:
        if sec['bx'] == bx and sec['by'] == by:
            do = sec['data_off']
            ds = sec['data_size']
            gctd[do: do + min(len(new_payload), ds)] = new_payload[:ds]
            break

    raw = _replace_chunks(raw, {
        b'LRS2': _build_lrs2(entries),
        b'GCTD': bytes(gctd),
    })
    ttile_path.write_bytes(bytes(raw))


def module_write_ttile(masques, mask_config, zone_a_mask, data_dir,
                        dry_run=True, backup=True, progress_cb=None):
    """
    Module 9B : Écriture directe dans les .ttile.

    Pour chaque bloc Zone A :
      - Calcule les matériaux actifs (masques présents)
      - Construit le payload GCTD 45×45
      - Écrit LRS2 + GCTD dans le .ttile
    """
    print("[9/9] Écriture directe .ttile...")

    # Détection automatique du préfixe des fichiers .ttile
    ttile_prefix = "Terrain_"  # défaut
    if data_dir and data_dir.exists():
        ttile_files = list(data_dir.glob("*.ttile"))
        if ttile_files:
            sample = ttile_files[0].stem  # ex: "ZBK_terrain_0" ou "Terrain_0"
            # Extraire le préfixe en supprimant le numéro final
            import re
            m = re.match(r'^(.*?)(\d+)$', sample)
            if m:
                ttile_prefix = m.group(1)  # ex: "ZBK_terrain_" ou "Terrain_"
        print(f"       Préfixe .ttile détecté : '{ttile_prefix}'")

    lrs2_shift = _detect_lrs2_shift(data_dir, ttile_prefix, NUM_BLK)
    print(f"       LRS2 shift détecté : {lrs2_shift}")

    print(f"[DEBUG] zone_a_mask is None: {zone_a_mask is None}")
    if zone_a_mask is not None:
        print(f"[DEBUG] zone_a_mask shape={zone_a_mask.shape}, max={zone_a_mask.max()}, min={zone_a_mask.min()}")
    if dry_run:
        print("       [DRY-RUN] Simulation uniquement")

    priority_names = [cfg[0] for cfg in mask_config]
    mat_map        = {cfg[0]: cfg[1] for cfg in mask_config}
    blocs_per_axis = GRID_W * NUM_BLK  # 128
    bloc_px_mask   = OUTPUT_SIZE // blocs_per_axis

    # Résolution masque d'exclusion à 128×128 blocs
    excl_bloc = None
    if zone_a_mask is not None:
        excl_bloc = cv2.resize(
            zone_a_mask.astype(np.uint8),
            (blocs_per_axis, blocs_per_axis),
            interpolation=cv2.INTER_NEAREST
        )

    # Grouper les blocs par tuile pour minimiser les lectures/écritures
    blocs_by_tile = {}
    for by_bloc in range(blocs_per_axis):
        for bx_bloc in range(blocs_per_axis):
            # Ignorer Zone B
            if excl_bloc is not None:
                py_excl = blocs_per_axis - 1 - by_bloc
                if excl_bloc[py_excl, bx_bloc] == 0:
                    continue  # Zone B → pas toucher

            tile_id = (by_bloc // NUM_BLK) * GRID_W + (bx_bloc // NUM_BLK)
            blocs_by_tile.setdefault(tile_id, []).append((bx_bloc, by_bloc))

    n_tiles  = len(blocs_by_tile)
    n_blocs  = sum(len(v) for v in blocs_by_tile.values())
    print(f"       {n_blocs} blocs Zone A dans {n_tiles} tuiles")

    written = 0
    for tile_id, tile_blocs in sorted(blocs_by_tile.items()):
        path = data_dir / f"{ttile_prefix}{tile_id}.ttile"
        if not path.exists():
            print(f"       [SKIP] Tuile {tile_id} introuvable")
            continue

        raw      = bytearray(path.read_bytes())
        lrs2_pos = raw.find(b'LRS2')
        lrs2_sz  = struct.unpack_from('>I', raw, lrs2_pos + 4)[0]
        lrs2_raw = bytes(raw[lrs2_pos + 8: lrs2_pos + 8 + lrs2_sz])
        lrs2_entries = _parse_lrs2(lrs2_raw, lrs2_shift)

        gctd_pos = raw.find(b'GCTD')
        gctd_sz  = struct.unpack_from('>I', raw, gctd_pos + 4)[0]
        gctd     = bytearray(raw[gctd_pos + 8: gctd_pos + 8 + gctd_sz])
        gctd_sections = _find_gctd_sections(bytes(gctd), lrs2_entries)
        gctd_sec_map  = {(s['bx'], s['by']): s for s in gctd_sections}

        modified = False

        for bx, by in tile_blocs:
            # Région du masque pour ce bloc
            py = (blocs_per_axis - 1 - by) * bloc_px_mask
            px = bx * bloc_px_mask
            py2 = min(py + bloc_px_mask, OUTPUT_SIZE)
            px2 = min(px + bloc_px_mask, OUTPUT_SIZE)
            n_px = (py2 - py) * (px2 - px)

            # Déterminer les matériaux actifs sur ce bloc
            active = []
            for name in priority_names:
                if name not in masques:
                    continue
                region   = masques[name][py:py2, px:px2]
                presence = float((region > 0).mean())
                if presence >= MASK_PRESENCE_THRESH:
                    strength = float(region.mean())
                    active.append((name, strength, presence))

            if not active:
                continue

            # Lire slots Zone B existants
            n_zone_b, mats_zone_b = _read_zone_b_slots(data_dir, bx, by) if (excl_bloc is not None and excl_bloc[blocs_per_axis - 1 - by, bx] > 0) else (0, [])
            budget = BUDGET_MAX - n_zone_b

            # Sélectionner dans le budget
            active.sort(key=lambda x: -x[1])
            selected = active[:max(0, budget)]

            # Construire nouvelle LRS2
            new_mat_ids = list(dict.fromkeys(
                mats_zone_b + [mat_map[name] for name, _, _ in selected]
            ))[:7]  # hard limit 7 slots

            # Construire payload GCTD 45×45
            # Pour chaque cellule GCTD, trouver le masque dominant
            payload = bytearray(GCTD_SIZE)
            for cell_row in range(GCTD_GRID):
                for cell_col in range(GCTD_GRID):
                    # Coordonnée pixel dans le masque 4096×4096
                    mx = int(px + (cell_col / GCTD_GRID) * bloc_px_mask)
                    my = int(py + (cell_row / GCTD_GRID) * bloc_px_mask)
                    mx = min(mx, OUTPUT_SIZE - 1)
                    my = min(my, OUTPUT_SIZE - 1)

                    # Trouver le masque dominant pour cette cellule
                    best_val  = 0.0
                    best_mat  = DEFAULT_MAT_ID
                    for name, _, _ in selected:
                        if name not in masques:
                            continue
                        v = float(masques[name][my, mx])
                        if v > best_val:
                            best_val = v
                            best_mat = mat_map[name]

                    # Convertir en index local
                    local_idx = new_mat_ids.index(best_mat) if best_mat in new_mat_ids else 0
                    cell_idx  = cell_row * GCTD_GRID + cell_col
                    if cell_idx < GCTD_SIZE:
                        payload[cell_idx] = local_idx

            # Mettre à jour LRS2
            lrs2_entries[(bx, by)] = new_mat_ids

            # Mettre à jour GCTD
            if (bx, by) in gctd_sec_map:
                sec = gctd_sec_map[(bx, by)]
                do  = sec['data_off']
                ds  = sec['data_size']
                gctd[do: do + min(GCTD_SIZE, ds)] = payload[:ds]
            # Si section absente → à créer (cas bloc sans texture préalable)
            # Pour l'instant on log et on passe

            modified = True
            written += 1

        if modified and not dry_run:
            # Backup
            if backup:
                bak = path.with_suffix('.ttile.bak')
                if not bak.exists():
                    shutil.copy2(path, bak)
            # Écriture
            raw = _replace_chunks(raw, {
                b'LRS2': _build_lrs2(lrs2_entries, lrs2_shift),
                b'GCTD': bytes(gctd),
            })
            path.write_bytes(bytes(raw))

        if progress_cb:
            progress_cb(tile_id)

    print(f"       {'[DRY-RUN] ' if dry_run else ''}{written} blocs traités dans {n_tiles} tuiles")


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
    exclusion_path: Optional[Path] = None,
    gaea_flow: Optional[Path] = None,
    gaea_deposit: Optional[Path] = None,
    data_dir: Optional[Path] = None,
    catalog_path: Optional[Path] = None,
    satmap_path: Optional[Path] = None,
    mask_config: Optional[List] = None,
    surfaces_map: Optional[Dict] = None,
    mode: str = 'masks',
    dry_run: bool = True,
    progress_cb=None,
    grid_w: int = 32,
    num_blk: int = 4,
    calibration: Optional[Dict] = None,
    **kwargs,
) -> Dict:
    """
    Point d'entrée principal du pipeline v5.

    Args:
        asc_path       : Chemin heightmap .asc
        output_dir     : Dossier de sortie
        exclusion_path : Masque exclusion PNG (Zone B = noir)
        gaea_flow      : Masque flow Gaea (optionnel)
        gaea_deposit   : Masque deposit Gaea (optionnel)
        data_dir       : Dossier .Data Reforger (pour écriture .ttile et lecture Zone B)
        mask_config    : Liste [(nom_masque, mat_id, color_rgb), ...]
        surfaces_map   : Dict {mat_id: nom_texture} pour affichage (depuis surfaces.json)
        mode           : 'masks' = export PNG, 'ttile' = écriture directe, 'preview' = visualisation seule
        dry_run        : Si True, pas d'écriture réelle
        progress_cb    : Callback de progression (optionnel)
        grid_w         : Nombre de tuiles par axe (défaut: 32)
        num_blk        : Nombre de blocs par tuile par axe (défaut: 4)

    Returns:
        dict avec résultats et chemins de sortie
    """
    global GAEA_FLOW, GAEA_DEPOSIT, GRID_W, NUM_BLK

    # Patcher les constantes globales avec les valeurs fournies
    GRID_W = grid_w
    NUM_BLK = num_blk

    # Fallback surfaces_map vide si non fourni
    if surfaces_map is None:
        surfaces_map = {}
    GAEA_FLOW    = gaea_flow
    GAEA_DEPOSIT = gaea_deposit

    cfg = mask_config or DEFAULT_MASK_CONFIG

    # Modules 1-4
    dem, cellsize  = load_heightmap_asc(asc_path)
    terrain        = module_terrain(dem, cellsize)
    calibration_auto = _build_calibration(dem, cellsize, terrain['slope'])
    calibration_final = {**calibration_auto, **(calibration or {})}
    print(f"[CALIB] alt={calibration_auto['alt_min']:.1f}→{calibration_auto['alt_max']:.1f}m | "
          f"slope p70/85/90={calibration_auto['slope_p70']:.1f}°/{calibration_auto['slope_p85']:.1f}°/{calibration_auto['slope_p90']:.1f}°")
    masques        = module_masques_base(dem, terrain, calibration_final)
    masques.update(module_vegetation(dem, terrain, calibration_final))

    # Module 5
    masques, zone_a = module_exclusion(masques, exclusion_path)

    # Module 6
    masques = module_normalize(masques, cfg)

    # Module 7
    masques, bloc_map, stats = module_budget(masques, cfg, zone_a, data_dir)

    # Module 8 — Visualisation
    output_dir.mkdir(parents=True, exist_ok=True)
    visu_path = output_dir / 'pipeline_preview.png'
    bloc_budget_map = {k: v["n_active"] for k, v in bloc_map.items()}  # Zone A uniquement

    # Phase 2 : lire Zone B depuis .ttile si data_dir fourni
    zone_b_colormap = None
    if data_dir and data_dir.exists():
        zone_b_colormap = build_zone_b_colormap(data_dir, cfg, surfaces_map, catalog_path)

    module_visualize(masques, cfg, visu_path, zone_a, bloc_budget_map, zone_b_colormap, satmap_path, surfaces_map)

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

    elif mode == 'ttile':
        if data_dir is None or not data_dir.exists():
            print("[ERREUR] --data-dir requis pour le mode ttile")
        else:
            module_write_ttile(masques, cfg, zone_a, data_dir,
                               dry_run=dry_run, progress_cb=progress_cb)

    return result


# ============================================================================
# MAIN STANDALONE
# ============================================================================

def main():
    import sys
    import argparse

    ap = argparse.ArgumentParser(description='Pipeline v5 — Terrain Reforger')
    ap.add_argument('--mode', choices=['masks', 'ttile', 'preview'], default='preview',
                    help='Mode sortie : masks=PNG, ttile=écriture directe, preview=visualisation seule')
    ap.add_argument('--dry-run', action='store_true', help='Simulation sans écriture')
    ap.add_argument('--asc',     type=str, default=str(ASC_PATH))
    ap.add_argument('--out',     type=str, default=str(OUTPUT_DIR))
    ap.add_argument('--excl',    type=str, default=str(EXCLUSION_MASK) if EXCLUSION_MASK else None)
    ap.add_argument('--flow',    type=str, default=str(GAEA_FLOW) if GAEA_FLOW else None)
    ap.add_argument('--deposit', type=str, default=str(GAEA_DEPOSIT) if GAEA_DEPOSIT else None)
    ap.add_argument('--data-dir', type=str, default=None,
                    help='Chemin .Data Reforger (optionnel — pour lire Zone B existante)')
    ap.add_argument('--catalog', type=str, default=None,
                    help='Chemin catalog.json pour couleurs réelles Zone B')
    ap.add_argument('--satmap', type=str, default=None,
                    help='Chemin satmap PNG pour fond Zone B (rendu le plus fidèle)')
    args = ap.parse_args()

    print("=" * 70)
    print("PIPELINE V5 — Génération terrain Reforger")
    print("=" * 70)
    print(f"Mode : {args.mode}" + (" [DRY-RUN]" if args.dry_run else ""))
    print()

    result = run_pipeline(
        asc_path       = Path(args.asc),
        output_dir     = Path(args.out),
        exclusion_path = Path(args.excl) if args.excl else None,
        gaea_flow      = Path(args.flow) if args.flow else None,
        gaea_deposit   = Path(args.deposit) if args.deposit else None,
        data_dir       = Path(args.data_dir) if args.data_dir else None,
        catalog_path   = Path(args.catalog) if args.catalog else None,
        satmap_path    = Path(args.satmap) if args.satmap else None,
        mode           = args.mode,
        dry_run        = args.dry_run,
    )

    print()
    print("=" * 70)
    stats = result['stats']
    print(f"RÉSULTATS : {stats['n_ok']} blocs OK, {stats['n_over']} dépassements corrigés, "
          f"{stats['n_frontier']} blocs frontière")
    print(f"Visualisation : {result['visu_path']}")
    print("=" * 70)

    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
