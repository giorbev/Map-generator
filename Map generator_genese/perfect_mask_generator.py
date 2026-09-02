#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎭 Perfect Mask Generator
Génère un mask noir/blanc PARFAIT pour Instant Terra

Crée un mask binaire (pas de gris, pas d'anti-aliasing)
avec une limite NETTE à la rivière
"""

import numpy as np
from PIL import Image
import argparse


def generate_perfect_mask(heightmap_path, output_mask_path, river_detection='auto', 
                         river_col=None, falloff_width=0, side='west'):
    """
    Génère un mask parfait.
    
    Args:
        heightmap_path: Path to heightmap (.png or .asc)
        output_mask_path: Output mask path (.png)
        river_detection: 'auto' ou 'manual'
        river_col: Position rivière (si manual)
        falloff_width: Largeur transition (0 = binaire pur, >0 = dégradé)
        side: 'west' = modifier ouest, 'east' = modifier est
    """
    
    print(f"\n🎭 Génération mask parfait...")
    
    # Charger heightmap
    if heightmap_path.endswith('.asc'):
        with open(heightmap_path, 'r') as f:
            lines = f.readlines()
        ncols = int(lines[0].split()[1])
        nrows = int(lines[1].split()[1])
        data = []
        for line in lines[6:]:
            values = line.strip().split()
            if values:
                data.extend([float(v) for v in values])
        heightmap = np.array(data).reshape(nrows, ncols).astype(np.float32)
    else:
        img = Image.open(heightmap_path)
        arr = np.array(img, dtype=np.float32)
        if arr.ndim == 3:
            heightmap = arr[:, :, 0]
        else:
            heightmap = arr
    
    print(f"✅ Heightmap: {heightmap.shape}")
    
    # Détecter rivière
    if river_detection == 'auto':
        if river_col is None:
            avg = np.mean(heightmap, axis=0)
            if avg.ndim > 1:
                avg = avg.flatten()
            river_col = int(np.argmin(avg))
        print(f"📍 Rivière détectée à X={river_col}")
    else:
        if river_col is None:
            raise ValueError("river_col required for manual mode")
        print(f"📍 Rivière spécifiée à X={river_col}")
    
    # Créer mask binaire
    height, width = heightmap.shape
    mask = np.zeros((height, width), dtype=np.uint8)
    
    if side == 'west':
        # Modifier OUEST (< river_col)
        if falloff_width == 0:
            # Binaire pur
            mask[:, :river_col] = 255
            print(f"🎭 Mask: 100% blanc OUEST (0-{river_col}), 100% noir EST ({river_col}-{width})")
        else:
            # Avec transition lissée
            for x in range(width):
                dist_to_river = abs(x - river_col)
                if dist_to_river < falloff_width:
                    # Zone transition: blend linéaire
                    intensity = int(255 * (1 - dist_to_river / falloff_width))
                    if x < river_col:
                        mask[:, x] = intensity
                elif x < river_col:
                    mask[:, x] = 255
            print(f"🎭 Mask: Blanc à l'OUEST + transition {falloff_width}px")
    
    else:  # side == 'east'
        if falloff_width == 0:
            # Binaire pur
            mask[:, river_col:] = 255
            print(f"🎭 Mask: 100% noir OUEST (0-{river_col}), 100% blanc EST ({river_col}-{width})")
        else:
            # Avec transition
            for x in range(width):
                dist_to_river = abs(x - river_col)
                if dist_to_river < falloff_width:
                    intensity = int(255 * (1 - dist_to_river / falloff_width))
                    if x >= river_col:
                        mask[:, x] = intensity
                elif x >= river_col:
                    mask[:, x] = 255
            print(f"🎭 Mask: Blanc à l'EST + transition {falloff_width}px")
    
    # Sauvegarder SANS compression (mode 'L' = grayscale)
    mask_img = Image.fromarray(mask, mode='L')
    # Sauvegarder en PNG sans compression
    mask_img.save(output_mask_path, compression_level=0)
    
    print(f"✅ Mask sauvegardé: {output_mask_path}")
    print(f"   Taille: {mask.shape}")
    print(f"   Format: PNG 8-bit Grayscale (NO COMPRESSION)")
    
    # Statistiques
    white_pct = np.sum(mask == 255) / mask.size * 100
    black_pct = np.sum(mask == 0) / mask.size * 100
    gray_pct = 100 - white_pct - black_pct
    
    print(f"\n📊 Statistiques:")
    print(f"   Blanc (modifié): {white_pct:.1f}%")
    print(f"   Noir (protégé): {black_pct:.1f}%")
    print(f"   Gris (transition): {gray_pct:.1f}%")
    
    return output_mask_path


def main():
    parser = argparse.ArgumentParser(
        description="🎭 Perfect Mask Generator - Génère un mask parfait pour Instant Terra"
    )
    
    parser.add_argument('heightmap', help='Heightmap source (.asc ou .png)')
    parser.add_argument('--output', default='perfect_mask.png',
                       help='Chemin mask de sortie')
    parser.add_argument('--river-col', type=int,
                       help='Position colonne rivière (auto-détecté par défaut)')
    parser.add_argument('--side', choices=['west', 'east'], default='west',
                       help='Côté à modifier: west ou east')
    parser.add_argument('--falloff', type=int, default=0,
                       help='Largeur transition dégradée (0=binaire pur)')
    
    args = parser.parse_args()
    
    print("\n" + "="*70)
    print("🎭 PERFECT MASK GENERATOR")
    print("="*70)
    
    try:
        generate_perfect_mask(
            args.heightmap,
            args.output,
            river_col=args.river_col,
            falloff_width=args.falloff,
            side=args.side
        )
        
        print("\n" + "="*70)
        print("✨ Mask généré!")
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
