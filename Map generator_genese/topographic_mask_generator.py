#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🗺️ Topographic Mask Generator
Génère un mask qui suit les contours RÉELS de la rivière et vallées

Basé sur la topographie:
- Zones BASSES (rivière) = NOIR (protégé)
- Zones HAUTES (plateau ouest) = BLANC (modifiable)
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


def generate_topographic_mask(heightmap_path, output_mask_path, threshold_method='percentile', 
                              threshold_value=None):
    """
    Génère un mask NOIR/BLANC (100% binaire) basé sur la topographie.
    
    Args:
        heightmap_path: Path to heightmap
        output_mask_path: Output mask path
        threshold_method: 'percentile' ou 'absolute'
        threshold_value: 
            - Si 'percentile': 0-100 (% des altitudes les plus basses = rivière)
            - Si 'absolute': valeur altitude exacte
    """
    
    print(f"\n🗺️ Génération mask NOIR/BLANC topographique...")
    
    # Charger heightmap
    heightmap = load_heightmap(heightmap_path)
    print(f"✅ Heightmap: {heightmap.shape}")
    print(f"   Altitudes: {heightmap.min():.1f}m - {heightmap.max():.1f}m")
    
    # Déterminer seuil (zones basses = rivière)
    if threshold_method == 'percentile':
        if threshold_value is None:
            threshold_value = 15  # Par défaut: 15% des plus basses altitudes = rivière
        
        # Calculer le seuil d'altitude
        altitude_threshold = np.percentile(heightmap, threshold_value)
        print(f"\n📊 Seuil: Percentile {threshold_value}% = {altitude_threshold:.1f}m")
    
    else:  # absolute
        if threshold_value is None:
            altitude_threshold = np.min(heightmap) + (np.max(heightmap) - np.min(heightmap)) * 0.2
        else:
            altitude_threshold = threshold_value
        print(f"\n📊 Seuil: Altitude absolue = {altitude_threshold:.1f}m")
    
    # Créer mask BINAIRE (0 ou 255 uniquement, PAS de gris)
    # Blanc (255) = altitudes hautes (à modifier)
    # Noir (0) = altitudes basses (rivière, protégé)
    mask_binary = (heightmap > altitude_threshold).astype(np.uint8)  # 0 ou 1
    mask = mask_binary * 255  # Convertir en 0 ou 255
    
    print(f"\n✅ Mask créé (BINAIRE PUR):")
    white_pct = np.sum(mask == 255) / mask.size * 100
    black_pct = np.sum(mask == 0) / mask.size * 100
    print(f"   Blanc (à modifier): {white_pct:.1f}%")
    print(f"   Noir (rivière/protégé): {black_pct:.1f}%")
    
    # Vérification: s'assurer qu'il n'y a AUCUN gris
    unique_vals = np.unique(mask)
    print(f"   Valeurs uniques dans le mask: {unique_vals}")
    if len(unique_vals) > 2 or (len(unique_vals) > 0 and not all(v in [0, 255] for v in unique_vals)):
        print(f"   ⚠️  WARNING: Valeurs autres que 0/255 détectées!")
    else:
        print(f"   ✅ Mask 100% binaire (0 et 255 uniquement)")
    
    # Sauvegarder SANS compression (PNG non compressé = pas d'artefacts)
    mask_img = Image.fromarray(mask, mode='L')
    mask_img.save(output_mask_path, compression_level=0)
    
    print(f"\n💾 Mask sauvegardé: {output_mask_path}")
    print(f"   Résolution: {mask.shape}")
    print(f"   Format: PNG 8-bit Grayscale (NO COMPRESSION)")
    print(f"   Valeurs: NOIR(0) = protégé, BLANC(255) = modifiable")
    
    # Génération rapport
    report = {
        'method': threshold_method,
        'threshold_value': float(threshold_value),
        'altitude_threshold': float(altitude_threshold),
        'heightmap_shape': list(heightmap.shape),
        'heightmap_min': float(heightmap.min()),
        'heightmap_max': float(heightmap.max()),
        'white_pixels_pct': float(white_pct),
        'black_pixels_pct': float(black_pct),
        'is_binary': len(unique_vals) <= 2
    }
    
    report_path = output_mask_path.replace('.png', '_report.json')
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"📊 Rapport: {report_path}")
    
    return output_mask_path, report


def main():
    parser = argparse.ArgumentParser(
        description="🗺️ Topographic Mask Generator - Suit les contours de la rivière"
    )
    
    parser.add_argument('heightmap', help='Heightmap source (.asc ou .png)')
    parser.add_argument('--output', default='topographic_mask.png',
                       help='Chemin mask de sortie')
    parser.add_argument('--method', choices=['percentile', 'absolute'], default='percentile',
                       help='Méthode seuil')
    parser.add_argument('--threshold', type=float,
                       help='Valeur seuil (0-100 percentile, ou altitude absolue)')
    
    args = parser.parse_args()
    
    print("\n" + "="*70)
    print("🗺️  TOPOGRAPHIC MASK GENERATOR")
    print("="*70)
    
    try:
        output_path, report = generate_topographic_mask(
            args.heightmap,
            args.output,
            threshold_method=args.method,
            threshold_value=args.threshold
        )
        
        print("\n" + "="*70)
        print("✨ Mask généré!")
        print("   NOIR = Rivière/Vallées (protégé)")
        print("   BLANC = Plateaux (à modifier/éroder)")
        print("   → À importer dans Instant Terra avec 'Import Mask'")
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
