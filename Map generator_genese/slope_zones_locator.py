#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🗺️  Slope Zones Locator
Visualise et localise les zones ROCHE, TERRE, HERBE sur la heightmap
"""

import numpy as np
from PIL import Image
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import argparse
import json
import os
from scipy import ndimage


def load_heightmap(path):
    """Charge une heightmap."""
    if path.endswith('.asc'):
        with open(path, 'r') as f:
            lines = f.readlines()
        ncols = int(lines[0].split()[1])
        nrows = int(lines[1].split()[1])
        data = []
        for line in lines[6:]:
            values = line.strip().split()
            if values:
                data.extend([float(v) for v in values])
        return np.array(data).reshape(nrows, ncols).astype(np.float32)
    else:
        img = Image.open(path)
        arr = np.array(img, dtype=np.float32)
        if arr.ndim == 3:
            return arr[:, :, 0]
        return arr


def calculate_slope(heightmap):
    """Calcule les pentes."""
    gx = ndimage.sobel(heightmap, axis=1)
    gy = ndimage.sobel(heightmap, axis=0)
    gradient_magnitude = np.sqrt(gx**2 + gy**2)
    slope_degrees = np.arctan(gradient_magnitude) * 180 / np.pi
    return slope_degrees


def generate_slope_zones_map(heightmap_path, output_dir='output',
                            slope_grass_max=15,
                            slope_soil_max=45):
    """
    Génère une carte des zones de pente avec couleurs distinctes.
    """
    
    print(f"\n{'='*70}")
    print("🗺️  SLOPE ZONES LOCATOR")
    print(f"{'='*70}")
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Charger et calculer
    heightmap = load_heightmap(heightmap_path)
    slopes = calculate_slope(heightmap)
    
    print(f"\n✅ Heightmap: {heightmap.shape}")
    print(f"   Min pente: {slopes.min():.1f}°")
    print(f"   Max pente: {slopes.max():.1f}°")
    
    # Créer zones colorées
    # 0 = Herbe (vert)
    # 1 = Terre (brun)
    # 2 = Roche (gris)
    zones = np.zeros(slopes.shape, dtype=np.uint8)
    zones[(slopes >= slope_grass_max) & (slopes <= slope_soil_max)] = 1  # Terre
    zones[slopes > slope_soil_max] = 2  # Roche
    
    # Statistiques
    grass_pct = np.sum(zones == 0) / zones.size * 100
    soil_pct = np.sum(zones == 1) / zones.size * 100
    rock_pct = np.sum(zones == 2) / zones.size * 100
    
    print(f"\n📊 Distribution:")
    print(f"   🌱 HERBE (Grass): {grass_pct:.1f}%")
    print(f"   🌍 TERRE (Soil):  {soil_pct:.1f}%")
    print(f"   🪨 ROCHE (Rock):  {rock_pct:.1f}%")
    
    # Créer image colorée
    print(f"\n🎨 Génération de la carte colorée...")
    
    # Palette: Herbe=Vert, Terre=Brun, Roche=Gris
    colors = np.array([
        [34, 139, 34],      # Herbe - Vert foncé
        [139, 69, 19],      # Terre - Brun
        [169, 169, 169]     # Roche - Gris
    ], dtype=np.uint8)
    
    colored_map = colors[zones]
    
    # Sauvegarder carte colorée
    colored_img = Image.fromarray(colored_map, mode='RGB')
    colored_path = os.path.join(output_dir, 'zones_colored_map.png')
    colored_img.save(colored_path)
    print(f"   ✅ Carte colorée: {colored_path}")
    
    # Créer heatmap avec pentes en gradient
    print(f"\n📈 Génération de la heatmap des pentes...")
    
    # Normaliser pentes pour affichage [0, 255]
    slopes_normalized = ((slopes - slopes.min()) / (slopes.max() - slopes.min()) * 255).astype(np.uint8)
    
    # Appliquer colormap
    from matplotlib import cm
    colormap = cm.get_cmap('terrain')
    heatmap_array = colormap(slopes_normalized / 255.0)
    heatmap_rgb = (heatmap_array[:, :, :3] * 255).astype(np.uint8)
    
    heatmap_img = Image.fromarray(heatmap_rgb, mode='RGB')
    heatmap_path = os.path.join(output_dir, 'slope_heatmap.png')
    heatmap_img.save(heatmap_path)
    print(f"   ✅ Heatmap: {heatmap_path}")
    
    # Créer visualisation avec matplotlib (vue zoomée)
    print(f"\n📊 Génération du rapport visuel...")
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 12))
    fig.suptitle('🗺️  SLOPE ZONES ANALYSIS', fontsize=16, fontweight='bold')
    
    # 1. Carte colorée
    ax = axes[0, 0]
    ax.imshow(colored_map)
    ax.set_title('🎨 Zones Matériaux')
    ax.set_xlabel('X (pixels)')
    ax.set_ylabel('Y (pixels)')
    green_patch = mpatches.Patch(color=[34/255, 139/255, 34/255], label='Herbe')
    brown_patch = mpatches.Patch(color=[139/255, 69/255, 19/255], label='Terre')
    gray_patch = mpatches.Patch(color=[169/255, 169/255, 169/255], label='Roche')
    ax.legend(handles=[green_patch, brown_patch, gray_patch], loc='upper right')
    
    # 2. Heatmap pentes
    ax = axes[0, 1]
    im = ax.imshow(slopes, cmap='terrain')
    ax.set_title('📈 Heatmap Pentes (degrés)')
    ax.set_xlabel('X (pixels)')
    ax.set_ylabel('Y (pixels)')
    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label('Pente (°)')
    
    # 3. Histogramme des pentes
    ax = axes[1, 0]
    ax.hist(slopes.flatten(), bins=50, color='steelblue', edgecolor='black', alpha=0.7)
    ax.axvline(slope_grass_max, color='green', linestyle='--', linewidth=2, label=f'Herbe/Terre ({slope_grass_max}°)')
    ax.axvline(slope_soil_max, color='red', linestyle='--', linewidth=2, label=f'Terre/Roche ({slope_soil_max}°)')
    ax.set_xlabel('Pente (degrés)')
    ax.set_ylabel('Fréquence')
    ax.set_title('📊 Distribution des Pentes')
    ax.legend()
    ax.grid(alpha=0.3)
    
    # 4. Statistiques texte
    ax = axes[1, 1]
    ax.axis('off')
    
    stats_text = f"""
    📋 STATISTIQUES DES ZONES

    🌱 HERBE (< {slope_grass_max}°)
       {grass_pct:.1f}% du terrain
       Zone: PLATES, terrains traversables
    
    🌍 TERRE ({slope_grass_max}° - {slope_soil_max}°)
       {soil_pct:.1f}% du terrain
       Zone: PENTES MODÉRÉES
    
    🪨 ROCHE (> {slope_soil_max}°)
       {rock_pct:.1f}% du terrain
       Zone: FALAISES, zones escarpées
    
    📐 PENTES GLOBALES
       Min: {slopes.min():.1f}°
       Max: {slopes.max():.1f}°
       Moyenne: {slopes.mean():.1f}°
    """
    
    ax.text(0.1, 0.5, stats_text, fontsize=11, family='monospace',
            verticalalignment='center',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    
    # Sauvegarder figure
    report_viz_path = os.path.join(output_dir, 'zones_analysis_report.png')
    plt.tight_layout()
    plt.savefig(report_viz_path, dpi=100, bbox_inches='tight')
    print(f"   ✅ Rapport visuel: {report_viz_path}")
    
    plt.close()
    
    # Créer JSON rapport détaillé
    report = {
        'type': 'slope_zones_analysis',
        'heightmap_shape': list(heightmap.shape),
        'thresholds': {
            'grass_max_degrees': slope_grass_max,
            'soil_max_degrees': slope_soil_max,
            'rock_min_degrees': slope_soil_max
        },
        'slope_stats': {
            'min_degrees': float(slopes.min()),
            'max_degrees': float(slopes.max()),
            'mean_degrees': float(slopes.mean())
        },
        'zone_distribution': {
            'grass_pct': float(grass_pct),
            'soil_pct': float(soil_pct),
            'rock_pct': float(rock_pct)
        },
        'files_generated': {
            'colored_map': 'zones_colored_map.png',
            'heatmap': 'slope_heatmap.png',
            'report_visualization': 'zones_analysis_report.png',
            'json_report': 'zones_report.json'
        }
    }
    
    report_path = os.path.join(output_dir, 'zones_report.json')
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"\n{'='*70}")
    print("✨ ANALYSE COMPLÈTE!")
    print(f"{'='*70}")
    print(f"\n📂 Fichiers générés dans: {os.path.abspath(output_dir)}")
    print(f"\n   • zones_colored_map.png - Carte avec zones distinctes")
    print(f"   • slope_heatmap.png - Gradient de pentes")
    print(f"   • zones_analysis_report.png - Rapport visuel complet")
    print(f"   • zones_report.json - Données détaillées")
    
    print(f"\n{'='*70}\n")
    
    return zones, slopes


def main():
    parser = argparse.ArgumentParser(
        description="🗺️  Slope Zones Locator - Visualise où sont les roches/terres/herbes"
    )
    
    parser.add_argument('heightmap', help='Heightmap source (.asc ou .png)')
    parser.add_argument('--output', default='output', help='Dossier de sortie')
    parser.add_argument('--grass-max', type=float, default=15, help='Seuil herbe (défaut: 15°)')
    parser.add_argument('--soil-max', type=float, default=45, help='Seuil terre (défaut: 45°)')
    
    args = parser.parse_args()
    
    try:
        zones, slopes = generate_slope_zones_map(
            args.heightmap,
            output_dir=args.output,
            slope_grass_max=args.grass_max,
            slope_soil_max=args.soil_max
        )
        return 0
    
    except Exception as e:
        print(f"\n❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    import sys
    sys.exit(main())
