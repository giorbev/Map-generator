#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🗺️ ASC ↔ PNG 16-bit Converter
Script autonome pour conversion ASC ↔ PNG avec dénormalisation correcte

Workflow:
1. ASC original (altitudes réelles: 100-3000m)
2. → PNG 16-bit normalisé (0-65535)
3. [Modifier le PNG]
4. → ASC final (altitudes conservées sauf modifications)

Usage:
    python asc_png_converter.py --asc-to-png input.asc output.png
    python asc_png_converter.py --png-to-asc input.png output.asc --metadata metadata.json
"""

import numpy as np
from PIL import Image
import json
import argparse
import os
from pathlib import Path


class ASCPNGConverter:
    """Convertisseur ASC ↔ PNG 16-bit avec gestion des métadonnées."""
    
    @staticmethod
    def load_asc(asc_path):
        """Charge un fichier ASC et retourne l'array + métadonnées."""
        print(f"📂 Chargement ASC: {asc_path}")
        
        with open(asc_path, 'r') as f:
            lines = f.readlines()
        
        # Parser les headers ESRI ASCII Grid
        headers = {}
        header_lines = 6  # Nombre standard de lignes d'en-tête
        
        for i in range(header_lines):
            parts = lines[i].strip().split()
            if len(parts) >= 2:
                key = parts[0].lower()
                value = parts[1]
                headers[key] = value
        
        ncols = int(headers['ncols'])
        nrows = int(headers['nrows'])
        cellsize = float(headers.get('cellsize', 1.0))
        nodata = float(headers.get('nodata_value', -9999))
        
        # Lire les données
        data = []
        for line in lines[header_lines:]:
            values = line.strip().split()
            if values:
                data.extend([float(v) for v in values])
        
        heightmap = np.array(data).reshape(nrows, ncols).astype(np.float32)
        
        metadata = {
            'ncols': ncols,
            'nrows': nrows,
            'cellsize': cellsize,
            'nodata_value': nodata,
            'alt_min': float(np.min(heightmap)),
            'alt_max': float(np.max(heightmap))
        }
        
        print(f"✅ ASC chargé: {ncols}×{nrows} pixels")
        print(f"   Altitudes: {metadata['alt_min']:.2f}m - {metadata['alt_max']:.2f}m")
        
        return heightmap, metadata
    
    @staticmethod
    def asc_to_png(asc_path, png_path, metadata_path=None):
        """Convertit ASC → PNG 16-bit avec sauvegarde des métadonnées."""
        print(f"\n🔄 Conversion ASC → PNG 16-bit...")
        
        heightmap, metadata = ASCPNGConverter.load_asc(asc_path)
        
        # Normaliser en 16-bit (0-65535)
        h_min = metadata['alt_min']
        h_max = metadata['alt_max']
        
        if h_max > h_min:
            heightmap_normalized = (heightmap - h_min) / (h_max - h_min) * 65535
        else:
            heightmap_normalized = np.zeros_like(heightmap)
        
        heightmap_16bit = heightmap_normalized.astype(np.uint16)
        
        # Sauvegarder le PNG
        png_image = Image.fromarray(heightmap_16bit, mode='I;16')
        png_image.save(png_path)
        print(f"✅ PNG 16-bit sauvegardé: {png_path}")
        
        # Sauvegarder les métadonnées
        if metadata_path is None:
            metadata_path = Path(png_path).stem + "_metadata.json"
        
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        print(f"📊 Métadonnées sauvegardées: {metadata_path}")
        
        return png_path, metadata_path
    
    @staticmethod
    def png_to_asc(png_path, asc_path, metadata_path=None):
        """Convertit PNG 16-bit → ASC avec dénormalisation via métadonnées."""
        print(f"\n🔄 Conversion PNG → ASC...")
        
        # Charger le PNG
        png_image = Image.open(png_path)
        png_array = np.array(png_image, dtype=np.float32)
        print(f"✅ PNG chargé: {png_array.shape}")
        
        # Charger les métadonnées
        if metadata_path is None:
            metadata_path = Path(png_path).stem + "_metadata.json"
        
        if not os.path.exists(metadata_path):
            print(f"⚠️  Métadonnées non trouvées: {metadata_path}")
            print("   Les altitudes seront perdues!")
            metadata = None
        else:
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
            print(f"📊 Métadonnées chargées")
            print(f"   Alt min: {metadata['alt_min']:.2f}m, Alt max: {metadata['alt_max']:.2f}m")
        
        # Dénormaliser
        if metadata:
            h_min = metadata['alt_min']
            h_max = metadata['alt_max']
            
            # Reconvertir 16-bit → altitudes réelles
            heightmap_denormalized = (png_array / 65535.0) * (h_max - h_min) + h_min
        else:
            # Sans métadonnées, utiliser directement les valeurs PNG
            heightmap_denormalized = png_array
        
        # Sauvegarder l'ASC
        nrows, ncols = heightmap_denormalized.shape
        cellsize = metadata.get('cellsize', 1.0) if metadata else 1.0
        nodata = metadata.get('nodata_value', -9999) if metadata else -9999
        
        print(f"\n📝 Écriture ASC...")
        with open(asc_path, 'w') as f:
            # Headers ESRI ASCII Grid
            f.write(f"ncols         {ncols}\n")
            f.write(f"nrows         {nrows}\n")
            f.write(f"xllcorner     0.0\n")
            f.write(f"yllcorner     0.0\n")
            f.write(f"cellsize      {cellsize}\n")
            f.write(f"NODATA_value  {nodata}\n")
            
            # Données
            for row in heightmap_denormalized:
                row_str = ' '.join([f"{val:.2f}" for val in row])
                f.write(row_str + '\n')
        
        print(f"✅ ASC sauvegardé: {asc_path}")
        
        if metadata:
            new_min = np.min(heightmap_denormalized)
            new_max = np.max(heightmap_denormalized)
            print(f"   Altitudes: {new_min:.2f}m - {new_max:.2f}m")
        
        return asc_path


def main():
    parser = argparse.ArgumentParser(
        description="🗺️ Convertisseur ASC ↔ PNG 16-bit avec dénormalisation"
    )
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '--asc-to-png',
        nargs=2,
        metavar=('INPUT.ASC', 'OUTPUT.PNG'),
        help='Convertir ASC → PNG 16-bit'
    )
    group.add_argument(
        '--png-to-asc',
        nargs=2,
        metavar=('INPUT.PNG', 'OUTPUT.ASC'),
        help='Convertir PNG 16-bit → ASC (avec dénormalisation)'
    )
    
    parser.add_argument(
        '--metadata',
        metavar='FILE.JSON',
        help='Chemin fichier métadonnées (auto-généré/détecté si non spécifié)'
    )
    
    args = parser.parse_args()
    
    print("\n" + "="*60)
    print("🗺️  ASC ↔ PNG 16-bit Converter")
    print("="*60)
    
    try:
        if args.asc_to_png:
            asc_input, png_output = args.asc_to_png
            metadata_output = args.metadata or Path(png_output).stem + "_metadata.json"
            ASCPNGConverter.asc_to_png(asc_input, png_output, metadata_output)
            print(f"\n✨ Conversion réussie!")
            print(f"   PNG: {png_output}")
            print(f"   Métadonnées: {metadata_output}")
        
        elif args.png_to_asc:
            png_input, asc_output = args.png_to_asc
            metadata_file = args.metadata
            ASCPNGConverter.png_to_asc(png_input, asc_output, metadata_file)
            print(f"\n✨ Conversion réussie!")
            print(f"   ASC: {asc_output}")
    
    except Exception as e:
        print(f"\n❌ Erreur: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    print("="*60 + "\n")
    return 0


if __name__ == '__main__':
    exit(main())
