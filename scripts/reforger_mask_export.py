"""
Reforger Mask Export — Phase 2 & 3: Export et validation des masques

Reconstitue les masques globaux PNG 8-bit par surface depuis les .ttile du monde.
Variantes des décodeurs QTRE pour retourner les poids complets (pas l'argmax).
"""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime

import numpy as np
from PIL import Image
from scipy.ndimage import zoom


# ── Décodeurs QTRE — Variantes "poids complets" ─────────────────────────────

def decode_qtre_2mat_weights(
    qtre_bytes: bytes,
    mat_ids: List[int],
    target_res: Tuple[int, int] = (128, 128)
) -> Dict[int, np.ndarray]:
    """
    Décode QTRE 2-mat (quadtree) → dict {mat_id: array float32 [0-1]}

    Args:
        qtre_bytes: données binaires QTRE
        mat_ids: [mat0, mat1] indices matériaux
        target_res: (H, W) résolution cible (128×128 natif)

    Returns:
        {mat_id: poids_array} shape target_res, float32 [0, 1]
    """
    if len(qtre_bytes) < 36 or len(mat_ids) != 2:
        # Fallback : mat0 = 100%
        return {mat_ids[0]: np.ones(target_res, dtype=np.float32)}

    n_nodes = (len(qtre_bytes) - 32) // 4
    nodes = np.frombuffer(qtre_bytes[32 : 32 + n_nodes*4], dtype=np.uint32)
    dim = 128
    grid = np.full((dim, dim), np.nan, dtype=np.float32)

    def fill(idx: int, x: int, y: int, size: int) -> None:
        if idx >= len(nodes):
            return
        node = int(nodes[idx])
        if node & 0xC0000000:  # Feuille
            grid[y:y+size, x:x+size] = (node & 0xFF) / 255.0
        else:
            half = size >> 1
            if half > 0 and node + 3 < len(nodes):
                fill(node,   x,      y,      half)
                fill(node+1, x+half, y,      half)
                fill(node+2, x,      y+half, half)
                fill(node+3, x+half, y+half, half)

    fill(0, 0, 0, dim)

    # NaN → 0 (pas de contribution)
    grid = np.nan_to_num(grid, nan=0.0)

    # Rééchantillonner si target_res != 128×128
    if (dim, dim) != target_res:
        grid = zoom(grid, (target_res[0] / dim, target_res[1] / dim), order=0)

    # mat0 = grid, mat1 = 1 - grid
    return {
        mat_ids[0]: grid,
        mat_ids[1]: 1.0 - grid,
    }


def decode_qtre_3mat_weights(
    qtre_bytes: bytes,
    mat_ids: List[int],
    target_res: Tuple[int, int] = (128, 128)
) -> Dict[int, np.ndarray]:
    """
    Décode QTRE 3-mat (4156 B) → dict {mat_id: array float32 [0-1]}

    Args:
        qtre_bytes: données binaires QTRE
        mat_ids: [mat0, mat1, mat2] indices matériaux
        target_res: (H, W) résolution cible (rééchantillonner depuis 32×32)

    Returns:
        {mat_id: poids_array} shape target_res, float32 [0, 1]
    """
    if len(qtre_bytes) != 4156 or len(mat_ids) != 3:
        # Fallback : mat0 = 100%
        return {mat_ids[0]: np.ones(target_res, dtype=np.float32)}

    raw = np.frombuffer(qtre_bytes[60:60+4096], dtype=np.uint8)
    data = raw.reshape(32, 32, 4)

    weights = data[:, :, :3].astype(np.float32)  # canaux [w0, w1, w2]
    totals = weights.sum(axis=2, keepdims=True)
    totals = np.where(totals == 0, 1.0, totals)
    norm = weights / totals  # Normaliser par pixel

    result = {}
    for i, mat_id in enumerate(mat_ids):
        w = norm[:, :, i]
        # Rééchantillonner vers target_res
        if (32, 32) != target_res:
            w = zoom(w, (target_res[0] / 32, target_res[1] / 32), order=0)
        result[mat_id] = w

    return result


def decode_qtre_4mat_weights(
    qtre_bytes: bytes,
    mat_ids: List[int],
    target_res: Tuple[int, int] = (128, 128)
) -> Dict[int, np.ndarray]:
    """
    Décode QTRE 4-mat ou 5-mat (6204 B) → dict {mat_id: array float32 [0-1]}

    Args:
        qtre_bytes: données binaires QTRE
        mat_ids: [mat0, ..., mat3/4] indices matériaux
        target_res: (H, W) résolution cible (rééchantillonner depuis 32×32)

    Returns:
        {mat_id: poids_array} shape target_res, float32 [0, 1]
    """
    n = len(mat_ids)
    if len(qtre_bytes) != 6204 or n not in (4, 5):
        # Fallback : mat0 = 100%
        return {mat_ids[0]: np.ones(target_res, dtype=np.float32)}

    raw = np.frombuffer(qtre_bytes[60:60+6144], dtype=np.uint8)
    data = raw.reshape(32, 32, 6)

    weights = data[:, :, :n].astype(np.float32)  # n canaux actifs
    totals = weights.sum(axis=2, keepdims=True)
    totals = np.where(totals == 0, 1.0, totals)
    norm = weights / totals

    result = {}
    for i, mat_id in enumerate(mat_ids):
        w = norm[:, :, i]
        if (32, 32) != target_res:
            w = zoom(w, (target_res[0] / 32, target_res[1] / 32), order=0)
        result[mat_id] = w

    return result


def decode_qtre_block_weights(
    mat_ids: List[int],
    qtre_bytes: Optional[bytes],
    target_res: Tuple[int, int] = (128, 128)
) -> Dict[int, np.ndarray]:
    """
    Décode un bloc QTRE → poids par matériau.

    Args:
        mat_ids: liste des indices matériaux du bloc
        qtre_bytes: données QTRE ou None
        target_res: (H, W) résolution cible

    Returns:
        {mat_id: array(H, W) float32 [0, 1]}
    """
    n = len(mat_ids)

    if n == 0:
        return {}

    if n == 1 or qtre_bytes is None:
        # Mono-matériau : poids 1.0 partout
        return {mat_ids[0]: np.ones(target_res, dtype=np.float32)}

    if n == 2:
        return decode_qtre_2mat_weights(qtre_bytes, mat_ids, target_res)

    if n == 3 and len(qtre_bytes) == 4156:
        return decode_qtre_3mat_weights(qtre_bytes, mat_ids, target_res)

    if n in (4, 5) and len(qtre_bytes) == 6204:
        return decode_qtre_4mat_weights(qtre_bytes, mat_ids, target_res)

    # Fallback : format inconnu → mat0 = 100%
    return {mat_ids[0]: np.ones(target_res, dtype=np.float32)}


# ── Parseur .bterr (métadonnées terrain) ────────────────────────────────────

def parse_bterr_metadata(bterr_path: str) -> dict:
    """
    Parse le fichier .bterr pour extraire métadonnées du terrain.

    Returns:
        {
            "tiles_x": int,
            "tiles_y": int,
            "blocks_per_tile_x": int,
            "blocks_per_tile_y": int,
            "surface_res_px": int,  # Résolution masque par bloc (128 ou 32)
        }
    """
    # TODO: implémenter parseur binaire .bterr
    # Pour l'instant, retour valeurs par défaut
    return {
        "tiles_x": 1,
        "tiles_y": 1,
        "blocks_per_tile_x": 4,
        "blocks_per_tile_y": 4,
        "surface_res_px": 128,
    }


# ── Exporteur de masques ─────────────────────────────────────────────────────

def export_all_masks(
    world_dir: str,
    out_dir: str,
    flip_y: bool = False,
    progress_callback=None,
    target_resolution: int = 4097  # Résolution cible (4k standard Reforger)
) -> dict:
    """
    Exporte tous les masques de surface depuis un monde Reforger.

    Args:
        world_dir: dossier du monde (contient .terr, .bterr, .ttile)
                   OU chemin vers le fichier .terr (le dossier parent sera utilisé)
        out_dir: dossier de sortie pour les PNG
        flip_y: inverser l'axe Y du PNG
        progress_callback: fonction(step, pct) pour barre de progression

    Returns:
        {
            "surfaces": List[str],
            "resolution": (H, W),
            "masks_exported": int,
            "warnings": List[str],
            "error_map": np.ndarray,  # |1 - somme| max par pixel
        }
    """
    from reforger_texture_budget import parse_terr_materials, find_terr_files, _iter_tmat_bmats
    import re

    world_path = Path(world_dir)

    # Si c'est un fichier .terr, utiliser le dossier parent
    if world_path.is_file() and world_path.suffix.lower() == '.terr':
        world_path = world_path.parent
    out_path = Path(out_dir)

    # Trouver .terr
    terr_files = find_terr_files(str(world_path))
    if not terr_files:
        raise FileNotFoundError(f"Aucun fichier .terr trouvé dans {world_dir}")

    terr_path = terr_files[0]

    # Parse matériaux
    materials = parse_terr_materials(str(terr_path))
    if not materials:
        raise ValueError("Aucun matériau trouvé dans le .terr")

    # Parse métadonnées terrain (chercher dans .EditorData/)
    bterr_files = list(world_path.glob("*.bterr"))
    if not bterr_files:
        editor_data = world_path / ".EditorData"
        if editor_data.exists():
            bterr_files = list(editor_data.glob("Terrain.bterr"))

    if bterr_files:
        meta = parse_bterr_metadata(str(bterr_files[0]))
    else:
        # Valeurs par défaut
        meta = {
            "tiles_x": 1,
            "tiles_y": 1,
            "blocks_per_tile_x": 4,
            "blocks_per_tile_y": 4,
            "surface_res_px": 128,
        }

    block_res = meta.get("surface_res_px", 128)

    # Canvas par surface (allocation lazy)
    canvases: Dict[int, np.ndarray] = {}

    # Trouver tous les .ttile (dans .Data/ ou à la racine)
    ttile_files = sorted(world_path.glob("**/*.ttile"))
    if not ttile_files:
        # Fallback : chercher dans .Data/ explicitement
        data_dir = world_path / ".Data"
        if data_dir.exists():
            ttile_files = sorted(data_dir.glob("*.ttile"))

    if not ttile_files:
        raise FileNotFoundError(f"Aucun fichier .ttile trouvé dans {world_path}")

    warnings = []
    n_tiles = len(ttile_files)

    _idx_re = re.compile(r"_(\d+)$")

    # ── Auto-détection dimensions depuis .ttile ──────────────────────────────
    # Scanner TOUS les .ttile pour trouver les coordonnées max (pas échantillon)
    print(f"[INFO] Auto-détection dimensions terrain depuis {n_tiles} .ttile...")
    max_bx = 0
    max_by = 0

    for i, ttile_path in enumerate(ttile_files):
        try:
            data = ttile_path.read_bytes()
            for bx, by, mat_ids, qtre in _iter_tmat_bmats(data):
                if bx > max_bx:
                    max_bx = bx
                if by > max_by:
                    max_by = by
        except Exception:
            continue

        # Progress tous les 200 fichiers
        if (i + 1) % 200 == 0 or i == n_tiles - 1:
            print(f"  [{i+1}/{n_tiles}] Analyse en cours...")

    # Dimensions réelles
    total_blocks_x = max_bx + 1
    total_blocks_y = max_by + 1

    print(f"[INFO] Dimensions détectées : {total_blocks_x}×{total_blocks_y} blocs")

    # Validation contre specs attendues Zimnitrita
    if total_blocks_x == 128 and total_blocks_y == 128:
        print(f"[INFO] ✅ Dimensions validées (carte 16km standard)")
    else:
        print(f"[WARN] Dimensions inhabituelles : attendu 128×128 pour carte 16km")

    # Dimensions globales (depuis auto-détection)
    global_h_native = total_blocks_y * block_res
    global_w_native = total_blocks_x * block_res

    # Calcul résolution de sortie (downscale si nécessaire)
    max_native = max(global_h_native, global_w_native)

    if target_resolution and target_resolution < max_native:
        # Downscale pour économiser RAM
        scale_factor = target_resolution / max_native
        global_h = int(global_h_native * scale_factor)
        global_w = int(global_w_native * scale_factor)
        print(f"[INFO] Résolution native : {global_w_native}×{global_h_native} px")
        print(f"[INFO] Résolution export : {global_w}×{global_h} px (downscale {scale_factor:.3f}x pour économiser RAM)")
    else:
        # Pleine résolution
        scale_factor = 1.0
        global_h = global_h_native
        global_w = global_w_native
        print(f"[INFO] Résolution masques globaux : {global_w}×{global_h} px ({block_res}px/bloc)")

    for tile_idx, ttile_path in enumerate(ttile_files):
        if progress_callback:
            progress_callback(f"Tuile {tile_idx+1}/{n_tiles}", (tile_idx+1) / n_tiles)

        # Lire TMAT/QTRE
        try:
            data = ttile_path.read_bytes()
        except OSError:
            warnings.append(f"Impossible de lire {ttile_path.name}")
            continue

        for bx, by, mat_ids, qtre in _iter_tmat_bmats(data):
            if not mat_ids:
                continue

            # Décoder poids
            weights = decode_qtre_block_weights(mat_ids, qtre, (block_res, block_res))

            # Calculer coordonnées avec downscaling
            block_res_scaled = int(block_res * scale_factor)
            y0 = int(by * block_res * scale_factor)
            y1 = y0 + block_res_scaled
            x0 = int(bx * block_res * scale_factor)
            x1 = x0 + block_res_scaled

            # Vérifier bounds
            if y1 > global_h or x1 > global_w:
                warnings.append(f"Bloc ({bx},{by}) hors limites")
                continue

            for mat_id, weight_grid in weights.items():
                if mat_id not in canvases:
                    canvases[mat_id] = np.zeros((global_h, global_w), dtype=np.float32)

                # Downscale poids si nécessaire
                if scale_factor < 1.0 and weight_grid.shape[0] != block_res_scaled:
                    from PIL import Image
                    weight_img = Image.fromarray(weight_grid)
                    weight_resized = weight_img.resize(
                        (block_res_scaled, block_res_scaled),
                        Image.BICUBIC
                    )
                    weight_grid = np.array(weight_resized, dtype=np.float32)

                canvases[mat_id][y0:y1, x0:x1] = weight_grid

    # Vérifier invariant somme = 1
    if canvases:
        sum_map = np.zeros((global_h, global_w), dtype=np.float32)
        for canvas in canvases.values():
            sum_map += canvas

        error_map = np.abs(1.0 - sum_map)
        max_error = float(error_map.max())

        if max_error > 2.0/255:
            warnings.append(
                f"⚠️ Invariant somme=1 violé : erreur max = {max_error:.4f} "
                f"(seuil 2/255 = {2/255:.4f})"
            )
    else:
        error_map = np.zeros((global_h, global_w), dtype=np.float32)

    # Export PNG
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    masks_dir = out_path / "masks" / timestamp
    masks_dir.mkdir(parents=True, exist_ok=True)

    exported = 0
    for mat_id, canvas in canvases.items():
        if mat_id >= len(materials):
            mat_name = f"material_{mat_id}"
            warnings.append(f"Matériau hors catalogue : index {mat_id}")
        else:
            mat_name = Path(materials[mat_id]).stem

        # Flip Y si demandé
        if flip_y:
            canvas = np.flipud(canvas)

        # Convert float32 [0-1] → uint8 [0-255]
        png_data = np.clip(canvas * 255, 0, 255).astype(np.uint8)

        # Export PNG
        png_path = masks_dir / f"{mat_name}.png"
        Image.fromarray(png_data, mode='L').save(png_path)
        exported += 1

    # Manifest JSON
    manifest = {
        "timestamp": timestamp,
        "world_dir": str(world_path),
        "surfaces": materials,
        "resolution": [global_h, global_w],
        "flip_y": flip_y,
        "masks_exported": exported,
        "warnings": warnings,
    }

    import json
    manifest_path = masks_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')

    return {
        "surfaces": materials,
        "resolution": (global_h, global_w),
        "masks_exported": exported,
        "warnings": warnings,
        "error_map": error_map,
        "output_dir": str(masks_dir),
    }


# ── Validation ───────────────────────────────────────────────────────────────

def compare_masks(
    mask_reconstructed: str,
    mask_reference: str,
) -> dict:
    """
    Compare un masque reconstruit avec une référence (export manuel Workbench).

    Teste automatiquement flip X/Y et rapporte la meilleure orientation.

    Args:
        mask_reconstructed: chemin PNG reconstruit
        mask_reference: chemin PNG référence (export manuel)

    Returns:
        {
            "best_flip": (flip_x, flip_y),
            "mean_error": float,
            "max_error": int,
            "pct_identical": float,  # % pixels identiques à ±1
            "diff_image": np.ndarray,  # Heatmap diff
        }
    """
    ref = np.array(Image.open(mask_reference).convert('L'), dtype=np.int16)
    rec = np.array(Image.open(mask_reconstructed).convert('L'), dtype=np.int16)

    # Rééchantillonner rec si résolutions différentes
    if rec.shape != ref.shape:
        from scipy.ndimage import zoom
        scale_y = ref.shape[0] / rec.shape[0]
        scale_x = ref.shape[1] / rec.shape[1]
        rec = zoom(rec, (scale_y, scale_x), order=0).astype(np.int16)

    # Tester 4 orientations
    candidates = [
        ((False, False), rec),
        ((True,  False), np.fliplr(rec)),
        ((False, True),  np.flipud(rec)),
        ((True,  True),  np.flipud(np.fliplr(rec))),
    ]

    best_flip = None
    best_mean = float('inf')
    best_diff = None

    for flip, variant in candidates:
        diff = np.abs(variant - ref)
        mean_err = float(diff.mean())

        if mean_err < best_mean:
            best_mean = mean_err
            best_flip = flip
            best_diff = diff

    max_error = int(best_diff.max())
    identical = float(np.sum(best_diff <= 1) / best_diff.size * 100)

    # Heatmap diff (0-255 → couleur)
    diff_heatmap = np.clip(best_diff * 5, 0, 255).astype(np.uint8)

    return {
        "best_flip": best_flip,
        "mean_error": best_mean,
        "max_error": max_error,
        "pct_identical": identical,
        "diff_image": diff_heatmap,
    }
