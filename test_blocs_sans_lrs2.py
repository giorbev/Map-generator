#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TEST RÉEL — Compter blocs SANS entrée LRS2 sur toute la carte
"""

import json
import sys
from pathlib import Path

# Import modules projet
sys.path.insert(0, str(Path(__file__).parent))
from clean_weights import read_lrs2_from_ttile

# Charger project.json
proj_path = Path("data/projects/Zimnitrita/project.json")
if not proj_path.exists():
    print(f"[ERREUR] project.json introuvable : {proj_path}")
    sys.exit(1)

pdata = json.loads(proj_path.read_text(encoding="utf-8"))
paths = pdata.get("paths", {})
grid = pdata.get("reforger_grid", {})

data_dir = Path(paths.get("data_dir", ""))
if not data_dir.exists():
    print(f"[ERREUR] data_dir introuvable : {data_dir}")
    sys.exit(1)

# Lire grille
tiles_list = grid.get("tiles", [32, 32])
grid_w = tiles_list[0]

print("=" * 80)
print("COMPTAGE BLOCS SANS ENTRÉE LRS2")
print("=" * 80)
print()
print(f"Chemins lus depuis project.json :")
print(f"  data_dir : {data_dir}")
print(f"  Grille   : {grid_w}×{grid_w} tuiles")
print()

# Scanner toutes les tuiles
n_tiles = grid_w * grid_w
blocs_sans_lrs2 = []

print(f"Scan de {n_tiles} tuiles...")
print()

for tid in range(n_tiles):
    ttile_path = data_dir / f"Terrain_{tid}.ttile"
    if not ttile_path.exists():
        continue

    lrs2_blocks = read_lrs2_from_ttile(ttile_path)
    if lrs2_blocks is None:
        continue

    # Convertir tid → tx, ty
    tx = tid % grid_w
    ty = tid // grid_w

    # Vérifier chaque bloc (4×4 = 16 blocs par tuile)
    for by in range(4):
        for bx in range(4):
            block_val = lrs2_blocks.get((bx, by))
            if block_val is None:
                # Bloc SANS entrée LRS2
                blocs_sans_lrs2.append((tx, ty, bx, by, tid))

print("=" * 80)
print("RÉSULTATS")
print("=" * 80)
print()
print(f"Blocs SANS entrée LRS2 : {len(blocs_sans_lrs2)}")
print()

if len(blocs_sans_lrs2) > 0:
    print("Premiers 20 blocs :")
    for tx, ty, bx, by, tid in blocs_sans_lrs2[:20]:
        print(f"  Tuile T{tid:4d} (tx={tx:2d}, ty={ty:2d}) Bloc ({bx},{by})")
