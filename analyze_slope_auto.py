"""
Analyse SLOPE automatique depuis heightmap ASC
- Calcul slope précis (pixel-perfect)
- Carte heatmap visualisation
- Auto-détection seuils pentes rocheuses (Jenks Natural Breaks)
- Histogramme distribution
- Export masques zones rocheuses
"""

import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import json

# Installer jenkspy si pas déjà fait : pip install jenkspy
try:
    from jenkspy import jenks_breaks
    HAS_JENKS = True
except ImportError:
    print("WARNING: jenkspy non installé. Auto-détection optimale désactivée.")
    print("Installer avec: pip install jenkspy")
    HAS_JENKS = False


def load_asc(asc_path):
    """Charge heightmap ASC et retourne array + métadonnées"""
    print(f"Chargement heightmap: {asc_path}")

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
    print(f"  Altitude min: {np.nanmin(heightmap):.2f}m")
    print(f"  Altitude max: {np.nanmax(heightmap):.2f}m")

    return heightmap, meta


def calculate_slope(heightmap, cellsize):
    """
    Calcule slope en degrés pour chaque pixel.

    Args:
        heightmap: array 2D altitudes (mètres)
        cellsize: taille pixel (mètres)

    Returns:
        slope: array 2D pentes (degrés 0-90)
    """
    print("\nCalcul slope...")

    # Gradient (rise/run)
    dy, dx = np.gradient(heightmap)

    # Convertir en pente (degrés)
    # rise = altitude change, run = cellsize
    rise_over_run = np.sqrt(dx**2 + dy**2) / cellsize
    slope = np.arctan(rise_over_run) * 180 / np.pi

    # NaN où heightmap est NaN
    slope[np.isnan(heightmap)] = np.nan

    print(f"  Slope min: {np.nanmin(slope):.2f}°")
    print(f"  Slope max: {np.nanmax(slope):.2f}°")
    print(f"  Slope moyen: {np.nanmean(slope):.2f}°")

    return slope


def detect_slope_thresholds(slope):
    """
    Détecte automatiquement les seuils de pente.

    Returns:
        dict: seuils détectés (gentle, moderate, steep, cliff)
    """
    print("\nDétection automatique seuils...")

    # Filtrer NaN et slope > 0
    slope_valid = slope[~np.isnan(slope) & (slope > 0)]

    # Percentiles (méthode simple)
    p25 = np.percentile(slope_valid, 25)
    p50 = np.percentile(slope_valid, 50)
    p75 = np.percentile(slope_valid, 75)
    p90 = np.percentile(slope_valid, 90)
    p95 = np.percentile(slope_valid, 95)

    print(f"  P25: {p25:.1f}°")
    print(f"  P50: {p50:.1f}°")
    print(f"  P75: {p75:.1f}°")
    print(f"  P90: {p90:.1f}°")
    print(f"  P95: {p95:.1f}°")

    thresholds = {
        'percentiles': {
            'gentle_max': p25,
            'moderate_max': p50,
            'steep_max': p75,
            'cliff_min': p90,
            'vertical_min': p95
        }
    }

    # Jenks Natural Breaks (méthode optimale)
    if HAS_JENKS:
        print("\n  Jenks Natural Breaks (optimal)...")

        # Échantillonner pour accélérer (Jenks lent sur gros datasets)
        sample_size = min(100000, len(slope_valid))
        slope_sample = np.random.choice(slope_valid, sample_size, replace=False)

        # 5 classes : flat, gentle, moderate, steep, cliff
        breaks = jenks_breaks(slope_sample, n_classes=5)

        print(f"  Breaks: {[f'{b:.1f}°' for b in breaks]}")

        thresholds['jenks'] = {
            'flat_max': breaks[1],
            'gentle_max': breaks[2],
            'moderate_max': breaks[3],
            'steep_max': breaks[4],
            'cliff_min': breaks[3],  # Début falaises = break 3
        }

        # Seuil rocheux recommandé = break 3 (cliff)
        thresholds['recommended_rock_threshold'] = breaks[3]
        print(f"\n  SEUIL ROCHEUX RECOMMANDÉ: {breaks[3]:.1f}° (Jenks break 3)")

    else:
        # Fallback sans Jenks : utiliser P75
        thresholds['recommended_rock_threshold'] = p75
        print(f"\n  SEUIL ROCHEUX RECOMMANDÉ: {p75:.1f}° (P75)")

    return thresholds


def plot_slope_heatmap(slope, output_path, thresholds=None):
    """
    Génère carte heatmap slope.

    Args:
        slope: array 2D pentes
        output_path: chemin PNG sortie
        thresholds: dict seuils (optionnel, pour overlay)
    """
    print(f"\nGénération heatmap: {output_path}")

    fig, ax = plt.subplots(figsize=(12, 10), dpi=150)

    # Colormap custom
    from matplotlib.colors import LinearSegmentedColormap
    colors = ['#2E7D32', '#66BB6A', '#FFEB3B', '#FF9800', '#D32F2F', '#000000']
    n_bins = 100
    cmap = LinearSegmentedColormap.from_list('slope', colors, N=n_bins)

    # Afficher slope
    im = ax.imshow(slope, cmap=cmap, vmin=0, vmax=60, interpolation='bilinear')

    # Colorbar
    cbar = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label('Pente (degrés)', rotation=270, labelpad=20, fontsize=12)

    # Titre
    title = "Carte Slope (Pentes)"
    if thresholds and 'recommended_rock_threshold' in thresholds:
        rock_thresh = thresholds['recommended_rock_threshold']
        title += f"\nSeuil rocheux recommandé: {rock_thresh:.1f}°"
    ax.set_title(title, fontsize=14, fontweight='bold')

    ax.axis('off')
    plt.tight_layout()
    plt.savefig(output_path, bbox_inches='tight')
    plt.close()

    print(f"  Sauvegardé: {output_path}")


def plot_histogram(slope, output_path, thresholds=None):
    """Génère histogramme distribution pentes"""
    print(f"\nGénération histogramme: {output_path}")

    slope_valid = slope[~np.isnan(slope) & (slope > 0)]

    fig, ax = plt.subplots(figsize=(12, 6), dpi=150)

    # Histogramme
    counts, bins, patches = ax.hist(slope_valid.flatten(), bins=90, range=(0, 90),
                                     color='#1976D2', alpha=0.7, edgecolor='black')

    # Overlay seuils
    if thresholds and 'jenks' in thresholds:
        jenks = thresholds['jenks']
        colors_thresh = ['green', 'yellow', 'orange', 'red']
        labels = ['Flat', 'Gentle', 'Moderate', 'Steep/Cliff']

        for i, (thresh, color, label) in enumerate(zip(
            [jenks['flat_max'], jenks['gentle_max'], jenks['moderate_max'], jenks['steep_max']],
            colors_thresh, labels
        )):
            ax.axvline(thresh, color=color, linestyle='--', linewidth=2, label=f'{label}: {thresh:.1f}°')

    # Seuil rocheux
    if thresholds and 'recommended_rock_threshold' in thresholds:
        rock_thresh = thresholds['recommended_rock_threshold']
        ax.axvline(rock_thresh, color='red', linestyle='-', linewidth=3,
                   label=f'SEUIL ROCHEUX: {rock_thresh:.1f}°')

    ax.set_xlabel('Pente (degrés)', fontsize=12)
    ax.set_ylabel('Nombre de pixels', fontsize=12)
    ax.set_title('Distribution Pentes Terrain', fontsize=14, fontweight='bold')
    ax.legend(loc='upper right', fontsize=10)
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, bbox_inches='tight')
    plt.close()

    print(f"  Sauvegardé: {output_path}")


def export_rock_masks(slope, heightmap, thresholds, output_dir):
    """
    Exporte masques zones rocheuses.

    Args:
        slope: array 2D pentes
        heightmap: array 2D altitudes
        thresholds: dict seuils
        output_dir: dossier sortie
    """
    print(f"\nExport masques zones rocheuses: {output_dir}")

    rock_thresh = thresholds.get('recommended_rock_threshold', 35)

    # Masque 1 : Toutes zones rocheuses (slope > seuil)
    mask_rock_all = (slope > rock_thresh).astype(np.uint16) * 65535
    mask_rock_all[np.isnan(slope)] = 0

    from PIL import Image
    Image.fromarray(mask_rock_all).save(output_dir / 'mask_rock_all.png')
    print(f"  mask_rock_all.png (slope > {rock_thresh:.1f}°)")

    # Masque 2 : Falaises côtières (slope > seuil ET altitude < 50m)
    mask_coastal_cliffs = ((slope > rock_thresh) & (heightmap < 50)).astype(np.uint16) * 65535
    mask_coastal_cliffs[np.isnan(slope)] = 0

    Image.fromarray(mask_coastal_cliffs).save(output_dir / 'mask_coastal_cliffs.png')
    print(f"  mask_coastal_cliffs.png (slope > {rock_thresh:.1f}° ET altitude < 50m)")

    # Masque 3 : Falaises montagnes (slope > seuil ET altitude > 200m)
    mask_mountain_cliffs = ((slope > rock_thresh) & (heightmap > 200)).astype(np.uint16) * 65535
    mask_mountain_cliffs[np.isnan(slope)] = 0

    Image.fromarray(mask_mountain_cliffs).save(output_dir / 'mask_mountain_cliffs.png')
    print(f"  mask_mountain_cliffs.png (slope > {rock_thresh:.1f}° ET altitude > 200m)")

    # Stats
    total_pixels = np.sum(~np.isnan(slope))
    rock_pixels = np.sum(slope > rock_thresh)
    rock_percent = (rock_pixels / total_pixels) * 100

    print(f"\n  Couverture zones rocheuses: {rock_percent:.2f}% de la carte")


def save_results_json(thresholds, slope, output_path):
    """Sauvegarde résultats JSON"""
    print(f"\nSauvegarde résultats: {output_path}")

    slope_valid = slope[~np.isnan(slope) & (slope > 0)]

    results = {
        'slope_stats': {
            'min': float(np.nanmin(slope)),
            'max': float(np.nanmax(slope)),
            'mean': float(np.nanmean(slope)),
            'median': float(np.nanmedian(slope)),
            'std': float(np.nanstd(slope))
        },
        'thresholds': {}
    }

    # Convertir thresholds en JSON-serializable
    for key, value in thresholds.items():
        if isinstance(value, dict):
            results['thresholds'][key] = {k: float(v) for k, v in value.items()}
        else:
            results['thresholds'][key] = float(value)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"  Sauvegardé: {output_path}")


def main():
    """Pipeline complet analyse slope"""

    print("="*60)
    print("ANALYSE SLOPE AUTOMATIQUE")
    print("="*60)

    # CONFIG
    asc_path = Path(r"H:\logiciel perso\Map generator\data\projects\Zbk_island\sources\temp_ZBK_terrain_modified7.asc")
    output_dir = Path(r"H:\logiciel perso\Map generator\data\projects\Zbk_island\analysis_slope")
    output_dir.mkdir(exist_ok=True)

    # 1. CHARGER HEIGHTMAP
    heightmap, meta = load_asc(asc_path)

    # 2. CALCULER SLOPE
    slope = calculate_slope(heightmap, meta['cellsize'])

    # 3. DÉTECTER SEUILS AUTOMATIQUEMENT
    thresholds = detect_slope_thresholds(slope)

    # 4. GÉNÉRER VISUALISATIONS
    plot_slope_heatmap(slope, output_dir / 'slope_heatmap.png', thresholds)
    plot_histogram(slope, output_dir / 'slope_histogram.png', thresholds)

    # 5. EXPORTER MASQUES ZONES ROCHEUSES
    export_rock_masks(slope, heightmap, thresholds, output_dir)

    # 6. SAUVEGARDER RÉSULTATS JSON
    save_results_json(thresholds, slope, output_dir / 'slope_analysis.json')

    print("\n" + "="*60)
    print("TERMINÉ !")
    print(f"Résultats dans: {output_dir}")
    print("="*60)

    # RÉSUMÉ
    print("\nRÉSUMÉ SEUILS DÉTECTÉS:")
    print("-" * 40)

    if 'jenks' in thresholds:
        jenks = thresholds['jenks']
        print(f"  Flat       : 0 - {jenks['flat_max']:.1f}°")
        print(f"  Gentle     : {jenks['flat_max']:.1f} - {jenks['gentle_max']:.1f}°")
        print(f"  Moderate   : {jenks['gentle_max']:.1f} - {jenks['moderate_max']:.1f}°")
        print(f"  Steep      : {jenks['moderate_max']:.1f} - {jenks['steep_max']:.1f}°")
        print(f"  Cliff      : > {jenks['steep_max']:.1f}°")

    rock_thresh = thresholds.get('recommended_rock_threshold')
    print(f"\n  SEUIL ROCHEUX RECOMMANDE: {rock_thresh:.1f}deg")
    print(f"  -> Utiliser pour Rock/Debris dans biome.json")
    print("-" * 40)


if __name__ == '__main__':
    main()
