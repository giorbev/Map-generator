"""
extract_texture_maps.py — Extraction des masques texture PNG 16 bits depuis les données terrain

Lit les fichiers .ttile et _layer.edds de toutes les tuiles et génère :
  - Un PNG 16 bits par texture (poids de 0 à 65535)
  - Une carte dominante couleur (quelle texture domine chaque bloc)
  - Un JSON de rapport complet

Usage:
    python extract_texture_maps.py --addon-path "I:/Reforger.../Zimnitrita_map" --output-dir "outputs/reports/texture_map"
    python extract_texture_maps.py --addon-path "..." --output-dir "..." --terr-file "path/to/terrain.terr"
"""

import argparse
import json
import sys
import numpy as np
import cv2
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Import depuis les modules existants
from app_config import resolve_paths
from clean_weights import read_lrs2_from_ttile, find_layer_path, read_layer_dds
from terrain_terr_reader import read_mats_from_terr

# Constantes
NUM_TILES   = 32
BLOCS_PER_TILE = 4
TOTAL_BLOCS = NUM_TILES * BLOCS_PER_TILE  # 128×128

# Palette couleurs pour la carte dominante (BGR)
PALETTE = [
    (0,   180, 0),    # vert
    (0,   100, 200),  # bleu
    (200, 100, 0),    # orange
    (0,   200, 200),  # cyan
    (200, 0,   200),  # magenta
    (200, 200, 0),    # jaune
    (100, 0,   200),  # violet
    (0,   200, 100),  # vert-cyan
    (200, 0,   100),  # rose
    (100, 200, 0),    # vert-jaune
    (0,   50,  200),  # bleu foncé
    (200, 50,  0),    # brun-orange
    (50,  200, 150),  # turquoise
    (150, 50,  200),  # lilas
    (200, 150, 50),   # ocre
    (50,  150, 200),  # bleu clair
    (200, 200, 100),  # jaune clair
    (100, 200, 200),  # cyan clair
    (200, 100, 200),  # rose clair
    (150, 200, 50),   # vert lime
]


def get_surface_name(mat_id: int, surfaces: List) -> str:
    """Retourne le nom de la surface depuis l'index."""
    if mat_id >= len(surfaces):
        return f"MAT_{mat_id}"
    s = surfaces[mat_id]
    if isinstance(s, dict):
        return s.get("emat", s.get("name", f"MAT_{mat_id}"))
    return str(s)


def extract_texture_maps(
    data_dir: Path,
    editor_dir: Path,
    surfaces: List,
    output_dir: Path,
    verbose: bool = True
) -> Dict:
    """
    Extrait les masques texture PNG 16 bits pour toutes les tuiles.

    Returns:
        Rapport avec stats par texture
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    n_surfaces = len(surfaces)
    surface_names = [get_surface_name(i, surfaces) for i in range(n_surfaces)]

    if verbose:
        print(f"[INFO] {n_surfaces} surfaces chargées")
        print(f"[INFO] Grille : {TOTAL_BLOCS}×{TOTAL_BLOCS} blocs")
        print(f"[INFO] Sortie : {output_dir}")
        print()

    # Tableaux de poids par texture — float32 [0..1] par bloc
    # Shape : (TOTAL_BLOCS, TOTAL_BLOCS) par surface
    texture_weights = {i: np.zeros((TOTAL_BLOCS, TOTAL_BLOCS), dtype=np.float32)
                       for i in range(n_surfaces)}

    # Carte texture dominante
    dominant_mat   = np.full((TOTAL_BLOCS, TOTAL_BLOCS), -1, dtype=np.int32)
    dominant_weight = np.zeros((TOTAL_BLOCS, TOTAL_BLOCS), dtype=np.float32)

    # Stats
    tiles_ok  = 0
    tiles_err = 0
    blocs_total = 0

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
                weights_raw = read_layer_dds(layer_path)  # (512,512,7) float32 [0..1]

            tiles_ok += 1

            for by_tile in range(BLOCS_PER_TILE):
                for bx_tile in range(BLOCS_PER_TILE):
                    # Coordonnées globales — orientation PNG inversée
                    bx_global = tx * BLOCS_PER_TILE + bx_tile
                    by_global = ty * BLOCS_PER_TILE + by_tile

                    mat_ids = lrs2_blocks.get((bx_tile, by_tile), [])
                    blocs_total += 1

                    # Extraire poids depuis layer.edds
                    bloc_weights = {}  # {mat_id: poids}

                    # Normaliser mat_ids — peut être liste de listes
                    def _mat_int(m):
                        return int(m[0]) if isinstance(m, (list, tuple)) else int(m)
                    mat_ids_int = [_mat_int(m) for m in mat_ids]

                    if weights_raw is not None and mat_ids_int:
                        x0 = bx_tile * 128
                        y0 = by_tile * 128
                        x1 = x0 + 128
                        y1 = y0 + 128
                        raw = weights_raw[y0:y1, x0:x1, :]

                        if raw.shape[2] == 6:
                            w0 = float(np.clip(1.0 - raw.sum(axis=-1), 0, 1).mean())
                        else:
                            w0 = float(raw[:, :, 0].mean())

                        bloc_weights[mat_ids_int[0]] = w0

                        for k in range(1, min(len(mat_ids_int), 7)):
                            if raw.shape[2] == 6:
                                w = float(raw[:, :, k-1].mean())
                            else:
                                w = float(raw[:, :, k].mean())
                            if w > 0.001:
                                bloc_weights[mat_ids_int[k]] = w

                    elif mat_ids_int:
                        bloc_weights[mat_ids_int[0]] = 1.0

                    else:
                        # Aucun LRS2 — Grass_03_default w0=1.0
                        bloc_weights[0] = 1.0

                    # Remplir les tableaux de poids
                    for mat_id, w in bloc_weights.items():
                        if mat_id < n_surfaces:
                            texture_weights[mat_id][by_global, bx_global] += w

                    # Texture dominante
                    if bloc_weights:
                        dom_mat = max(bloc_weights, key=bloc_weights.get)
                        dom_w   = bloc_weights[dom_mat]
                        if dom_w > dominant_weight[by_global, bx_global]:
                            dominant_mat[by_global, bx_global]    = dom_mat
                            dominant_weight[by_global, bx_global] = dom_w

        if verbose and (ty + 1) % 8 == 0:
            print(f"  [{ty+1}/{NUM_TILES}] rangées traitées...")

    if verbose:
        print(f"[OK] {tiles_ok} tuiles traitées, {tiles_err} ignorées")
        print()

    # ── Export PNG 16 bits par texture ──────────────────────────────────────
    textures_dir = output_dir / "textures"
    textures_dir.mkdir(exist_ok=True)

    textures_exported = []
    rapport = {}

    # Upscale de 128×128 blocs → 4096×4096 pixels (32px par bloc)
    cell = 32
    out_size = TOTAL_BLOCS * cell

    for mat_id, weights in texture_weights.items():
        max_w = weights.max()
        if max_w < 0.001:
            continue  # Texture absente — skip

        name = surface_names[mat_id]
        coverage = float((weights > 0.01).sum()) / (TOTAL_BLOCS * TOTAL_BLOCS) * 100

        # Upscale bloc → pixels
        img_float = np.repeat(np.repeat(weights, cell, axis=0), cell, axis=1)
        # Flip vertical (Reforger ↕ PNG)
        img_float = np.flip(img_float, axis=0)
        # Convertir en uint16
        img_16 = (np.clip(img_float, 0, 1) * 65535).astype(np.uint16)

        safe_name = name.replace(".emat", "").replace("/", "_").replace("\\", "_")
        out_path = textures_dir / f"{safe_name}.png"
        cv2.imwrite(str(out_path), img_16)

        textures_exported.append(name)
        rapport[name] = {
            "mat_id": mat_id,
            "coverage_pct": round(coverage, 2),
            "max_weight": round(float(max_w), 4),
            "mean_weight": round(float(weights[weights > 0.001].mean()), 4) if (weights > 0.001).any() else 0.0,
        }

        if verbose:
            print(f"  ✅ {safe_name}.png — coverage {coverage:.1f}%")

    # ── Export carte dominante ───────────────────────────────────────────────
    dom_img = np.zeros((out_size, out_size, 3), dtype=np.uint8)

    for by in range(TOTAL_BLOCS):
        for bx in range(TOTAL_BLOCS):
            mat_id = int(dominant_mat[by, bx])
            by_png = TOTAL_BLOCS - 1 - by  # flip vertical
            y0 = by_png * cell
            x0 = bx * cell
            if mat_id >= 0:
                color = PALETTE[mat_id % len(PALETTE)]
            else:
                color = (30, 30, 30)
            dom_img[y0:y0+cell, x0:x0+cell] = color

    # Grille tuiles
    for i in range(1, NUM_TILES):
        pos = i * BLOCS_PER_TILE * cell
        cv2.line(dom_img, (pos, 0), (pos, out_size), (60, 60, 60), 1)
        cv2.line(dom_img, (0, pos), (out_size, pos), (60, 60, 60), 1)

    dom_path = output_dir / "dominant_texture.png"
    cv2.imwrite(str(dom_path), dom_img)
    if verbose:
        print(f"\n  ✅ dominant_texture.png")

    # ── Export légende ───────────────────────────────────────────────────────
    legend = {}
    for mat_id, name in enumerate(surface_names):
        if name in rapport:
            color = PALETTE[mat_id % len(PALETTE)]
            legend[name] = {
                "mat_id": mat_id,
                "color_bgr": list(color),
                **rapport[name]
            }

    legend_path = output_dir / "legend.json"
    with open(legend_path, 'w', encoding='utf-8') as f:
        json.dump(legend, f, indent=2, ensure_ascii=False)

    # ── Rapport final ────────────────────────────────────────────────────────
    rapport_final = {
        "tiles_processed": tiles_ok,
        "tiles_errors": tiles_err,
        "blocs_total": blocs_total,
        "textures_found": len(textures_exported),
        "textures": rapport,
    }

    rapport_path = output_dir / "rapport.json"
    with open(rapport_path, 'w', encoding='utf-8') as f:
        json.dump(rapport_final, f, indent=2, ensure_ascii=False)

    if verbose:
        print()
        print("=" * 70)
        print(f"EXTRACTION TERMINÉE")
        print(f"  {len(textures_exported)} textures exportées")
        print(f"  Sortie : {output_dir}")
        print("=" * 70)

    return rapport_final


def main():
    parser = argparse.ArgumentParser(
        description="Extraction des masques texture PNG 16 bits depuis les données terrain"
    )
    parser.add_argument("--addon-path", type=str, required=True,
                        help="Chemin racine addon Reforger")
    parser.add_argument("--output-dir", type=str, required=True,
                        help="Dossier de sortie pour les masques")
    parser.add_argument("--terr-file", type=str, default=None,
                        help="Chemin fichier terrain.terr (détection auto si absent)")
    parser.add_argument("--quiet", action="store_true",
                        help="Mode silencieux")

    args = parser.parse_args()

    # Résoudre chemins
    rp = resolve_paths(args.addon_path)
    if not rp.get("valid"):
        print(f"[ERREUR] Chemin addon invalide : {rp.get('error')}")
        sys.exit(1)

    data_dir   = Path(rp["data_dir"])
    editor_dir = Path(rp["editor_dir"])
    terr_path  = Path(args.terr_file) if args.terr_file else Path(rp.get("terr_file", ""))

    if not terr_path.exists():
        print(f"[ERREUR] terrain.terr introuvable : {terr_path}")
        sys.exit(1)

    surfaces = read_mats_from_terr(terr_path)
    print(f"[INFO] {len(surfaces)} surfaces depuis {terr_path.name}")

    output_dir = Path(args.output_dir)

    extract_texture_maps(
        data_dir=data_dir,
        editor_dir=editor_dir,
        surfaces=surfaces,
        output_dir=output_dir,
        verbose=not args.quiet
    )


if __name__ == "__main__":
    main()
