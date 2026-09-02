#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🗺️ Mask Validation Analyzer
Analyse comparative de deux heightmaps pour valider l'application d'un mask

Cas d'usage: 
- Heightmap AVANT mask
- Heightmap APRÈS mask (modifié à gauche de la rivière)
- Vérifier que les modifications respectent les limites du mask

Résultats:
- Heatmap des différences
- Rapport de validation (mask correct ?)
- Statistiques par zone (ouest/est)
"""

import numpy as np
from PIL import Image
import json
import argparse
from pathlib import Path
import sys


class MaskValidator:
    """Valide l'application d'un mask en comparant deux heightmaps."""
    
    @staticmethod
    def load_heightmap(path):
        """Charge une heightmap (PNG ou ASC)."""
        print(f"📂 Chargement: {path}")
        
        if path.endswith('.asc'):
            # Charger ASC
            with open(path, 'r') as f:
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
            # Charger PNG
            img = Image.open(path)
            arr = np.array(img, dtype=np.float32)
            
            # Si multi-canal (RGB/RGBA), prendre le premier canal
            if arr.ndim == 3:
                heightmap = arr[:, :, 0]
            else:
                heightmap = arr
        
        print(f"✅ Chargé: {heightmap.shape} - Min: {heightmap.min():.1f}, Max: {heightmap.max():.1f}")
        return heightmap
    
    @staticmethod
    def find_river_center(heightmap_before, heightmap_after):
        """Détecte la position de la rivière (dépression nord-sud)."""
        print("\n🔍 Détection de la rivière...")
        
        # Moyennes verticales (par colonne)
        avg_before = np.mean(heightmap_before, axis=0)
        avg_after = np.mean(heightmap_after, axis=0)
        
        # Gérer cas où avg serait 2D
        if avg_before.ndim > 1:
            avg_before = avg_before.flatten()
        if avg_after.ndim > 1:
            avg_after = avg_after.flatten()
        
        # La rivière = dépression continue (valeurs basses)
        # On cherche la colonne avec les plus basses valeurs
        river_col = int(np.argmin(avg_before))
        river_x = river_col / heightmap_before.shape[1]  # Position normalisée (0-1)
        river_altitude = float(avg_before[river_col])
        
        print(f"📍 Rivière détectée à X={river_col} (normalisé: {river_x:.1%})")
        print(f"   Altitude rivière: {river_altitude:.1f}m")
        
        return river_col, river_x
    
    @staticmethod
    def analyze_differences(hmap_before, hmap_after, river_col):
        """Analyse les différences entre avant/après."""
        print("\n📊 Analyse des différences...")
        
        # Calcul des deltas
        delta = hmap_after - hmap_before
        
        # Zones
        width = hmap_before.shape[1]
        west_mask = np.arange(width) < river_col  # À gauche de la rivière
        east_mask = np.arange(width) >= river_col  # À droite
        
        # Statistiques OUEST (doit être modifié)
        delta_west = delta[:, west_mask]
        changed_west = np.abs(delta_west) > 0.5  # Pixels avec delta > 0.5
        pct_changed_west = np.sum(changed_west) / changed_west.size * 100
        avg_delta_west = np.mean(np.abs(delta_west[changed_west])) if np.any(changed_west) else 0
        
        # Statistiques EST (ne doit pas être modifié)
        delta_east = delta[:, east_mask]
        changed_east = np.abs(delta_east) > 0.5
        pct_changed_east = np.sum(changed_east) / changed_east.size * 100
        avg_delta_east = np.mean(np.abs(delta_east[changed_east])) if np.any(changed_east) else 0
        
        # Global
        total_changed = np.sum(np.abs(delta) > 0.5)
        total_pixels = delta.size
        pct_total = total_changed / total_pixels * 100
        
        analysis = {
            'delta_global': {
                'min': float(np.min(delta)),
                'max': float(np.max(delta)),
                'mean': float(np.mean(delta)),
                'std': float(np.std(delta)),
                'total_changed_pixels': int(total_changed),
                'total_pixels': int(total_pixels),
                'pct_changed': float(pct_total)
            },
            'west_zone': {
                'pct_changed': float(pct_changed_west),
                'avg_delta': float(avg_delta_west),
                'max_delta': float(np.max(np.abs(delta_west))),
                'min_delta': float(np.min(np.abs(delta_west)))
            },
            'east_zone': {
                'pct_changed': float(pct_changed_east),
                'avg_delta': float(avg_delta_east),
                'max_delta': float(np.max(np.abs(delta_east))),
                'min_delta': float(np.min(np.abs(delta_east)))
            },
            'river_col': int(river_col)
        }
        
        return delta, analysis
    
    @staticmethod
    def validate_mask(analysis):
        """Valide que le mask a correctement agi (ouest modifié, est inchangé)."""
        print("\n✅ Validation du Mask:")
        
        validation = {
            'status': 'UNKNOWN',
            'issues': [],
            'warnings': []
        }
        
        west = analysis['west_zone']
        east = analysis['east_zone']
        
        # Critères
        threshold_modified = 10  # % de pixels modifiés = signe que mask a agi
        threshold_unmodified = 2  # % max modifiés à l'est (tolérance)
        
        # Vérifications
        print(f"\n🔍 OUEST (zone modifiée attendue):")
        print(f"   {west['pct_changed']:.2f}% pixels changés")
        
        if west['pct_changed'] < threshold_modified:
            validation['issues'].append(f"OUEST: Trop peu de changements ({west['pct_changed']:.2f}% < {threshold_modified}%)")
            print(f"   ⚠️  PROBLÈME: Trop peu de changements!")
        else:
            print(f"   ✅ OK: Suffisamment de changements")
        
        print(f"\n🔍 EST (zone non modifiée attendue):")
        print(f"   {east['pct_changed']:.2f}% pixels changés")
        
        if east['pct_changed'] > threshold_unmodified:
            validation['issues'].append(f"EST: Trop de changements ({east['pct_changed']:.2f}% > {threshold_unmodified}%)")
            print(f"   ⚠️  PROBLÈME: Mask a débordé à l'est!")
        else:
            print(f"   ✅ OK: Peu de changements (attendu)")
        
        # Ratio ouest/est
        if west['pct_changed'] > 0:
            ratio = east['pct_changed'] / west['pct_changed']
            print(f"\n📊 Ratio EST/OUEST: {ratio:.2%}")
            if ratio > 0.3:
                validation['warnings'].append(f"Ratio EST/OUEST élevé ({ratio:.2%}) - vérifier limites mask")
        
        # Verdict
        if len(validation['issues']) == 0:
            validation['status'] = 'PASS'
            print(f"\n✨ VERDICT: Mask semble correct!")
        else:
            validation['status'] = 'FAIL'
            print(f"\n❌ VERDICT: Problèmes détectés!")
        
        return validation
    
    @staticmethod
    def generate_heatmap(delta, output_path):
        """Génère une heatmap des différences."""
        print(f"\n🎨 Génération heatmap...")
        
        # Normaliser pour visualisation (-100 à +100 -> 0 à 255)
        delta_clipped = np.clip(delta, -100, 100)
        heatmap_normalized = (delta_clipped + 100) / 200 * 255
        
        # Créer colormaps (négatif=bleu, zéro=gris, positif=rouge)
        heatmap_rgb = np.zeros((*delta.shape, 3), dtype=np.uint8)
        
        for i in range(delta.shape[0]):
            for j in range(delta.shape[1]):
                val = delta_clipped[i, j]
                
                if val < 0:  # Baisse = bleu
                    intensity = np.abs(val) / 100
                    heatmap_rgb[i, j] = [0, 0, int(255 * intensity)]
                elif val > 0:  # Hausse = rouge
                    intensity = val / 100
                    heatmap_rgb[i, j] = [int(255 * intensity), 0, 0]
                else:  # Zéro = gris
                    heatmap_rgb[i, j] = [128, 128, 128]
        
        img = Image.fromarray(heatmap_rgb)
        img.save(output_path)
        print(f"✅ Heatmap sauvegardée: {output_path}")
        
        return output_path


def main():
    parser = argparse.ArgumentParser(
        description="🗺️ Mask Validation Analyzer - Valide l'application d'un mask"
    )
    
    parser.add_argument('before', help='Heightmap AVANT mask (.asc ou .png)')
    parser.add_argument('after', help='Heightmap APRÈS mask (.asc ou .png)')
    parser.add_argument('--output', default='mask_validation_report.json',
                       help='Chemin rapport JSON')
    parser.add_argument('--heatmap', default='mask_differences_heatmap.png',
                       help='Chemin heatmap')
    
    args = parser.parse_args()
    
    print("\n" + "="*70)
    print("🗺️  MASK VALIDATION ANALYZER")
    print("="*70)
    
    try:
        # Charger les heightmaps
        hmap_before = MaskValidator.load_heightmap(args.before)
        hmap_after = MaskValidator.load_heightmap(args.after)
        
        # Vérifier compatibilité
        if hmap_before.shape != hmap_after.shape:
            print(f"\n❌ ERREUR: Dimensions incompatibles!")
            print(f"   Avant: {hmap_before.shape}")
            print(f"   Après: {hmap_after.shape}")
            return 1
        
        # Détecter rivière
        river_col, river_x = MaskValidator.find_river_center(hmap_before, hmap_after)
        
        # Analyser différences
        delta, analysis = MaskValidator.analyze_differences(hmap_before, hmap_after, river_col)
        
        # Valider mask
        validation = MaskValidator.validate_mask(analysis)
        
        # Générer heatmap
        MaskValidator.generate_heatmap(delta, args.heatmap)
        
        # Sauvegarder rapport
        report = {
            'status': validation['status'],
            'analysis': analysis,
            'validation': validation
        }
        
        with open(args.output, 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"\n📊 Rapport sauvegardé: {args.output}")
        print("="*70 + "\n")
        
        return 0 if validation['status'] == 'PASS' else 1
    
    except Exception as e:
        print(f"\n❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
