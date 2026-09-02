#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🗻 Slope Mask Generator
Génère des masks binaires basés sur la PENTE du terrain

Cas d'usage:
- Protéger les falaises (pentes fortes)
- Protéger les zones plates
- Modifier uniquement les pentes moyennes
"""

import numpy as np
from PIL import Image
import argparse
import json


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


def calculate_slope(heightmap, kernel_size=3):
    """
    Calcule la pente (magnitude du gradient) en degrés.
    
    Args:
        heightmap: Array 2D des altitudes
        kernel_size: Taille du kernel (3, 5, 7, etc.)
    
    Returns:
        Array 2D des pentes en degrés
    """
    print(f"\n📐 Calcul des pentes (kernel {kernel_size}×{kernel_size})...")
    
    # Gradient Sobel
    from scipy import ndimage
    
    # Gradient X et Y
    gx = ndimage.sobel(heightmap, axis=1)
    gy = ndimage.sobel(heightmap, axis=0)
    
    # Magnitude du gradient
    gradient_magnitude = np.sqrt(gx**2 + gy**2)
    
    # Convertir en pente en degrés
    # pente (degrés) = arctan(gradient_magnitude) * 180 / pi
    slope_degrees = np.arctan(gradient_magnitude) * 180 / np.pi
    
    print(f"✅ Pentes calculées:")
    print(f"   Min: {slope_degrees.min():.1f}°")
    print(f"   Max: {slope_degrees.max():.1f}°")
    print(f"   Moyenne: {slope_degrees.mean():.1f}°")
    
    return slope_degrees


def generate_slope_mask(heightmap_path, output_mask_path, slope_min=None, slope_max=None, 
                       invert=False):
    """
    Génère un mask NOIR/BLANC basé sur la pente.
    
    Args:
        heightmap_path: Path to heightmap
        output_mask_path: Output mask path
        slope_min: Pente minimale à protéger (noir)
        slope_max: Pente maximale à protéger (noir)
        invert: Inverser blanc/noir
    
    Logique:
    - Si slope_min/max définis: pentes ENTRE ces valeurs = BLANC (modifiable)
    - Sinon: zones PLATES (pente faible) = BLANC, falaises (pente forte) = NOIR
    """
    
    print(f"\n🗻 Génération mask de pente...")
    
    # Charger heightmap
    heightmap = load_heightmap(heightmap_path)
    print(f"✅ Heightmap: {heightmap.shape}")
    
    # Calculer pentes
    slopes = calculate_slope(heightmap)
    
    # Déterminer seuils
    if slope_min is None and slope_max is None:
        # Par défaut: protéger les falaises (pentes > 45°)
        slope_max = 45.0
        slope_min = 0.0
        print(f"\n📊 Seuil par défaut: Protéger pentes > {slope_max}°")
    else:
        if slope_min is None:
            slope_min = 0.0
        if slope_max is None:
            slope_max = 90.0
        print(f"\n📊 Seuil: Pentes entre {slope_min}° et {slope_max}°")
    
    # Créer mask
    # Blanc (255) = Pentes ENTRE min et max = à modifier
    # Noir (0) = Pentes HORS limites = protégé (falaises + zones plates)
    mask_white = (slopes >= slope_min) & (slopes <= slope_max)
    
    if invert:
        mask_white = ~mask_white
    
    mask = mask_white.astype(np.uint8) * 255
    
    print(f"\n✅ Mask créé (BINAIRE PUR):")
    white_pct = np.sum(mask == 255) / mask.size * 100
    black_pct = np.sum(mask == 0) / mask.size * 100
    print(f"   Blanc (à modifier): {white_pct:.1f}%")
    print(f"   Noir (protégé): {black_pct:.1f}%")
    
    # Vérification binaire
    unique_vals = np.unique(mask)
    if len(unique_vals) <= 2 and all(v in [0, 255] for v in unique_vals):
        print(f"   ✅ Mask 100% binaire (0 et 255 uniquement)")
    else:
        print(f"   ⚠️  WARNING: Valeurs détectées: {unique_vals}")
    
    # Sauvegarder
    mask_img = Image.fromarray(mask, mode='L')
    mask_img.save(output_mask_path, compression_level=0)
    
    print(f"\n💾 Mask sauvegardé: {output_mask_path}")
    print(f"   Résolution: {mask.shape}")
    print(f"   Format: PNG 8-bit (NO COMPRESSION)")
    
    # Rapport
    report = {
        'type': 'slope_mask',
        'slope_min_degrees': float(slope_min),
        'slope_max_degrees': float(slope_max),
        'heightmap_shape': list(heightmap.shape),
        'slope_min_actual': float(slopes.min()),
        'slope_max_actual': float(slopes.max()),
        'slope_mean': float(slopes.mean()),
        'white_pixels_pct': float(white_pct),
        'black_pixels_pct': float(black_pct),
        'invert': invert,
        'is_binary': len(unique_vals) <= 2
    }
    
    report_path = output_mask_path.replace('.png', '_report.json')
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"📊 Rapport: {report_path}")
    
    return output_mask_path, report


def main():
    parser = argparse.ArgumentParser(
        description="🗻 Slope Mask Generator - Crée des masks basés sur la pente"
    )
    
    parser.add_argument('heightmap', help='Heightmap source (.asc ou .png)')
    parser.add_argument('--output', default='slope_mask.png',
                       help='Chemin mask de sortie')
    parser.add_argument('--min-slope', type=float,
                       help='Pente minimale (degrés)')
    parser.add_argument('--max-slope', type=float,
                       help='Pente maximale (degrés)')
    parser.add_argument('--invert', action='store_true',
                       help='Inverser blanc/noir')
    
    args = parser.parse_args()
    
    print("\n" + "="*70)
    print("🗻 SLOPE MASK GENERATOR")
    print("="*70)
    
    try:
        output_path, report = generate_slope_mask(
            args.heightmap,
            args.output,
            slope_min=args.min_slope,
            slope_max=args.max_slope,
            invert=args.invert
        )
        
        print("\n" + "="*70)
        print("✨ Mask de pente généré!")
        print("   BLANC = Zones modifiables")
        print("   NOIR = Zones protégées")
        print("="*70 + "\n")
        
        return 0
    
    except Exception as e:
        print(f"\n❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    import sys
    sys.exit(main())
