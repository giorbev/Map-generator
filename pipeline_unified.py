"""
pipeline_unified.py — Pipeline unifié de génération masques terrain
====================================================================
Remplace pipeline_v2, v3, v4.

Modules :
  [1] Lecture heightmap .asc
  [2] Calcul terrain (slope, fBm, coastal)
  [3] Génération masques de base
  [4] Végétation
  [5] Application masque exclusion
  [6] Normalisation exclusive
  [7] Arbitrage budget
  [8] Export masques 4096×4096

Usage:
    python pipeline_unified.py
"""

import numpy as np
import cv2
from pathlib import Path
from scipy.ndimage import uniform_filter
from typing import Dict, Optional, Tuple, List

# Import modules terrain
from edds_decoder import decode_edds_layer, extract_all_weights
from clean_weights import find_layer_path, read_lrs2_from_ttile
from terrain_terr_reader import read_mats_from_terr


# ============================================================================
# CONFIGURATION
# ============================================================================

# Chemins (obligatoires)
ASC_PATH = Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\sources\Terrain_modified5.asc")
OUTPUT_DIR = Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\exports_mask")

# Chemins optionnels (None = désactivé)
EXCLUSION_MASK = Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\masks\new_exclusion4.png")
GAEA_FLOW = Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\masks\flow_uint16.png")
GAEA_DEPOSIT = Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\masks\sediment_uint16.png")

# Terrain Reforger
TERRAIN_ROOT = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain")
DATA_DIR = TERRAIN_ROOT / ".Data"
EDITOR_DATA_DIR = TERRAIN_ROOT / ".EditorData"
TERR_PATH = TERRAIN_ROOT / "terrain.terr"

# Paramètres
CELL_SIZE = None  # Auto-détecté depuis .asc header
BUDGET_MAX = 6
OUTPUT_SIZE = 4096

# --- Masques côtiers ---
COASTAL_SEA_LEVEL = 0.0   # altitude du trait de côte (m)
COASTAL_WIDTH     = 40.0  # largeur totale bande côtière (m)

# --- Seuils de pente (None = auto depuis percentiles) ---
THRESHOLD_GENTLE = None   # p70 — début pentes notables
THRESHOLD_LANDES = None   # p85 — landes rocheuses
THRESHOLD_ROCK   = 22.0   # fixe — rock (None = p90)
THRESHOLD_CLIFF  = 26.0   # fixe — falaise (None = p95)

# --- Transitions ---
TRANSITION_WIDTH = 5.0  # largeur zone neutre entre landes et rock (degrés)

# --- Roughness (enrichissement slope) ---
ROUGHNESS_AMPLITUDE = 8.0    # degrés de perturbation max (slope_perturb)
ROUGHNESS_SCALE     = 0.008  # fréquence spatiale du bruit (plus bas = plus large)
ROUGHNESS_OCTAVES   = 6
ROUGHNESS_SEED      = 42
ROUGHNESS_MODE      = "slope_perturb"  # "slope_perturb" | "domain_warp" | "additive" | None

# --- Végétation ---
VEG_MIN_SCORE = 0.15   # Score minimum pour qu'un pixel soit actif

# --- QTRE ---
QTRE_BUDGET          = 7    # slots LRS2 max par bloc
QTRE_PRESENCE_THRESH = 0.10 # coverage minimale pour compter un masque actif dans un bloc

# Post-processing
STRETCH_AUTO = True
WEIGHT_MIN = 0.10

# Masques Gaea — post-processing spécifique
DEPOSIT_CUT_LOW = 0.55  # coupe les zones de faible dépôt (percentile)

# Priorité masques
MASK_PRIORITY = [
    "mask_seabed",
    "mask_flow",
    "mask_deposit",
    "mask_coastal",
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


# ============================================================================
# MODULE 1 — LECTURE HEIGHTMAP
# ============================================================================

def load_heightmap_asc(asc_path: Path) -> Tuple[np.ndarray, float]:
    """
    Charge heightmap depuis .asc.

    Returns:
        dem : array (H, W) float32 — altitudes en mètres
        cellsize : float — mètres par pixel
    """
    print("[1/8] Chargement heightmap...")

    with open(asc_path, 'r') as f:
        lines = f.readlines()

    # Parser header
    header = {}
    for i, line in enumerate(lines[:10]):
        parts = line.strip().split()
        if len(parts) == 2:
            header[parts[0].lower()] = float(parts[1])

    ncols = int(header.get('ncols', 0))
    nrows = int(header.get('nrows', 0))
    cellsize = header.get('cellsize', 4.0)

    # Charger données
    dem = np.loadtxt(asc_path, skiprows=6, dtype=np.float32)

    print(f"       Heightmap chargée : {nrows}×{ncols} pixels, cellsize={cellsize}m")

    return dem, cellsize


# ============================================================================
# MODULE 2 — CALCUL TERRAIN
# ============================================================================

def compute_slope_aspect(dem: np.ndarray, cellsize: float) -> Tuple[np.ndarray, np.ndarray]:
    """Calcule slope et aspect depuis DEM."""
    fy, fx = np.gradient(dem, cellsize)
    slope = np.degrees(np.arctan(np.sqrt(fx**2 + fy**2)))
    aspect = np.degrees(np.arctan2(-fx, fy))
    return slope, aspect


def enrichissement_slope_fbm(slope: np.ndarray, cellsize: float) -> np.ndarray:
    """Enrichit slope via fBm (depuis pipeline_v3)."""
    if ROUGHNESS_MODE is None or ROUGHNESS_MODE == "":
        return slope

    np.random.seed(ROUGHNESS_SEED)
    h, w = slope.shape
    noise = np.zeros((h, w), dtype=np.float32)

    for octave in range(ROUGHNESS_OCTAVES):
        freq = 2 ** octave * ROUGHNESS_SCALE
        amp = ROUGHNESS_AMPLITUDE / (2 ** octave)

        # Génération bruit simple (à améliorer avec vrai fBm si besoin)
        octave_noise = np.random.randn(h, w).astype(np.float32) * amp
        octave_noise = uniform_filter(octave_noise, size=int(1.0 / freq))
        noise += octave_noise

    slope_enriched = slope + noise
    return np.clip(slope_enriched, 0, 90)


def compute_coastal_distance(dem: np.ndarray) -> np.ndarray:
    """Calcule distance depuis la côte (niveau mer = 0m)."""
    sea_mask = (dem <= COASTAL_SEA_LEVEL).astype(np.uint8)
    land_mask = (dem > COASTAL_SEA_LEVEL).astype(np.uint8)

    dist_from_sea = cv2.distanceTransform(land_mask, cv2.DIST_L2, 5)

    return dist_from_sea


def module_terrain(dem: np.ndarray, cellsize: float) -> Dict:
    """
    Module 2 : Calcul terrain complet.

    Returns:
        dict avec slope, aspect, coastal_distance
    """
    print("[2/8] Calcul terrain...")

    slope, aspect = compute_slope_aspect(dem, cellsize)
    slope_enriched = enrichissement_slope_fbm(slope, cellsize)
    coastal_distance = compute_coastal_distance(dem)

    print(f"       Terrain calculé : slope enrichi, coastal distance")

    return {
        'slope': slope_enriched,
        'aspect': aspect,
        'coastal_distance': coastal_distance
    }


# ============================================================================
# MODULE 3 — MASQUES DE BASE
# ============================================================================

def generate_seabed(dem: np.ndarray) -> np.ndarray:
    """
    Génère masque seabed (fond marin).
    Copié depuis pipeline_v3.py::generate_seabed_mask.
    """
    sea_level = COASTAL_SEA_LEVEL
    transition = 2.0

    seabed = np.zeros_like(dem, dtype=np.float32)

    # Zone pleine : sous sea_level - transition
    seabed[dem <= sea_level - transition] = 1.0

    # Transition douce : [sea_level - transition .. sea_level]
    if transition > 0:
        m_trans = (dem > sea_level - transition) & (dem <= sea_level)
        seabed[m_trans] = 1.0 - (dem[m_trans] - (sea_level - transition)) / transition

    # Appliquer weight_min sur les pixels actifs
    if WEIGHT_MIN > 0:
        seabed = np.where(seabed > 0, WEIGHT_MIN + seabed * (1.0 - WEIGHT_MIN), 0.0)

    seabed = np.clip(seabed, 0, 1)
    return seabed


def generate_coastal(dem: np.ndarray, coastal_distance: np.ndarray) -> np.ndarray:
    """Génère masque coastal (bande côtière unifiée)."""
    # Bande côtière : de COASTAL_SEA_LEVEL à COASTAL_WIDTH mètres depuis le trait de côte
    # Transition douce basée sur la distance
    coastal = np.clip((COASTAL_WIDTH - coastal_distance) / COASTAL_WIDTH, 0, 1)

    # Limiter à la zone terrestre (au-dessus du niveau de la mer)
    land_mask = dem > COASTAL_SEA_LEVEL
    coastal = coastal * land_mask.astype(np.float32)

    return coastal


def generate_landes_rocheuses(slope: np.ndarray, t: dict) -> np.ndarray:
    """
    Génère masque landes_rocheuses.
    Copié depuis pipeline_v3.py::generate_slope_masks.
    """
    GAP         = TRANSITION_WIDTH
    landes_end  = max(t['landes'], t['rock'] - GAP / 2)

    landes = np.zeros_like(slope, dtype=np.float32)
    m_rise = (slope >= t['gentle']) & (slope < t['landes'])
    landes[m_rise] = (slope[m_rise] - t['gentle']) / (t['landes'] - t['gentle'])
    landes[(slope >= t['landes']) & (slope < landes_end)] = 1.0
    m_fall = (slope >= landes_end) & (slope < t['rock'])
    landes[m_fall] = 1.0 - (slope[m_fall] - landes_end) / (t['rock'] - landes_end)

    return landes


def generate_rock(slope: np.ndarray) -> np.ndarray:
    """Génère masque rock (roche nue)."""
    if THRESHOLD_ROCK is not None:
        rock_start = THRESHOLD_ROCK
    else:
        p90 = np.percentile(slope[slope > 0], 90)
        rock_start = p90 + TRANSITION_WIDTH / 2

    rock = np.clip((slope - rock_start) / TRANSITION_WIDTH, 0, 1)
    return rock


def load_gaea_mask(gaea_path: Optional[Path], target_shape: Tuple[int, int]) -> Optional[np.ndarray]:
    """Charge masque Gaea (flow ou deposit) avec seuillage parasites."""
    if gaea_path is None or not gaea_path.exists():
        return None

    img = cv2.imread(str(gaea_path), cv2.IMREAD_UNCHANGED)
    if img is None:
        return None

    if len(img.shape) == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Resize si nécessaire
    if img.shape != target_shape:
        img = cv2.resize(img, (target_shape[1], target_shape[0]), interpolation=cv2.INTER_LINEAR)

    # Normaliser 0-1
    if img.dtype == np.uint16:
        mask = img.astype(np.float32) / 65535.0
    else:
        mask = img.astype(np.float32) / 255.0

    # Seuillage parasites AVANT stretch
    mask_max = mask.max()
    if mask_max > 0:
        cutoff = mask_max * 0.02
        mask[mask < cutoff] = 0

    return mask


def apply_output_curve(mask: np.ndarray, gamma: float = 1.0) -> np.ndarray:
    """Post-processing : stretch → gamma → seuillage → weight_min."""
    if STRETCH_AUTO:
        active = mask[mask > 0]
        if active.size > 0:
            lo = np.percentile(active, 2)
            hi = np.percentile(mask, 98)
            if hi > lo:
                mask = np.clip((mask - lo) / (hi - lo), 0, 1)

    if gamma != 1.0:
        mask = np.power(np.clip(mask, 0, 1), gamma)

    # Seuillage après stretch
    mask_max = mask.max()
    if mask_max > 0:
        cutoff = mask_max * 0.02
        mask[mask < cutoff] = 0

    if WEIGHT_MIN > 0:
        mask = np.where(mask > 0, WEIGHT_MIN + mask * (1.0 - WEIGHT_MIN), 0.0)

    return np.clip(mask, 0, 1)


def module_masques_base(dem: np.ndarray, terrain: Dict) -> Dict[str, np.ndarray]:
    """
    Module 3 : Génération masques de base.

    Returns:
        dict {nom_masque: array}
    """
    print("[3/8] Génération masques de base...")

    masques = {}

    slope = terrain['slope']

    # Calcul seuils automatiques depuis percentiles
    slope_active = slope[slope > 0]
    t = {
        'gentle': THRESHOLD_GENTLE if THRESHOLD_GENTLE is not None else np.percentile(slope_active, 70),
        'landes': THRESHOLD_LANDES if THRESHOLD_LANDES is not None else np.percentile(slope_active, 85),
        'rock':   THRESHOLD_ROCK   if THRESHOLD_ROCK   is not None else np.percentile(slope_active, 90),
        'cliff':  THRESHOLD_CLIFF  if THRESHOLD_CLIFF  is not None else np.percentile(slope_active, 95),
    }

    # Seabed
    masques['mask_seabed'] = generate_seabed(dem)

    # Coastal
    masques['mask_coastal'] = generate_coastal(dem, terrain['coastal_distance'])

    # Pente
    masques['mask_landes_rocheuses'] = generate_landes_rocheuses(terrain['slope'], t)
    masques['mask_rock'] = generate_rock(terrain['slope'])

    # Gaea (optionnels)
    flow = load_gaea_mask(GAEA_FLOW, dem.shape)
    if flow is not None:
        masques['mask_flow'] = apply_output_curve(flow, gamma=0.5)

    deposit = load_gaea_mask(GAEA_DEPOSIT, dem.shape)
    if deposit is not None:
        # Appliquer cut_low : couper les zones de faible dépôt
        if deposit.max() > 0:
            threshold = deposit.max() * 0.30
            deposit[deposit < threshold] = 0
        masques['mask_deposit'] = apply_output_curve(deposit, gamma=1.0)

    print(f"       Masques de base : seabed, coastal (40m), landes, rock, Gaea ({len(masques)} actifs)")

    return masques


# ============================================================================
# MODULE 4 — VÉGÉTATION
# ============================================================================

def generate_alpages(dem: np.ndarray, slope: np.ndarray) -> np.ndarray:
    """
    Génère masque alpages.
    Copié depuis pipeline_v3.py::generate_vegetation_masks.
    """
    from scipy.ndimage import gaussian_filter

    land_mask = dem > 0
    land = land_mask.astype(np.float32)

    # Paramètres auto-calibrés
    debris_min = 18.0
    rock_min = 28.0

    def _bell(arr, lo, hi, slope=10.0):
        center = (lo + hi) / 2.0
        half = (hi - lo) / 2.0 + 1e-6
        dist = np.abs(arr - center) - half
        return np.clip(1.0 - dist / (slope + 1e-6), 0.0, 1.0)

    flat = np.clip(1 - slope / (debris_min + 1e-9), 0, 1)
    gentle = _bell(slope, 5, debris_min, slope=5)
    steep = np.clip((slope - debris_min) / (rock_min - debris_min + 1), 0, 1)

    # TPI macro
    from scipy.ndimage import uniform_filter as uf
    tpi_macro = dem - uf(dem, size=50)
    tpi_macro = np.clip(tpi_macro / (np.abs(tpi_macro).max() + 1e-9), -1, 1)
    tpi_mac_pos = np.clip(tpi_macro, 0, 1)

    alpages = (
        np.clip((dem - 180) / 80, 0, 1) * (flat * 0.7 + gentle * 0.3) * land
        * (0.7 + tpi_mac_pos * 0.4 + (1 - steep) * 0.2)
    )

    alpages = gaussian_filter(alpages.astype(np.float32), sigma=2.5)
    alpages = np.clip(alpages, 0, 1)
    alpages = np.where(alpages >= VEG_MIN_SCORE, alpages, 0.0)

    return alpages


def generate_foret_coniferes(dem: np.ndarray, slope: np.ndarray, aspect: np.ndarray, coastal_distance: np.ndarray) -> np.ndarray:
    """
    Génère masque forêt conifères.
    Copié depuis pipeline_v3.py::generate_vegetation_masks.
    """
    from scipy.ndimage import gaussian_filter

    land_mask = dem > 0
    land = land_mask.astype(np.float32)

    # Paramètres auto-calibrés
    alt_min = float(np.nanmin(dem[land_mask])) if land_mask.any() else 0
    alt_max = float(np.nanmax(dem[land_mask])) if land_mask.any() else 500
    debris_min = 18.0
    rock_min = 28.0
    coastal_alt_max = 15.0
    coastal_distance_max = 60.0

    def _bell(arr, lo, hi, slope=10.0):
        center = (lo + hi) / 2.0
        half = (hi - lo) / 2.0 + 1e-6
        dist = np.abs(arr - center) - half
        return np.clip(1.0 - dist / (slope + 1e-6), 0.0, 1.0)

    alt_pine = _bell(dem, 0, 250, slope=40)

    flat = np.clip(1 - slope / (debris_min + 1e-9), 0, 1)
    gentle = _bell(slope, 5, debris_min, slope=5)
    steep = np.clip((slope - debris_min) / (rock_min - debris_min + 1), 0, 1)
    rocky = np.clip((slope - rock_min) / 20, 0, 1)

    # Aspect
    north = np.cos(np.radians(aspect))
    south_f = np.clip((-north + 1) / 2, 0, 1)

    # Distance côte normalisée
    dist_w_norm = np.clip(coastal_distance / 500, 0, 1)

    # Curvature pour flow proxy
    c = 4.0  # cellsize
    curv_x = (np.roll(dem, -1, axis=1) - 2*dem + np.roll(dem, 1, axis=1)) / c**2
    curv_y = (np.roll(dem, -1, axis=0) - 2*dem + np.roll(dem, 1, axis=0)) / c**2
    curvature = np.clip((curv_x + curv_y) / (np.abs(curv_x + curv_y).max() + 1e-9), -1, 1)
    flow = np.clip(-curvature * 0.5 + (1 - slope / (slope.max() + 1e-9)) * 0.5, 0, 1)

    humid = np.clip(flow * 0.6 + (1 - dist_w_norm) * 0.4, 0, 1)
    dry = np.clip(1 - humid, 0, 1)

    coastal = ((coastal_distance < coastal_distance_max) &
               (dem < coastal_alt_max)).astype(np.float32)
    non_coastal = 1 - coastal

    coastal_zone = np.clip(1 - coastal_distance / 800, 0, 1)
    interior = np.clip((coastal_distance - 600) / 1200, 0, 1)

    foret_coniferes = (
        alt_pine * (coastal_zone * 0.7 + (1 - interior) * 0.3) * non_coastal * land
        * (0.5 + south_f * 0.30 + dry * 0.15 + rocky * 0.10)
        * (flat * 0.6 + gentle * 0.4)
    )

    foret_coniferes = gaussian_filter(foret_coniferes.astype(np.float32), sigma=2.5)
    foret_coniferes = np.clip(foret_coniferes, 0, 1)
    foret_coniferes = np.where(foret_coniferes >= VEG_MIN_SCORE, foret_coniferes, 0.0)

    return foret_coniferes


def module_vegetation(dem: np.ndarray, terrain: Dict) -> Dict[str, np.ndarray]:
    """
    Module 4 : Génération masques végétation.

    Returns:
        dict {nom_masque: array}
    """
    print("[4/8] Génération masques végétation...")

    masques = {}

    slope = terrain['slope']
    aspect = terrain['aspect']
    coastal_distance = terrain['coastal_distance']

    # Prairie humide (zones basses, pente douce)
    prairie_humide = np.clip((80 - dem) / 80, 0, 1) * np.clip((12 - slope) / 12, 0, 1)
    masques['mask_prairie_humide'] = prairie_humide

    # Prairie sèche (zones moyennes, pente douce)
    prairie_seche = np.clip((dem - 15) / 35, 0, 1) * np.clip((80 - dem) / 30, 0, 1) * np.clip((15 - slope) / 15, 0, 1)
    masques['mask_prairie_seche'] = prairie_seche

    # Landes plateau (zones élevées, pente moyenne)
    landes_plateau = np.clip((dem - 100) / 50, 0, 1) * np.clip((slope - 10) / 10, 0, 1)
    masques['mask_landes_plateau'] = landes_plateau

    # Maquis landes (zones variées)
    maquis_landes = np.clip((dem - 30) / 50, 0, 1) * np.clip((slope - 8) / 8, 0, 1) * np.clip((25 - slope) / 10, 0, 1)
    masques['mask_maquis_landes'] = maquis_landes

    # Alpages (depuis pipeline_v3)
    masques['mask_alpages'] = generate_alpages(dem, slope)

    # Forêt feuillue (altitude moyenne)
    foret_feuillue = np.clip((dem - 30) / 40, 0, 1) * np.clip((18 - slope) / 18, 0, 1) * 0.8
    masques['mask_foret_feuillue'] = foret_feuillue

    # Forêt conifères (depuis pipeline_v3)
    masques['mask_foret_coniferes'] = generate_foret_coniferes(dem, slope, aspect, coastal_distance)

    print(f"       Masques végétation générés : {len(masques)} masques")

    return masques


# ============================================================================
# MODULE 5 — MASQUE EXCLUSION
# ============================================================================

def module_exclusion(masques: Dict[str, np.ndarray], exclusion_path: Optional[Path]) -> Dict[str, np.ndarray]:
    """
    Module 5 : Application masque exclusion.
    """
    if exclusion_path is None or not exclusion_path.exists():
        print("[5/8] Pas de masque exclusion")
        return masques

    print("[5/8] Application masque exclusion...")

    img = cv2.imread(str(exclusion_path), cv2.IMREAD_UNCHANGED)
    if img is None:
        print("       WARNING : Impossible de lire le masque exclusion")
        return masques

    if len(img.shape) == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Resize si nécessaire
    first_mask = next(iter(masques.values()))
    if img.shape != first_mask.shape:
        img = cv2.resize(img, (first_mask.shape[1], first_mask.shape[0]), interpolation=cv2.INTER_NEAREST)

    # Binaire : blanc = Zone B (où les masques s'appliquent)
    exclusion = (img > 0)

    # Appliquer à tous les masques sauf seabed : mettre à 0 les pixels noirs (Zone A)
    for name in masques:
        if name == 'mask_seabed':
            continue  # seabed sur toute la map
        masques[name][~exclusion] = 0

    excluded_pct = (~exclusion).sum() / exclusion.size * 100
    print(f"       Masque exclusion appliqué : {excluded_pct:.1f}% pixels Zone A exclus (seabed préservé)")

    return masques


# ============================================================================
# MODULE 6 — NORMALISATION EXCLUSIVE
# ============================================================================

def module_normalize(masques: Dict[str, np.ndarray]) -> Dict[str, np.ndarray]:
    """
    Module 6 : Normalisation exclusive selon MASK_PRIORITY.
    """
    print("[6/8] Normalisation exclusive...")

    # Retirer masques non présents de MASK_PRIORITY
    priority_active = [name for name in MASK_PRIORITY if name in masques]

    first_mask = next(iter(masques.values()))
    h, w = first_mask.shape

    # Pour chaque pixel, attribuer au masque de priorité max
    normalized = {name: np.zeros((h, w), dtype=np.float32) for name in masques.keys()}

    for y in range(h):
        for x in range(w):
            # Collecter poids tous masques
            weights = {name: masques[name][y, x] for name in priority_active}

            # Trouver masque avec poids max selon priorité
            max_weight = 0
            winner = None
            for name in priority_active:
                if weights[name] > max_weight:
                    max_weight = weights[name]
                    winner = name

            if winner is not None:
                normalized[winner][y, x] = max_weight

    print(f"       Normalisation exclusive : {len(priority_active)} masques actifs")

    return normalized


# ============================================================================
# MODULE 7 — ARBITRAGE BUDGET
# ============================================================================

def module_budget(masques: Dict[str, np.ndarray], surfaces: List[Dict]) -> Tuple[Dict[str, np.ndarray], int]:
    """
    Module 7 : Arbitrage budget par bloc.

    Returns:
        masques corrigés, nombre blocs corrigés
    """
    print("[7/8] Arbitrage budget...")

    # TODO : Implémenter lecture .edds + fusion selon budget
    # Pour l'instant, retourner masques inchangés

    blocs_corriges = 0
    blocs_total = 128 * 128

    print(f"       Arbitrage budget : {blocs_corriges} blocs corrigés sur {blocs_total}")

    return masques, blocs_corriges


# ============================================================================
# MODULE 8 — EXPORT
# ============================================================================

def module_export(masques: Dict[str, np.ndarray], output_dir: Path) -> int:
    """
    Module 8 : Export masques 4096×4096.

    Returns:
        nombre warnings budget
    """
    print("[8/8] Export masques...")

    output_dir.mkdir(parents=True, exist_ok=True)

    # Créer dictionnaire ordre masques selon MASK_PRIORITY
    mask_order = {mask_name: idx + 1 for idx, mask_name in enumerate(MASK_PRIORITY)}

    warnings_budget = 0

    for name, mask in masques.items():
        # Resize à OUTPUT_SIZE
        if mask.shape[0] != OUTPUT_SIZE or mask.shape[1] != OUTPUT_SIZE:
            mask = cv2.resize(mask, (OUTPUT_SIZE, OUTPUT_SIZE), interpolation=cv2.INTER_AREA)

        # Seuillage final
        mask_max = mask.max()
        if mask_max > 0:
            cutoff = mask_max * 0.01
            mask[mask < cutoff] = 0

        # Convertir 0-1 → 0-65535
        mask_uint16 = (mask * 65535).astype(np.uint16)

        # Préfixer nom avec numéro d'ordre si dans MASK_PRIORITY
        if name in mask_order:
            filename = f"{mask_order[name]:02d}_{name}.png"
        else:
            filename = f"{name}.png"

        # Sauvegarder
        output_path = output_dir / filename
        cv2.imwrite(str(output_path), mask_uint16)

        print(f"       {filename}")

    print(f"       Export terminé : {len(masques)} masques dans {output_dir}, {warnings_budget} warnings budget")

    return warnings_budget


# ============================================================================
# MAIN
# ============================================================================

def main():
    print("=" * 70)
    print("PIPELINE UNIFIÉ — Génération masques terrain")
    print("=" * 70)

    # Module 1
    dem, cellsize = load_heightmap_asc(ASC_PATH)

    # Module 2
    terrain = module_terrain(dem, cellsize)

    # Module 3
    masques = module_masques_base(dem, terrain)

    # Module 4
    masques_veg = module_vegetation(dem, terrain)
    masques.update(masques_veg)

    # Module 5
    masques = module_exclusion(masques, EXCLUSION_MASK)

    # Module 6
    masques = module_normalize(masques)

    # Module 7
    surfaces = read_mats_from_terr(TERR_PATH) if TERR_PATH.exists() else []
    masques, blocs_corriges = module_budget(masques, surfaces)

    # Module 8
    warnings = module_export(masques, OUTPUT_DIR)

    print("=" * 70)
    print("PIPELINE TERMINÉ")
    print("=" * 70)

    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
