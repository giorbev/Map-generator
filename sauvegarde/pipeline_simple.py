"""
Pipeline Simple — Génération 7 masques terrain
- Auto-calibration altitude (P10, P33, P66)
- Auto-calibration slope (Jenks)
- 7 masques : SeaBed + Coastal + 3 Grass zones + Debris + Rock
- Pas de superposition
"""

import numpy as np
from PIL import Image
from pathlib import Path
import json
from datetime import datetime


def load_asc(asc_path):
    """Charge heightmap ASC et retourne array + métadonnées"""
    print(f"[1/6] Chargement heightmap: {asc_path}")

    with open(asc_path, 'r') as f:
        lines = f.readlines()

    # Parse header
    ncols = int(lines[0].split()[1])
    nrows = int(lines[1].split()[1])
    xllcorner = float(lines[2].split()[1])
    yllcorner = float(lines[3].split()[1])
    cellsize = float(lines[4].split()[1])
    nodata = float(lines[5].split()[1])

    # Parse data
    data = []
    for line in lines[6:]:
        data.append([float(x) for x in line.split()])

    heightmap = np.array(data, dtype=np.float32)

    # Replace nodata
    heightmap[heightmap == nodata] = np.nan

    meta = {
        'ncols': ncols,
        'nrows': nrows,
        'cellsize': cellsize,
        'xllcorner': xllcorner,
        'yllcorner': yllcorner,
        'nodata': nodata
    }

    print(f"  Shape: {heightmap.shape}")
    print(f"  Altitude: {np.nanmin(heightmap):.2f}m - {np.nanmax(heightmap):.2f}m")

    return heightmap, meta


def calculate_slope(heightmap, cellsize):
    """Calcule slope en degrés pour chaque pixel"""
    print("[2/6] Calcul slope...")

    # Gradient
    dy, dx = np.gradient(heightmap)

    # Pente (degrés)
    rise_over_run = np.sqrt(dx**2 + dy**2) / cellsize
    slope = np.arctan(rise_over_run) * 180 / np.pi

    # NaN où heightmap est NaN
    slope[np.isnan(heightmap)] = np.nan

    print(f"  Slope: {np.nanmin(slope):.2f}° - {np.nanmax(slope):.2f}° (moyen: {np.nanmean(slope):.2f}°)")

    return slope


def auto_calibrate(heightmap, slope):
    """
    Auto-calibration altitude + slope

    Returns:
        dict: {
            'altitude': {'p10': X, 'p33': Y, 'p66': Z},
            'slope': {'debris_min': A, 'rock_min': B}
        }
    """
    print("[3/6] Auto-calibration...")

    # ── ALTITUDE ─────────────────────────────────────────────────────────────
    # Percentiles terrain ferme (altitude > 0m)
    land_mask = (heightmap > 0) & (~np.isnan(heightmap))
    land_alt = heightmap[land_mask]

    p10 = float(np.percentile(land_alt, 10))
    p33 = float(np.percentile(land_alt, 33))
    p66 = float(np.percentile(land_alt, 66))

    print(f"  Altitude P10 (coastal max): {p10:.1f}m")
    print(f"  Altitude P33 (lowland max): {p33:.1f}m")
    print(f"  Altitude P66 (midland max): {p66:.1f}m")

    # ── SLOPE ────────────────────────────────────────────────────────────────
    # Jenks Natural Breaks (si disponible) OU Percentiles fallback
    try:
        from jenkspy import jenks_breaks

        slope_valid = slope[~np.isnan(slope) & (slope > 0)]
        sample_size = min(100000, len(slope_valid))
        slope_sample = np.random.choice(slope_valid, sample_size, replace=False)

        breaks = jenks_breaks(slope_sample, n_classes=5)

        debris_min = float(breaks[2])  # Moderate min
        rock_min = float(breaks[3])    # Steep min (seuil rocheux)

        print(f"  Slope seuils (Jenks):")
        print(f"    Debris min: {debris_min:.1f}°")
        print(f"    Rock min: {rock_min:.1f}° <- seuil rocheux")

    except ImportError:
        # Fallback : Percentiles
        slope_valid = slope[~np.isnan(slope) & (slope > 0)]
        p50 = float(np.percentile(slope_valid, 50))
        p75 = float(np.percentile(slope_valid, 75))

        debris_min = p50
        rock_min = p75

        print(f"  Slope seuils (Percentiles fallback):")
        print(f"    Debris min: {debris_min:.1f}° (P50)")
        print(f"    Rock min: {rock_min:.1f}° (P75)")

    return {
        'altitude': {'p10': p10, 'p33': p33, 'p66': p66},
        'slope': {'debris_min': debris_min, 'rock_min': rock_min}
    }


def generate_masks(heightmap, slope, thresholds):
    """
    Génère 7 masques sans superposition

    Priorité:
      1. Slope (Debris, Rock) override tout
      2. Altitude (SeaBed, Coastal, Grass zones) sur zones plates uniquement

    Returns:
        dict: {name: boolean_array}
    """
    print("[4/7] Génération masques...")

    p10 = thresholds['altitude']['p10']
    p33 = thresholds['altitude']['p33']
    p66 = thresholds['altitude']['p66']

    debris_min = thresholds['slope']['debris_min']
    rock_min = thresholds['slope']['rock_min']

    # Masques SLOPE (priorité max, toutes altitudes)
    mask_debris = (slope >= debris_min) & (slope < rock_min)
    mask_rock = (slope >= rock_min)

    # Masques ALTITUDE (zones plates uniquement, slope < debris_min)
    flat_mask = (slope < debris_min) & (~np.isnan(slope))

    mask_seabed = (heightmap < 0) & flat_mask
    mask_coastal = (heightmap >= 0) & (heightmap < p10) & flat_mask
    mask_lowland = (heightmap >= p10) & (heightmap < p33) & flat_mask
    mask_midland = (heightmap >= p33) & (heightmap < p66) & flat_mask
    mask_highland = (heightmap >= p66) & flat_mask

    # Stats couverture
    total_pixels = np.sum(~np.isnan(heightmap))

    masks = {
        '01_seabed': mask_seabed,
        '02_coastal': mask_coastal,
        '03_grass_lowland': mask_lowland,
        '04_grass_midland': mask_midland,
        '05_grass_highland': mask_highland,
        '06_debris': mask_debris,
        '07_rock': mask_rock
    }

    print("  Couverture:")
    for name, mask in masks.items():
        pct = (np.sum(mask) / total_pixels) * 100
        print(f"    {name:20s}: {pct:5.2f}%")

    return masks


def export_masks(masks, output_dir):
    """Exporte masques PNG 16-bit"""
    print(f"[5/6] Export masques: {output_dir}")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for name, mask in masks.items():
        # Convertir boolean -> uint16 (0 ou 65535)
        mask_uint16 = mask.astype(np.uint16) * 65535

        # Remplacer NaN par 0
        mask_uint16[np.isnan(mask_uint16)] = 0

        # Sauvegarder PNG
        output_path = output_dir / f"{name}.png"
        Image.fromarray(mask_uint16).save(output_path)

        print(f"  {name}.png")

    print(f"  Total: {len(masks)} masques")


def save_calibration(thresholds, output_path):
    """Sauvegarde calibration JSON"""
    print(f"[6/6] Sauvegarde calibration: {output_path}")

    data = {
        'version': '1.0',
        'generated_at': datetime.now().isoformat(),
        'thresholds': thresholds
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print("  Calibration sauvegardée")


def run_pipeline(heightmap_path, output_dir):
    """
    Pipeline complet : heightmap -> 7 masques PNG

    Args:
        heightmap_path: chemin fichier ASC
        output_dir: dossier output masques
    """
    print("="*60)
    print("PIPELINE SIMPLE — GÉNÉRATION 7 MASQUES")
    print("="*60)

    # 1. Charger heightmap
    heightmap, meta = load_asc(heightmap_path)

    # 2. Calculer slope
    slope = calculate_slope(heightmap, meta['cellsize'])

    # 3. Auto-calibration
    thresholds = auto_calibrate(heightmap, slope)

    # 4. Générer masques
    masks = generate_masks(heightmap, slope, thresholds)

    # 5. Exporter PNG
    export_masks(masks, output_dir)

    # 6. Sauvegarder calibration
    calibration_path = Path(output_dir) / 'calibration.json'
    save_calibration(thresholds, calibration_path)

    print("\n" + "="*60)
    print("TERMINÉ !")
    print(f"Masques: {output_dir}")
    print("="*60)

    return thresholds


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage: python pipeline_simple.py <heightmap.asc> [output_dir]")
        print("Exemple: python pipeline_simple.py data/projects/Zbk_island/sources/temp_ZBK_terrain_modified7.asc")
        sys.exit(1)

    heightmap_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "output_masks"

    run_pipeline(heightmap_path, output_dir)
