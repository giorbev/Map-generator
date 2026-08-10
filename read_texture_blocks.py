"""
read_texture_blocks.py — Lecture précise des textures bloc par bloc

Lit les fichiers .ttile et _layer.edds de toutes les tuiles et génère
un CSV avec les poids exacts de chaque texture par bloc.

Usage:
    python read_texture_blocks.py --addon-path "I:/..." --output "texture_blocks.csv"
    python read_texture_blocks.py --addon-path "I:/..." --output "texture_blocks.csv" --min-pct 1.0
"""

import argparse
import csv
import sys
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app_config import resolve_paths
from clean_weights import read_lrs2_from_ttile, find_layer_path, read_layer_dds
from terrain_terr_reader import read_mats_from_terr

NUM_TILES      = 32
BLOCS_PER_TILE = 4
TOTAL_BLOCS    = NUM_TILES * BLOCS_PER_TILE  # 128×128


def get_surface_name(mat_id: int, surfaces: List) -> str:
    if mat_id >= len(surfaces):
        return f"MAT_{mat_id}"
    s = surfaces[mat_id]
    if isinstance(s, dict):
        name = s.get("emat", s.get("name", f"MAT_{mat_id}"))
    else:
        name = str(s)
    return name.replace(".emat", "")


def mat_int(m) -> int:
    return int(m[0]) if isinstance(m, (list, tuple)) else int(m)


def read_all_blocks(
    data_dir: Path,
    editor_dir: Path,
    surfaces: List,
    min_pct: float = 0.5,
    verbose: bool = True
) -> List[Dict]:
    """
    Lit tous les blocs terrain et retourne les poids de textures.

    Args:
        min_pct: % minimum pour inclure une texture dans le résultat

    Returns:
        Liste de dicts, un par bloc
    """
    rows = []
    tiles_ok = 0
    tiles_err = 0

    for ty in range(NUM_TILES):
        for tx in range(NUM_TILES):
            tile_id = ty * NUM_TILES + tx

            ttile_path = data_dir / f"Terrain_{tile_id}.ttile"
            if not ttile_path.exists():
                tiles_err += 1
                continue

            lrs2_blocks = read_lrs2_from_ttile(ttile_path)
            if lrs2_blocks is None:
                lrs2_blocks = {}

            layer_path = find_layer_path(tile_id, data_dir, editor_dir)
            weights_raw = None
            if layer_path and layer_path.exists():
                weights_raw = read_layer_dds(layer_path)  # (512,512,7) float32

            tiles_ok += 1

            for by_tile in range(BLOCS_PER_TILE):
                for bx_tile in range(BLOCS_PER_TILE):
                    bx_global = tx * BLOCS_PER_TILE + bx_tile
                    by_global = ty * BLOCS_PER_TILE + by_tile

                    block_data = lrs2_blocks.get((bx_tile, by_tile), None)
                    if block_data is not None:
                        mat_ids_raw, _ = block_data  # déballer (mat_ids, index)
                        mat_ids = [int(m) for m in mat_ids_raw]
                    else:
                        mat_ids = []

                    bloc_weights: Dict[int, float] = {}

                    if weights_raw is not None and mat_ids:
                        x0 = bx_tile * 128
                        y0 = by_tile * 128
                        raw = weights_raw[y0:y0+128, x0:x0+128, :]

                        # w0 implicite
                        if raw.shape[2] == 6:
                            w0 = float(np.clip(1.0 - raw.sum(axis=-1), 0, 1).mean())
                        else:
                            w0 = float(raw[:, :, 0].mean())

                        bloc_weights[mat_ids[0]] = round(w0 * 100, 2)

                        # w1..w6 explicites
                        for k in range(1, min(len(mat_ids), 7)):
                            if raw.shape[2] == 6:
                                w = float(raw[:, :, k-1].mean())
                            else:
                                w = float(raw[:, :, k].mean())
                            if w > 0.001:
                                bloc_weights[mat_ids[k]] = round(w * 100, 2)

                    elif mat_ids:
                        bloc_weights[mat_ids[0]] = 100.0
                    else:
                        # Aucun LRS2 — Grass_03_default w0 implicite
                        bloc_weights[0] = 100.0

                    # Filtrer par min_pct et trier par poids décroissant
                    filtered = {k: v for k, v in bloc_weights.items() if v >= min_pct}
                    sorted_weights = sorted(filtered.items(), key=lambda x: -x[1])

                    if not sorted_weights:
                        continue

                    # Texture dominante
                    dom_mat_id, dom_pct = sorted_weights[0]
                    dom_name = get_surface_name(dom_mat_id, surfaces)

                    row = {
                        "tx": tx,
                        "ty": ty,
                        "tile_id": tile_id,
                        "bx_global": bx_global,
                        "by_global": by_global,
                        "dominant_texture": dom_name,
                        "dominant_pct": dom_pct,
                        "n_textures": len(sorted_weights),
                    }

                    # Ajouter chaque texture avec son %
                    for i, (mat_id, pct) in enumerate(sorted_weights, 1):
                        row[f"tex_{i}"] = get_surface_name(mat_id, surfaces)
                        row[f"pct_{i}"] = pct

                    rows.append(row)

        if verbose and (ty + 1) % 8 == 0:
            print(f"  [{ty+1}/{NUM_TILES}] rangées traitées — {len(rows)} blocs lus...")

    if verbose:
        print(f"[OK] {tiles_ok} tuiles, {tiles_err} ignorées, {len(rows)} blocs exportés")

    return rows


def write_csv(rows: List[Dict], output_path: Path):
    """Écrit le CSV avec colonnes dynamiques."""
    if not rows:
        print("[WARN] Aucun bloc à exporter")
        return

    # Trouver le nombre max de textures par bloc
    max_tex = max(r["n_textures"] for r in rows)

    # Construire les en-têtes
    base_cols = ["tx", "ty", "tile_id", "bx_global", "by_global",
                 "dominant_texture", "dominant_pct", "n_textures"]
    tex_cols = []
    for i in range(1, max_tex + 1):
        tex_cols += [f"tex_{i}", f"pct_{i}"]

    fieldnames = base_cols + tex_cols

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            # Remplir les colonnes manquantes avec vide
            for col in fieldnames:
                row.setdefault(col, "")
            writer.writerow(row)

    print(f"[OK] CSV écrit : {output_path} ({len(rows)} lignes)")


def main():
    parser = argparse.ArgumentParser(
        description="Lecture précise des textures bloc par bloc"
    )
    parser.add_argument("--addon-path", type=str, required=True,
                        help="Chemin racine addon Reforger")
    parser.add_argument("--output", type=str, required=True,
                        help="Fichier CSV de sortie")
    parser.add_argument("--terr-file", type=str, default=None,
                        help="Chemin fichier terrain.terr (auto si absent)")
    parser.add_argument("--min-pct", type=float, default=0.5,
                        help="% minimum pour inclure une texture (défaut: 0.5)")
    parser.add_argument("--quiet", action="store_true")

    args = parser.parse_args()

    rp = resolve_paths(args.addon_path)
    if not rp.get("valid"):
        print(f"[ERREUR] {rp.get('error')}")
        sys.exit(1)

    data_dir   = Path(rp["data_dir"])
    editor_dir = Path(rp["editor_dir"])
    terr_path  = Path(args.terr_file) if args.terr_file else Path(rp.get("terr_file", ""))

    if not terr_path.exists():
        print(f"[ERREUR] terrain.terr introuvable : {terr_path}")
        sys.exit(1)

    surfaces = read_mats_from_terr(terr_path)
    if not args.quiet:
        print(f"[INFO] {len(surfaces)} surfaces depuis {terr_path.name}")
        print(f"[INFO] Lecture de {NUM_TILES}×{NUM_TILES} tuiles...")
        print()

    rows = read_all_blocks(
        data_dir=data_dir,
        editor_dir=editor_dir,
        surfaces=surfaces,
        min_pct=args.min_pct,
        verbose=not args.quiet
    )

    write_csv(rows, Path(args.output))

    # Résumé par texture dominante
    if not args.quiet:
        from collections import Counter
        dom_count = Counter(r["dominant_texture"] for r in rows)
        print()
        print("=== TEXTURES DOMINANTES ===")
        total = len(rows)
        for tex, count in dom_count.most_common():
            print(f"  {tex:40s} : {count:5d} blocs ({count/total*100:5.1f}%)")


if __name__ == "__main__":
    main()
