# -*- coding: utf-8 -*-
"""
bterr_reader.py — Altitudes du terrain Workbench depuis <Terrain>/.EditorData/<préfixe>N.bterr

Chaque tuile a un fichier IFF « FORM … EDTR » dont le bloc DATA contient (n × n) altitudes en mètres
(float32, petit-boutiste ; n = 129 pour des tuiles de 4 blocs de 32 cellules). Les tuiles voisines
partagent leur bord : la heightmap complète fait grid_w × (n - 1) + 1 points de côté.

Placement : coordonnées LRS2 de la tuile (.ttile de .Data) puis retournement vertical (nord en haut),
comme la satmap et les normales. Contrôle (03/11, voir CONCEPTION.md, étape 15c) : corrélation 0,998
avec la heightmap .asc du projet, écart médian 0 m ; les écarts restants sont les retouches faites
dans Workbench.
"""

import struct
from pathlib import Path

import numpy as np

from lrs2_parser import get_tile_coords_from_ttile


def read_bterr(path):
    """Altitudes (n × n float32) d'un fichier .bterr de tuile, ou None (format inattendu)."""
    b = Path(path).read_bytes()
    if b[:4] != b"FORM" or b[8:12] != b"EDTR":
        return None
    pos = 12
    while pos + 8 <= len(b):
        tag, size = b[pos:pos + 4], struct.unpack(">I", b[pos + 4:pos + 8])[0]
        if tag == b"DATA":
            values = np.frombuffer(b[pos + 8:pos + 8 + size], "<f4")
            n = int(round(len(values) ** 0.5))
            return values.reshape(n, n) if n * n == len(values) else None
        pos += 8 + size + (size & 1)
    return None


def load_workbench_heights(editor_dir, data_dir, tile_prefix: str, grid_w: int, num_blk: int, log=print):
    """Heightmap complète du terrain Workbench (nord en haut, mètres), ou None si les .bterr manquent.

    Une tuile absente ou illisible laisse un trou à 0 m ; au-delà de 1 % de tuiles manquantes, None.
    """
    editor_dir, data_dir = Path(editor_dir), Path(data_dir)
    heights, n, missing = None, None, 0
    for tid in range(grid_w * grid_w):
        f = editor_dir / f"{tile_prefix}{tid}.bterr"
        coords = get_tile_coords_from_ttile(data_dir / f"{tile_prefix}{tid}.ttile", grid_w, num_blk) if f.exists() else None
        h = read_bterr(f) if coords else None
        if h is None:
            missing += 1
            continue
        if heights is None:
            n = h.shape[0]
            heights = np.zeros((grid_w * (n - 1) + 1,) * 2, np.float32)
        if h.shape[0] != n:
            missing += 1
            continue
        tx, ty = coords
        heights[ty * (n - 1):ty * (n - 1) + n, tx * (n - 1):tx * (n - 1) + n] = h
    if heights is None or missing > grid_w * grid_w * 0.01:
        if missing:
            log(f"[CARTE2D] Altitudes Workbench incomplètes ({missing} tuiles .bterr manquantes)")
        return None
    if missing:
        log(f"[CARTE2D] {missing} tuiles .bterr manquantes (altitude 0 m à leur place)")
    return heights[::-1].copy()
