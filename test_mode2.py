#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test MODE 2 — Diagnostic
"""

from pathlib import Path
from pipeline_v2 import run_pipeline

# Chemins
heightmap = "data/projects/Zimnitrita/sources/temp_Terrain_modified3.asc"
output = "data/projects/Zimnitrita/generated/test_mode2"
veg_masks = "data/projects/Zimnitrita/vegetation_masks"

print("="*80)
print("TEST MODE 2")
print("="*80)

# Vérifier végétation
veg_path = Path(veg_masks)
if veg_path.exists():
    files = list(veg_path.glob("*.png"))
    print(f"\nVegetation masks : {len(files)} fichiers trouves")
    for f in files:
        print(f"  - {f.name}")
else:
    print(f"\n[ERREUR] Dossier inexistant : {veg_masks}")

# Lancer pipeline
print(f"\nLancement pipeline MODE 2...")
print(f"  Heightmap : {heightmap}")
print(f"  Output    : {output}")
print(f"  Veg masks : {veg_masks}")

results = run_pipeline(
    heightmap,
    output,
    vegetation_map=veg_masks
)

print("\n" + "="*80)
print("RESULTATS")
print("="*80)
print(f"Mode      : {results.get('mode')}")
print(f"N masks   : {results.get('n_masks')}")
print(f"Verdict   : {results.get('qtre_verdict')}")
print(f"Output    : {results.get('output_dir')}")

# Lister masks générés
output_path = Path(output)
if output_path.exists():
    masks = sorted(output_path.glob("*.png"))
    print(f"\n{len(masks)} masks generes :")
    for m in masks:
        print(f"  - {m.name}")
