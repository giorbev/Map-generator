#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🗺️ Mask Correction Tool
Corrige un mask mal appliqué en restaurant les zones qui ne devaient pas être modifiées

Utilisé quand :
- Le mask a débordé à l'EST (zone de protection)
- On veut garder les modifs à l'OUEST mais restaurer l'EST
"""

import numpy as np
from PIL import Image
import argparse
from pathlib import Path


class MaskCorrectionTool:
    """Corriger les débordements de mask."""
    
    @staticmethod
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
    
    @staticmethod
    def find_river_column(heightmap):
        """Détecte la colonne de la rivière."""
        avg = np.mean(heightmap, axis=0)
        if avg.ndim > 1:
            avg = avg.flatten()
        return int(np.argmin(avg))
    
    @staticmethod
    def correct_mask_overflow(hmap_original, hmap_corrupted, river_col, east_zone_restore_pct=1.0):
        """
        Corrige un mask qui a débordé.
        
        Stratégie:
        - OUEST (< river_col): Garder les modifications
        - EST (>= river_col): Restaurer les altitudes originales
        """
        print(f"\n🔧 Correction du débordement de mask...")
        print(f"   Rivière détectée à X={river_col}")
        
        hmap_corrected = hmap_corrupted.copy()
        
        # Restaurer la zone EST
        hmap_corrected[:, river_col:] = hmap_original[:, river_col:]
        
        # Appliquer une zone de transition progressive (falloff)
        transition_width = 50  # pixels
        
        for x in range(max(0, river_col - transition_width), river_col + 1):
            if x >= hmap_corrupted.shape[1]:
                continue
            
            # Facteur de blend (0 = original, 1 = corrupted)
            blend_factor = (x - (river_col - transition_width)) / transition_width
            blend_factor = np.clip(blend_factor, 0, 1)
            
            # Interpoler entre original et corrupted
            hmap_corrected[:, x] = (1 - blend_factor) * hmap_original[:, x] + blend_factor * hmap_corrupted[:, x]
        
        print(f"✅ Correction appliquée:")
        print(f"   Zone OUEST (< {river_col}): Modifications conservées")
        print(f"   Zone EST (>= {river_col}): Restaurée")
        print(f"   Transition: {transition_width}px (falloff lissé)")
        
        return hmap_corrected
    
    @staticmethod
    def save_corrected(hmap_corrected, output_path):
        """Sauvegarde la heightmap corrigée."""
        if output_path.endswith('.png'):
            # Sauvegarder en PNG 16-bit
            hmap_uint16 = hmap_corrected.astype(np.uint16)
            img = Image.fromarray(hmap_uint16, mode='I;16')
            img.save(output_path)
        else:
            # Sauvegarder en ASC
            nrows, ncols = hmap_corrected.shape
            with open(output_path, 'w') as f:
                f.write(f"ncols         {ncols}\n")
                f.write(f"nrows         {nrows}\n")
                f.write(f"xllcorner     0.0\n")
                f.write(f"yllcorner     0.0\n")
                f.write(f"cellsize      1.0\n")
                f.write(f"NODATA_value  -9999\n")
                for row in hmap_corrected:
                    row_str = ' '.join([f"{val:.2f}" for val in row])
                    f.write(row_str + '\n')
        
        print(f"✅ Sauvegardé: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="🗺️ Mask Correction Tool - Corrige les débordements de mask"
    )
    
    parser.add_argument('original', help='Heightmap originale (.asc ou .png)')
    parser.add_argument('corrupted', help='Heightmap avec débordement mask (.asc ou .png)')
    parser.add_argument('--output', default='heightmap_corrected.png',
                       help='Chemin fichier corrigé')
    parser.add_argument('--river-col', type=int,
                       help='Position colonne rivière (auto-détecté si non spécifié)')
    
    args = parser.parse_args()
    
    print("\n" + "="*70)
    print("🗺️  MASK CORRECTION TOOL")
    print("="*70)
    
    try:
        print(f"\n📂 Chargement heightmaps...")
        hmap_original = MaskCorrectionTool.load_heightmap(args.original)
        hmap_corrupted = MaskCorrectionTool.load_heightmap(args.corrupted)
        
        print(f"✅ Original: {hmap_original.shape}")
        print(f"✅ Corruptée: {hmap_corrupted.shape}")
        
        # Détecter rivière
        if args.river_col:
            river_col = args.river_col
            print(f"\n📍 Colonne rivière spécifiée: {river_col}")
        else:
            river_col = MaskCorrectionTool.find_river_column(hmap_original)
            print(f"\n📍 Colonne rivière détectée: {river_col}")
        
        # Corriger
        hmap_corrected = MaskCorrectionTool.correct_mask_overflow(
            hmap_original, hmap_corrupted, river_col
        )
        
        # Sauvegarder
        MaskCorrectionTool.save_corrected(hmap_corrected, args.output)
        
        print("\n" + "="*70)
        print("✨ Correction terminée!")
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
