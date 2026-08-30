"""
Debug : Voir exactement quelles textures sont chargées pendant la génération
"""

import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import reforger_satmap_direct as satmap_direct

world_terr = r"I:\reforger_travail\Zimnitrita_map\World\Zimnitrita\Terrain\Terrain.terr"
output = Path("output/debug_satmap.png")

print("="*80)
print("DEBUG GÉNÉRATION SATMAP")
print("="*80 + "\n")

result = satmap_direct.generate_satmap_from_world(
    world_terr_path=world_terr,
    output_path=output,
    mode="textured",
    resolution=4097
)

print("\n" + "="*80)
print("RÉSULTAT")
print("="*80 + "\n")

print(f"Fichier : {result['output_path']}")
print(f"Résolution : {result['resolution']}")
print(f"Temps : {result['elapsed_sec']}s")
print(f"Surfaces : {result['n_surfaces']}")

if result.get('warnings'):
    print(f"\n⚠️ WARNINGS ({len(result['warnings'])}) :")
    for w in result['warnings'][:50]:  # Afficher les 50 premiers
        print(f"  {w}")
else:
    print("\n✓ Aucun warning")
