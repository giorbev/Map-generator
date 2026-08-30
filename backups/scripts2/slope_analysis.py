#!/usr/bin/env python3
"""
slope_analysis.py - Analyse géomorphologique et cartes de pentes
Générique : fonctionne avec n'importe quel heightmap .asc

Usage:
    python slope_analysis.py

Configuration: modifier la section CONFIG ci-dessous
"""

import struct
import numpy as np
import cv2
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from pathlib import Path

# ============================================================================
# CONFIG - À ADAPTER SELON LA CARTE
# ============================================================================

# Chemins
ASC_PATH = Path(r"I:\Reforger_addons travail\Zimnitrita_map\heightmap\Terrain_modified5.asc")
SATMAP_PATH = Path(r"H:\logiciel perso\Map generator\satmap_v2_textured_4097__13_.png")
MASKS_DIR = Path(r"H:\logiciel perso\Map generator\export")  # dossier masques PNG
OUTPUT_DIR = Path(r"H:\logiciel perso\Map generator\slope_output")

# Paramètres carte (Zimnitrita 32x32 tiles)
TILES_X = 32
TILES_Y = 32

# Seuils de pente en degrés
# None = calculé automatiquement depuis les percentiles
# Ou fixer manuellement ex: THRESHOLD_LANDES = 20.0
THRESHOLD_GENTLE   = None   # pente douce / terrain plat  (auto: p70)
THRESHOLD_LANDES   = None   # début landes rocheuses       (auto: p85)
THRESHOLD_ROCK     = None   # début rock                   (auto: p90)
THRESHOLD_CLIFF    = None   # falaise / roche nue          (auto: p95)

# Masques flow/deposit à superposer (noms de fichiers dans MASKS_DIR)
MASK_FLOW_NAME    = "10_mask_flow.png"      # None pour désactiver
MASK_DEPOSIT_NAME = "11_mask_deposit.png"   # None pour désactiver

# ============================================================================
# LECTURE DU HEIGHTMAP
# ============================================================================

def read_asc(path: Path) -> tuple:
    """Lit un fichier ASC et retourne (dem, cellsize, nodata)."""
    print(f"[READ] {path.name}...")
    with open(path, 'r') as f:
        ncols    = int(f.readline().split()[1])
        nrows    = int(f.readline().split()[1])
        xll      = float(f.readline().split()[1])
        yll      = float(f.readline().split()[1])
        cellsize = float(f.readline().split()[1])
        nodata   = float(f.readline().split()[1])
        data = []
        for line in f:
            data.extend(float(x) for x in line.split())

    dem = np.array(data, dtype=np.float32).reshape(nrows, ncols)
    dem[dem == nodata] = np.nan
    print(f"  → {ncols}×{nrows}, cellsize={cellsize}m, alt [{np.nanmin(dem):.0f}m, {np.nanmax(dem):.0f}m]")
    return dem, cellsize


# ============================================================================
# CALCUL DES PENTES
# ============================================================================

def compute_slope(dem: np.ndarray, cellsize: float) -> np.ndarray:
    """Calcule la pente en degrés (Zevenbergen & Thorne)."""
    print("[SLOPE] Calcul des pentes...")
    dz_dx = (np.roll(dem, -1, axis=1) - np.roll(dem, 1, axis=1)) / (2 * cellsize)
    dz_dy = (np.roll(dem, -1, axis=0) - np.roll(dem, 1, axis=0)) / (2 * cellsize)

    # Corriger les bords
    dz_dx[:, 0]  = (dem[:, 1]  - dem[:, 0])  / cellsize
    dz_dx[:, -1] = (dem[:, -1] - dem[:, -2]) / cellsize
    dz_dy[0, :]  = (dem[1, :]  - dem[0, :])  / cellsize
    dz_dy[-1, :] = (dem[-1, :] - dem[-2, :]) / cellsize

    slope = np.degrees(np.arctan(np.sqrt(dz_dx**2 + dz_dy**2)))
    print(f"  → min={np.nanmin(slope):.1f}° max={np.nanmax(slope):.1f}° moyenne={np.nanmean(slope):.1f}°")
    return slope


# ============================================================================
# ANALYSE STATISTIQUE ET SEUILS AUTOMATIQUES
# ============================================================================

def analyze_and_set_thresholds(slope: np.ndarray) -> dict:
    """Analyse la distribution et calcule les seuils."""
    global THRESHOLD_GENTLE, THRESHOLD_LANDES, THRESHOLD_ROCK, THRESHOLD_CLIFF

    print("\n[STATS] Distribution des pentes:")
    percentiles = {}
    for p in [50, 70, 75, 80, 85, 90, 95, 99]:
        v = np.nanpercentile(slope, p)
        percentiles[p] = v
        print(f"  p{p:2d}: {v:5.1f}°")

    print("\n  Répartition par tranches:")
    tranches = [(0,5),(5,10),(10,15),(15,20),(20,25),(25,30),(30,35),(35,45),(45,90)]
    for lo, hi in tranches:
        pct = ((slope >= lo) & (slope < hi)).sum() / slope.size * 100
        print(f"    {lo:2d}-{hi:2d}°: {pct:.1f}%")

    # Seuils automatiques si non définis
    if THRESHOLD_GENTLE is None:
        THRESHOLD_GENTLE = round(percentiles[70], 1)
    if THRESHOLD_LANDES is None:
        THRESHOLD_LANDES = round(percentiles[85], 1)
    if THRESHOLD_ROCK is None:
        THRESHOLD_ROCK = round(percentiles[90], 1)
    if THRESHOLD_CLIFF is None:
        THRESHOLD_CLIFF = round(percentiles[95], 1)

    thresholds = {
        'gentle':  THRESHOLD_GENTLE,
        'landes':  THRESHOLD_LANDES,
        'rock':    THRESHOLD_ROCK,
        'cliff':   THRESHOLD_CLIFF,
    }

    print(f"\n[SEUILS] Utilisés:")
    print(f"  Terrain plat/doux  : 0 → {thresholds['gentle']}° (p70)")
    print(f"  Landes rocheuses   : {thresholds['gentle']}° → {thresholds['landes']}° (p85)")
    print(f"  Rock               : {thresholds['landes']}° → {thresholds['rock']}° (p90)")
    print(f"  Rock dominant      : {thresholds['rock']}° → {thresholds['cliff']}° (p95)")
    print(f"  Falaise/roche nue  : {thresholds['cliff']}°+ (p95+)")

    return thresholds


# ============================================================================
# HISTOGRAMME
# ============================================================================

def generate_histogram(slope: np.ndarray, thresholds: dict, output_dir: Path):
    """Génère un histogramme de distribution des pentes avec seuils."""
    print("\n[HISTO] Génération histogramme...")

    fig, ax = plt.subplots(1, 1, figsize=(14, 6))
    fig.patch.set_facecolor('#1a1a2e')
    ax.set_facecolor('#16213e')

    # Histogramme
    valid = slope[~np.isnan(slope)].flatten()
    counts, bins, patches = ax.hist(valid, bins=180, range=(0, 90),
                                     color='#4ecdc4', alpha=0.7, edgecolor='none')

    # Colorier les barres selon les zones
    t = thresholds
    colors_zones = [
        (0,            t['gentle'],  '#2ecc71', 'Plat/doux'),
        (t['gentle'],  t['landes'],  '#f39c12', 'Landes rocheuses'),
        (t['landes'],  t['rock'],    '#e74c3c', 'Rock'),
        (t['rock'],    t['cliff'],   '#c0392b', 'Rock dominant'),
        (t['cliff'],   90,           '#8e44ad', 'Falaise'),
    ]
    for lo, hi, color, label in colors_zones:
        for patch, left in zip(patches, bins[:-1]):
            if lo <= left < hi:
                patch.set_facecolor(color)
                patch.set_alpha(0.8)

    # Lignes de seuil
    for key, color, label in [
        ('gentle', '#f39c12', f"p70 = {t['gentle']}°"),
        ('landes', '#e74c3c', f"p85 = {t['landes']}°"),
        ('rock',   '#c0392b', f"p90 = {t['rock']}°"),
        ('cliff',  '#8e44ad', f"p95 = {t['cliff']}°"),
    ]:
        ax.axvline(t[key], color=color, linewidth=2, linestyle='--', alpha=0.9)
        ax.text(t[key]+0.3, ax.get_ylim()[1]*0.95, label,
                color=color, fontsize=9, va='top', fontweight='bold')

    ax.set_xlabel('Pente (degrés)', color='white', fontsize=12)
    ax.set_ylabel('Nombre de pixels', color='white', fontsize=12)
    ax.set_title('Distribution des pentes — Zimnitrita', color='white', fontsize=14, fontweight='bold')
    ax.tick_params(colors='white')
    for spine in ax.spines.values():
        spine.set_edgecolor('#333')

    # Légende
    legend_patches = [mpatches.Patch(color=c, label=l) for _, _, c, l in colors_zones]
    ax.legend(handles=legend_patches, loc='upper right',
              facecolor='#1a1a2e', edgecolor='#444', labelcolor='white')

    out = output_dir / "slope_histogram.png"
    plt.tight_layout()
    plt.savefig(str(out), dpi=150, bbox_inches='tight', facecolor='#1a1a2e')
    plt.close()
    print(f"  → {out.name}")
    return out


# ============================================================================
# CARTE HEATMAP PENTES
# ============================================================================

def generate_heatmap(slope: np.ndarray, thresholds: dict, satmap: np.ndarray,
                     size: int, output_dir: Path) -> Path:
    """Génère la heatmap des pentes superposée à la satmap."""
    print("\n[HEATMAP] Génération carte pentes...")

    t = thresholds
    result = satmap.astype(np.float32).copy()

    # Zones et couleurs BGR
    zones = [
        (t['gentle'],  t['landes'],  (0, 200, 255), 0.45),  # jaune  - landes douces
        (t['landes'],  t['rock'],    (0, 130, 255), 0.60),  # orange - landes rocheuses
        (t['rock'],    t['cliff'],   (0, 0, 255),   0.70),  # rouge  - rock
        (t['cliff'],   90,           (80, 0, 220),  0.80),  # violet - falaise
    ]

    for lo, hi, color, alpha in zones:
        mask = (slope >= lo) & (slope < hi)
        for c, col in enumerate(color):
            result[:,:,c][mask] = result[:,:,c][mask] * (1-alpha) + col * alpha

    # Isolignes
    for threshold, color, thickness in [
        (t['landes'], (0, 255, 255), 1),   # cyan
        (t['rock'],   (255, 200, 0), 1),   # bleu clair
        (t['cliff'],  (200, 0, 255), 1),   # violet
    ]:
        mask_iso = ((slope >= threshold - 0.5) & (slope < threshold + 0.5)).astype(np.uint8) * 255
        contours, _ = cv2.findContours(mask_iso, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(result, contours, -1, color, thickness)

    # Grille tiles avec numéros
    tile_pix = size // TILES_X
    for ty in range(TILES_Y + 1):
        y = ty * tile_pix
        if y < size:
            result[y, :, :] = result[y, :, :] * 0.3 + 160 * 0.7
    for tx in range(TILES_X + 1):
        x = tx * tile_pix
        if x < size:
            result[:, x, :] = result[:, x, :] * 0.3 + 160 * 0.7

    result = np.clip(result, 0, 255).astype(np.uint8)

    # Numéros de tiles
    for ty in range(TILES_Y):
        for tx in range(TILES_X):
            px = tx * tile_pix + 4
            py = ty * tile_pix + 12
            label = f"{tx},{ty}"
            cv2.putText(result, label, (px+1, py+1),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.22, (0,0,0), 1, cv2.LINE_AA)
            cv2.putText(result, label, (px, py),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.22, (220,220,220), 1, cv2.LINE_AA)

    # Légende
    legend = _make_legend(size, thresholds, [
        ((0, 200, 255), f"{t['gentle']}°-{t['landes']}° Landes douces"),
        ((0, 130, 255), f"{t['landes']}°-{t['rock']}° Landes rocheuses"),
        ((0, 0, 255),   f"{t['rock']}°-{t['cliff']}° Rock"),
        ((80, 0, 220),  f"{t['cliff']}°+ Falaise"),
        ((0, 255, 255), f"Isoline {t['landes']}° (p85)"),
        ((255, 200, 0), f"Isoline {t['rock']}° (p90)"),
        ((200, 0, 255), f"Isoline {t['cliff']}° (p95)"),
    ], title="PENTES")

    final = np.hstack([result, legend])
    out = output_dir / "slope_heatmap.png"
    cv2.imwrite(str(out), final)
    print(f"  → {out.name} ({final.shape[1]}×{final.shape[0]}px)")
    return out


# ============================================================================
# CARTE COMBINÉE PENTES + FLOW/DEPOSIT
# ============================================================================

def generate_combined(slope: np.ndarray, thresholds: dict, satmap: np.ndarray,
                      masks_dir: Path, size: int, output_dir: Path) -> Path:
    """Génère la carte combinée pentes + masques flow/deposit."""
    print("\n[COMBINED] Génération carte combinée...")

    t = thresholds
    result = satmap.astype(np.float32).copy()

    # Pentes en fond (alpha réduit pour laisser de la place aux masques)
    zones = [
        (t['gentle'],  t['landes'],  (0, 200, 255), 0.30),
        (t['landes'],  t['rock'],    (0, 130, 255), 0.45),
        (t['rock'],    t['cliff'],   (0, 0, 255),   0.55),
        (t['cliff'],   90,           (80, 0, 220),  0.65),
    ]
    for lo, hi, color, alpha in zones:
        mask = (slope >= lo) & (slope < hi)
        for c, col in enumerate(color):
            result[:,:,c][mask] = result[:,:,c][mask] * (1-alpha) + col * alpha

    legend_items = [
        ((0, 200, 255), f"Landes douces ({t['gentle']}-{t['landes']}°)"),
        ((0, 130, 255), f"Landes rocheuses ({t['landes']}-{t['rock']}°)"),
        ((0, 0, 255),   f"Rock ({t['rock']}-{t['cliff']}°)"),
        ((80, 0, 220),  f"Falaise ({t['cliff']}°+)"),
    ]

    # Overlay masque flow
    if MASK_FLOW_NAME:
        flow_path = masks_dir / MASK_FLOW_NAME
        if flow_path.exists():
            flow = cv2.imread(str(flow_path), cv2.IMREAD_GRAYSCALE)
            if flow.shape[0] != size:
                flow = cv2.resize(flow, (size, size), interpolation=cv2.INTER_LINEAR)
            flow_mask = flow > 128
            flow_color = (255, 200, 0)  # cyan
            alpha_flow = 0.65
            for c, col in enumerate(flow_color):
                result[:,:,c][flow_mask] = result[:,:,c][flow_mask] * (1-alpha_flow) + col * alpha_flow
            legend_items.append((flow_color, "Flow (talwegs/rivières)"))
            print(f"  + Flow: {flow_mask.sum()} pixels actifs")

    # Overlay masque deposit
    if MASK_DEPOSIT_NAME:
        dep_path = masks_dir / MASK_DEPOSIT_NAME
        if dep_path.exists():
            dep = cv2.imread(str(dep_path), cv2.IMREAD_GRAYSCALE)
            if dep.shape[0] != size:
                dep = cv2.resize(dep, (size, size), interpolation=cv2.INTER_LINEAR)
            dep_mask = dep > 128
            dep_color = (0, 165, 255)  # orange
            alpha_dep = 0.65
            for c, col in enumerate(dep_color):
                result[:,:,c][dep_mask] = result[:,:,c][dep_mask] * (1-alpha_dep) + col * alpha_dep
            legend_items.append((dep_color, "Deposit (sédiments)"))
            print(f"  + Deposit: {dep_mask.sum()} pixels actifs")

    # Grille + numéros
    tile_pix = size // TILES_X
    for ty in range(TILES_Y + 1):
        y = ty * tile_pix
        if y < size:
            result[y, :, :] = result[y, :, :] * 0.4 + 140 * 0.6
    for tx in range(TILES_X + 1):
        x = tx * tile_pix
        if x < size:
            result[:, x, :] = result[:, x, :] * 0.4 + 140 * 0.6

    result = np.clip(result, 0, 255).astype(np.uint8)

    for ty in range(TILES_Y):
        for tx in range(TILES_X):
            px = tx * tile_pix + 4
            py = ty * tile_pix + 12
            label = f"{tx},{ty}"
            cv2.putText(result, label, (px+1, py+1),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.22, (0,0,0), 1, cv2.LINE_AA)
            cv2.putText(result, label, (px, py),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.22, (220,220,220), 1, cv2.LINE_AA)

    legend = _make_legend(size, thresholds, legend_items, title="PENTES + FLOW/DEPOSIT")
    final = np.hstack([result, legend])
    out = output_dir / "slope_combined.png"
    cv2.imwrite(str(out), final)
    print(f"  → {out.name} ({final.shape[1]}×{final.shape[0]}px)")
    return out


# ============================================================================
# UTILITAIRE LÉGENDE
# ============================================================================

def _make_legend(size: int, thresholds: dict, items: list, title: str) -> np.ndarray:
    """Génère une légende verticale."""
    LEG_W = 340
    legend = np.full((size, LEG_W, 3), 20, dtype=np.uint8)

    cv2.putText(legend, title, (10, 35),
               cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255,255,255), 2)

    # Seuils
    t = thresholds
    cv2.putText(legend, f"Seuils (percentiles):", (10, 70),
               cv2.FONT_HERSHEY_SIMPLEX, 0.38, (180,180,180), 1)
    for i, (key, label) in enumerate([
        ('gentle', 'p70'), ('landes', 'p85'), ('rock', 'p90'), ('cliff', 'p95')
    ]):
        cv2.putText(legend, f"  {label}: {t[key]}°", (10, 90 + i*18),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.35, (160,160,160), 1)

    # Éléments
    y_start = 175
    for i, (color, label) in enumerate(items):
        y = y_start + i * 38
        cv2.rectangle(legend, (10, y-14), (32, y+8), color, -1)
        # Wrap long labels
        words = label.split()
        line1 = ' '.join(words[:4])
        line2 = ' '.join(words[4:]) if len(words) > 4 else ''
        cv2.putText(legend, line1, (40, y),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255,255,255), 1)
        if line2:
            cv2.putText(legend, line2, (40, y+16),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200,200,200), 1)

    return legend


# ============================================================================
# MAIN
# ============================================================================

def main():
    OUTPUT_DIR.mkdir(exist_ok=True, parents=True)
    SIZE = 4097

    # 1. Lire le DEM
    dem, cellsize = read_asc(ASC_PATH)

    # 2. Calculer les pentes
    slope = compute_slope(dem, cellsize)

    # 3. Analyser et définir les seuils
    thresholds = analyze_and_set_thresholds(slope)

    # 4. Charger la satmap
    print(f"\n[SATMAP] Chargement...")
    satmap = cv2.imread(str(SATMAP_PATH))
    if satmap is None:
        print(f"  [WARN] Satmap introuvable, fond noir utilisé")
        satmap = np.zeros((SIZE, SIZE, 3), dtype=np.uint8)
    else:
        if satmap.shape[0] != SIZE:
            satmap = cv2.resize(satmap, (SIZE, SIZE))
        print(f"  → {satmap.shape}")

    # 5. Histogramme
    generate_histogram(slope, thresholds, OUTPUT_DIR)

    # 6. Heatmap pentes
    generate_heatmap(slope, thresholds, satmap, SIZE, OUTPUT_DIR)

    # 7. Carte combinée pentes + flow/deposit
    generate_combined(slope, thresholds, satmap, MASKS_DIR, SIZE, OUTPUT_DIR)

    print(f"\n✅ Terminé ! Fichiers dans: {OUTPUT_DIR}")
    print(f"   - slope_histogram.png")
    print(f"   - slope_heatmap.png")
    print(f"   - slope_combined.png")


if __name__ == '__main__':
    main()
