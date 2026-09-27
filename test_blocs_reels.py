#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test RÉEL — Analyse 2 blocs LRS2 avec fonctions exactes de --inspect
"""

import json
import sys
from pathlib import Path
import numpy as np

# Import modules projet
sys.path.insert(0, str(Path(__file__).parent))
from clean_weights import read_lrs2_from_ttile
from edds_decoder import decode_edds_layer, extract_all_weights
from clean_weights import find_layer_path

# Charger project.json
proj_path = Path("data/projects/Zimnitrita/project.json")
if not proj_path.exists():
    print(f"[ERREUR] project.json introuvable : {proj_path}")
    sys.exit(1)

pdata = json.loads(proj_path.read_text(encoding="utf-8"))
paths = pdata.get("paths", {})

data_dir = Path(paths.get("data_dir", ""))
if not data_dir.exists():
    print(f"[ERREUR] data_dir introuvable : {data_dir}")
    sys.exit(1)

# Charger surfaces.json
surfaces_json = proj_path.parent / "surfaces.json"
if not surfaces_json.exists():
    print(f"[ERREUR] surfaces.json introuvable : {surfaces_json}")
    sys.exit(1)

s = json.loads(surfaces_json.read_text(encoding="utf-8"))
mats = s.get("materials", {})
mat_id_to_name = {int(v): k for k, v in mats.items()}
max_id = max(mat_id_to_name.keys())
surfaces = [mat_id_to_name.get(i, f"MAT_{i}") for i in range(max_id + 1)]

print("=" * 80)
print("TEST RÉEL — 2 BLOCS LRS2")
print("=" * 80)
print()
print(f"Chemins lus depuis project.json :")
print(f"  data_dir : {data_dir}")
print(f"  surfaces : {surfaces_json}")
print()

# Définir blocs à analyser
blocs_test = [
    (63, 8, "SeaBed_01 seul, w0=100%"),
    (23, 116, "mixte")
]

for lrs_x, lrs_y, description in blocs_test:
    print("=" * 80)
    print(f"BLOC LRS2 ({lrs_x},{lrs_y}) — {description}")
    print("=" * 80)
    print()

    # Conversion LRS2 → tuile + bloc local
    tx = lrs_x // 4
    ty = lrs_y // 4
    bx = lrs_x % 4
    by = lrs_y % 4
    tid = ty * 32 + tx

    print(f"Conversion :")
    print(f"  LRS2 global  : ({lrs_x}, {lrs_y})")
    print(f"  Tuile        : tx={tx}, ty={ty}, tid={tid}")
    print(f"  Bloc local   : bx={bx}, by={by}")
    print()

    # Charger .ttile
    ttile_path = data_dir / f"Terrain_{tid}.ttile"
    if not ttile_path.exists():
        print(f"[ERREUR] .ttile introuvable : {ttile_path}")
        print()
        continue

    print(f"Fichiers lus :")
    print(f"  .ttile : {ttile_path}")

    lrs2_blocks = read_lrs2_from_ttile(ttile_path)
    if lrs2_blocks is None:
        print(f"[ERREUR] Impossible de lire LRS2")
        print()
        continue

    # Trouver layer.dds
    # find_layer_path attend data_dir et editor_data_dir
    # On simule editor_data_dir
    editor_data_dir = data_dir.parent / ".EditorData"
    layer_path = find_layer_path(tid, data_dir, editor_data_dir)

    if layer_path is None:
        print(f"[ERREUR] _layer introuvable pour Terrain_{tid}")
        print()
        continue

    print(f"  _layer : {layer_path}")
    print()

    # Charger layer (EXACTEMENT comme --inspect)
    decoded = decode_edds_layer(layer_path)
    if decoded is None:
        print(f"[ERREUR] Décodage _layer échoué")
        print()
        continue

    weights = extract_all_weights(decoded)

    # Récupérer mat_ids du bloc
    # clean_weights.read_lrs2_from_ttile retourne blocks[(bx, by)] = (mat_ids, index)
    block_val = lrs2_blocks.get((bx, by))
    if block_val is None:
        print(f"[INFO] Bloc ({bx},{by}) SANS entrée LRS2")
        mat_ids = []
    else:
        mat_ids, index = block_val  # Unpack tuple (mat_ids: liste, index: uint32)

    print(f"mat_ids LRS2 : {mat_ids}")
    if len(mat_ids) > 0:
        noms = [surfaces[mid] if mid < len(surfaces) else f"MAT_{mid}" for mid in mat_ids]
        print(f"Noms        : {noms}")
    print()

    # Extraire pixels du bloc (128×128)
    x0 = bx * 128
    y0 = by * 128
    block_pixels = weights[y0:y0+128, x0:x0+128, :]
    pixel_count = 128 * 128

    # Analyser chaque slot
    print(f"Analyse slots (i=0..6) :")
    print()
    for i in range(7):
        mean_weight = block_pixels[:, :, i].mean()
        pix_nonzero = (block_pixels[:, :, i] > 0).sum()
        pct_pixels = pix_nonzero / pixel_count * 100

        print(f"  Slot {i} (w{i}) :")
        print(f"    Moyenne poids : {mean_weight:.3f} ({mean_weight*31:.1f}/31)")
        print(f"    Pixels > 0    : {pix_nonzero:5d} / {pixel_count} ({pct_pixels:.1f}%)")

        # 3 pixels bruts (du layer décodé uint32)
        # Prendre 3 positions : centre, coin, milieu bord
        positions = [
            (y0 + 64, x0 + 64, "centre"),
            (y0 + 0, x0 + 0, "coin"),
            (y0 + 64, x0 + 0, "milieu bord")
        ]

        print(f"    3 pixels bruts (uint32 hex) :")
        for py, px, label in positions:
            pixel_raw = decoded[py, px]

            # Décoder w1..w6
            w1 = (pixel_raw >>  0) & 0x1F
            w2 = (pixel_raw >>  5) & 0x1F
            w3 = (pixel_raw >> 10) & 0x1F
            w4 = (pixel_raw >> 15) & 0x1F
            w5 = (pixel_raw >> 20) & 0x1F
            w6 = (pixel_raw >> 25) & 0x1F

            # w0 calculé
            w0_calc = 31 - (w1 + w2 + w3 + w4 + w5 + w6)

            # Valeur w{i} de ce pixel
            wi_val = [w0_calc, w1, w2, w3, w4, w5, w6][i]

            print(f"      {label:12} : 0x{pixel_raw:08X} → w1..w6=[{w1:2d},{w2:2d},{w3:2d},{w4:2d},{w5:2d},{w6:2d}] w0(calc)={w0_calc:2d} → w{i}={wi_val:2d}/31")

        print()

    print()

print("=" * 80)
print("TEST TERMINÉ")
print("=" * 80)
