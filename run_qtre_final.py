"""
Analyse QTRE sur version FINAL
"""

import sys
sys.path.insert(0, r'h:\logiciel perso\Map generator')

from pipeline_core import generate_qtre_heatmap
from pathlib import Path

masks_dir = Path(r"h:\logiciel perso\Map generator\data\projects\Zimnitrita\pipeline_11masks_FINAL_20260612_113137")
output_dir = masks_dir
cellsize = 4.0

print("="*80)
print("ANALYSE QTRE - Version FINAL (toutes corrections)")
print("="*80)

results = generate_qtre_heatmap(
    masks_dir=masks_dir,
    cellsize=cellsize,
    output_dir=output_dir,
    heightmap=None,
    presence_threshold=3276,
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
        status = "[OK]" if density <= 3 else "[LIMITE]" if density <= 5 else "[CRITIQUE]"
        print(f"  {density} textures/bloc: {info['count']:6} blocs ({info['percent']:5.2f}%) {status}")

    blocs_ok = sum(results['distribution'][d]['count'] for d in range(0, 4) if d in results['distribution'])
    blocs_limite = sum(results['distribution'][d]['count'] for d in [4, 5] if d in results['distribution'])
    blocs_critique = sum(results['distribution'][d]['count'] for d in range(6, 20) if d in results['distribution'])

    total = results['total_blocs']
    pct_ok = blocs_ok / total * 100
    pct_limite = blocs_limite / total * 100
    pct_critique = blocs_critique / total * 100

    print(f"\n" + "-"*80)
    print(f"BUDGET QTRE:")
    print(f"  Blocs OK (<=3):        {blocs_ok:6} ({pct_ok:5.2f}%)")
    print(f"  Blocs Limite (4-5):    {blocs_limite:6} ({pct_limite:5.2f}%)")
    print(f"  Blocs Critique (6+):   {blocs_critique:6} ({pct_critique:5.2f}%)")
    print("-"*80)

    print("\n" + "="*80)
else:
    print("\n[ERREUR] Echec analyse QTRE")
