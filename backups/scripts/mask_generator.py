#!/usr/bin/env python3
"""
mask_generator.py - Génération de masques terrain pour Reforger/Enfusion

Génère des masques PNG 16 bits normalisés depuis :
  - Un heightmap .asc (pentes calculées automatiquement)
  - Des masques Gaea PNG float32 (flow, deposit, etc.)
  - Un masque d'exclusion optionnel

Toutes les sorties sont normalisées à la résolution cible (OUTPUT_SIZE).

Usage:
    python mask_generator.py
"""

import numpy as np
import cv2
from pathlib import Path

# ============================================================================
# CONFIG — À ADAPTER
# ============================================================================

# Heightmap source
ASC_PATH = Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\sources\Terrain_modified5.asc")
# Masque d'exclusion (None pour désactiver)
# Blanc = zone active, Noir = zone protégée (masques = 0)
EXCLUSION_MASK = Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\masks\masque exclusion.png")

# Dossier de sortie
OUTPUT_DIR = Path(r"H:\logiciel perso\Map generator\masks_output")

# Résolution de sortie (pixels)
OUTPUT_SIZE = 4097

# Seuils de pente en degrés
# None = calculé automatiquement depuis les percentiles du heightmap
THRESHOLD_GENTLE = None   # p70 — début pentes notables
THRESHOLD_LANDES = None   # p85 — landes rocheuses
THRESHOLD_ROCK   = 22   # p90 — rock
THRESHOLD_CLIFF  = 26   # p95 — falaise

# Largeur de transition (degrés)
TRANSITION_WIDTH = 5.0

# Post-processing universel (appliqué à TOUS les masques en sortie)
STRETCH_AUTO = True   # normalise la plage dynamique via percentiles
WEIGHT_MIN   = 0.10  # poids minimum visible dans Workbench (0.0 = désactivé)

# ============================================================================
# MASQUES GAEA À NORMALISER
# Chaque entrée : (chemin_source, nom_sortie)
# Les masques float32 Gaea sont normalisés [0..1] → uint16
# ============================================================================
GAEA_MASKS = [
    (Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\masks\flow.png"),    "mask_flow",    0.5),
    (Path(r"H:\logiciel perso\Map generator\data\projects\Zimnitrita\masks\deposit.png"), "mask_deposit", 1.0),
    # Ajouter d'autres masques ici...
]

# Appliquer le masque d'exclusion aux masques Gaea aussi ?
APPLY_EXCLUSION_TO_GAEA = True

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
    print(f"  → {ncols}×{nrows}, cellsize={cellsize}m")
    return dem, cellsize


# ============================================================================
# CALCUL DES PENTES
# ============================================================================

def compute_slope(dem: np.ndarray, cellsize: float) -> np.ndarray:
    print("[SLOPE] Calcul des pentes (Zevenbergen & Thorne)...")
    dz_dx = (np.roll(dem, -1, axis=1) - np.roll(dem, 1, axis=1)) / (2 * cellsize)
    dz_dy = (np.roll(dem, -1, axis=0) - np.roll(dem, 1, axis=0)) / (2 * cellsize)
    dz_dx[:, 0]  = (dem[:, 1]  - dem[:, 0])  / cellsize
    dz_dx[:, -1] = (dem[:, -1] - dem[:, -2]) / cellsize
    dz_dy[0, :]  = (dem[1, :]  - dem[0, :])  / cellsize
    dz_dy[-1, :] = (dem[-1, :] - dem[-2, :]) / cellsize
    slope = np.degrees(np.arctan(np.sqrt(dz_dx**2 + dz_dy**2)))
    print(f"  → min={np.nanmin(slope):.1f}° max={np.nanmax(slope):.1f}° moy={np.nanmean(slope):.1f}°")
    return slope


# ============================================================================
# SEUILS AUTOMATIQUES
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
    """
    Charge un masque PNG (8, 16 ou float32) et le normalise en float32 [0..1].
    Redimensionne à out_size×out_size.
    """
    raw = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if raw is None:
        raise FileNotFoundError(f"Masque introuvable: {path}")

    # Gérer les différents formats
    if raw.ndim == 3:
        raw = cv2.cvtColor(raw, cv2.COLOR_BGR2GRAY)

    if raw.dtype == np.uint8:
        mask = raw.astype(np.float32) / 255.0
    elif raw.dtype == np.uint16:
        mask = raw.astype(np.float32) / 65535.0
    elif raw.dtype == np.float32:
        # Gaea exporte en float32, peut être > 1.0
        mask = raw.astype(np.float32)
        if mask.max() > 1.0:
            mask = mask / mask.max()
    else:
        mask = raw.astype(np.float32)
        mask = mask / max(mask.max(), 1.0)

    # Redimensionner si nécessaire
    if mask.shape[0] != out_size or mask.shape[1] != out_size:
        mask = cv2.resize(mask, (out_size, out_size), interpolation=cv2.INTER_LINEAR)

    return np.clip(mask, 0, 1)


def save_mask_16bit(mask_f32: np.ndarray, path: Path):
    """Sauvegarde un masque float32 [0..1] en PNG 16 bits."""
    mask_16 = (np.clip(mask_f32, 0, 1) * 65535).astype(np.uint16)
    cv2.imwrite(str(path), mask_16)


def smooth_transition(slope: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """Génère un gradient linéaire entre lo et hi (0 sous lo, 1 au-dessus de hi)."""
    result = np.zeros_like(slope, dtype=np.float32)
    in_range = (slope >= lo) & (slope < hi)
    result[in_range] = (slope[in_range] - lo) / (hi - lo)
    result[slope >= hi] = 1.0
    return result


def apply_output_curve(mask: np.ndarray, gamma: float = 1.0) -> np.ndarray:
    """Post-processing universel sur tous les masques en sortie."""
    # 1. Stretch percentile
    if STRETCH_AUTO:
        active = mask[mask > 0]
        if active.size > 0:
            lo = np.percentile(active, 2)
            hi = np.percentile(mask, 98)
            if hi > lo:
                mask = np.clip((mask - lo) / (hi - lo), 0, 1)

    # 2. Gamma
    if gamma != 1.0:
        mask = np.power(mask, gamma)

    # 3. Poids minimum visible
    if WEIGHT_MIN > 0:
        mask = np.where(mask > 0, WEIGHT_MIN + mask * (1.0 - WEIGHT_MIN), 0.0)

    return np.clip(mask, 0, 1)


# ============================================================================
# GÉNÉRATION DES MASQUES DE PENTE
# ============================================================================

def generate_slope_masks(slope: np.ndarray, t: dict,
                          exclusion: np.ndarray, out_size: int,
                          output_dir: Path):
    """Génère les masques landes_rocheuses et rock en 16 bits."""

    # Redimensionner la slope si nécessaire
    if slope.shape[0] != out_size:
        slope = cv2.resize(slope, (out_size, out_size), interpolation=cv2.INTER_LINEAR)

    # ================================================================
    # MASQUES MUTUELLEMENT EXCLUSIFS avec zone de transition neutre
    #
    # 0° → gentle        : zones plates (autres masques)
    # gentle → landes    : montée landes (0→1)
    # landes → landes+GAP: landes plein (1)
    # landes+GAP → rock  : zone NEUTRE (trou = 0 pour les deux)
    # rock → cliff       : montée rock (0→1)
    # cliff+             : rock plein (1)
    #
    # GAP = zone neutre entre les deux masques
    # ================================================================

    GAP = TRANSITION_WIDTH  # largeur de la zone neutre (degrés)

    # Fin du plateau landes = début de la zone neutre
    landes_end  = t['rock'] - GAP / 2   # landes s'arrête avant rock
    rock_start  = t['rock'] + GAP / 2   # rock commence après landes

    # --- LANDES ROCHEUSES ---
    landes = np.zeros((out_size, out_size), dtype=np.float32)
    # Montée : gentle → landes
    m_rise = (slope >= t['gentle']) & (slope < t['landes'])
    landes[m_rise] = (slope[m_rise] - t['gentle']) / (t['landes'] - t['gentle'])
    # Plateau : landes → landes_end
    m_plat = (slope >= t['landes']) & (slope < landes_end)
    landes[m_plat] = 1.0
    # Descente douce : landes_end → rock (entrée dans la zone neutre)
    m_fall = (slope >= landes_end) & (slope < t['rock'])
    landes[m_fall] = 1.0 - (slope[m_fall] - landes_end) / (t['rock'] - landes_end)
    # Zone neutre et au-delà = 0 (pas de plancher)

    landes[exclusion == 0] = 0.0
    landes = apply_output_curve(landes)
    save_mask_16bit(landes, output_dir / "mask_landes_rocheuses.png")
    pct = (landes > 0).sum() / landes.size * 100
    print(f"  [OK] mask_landes_rocheuses.png  — {pct:.1f}% actif")
    print(f"       Zones: gentle({t['gentle']}°) → plein({t['landes']}°) → neutre({landes_end:.1f}°) → 0")

    # --- ROCK ---
    rock = np.zeros((out_size, out_size), dtype=np.float32)
    # Zone neutre = 0 (pas de rock avant rock_start)
    # Montée : rock_start → cliff
    m_rise_r = (slope >= rock_start) & (slope < t['cliff'])
    rock[m_rise_r] = (slope[m_rise_r] - rock_start) / (t['cliff'] - rock_start)
    # Plateau : cliff et au-dessus
    rock[slope >= t['cliff']] = 1.0

    rock[exclusion == 0] = 0.0
    rock = apply_output_curve(rock)
    save_mask_16bit(rock, output_dir / "mask_rock.png")
    pct = (rock > 0).sum() / rock.size * 100
    print(f"  [OK] mask_rock.png              — {pct:.1f}% actif")
    print(f"       Zones: 0 → montée({rock_start:.1f}°) → plein({t['cliff']}°)")


# ============================================================================
# NORMALISATION DES MASQUES GAEA
# ============================================================================

def process_gaea_masks(gaea_masks: list, exclusion: np.ndarray,
                        out_size: int, output_dir: Path):
    """Charge, normalise et sauvegarde les masques Gaea en 16 bits."""
    for entry in gaea_masks:
        src_path, out_name, gamma = entry if len(entry) == 3 else (*entry, 1.0)
        if not src_path.exists():
            print(f"  [SKIP] {src_path.name} introuvable")
            continue

        mask = load_and_normalize_mask(src_path, out_size)

        if APPLY_EXCLUSION_TO_GAEA:
            mask[exclusion == 0] = 0.0

        mask = apply_output_curve(mask, gamma=gamma)
        print(f"       curve appliquée (gamma={gamma}, stretch={STRETCH_AUTO}, weight_min={WEIGHT_MIN})")

        out_path = output_dir / f"{out_name}.png"
        save_mask_16bit(mask, out_path)
        pct = (mask > 0).sum() / mask.size * 100
        print(f"  [OK] {out_path.name:<35} — {pct:.1f}% actif  "
              f"(src: {src_path.name})")


# ============================================================================
# MAIN
# ============================================================================

def main():
    OUTPUT_DIR.mkdir(exist_ok=True, parents=True)

    print("=" * 70)
    print("MASK GENERATOR — Masques terrain Reforger 16 bits")
    print("=" * 70)

    # 1. Charger et calculer les pentes
    dem, cellsize = read_asc(ASC_PATH)
    slope = compute_slope(dem, cellsize)
    t = compute_thresholds(slope)

    # 2. Charger le masque d'exclusion
    if EXCLUSION_MASK and EXCLUSION_MASK.exists():
        excl_raw = load_and_normalize_mask(EXCLUSION_MASK, OUTPUT_SIZE)
        exclusion = (excl_raw > 0.5).astype(np.uint8)  # binaire
        print(f"[EXCL] Masque d'exclusion: {exclusion.mean()*100:.1f}% actif")
    else:
        exclusion = np.ones((OUTPUT_SIZE, OUTPUT_SIZE), dtype=np.uint8)
        print("[EXCL] Pas de masque d'exclusion — toute la carte active")

    # 3. Générer les masques de pente
    print(f"\n[PENTE] Génération masques landes + rock...")
    generate_slope_masks(slope, t, exclusion, OUTPUT_SIZE, OUTPUT_DIR)

    # 4. Normaliser les masques Gaea
    if GAEA_MASKS:
        print(f"\n[GAEA] Normalisation {len(GAEA_MASKS)} masque(s)...")
        process_gaea_masks(GAEA_MASKS, exclusion, OUTPUT_SIZE, OUTPUT_DIR)

    print(f"\n✅ Terminé ! {OUTPUT_DIR}")
    print(f"   Résolution: {OUTPUT_SIZE}×{OUTPUT_SIZE} px, format: PNG 16 bits")
    print(f"   Seuils: gentle={t['gentle']}° landes={t['landes']}° "
          f"rock={t['rock']}° cliff={t['cliff']}°")


if __name__ == '__main__':
    main()
