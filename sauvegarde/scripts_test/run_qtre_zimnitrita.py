"""
Lance analyse QTRE sur masks Zimnitrita générés
"""

import sys
sys.path.insert(0, r'h:\logiciel perso\Map generator')

from pipeline_core import generate_qtre_heatmap
from pathlib import Path

# Dossier masks générés
masks_dir = Path(r"h:\logiciel perso\Map generator\data\projects\Zimnitrita\pipeline_11masks_20260611_173326")

# Dossier output (même dossier que masks)
output_dir = masks_dir

# Cellsize Zimnitrita
cellsize = 4.0

print("="*80)
print("ANALYSE QTRE — Zimnitrita 11 Masks")
print("="*80)
print(f"\nMasks: {masks_dir}")
print(f"Output: {output_dir}")
print(f"Cellsize: {cellsize}m/px\n")

# Lancer analyse QTRE
results = generate_qtre_heatmap(
    masks_dir=masks_dir,
    cellsize=cellsize,
    output_dir=output_dir,
    heightmap=None,
    presence_threshold=3276,  # 5% de 65535
    threshold_ok=3,
    threshold_limit=5,
    analyze_conflicts=True,
    generate_per_texture_heatmaps=False
)

if results:
    print("\n" + "="*80)
    print("STATISTIQUES FINALES")
    print("="*80)
    print(f"\nTotal blocs: {results['total_blocs']}")
    print(f"Densite max: {results['max_density']} textures/bloc")
    print(f"Densite moyenne: {results['mean_density']:.2f} textures/bloc")
    print(f"Densite mediane: {results['median_density']:.0f} textures/bloc")

    print(f"\nDistribution:")
    for density in sorted(results['distribution'].keys()):
        info = results['distribution'][density]
        print(f"  {density} textures/bloc: {info['count']} blocs ({info['percent']:.2f}%)")

    print(f"\nTop 10 zones les plus denses:")
    for i, zone in enumerate(results['top_zones'][:10], 1):
        print(f"\n  #{i} Bloc ({zone['x_m']:.0f}m, {zone['y_m']:.0f}m): {zone['density']} textures")
        print(f"      Textures actives:")
        for tex in zone['textures']:
            print(f"        - {tex['name']}: {tex['coverage']:.1f}% couverture")

    print("\n" + "="*80)
    print("[OK] Analyse QTRE terminee")
    print("="*80)
else:
    print("\n[ERREUR] Echec analyse QTRE")
