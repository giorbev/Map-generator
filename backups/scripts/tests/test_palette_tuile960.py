"""
Tester hypothèse : palette tuile = [0] + LRS2 unique IDs
"""

from pathlib import Path
from lrs2_parser import load_lrs2_from_ttile

tile_id = 960
data_dir = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain\.Data")
ttile_path = data_dir / f"Terrain_{tile_id}.ttile"

# Charger LRS2
lrs2_blocks = load_lrs2_from_ttile(ttile_path)

# Collecter tous les mat_ids
all_ids = set()
for mat_ids in lrs2_blocks.values():
    all_ids.update(mat_ids)

print(f"Tuile {tile_id}:")
print(f"  Mat IDs uniques LRS2: {sorted(all_ids)}")
print()

# Hypothèse: palette = [0] + sorted(all_ids)
palette_hyp1 = [0] + sorted(all_ids)
print(f"Hypothèse 1 - Palette = [0] + sorted IDs:")
print(f"  {palette_hyp1[:7]}")
print()

# Hypothèse: palette = sorted(all_ids) (0 inclus si présent)
if 0 not in all_ids:
    all_ids.add(0)
palette_hyp2 = sorted(all_ids)
print(f"Hypothèse 2 - Palette = sorted(all IDs avec 0):")
print(f"  {palette_hyp2[:7]}")
print()

print("Diagnostic tuile 960:")
print("  w0=98.5%, w1=0.8% → matériau dominant dans slot 0")
print("  LRS2 dit mat_ids=[1] → SeaBed")
print()
print("Si palette=[0,1], alors:")
print("  w0 → mat 0 (Grass_03_default)")
print("  w1 → mat 1 (SeaBed_01)")
print("Cela explique pourquoi w0 domine (fond par défaut) !")
