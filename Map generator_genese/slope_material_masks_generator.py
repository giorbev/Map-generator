#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎮 Slope Material Masks Generator for Reforger
Génère 3 masks de matériaux terrain basés sur la PENTE:
  - ROCHE (Rock): Fortes pentes (falaises, > 45°)
  - TERRE (Soil): Pentes moyennes (15-45°)
  - HERBE (Grass): Pentes faibles/plates (< 15°)

Cas d'usage Reforger:
  - Importer les 3 masks comme couches de matériaux
  - Le moteur applique la texture en fonction du mask blanc/noir
  - Max 5 seuils par matériau
"""

import numpy as np
from PIL import Image
import argparse
import json
import os


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
    """
    Calcule la pente (magnitude du gradient) en degrés.
    """
    from scipy import ndimage
    
    # Gradient Sobel
    gx = ndimage.sobel(heightmap, axis=1)
    gy = ndimage.sobel(heightmap, axis=0)
    
    # Magnitude du gradient
    gradient_magnitude = np.sqrt(gx**2 + gy**2)
    
    # Convertir en pente en degrés
    slope_degrees = np.arctan(gradient_magnitude) * 180 / np.pi
    
    return slope_degrees


def generate_material_masks(heightmap_path, output_dir='output', 
                           slope_grass_max=15, 
                           slope_soil_max=45):
    """
    Génère 3 masks binaires pour les matériaux Reforger.
    
    Args:
        heightmap_path: Path to heightmap
        output_dir: Dossier de sortie pour les masks
        slope_grass_max: Seuil pente pour HERBE (< ce seuil = herbe)
        slope_soil_max: Seuil pente pour TERRE (herbe à soil, soil à roche)
    
    Logique des masks:
    ├─ GRASS.png : Blanc si pente < 15° (zones plates)
    ├─ SOIL.png  : Blanc si 15° < pente < 45° (pentes moyennes)
    └─ ROCK.png  : Blanc si pente > 45° (falaises)
    """
    
    print(f"\n{'='*70}")
    print("🎮 REFORGER MATERIAL MASKS GENERATOR")
    print(f"{'='*70}")
    
    # Créer dossier sortie
    os.makedirs(output_dir, exist_ok=True)
    
    # Charger heightmap
    heightmap = load_heightmap(heightmap_path)
    print(f"\n✅ Heightmap chargée: {heightmap.shape}")
    
    # Calculer pentes
    print(f"\n📐 Calcul des pentes...")
    slopes = calculate_slope(heightmap)
    
    print(f"   Min: {slopes.min():.1f}°")
    print(f"   Max: {slopes.max():.1f}°")
    print(f"   Moyenne: {slopes.mean():.1f}°")
    
    # Générer les 3 masks
    print(f"\n🎨 Génération des masks de matériaux...")
    print(f"   GRASS: pente < {slope_grass_max}° (zones plates)")
    print(f"   SOIL:  {slope_grass_max}° < pente < {slope_soil_max}° (pentes moyennes)")
    print(f"   ROCK:  pente > {slope_soil_max}° (falaises)")
    
    # GRASS mask (blanc si pente faible)
    mask_grass_white = slopes < slope_grass_max
    mask_grass = mask_grass_white.astype(np.uint8) * 255
    
    # SOIL mask (blanc si pente moyenne)
    mask_soil_white = (slopes >= slope_grass_max) & (slopes <= slope_soil_max)
    mask_soil = mask_soil_white.astype(np.uint8) * 255
    
    # ROCK mask (blanc si pente forte)
    mask_rock_white = slopes > slope_soil_max
    mask_rock = mask_rock_white.astype(np.uint8) * 255
    
    # Statistiques
    grass_pct = np.sum(mask_grass == 255) / mask_grass.size * 100
    soil_pct = np.sum(mask_soil == 255) / mask_soil.size * 100
    rock_pct = np.sum(mask_rock == 255) / mask_rock.size * 100
    
    print(f"\n📊 Statistiques des couches:")
    print(f"   GRASS: {grass_pct:.1f}%")
    print(f"   SOIL:  {soil_pct:.1f}%")
    print(f"   ROCK:  {rock_pct:.1f}%")
    
    # Sauvegarder masks
    masks = {
        'grass': (mask_grass, 'GRASS_mask.png', 'Herbe (pentes < 15°)'),
        'soil': (mask_soil, 'SOIL_mask.png', 'Terre (pentes 15-45°)'),
        'rock': (mask_rock, 'ROCK_mask.png', 'Roche (pentes > 45°)')
    }
    
    saved_files = {}
    
    print(f"\n💾 Sauvegarde des masks...")
    for material_type, (mask_array, filename, description) in masks.items():
        filepath = os.path.join(output_dir, filename)
        
        # Vérifier binaire
        unique_vals = np.unique(mask_array)
        is_binary = len(unique_vals) <= 2 and all(v in [0, 255] for v in unique_vals)
        
        # Sauvegarder
        mask_img = Image.fromarray(mask_array, mode='L')
        mask_img.save(filepath, compression_level=0)
        
        saved_files[material_type] = {
            'path': filepath,
            'description': description,
            'is_binary': is_binary
        }
        
        white_pct = np.sum(mask_array == 255) / mask_array.size * 100
        print(f"   ✅ {filename}: {white_pct:.1f}% blanc {'(BINAIRE ✓)' if is_binary else '(⚠️  WARN)'}")
    
    # Générer rapport global
    report = {
        'type': 'reforger_material_masks',
        'heightmap_path': str(heightmap_path),
        'heightmap_shape': list(heightmap.shape),
        'material_thresholds': {
            'grass_max_degrees': slope_grass_max,
            'soil_max_degrees': slope_soil_max,
            'rock_min_degrees': slope_soil_max
        },
        'slope_statistics': {
            'min_degrees': float(slopes.min()),
            'max_degrees': float(slopes.max()),
            'mean_degrees': float(slopes.mean())
        },
        'material_coverage': {
            'grass_pct': float(grass_pct),
            'soil_pct': float(soil_pct),
            'rock_pct': float(rock_pct)
        },
        'output_directory': str(output_dir),
        'masks': saved_files
    }
    
    report_path = os.path.join(output_dir, 'material_masks_report.json')
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"\n📋 Rapport: {report_path}")
    
    print(f"\n{'='*70}")
    print("✨ MASKS GÉNÉRÉS AVEC SUCCÈS!")
    print(f"{'='*70}")
    print(f"\n📂 Dossier: {os.path.abspath(output_dir)}")
    print(f"\n📄 Fichiers (à importer dans Reforger):")
    for material_type, info in saved_files.items():
        print(f"   • {os.path.basename(info['path'])}")
    
    print(f"\n🎯 Instructions Reforger:")
    print(f"   1. Importer GRASS_mask.png comme couche 'Grass'")
    print(f"   2. Importer SOIL_mask.png comme couche 'Soil'")
    print(f"   3. Importer ROCK_mask.png comme couche 'Rock'")
    print(f"   4. Appliquer par seuil: < 5 max")
    print(f"{'='*70}\n")
    
    return saved_files, report


def generate_preview_composite(output_dir):
    """
    Génère une preview composite des 3 masks.
    """
    print("🖼️  Génération de la preview composite...")
    
    try:
        # Charger les 3 masks
        grass = Image.open(os.path.join(output_dir, 'GRASS_mask.png')).convert('L')
        soil = Image.open(os.path.join(output_dir, 'SOIL_mask.png')).convert('L')
        rock = Image.open(os.path.join(output_dir, 'ROCK_mask.png')).convert('L')
        
        # Créer image RGB composite
        # R=Rock, G=Soil, B=Grass
        rock_arr = np.array(rock, dtype=np.uint8)
        soil_arr = np.array(soil, dtype=np.uint8)
        grass_arr = np.array(grass, dtype=np.uint8)
        
        # Normaliser à [0, 255]
        rock_arr = (rock_arr / 255 * 255).astype(np.uint8)
        soil_arr = (soil_arr / 255 * 255).astype(np.uint8)
        grass_arr = (grass_arr / 255 * 255).astype(np.uint8)
        
        composite = np.stack([rock_arr, soil_arr, grass_arr], axis=2)
        composite_img = Image.fromarray(composite, mode='RGB')
        
        composite_path = os.path.join(output_dir, 'composite_preview.png')
        composite_img.save(composite_path)
        
        print(f"   ✅ Preview: {composite_path}")
        print(f"      (Rouge=Roche, Vert=Terre, Bleu=Herbe)")
        
    except Exception as e:
        print(f"   ⚠️  Impossible de créer la preview: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="🎮 Slope Material Masks for Reforger - Crée 3 masks (Grass/Soil/Rock)"
    )
    
    parser.add_argument('heightmap', help='Heightmap source (.asc ou .png)')
    parser.add_argument('--output', default='output',
                       help='Dossier de sortie')
    parser.add_argument('--grass-max', type=float, default=15,
                       help='Seuil max pente pour HERBE (défaut: 15°)')
    parser.add_argument('--soil-max', type=float, default=45,
                       help='Seuil max pente pour TERRE (défaut: 45°)')
    parser.add_argument('--preview', action='store_true',
                       help='Générer une preview RGB composite')
    
    args = parser.parse_args()
    
    try:
        saved_files, report = generate_material_masks(
            args.heightmap,
            output_dir=args.output,
            slope_grass_max=args.grass_max,
            slope_soil_max=args.soil_max
        )
        
        if args.preview:
            generate_preview_composite(args.output)
        
        return 0
    
    except Exception as e:
        print(f"\n❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    import sys
    sys.exit(main())
