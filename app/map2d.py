# -*- coding: utf-8 -*-
"""
map2d.py — Carte 2D du terrain dans l'esprit de la carte du jeu (relief ombré, mer, végétation)

Sources :
  relief      cartes de normales des tuiles Workbench (<.Data>/<préfixe>N_normal.edds) : terrain
              réellement édité (routes aplanies comprises), sans recalcul depuis la heightmap
  mer         altitude < 0 (tableau fourni par l'appelant : altitudes du terrain Workbench lues dans
              les .bterr, bterr_reader.py, ou à défaut heightmap du projet)
  végétation  de préférence les arbres et buissons des .layer du monde (layer_vegetation.py :
              position de chaque arbre, placé à la main ou produit par un générateur de forêt) ;
              à défaut, poids des textures de forêt peintes dans les tuiles (_layer.dds + matériaux
              du .ttile), semés en points

Orientation : les tuiles sont placées d'après leurs coordonnées LRS2 puis l'image est retournée
verticalement (nord en haut), comme pour la satmap.
"""

import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from edds_decoder import decode_edds_color
from layer_dds_reader import read_layer_dds, extract_all_weights
from layer_vegetation import BUSH, CONIFER, DECIDUOUS
from lrs2_parser import get_tile_coords_from_ttile, load_lrs2_from_ttile

# Couleurs (proches de la carte générée par Workbench)
SEA_COLOR = (15, 32, 32)
VEG_COLORS = {"deciduous": (50, 140, 20), "coniferous": (10, 110, 10)}
BUSH_COLOR = (60, 150, 30)
# Lumière : azimut nord-ouest, hauteur 45° (convention des cartes ombrées)
LIGHT_AZIMUTH_DEG = 315.0
LIGHT_ALTITUDE_DEG = 45.0
# Courbe de tons du relief : gris = SHADE_FLOOR + (1 - SHADE_FLOOR) * q ** (SHADE_GAMMA * relief_strength),
# q = éclairage relatif (1 = plat ou face à la lumière). Ajustée sur la carte du jeu de Zimnitrita
# (médianes de gris par niveau d'ombrage, écart de quelques niveaux sur toute la plage).
SHADE_FLOOR = 0.30
SHADE_GAMMA = 3.5
# Part des pixels de forêt pleine qui reçoivent un point d'arbre
VEG_DOT_DENSITY = 0.40
VEG_DOT_ALPHA = 0.85
VEG_BUSH_ALPHA = 0.6
# Flou de la végétation des .layer, en pixels à 8192 px (proportionnel à la taille)
VEG_BLUR_PX = 0.6
# Forme d'un arbre des .layer à partir de 8192 px (décalages ligne, colonne)
TREE_CROWN_8K = [(0, 0), (0, 1), (0, -1), (1, 0), (-1, 0)]


def vegetation_kind(material_name: str):
    """Type de végétation d'une texture : « deciduous », « coniferous » ou None (pas une forêt)."""
    n = material_name.lower()
    if "forest" not in n or "clearing" in n:
        return None
    return "coniferous" if ("coniferous" in n or "pine" in n) else "deciduous"


def _tile_forest(layer_path: Path, ttile_path: Path, grid_w: int, num_blk: int, kinds: dict):
    """Poids de forêt d'une tuile par type : {kind: (512, 512) float32} ou None."""
    layer = read_layer_dds(layer_path) if layer_path.exists() else None
    blocks = load_lrs2_from_ttile(ttile_path, grid_w, num_blk) if layer is not None else None
    if layer is None or not blocks:
        return None
    weights = extract_all_weights(layer)
    size = layer.shape[0]
    bs = size // num_blk
    out = {}
    for (bx, by), ids in blocks.items():
        raw = weights[by * bs:(by + 1) * bs, bx * bs:(bx + 1) * bs]
        for k, mat_id in enumerate(ids[:7]):
            kind = kinds.get(mat_id)
            if kind is None:
                continue
            if raw.shape[2] == 6:
                w = np.clip(1.0 - raw.sum(axis=-1), 0, 1) if k == 0 else raw[..., k - 1]
            else:
                w = raw[..., k]
            dest = out.setdefault(kind, np.zeros((size, size), np.float32))
            dest[by * bs:(by + 1) * bs, bx * bs:(bx + 1) * bs] += w
    return out


def generate_map2d(data_dir, editor_dir, tile_prefix: str, surfaces: list, heights, output_path,
                   grid_w: int, num_blk: int, size: int = 8192, vegetation: bool = True,
                   relief_strength: float = 1.0, seed: int = 0, trees=None, terrain_size_m: float = None,
                   log=print) -> dict:
    """Écrit la carte 2D (PNG RGB, size × size) et retourne {"ok", "path", "size", "tiles", "seconds",
    "vegetation_source" ("layers", "textures" ou None)}.

    heights : altitudes de la heightmap du projet (2D, nord en haut) pour la mer, ou None (pas de mer).
    trees : {"x", "z", "kind"} de layer_vegetation.load_vegetation (coordonnées monde en mètres) ;
            None = végétation tirée des textures de forêt. terrain_size_m : côté du terrain (requis avec trees).
    relief_strength : 1.0 = ombrage de la carte du jeu ; 0 = pas de relief ; plus haut = pentes plus sombres.
    """
    t0 = time.time()
    data_dir, editor_dir = Path(data_dir), Path(editor_dir)
    px = size // grid_w
    if px < 8:
        return {"ok": False, "error": f"Résolution trop faible pour {grid_w} tuiles : {size} px"}
    size = px * grid_w
    kinds = {i: vegetation_kind(Path(str(s)).stem) for i, s in enumerate(surfaces)}
    kinds = {i: k for i, k in kinds.items() if k}

    nx = np.zeros((size, size), np.float32)
    ny = np.zeros((size, size), np.float32)
    use_trees = bool(vegetation and trees is not None and terrain_size_m)
    veg = {k: np.zeros((size, size), np.uint8) for k in VEG_COLORS} if vegetation and not use_trees else {}
    placed = 0
    ttiles = sorted(data_dir.glob(f"{tile_prefix}*.ttile"))
    log(f"[CARTE2D] {len(ttiles)} tuiles, {size} px ({px} px par tuile), végétation {'oui' if vegetation else 'non'}")
    for ttile in ttiles:
        try:
            tid = int(ttile.stem[len(tile_prefix):])
        except ValueError:
            continue
        coords = get_tile_coords_from_ttile(ttile, grid_w, num_blk)
        if not coords:
            log(f"[CARTE2D] Tuile {tid} sans coordonnées, ignorée")
            continue
        tx, ty = coords
        y0, x0 = ty * px, tx * px
        if not (0 <= x0 <= size - px and 0 <= y0 <= size - px):
            continue
        normal = decode_edds_color(data_dir / f"{tile_prefix}{tid}_normal.edds")
        if normal is None:
            log(f"[CARTE2D] Normales illisibles pour la tuile {tid} (relief plat)")
        else:
            a = np.asarray(normal.resize((px, px), Image.BILINEAR), dtype=np.float32)
            # Normale compressée sur deux canaux : X dans l'alpha, Y (nord) dans le vert
            nx[y0:y0 + px, x0:x0 + px] = (a[..., 3] - 127.5) / 127.5
            ny[y0:y0 + px, x0:x0 + px] = (a[..., 1] - 127.5) / 127.5
            placed += 1
        if veg:
            forest = _tile_forest(editor_dir / f"{tile_prefix}{tid}_layer.dds", ttile, grid_w, num_blk, kinds)
            for kind, w in (forest or {}).items():
                img = Image.fromarray(np.clip(w, 0, 1) * 255).convert("L").resize((px, px), Image.BILINEAR)
                veg[kind][y0:y0 + px, x0:x0 + px] = np.asarray(img)
    log(f"[CARTE2D] Tuiles assemblées : {placed} ({time.time() - t0:.0f} s)")

    # Nord en haut (comme la satmap) : retournement vertical ; l'axe Y de la normale suit
    nx = np.flip(nx, 0)
    ny = np.flip(ny, 0)
    veg = {k: np.flip(v, 0) for k, v in veg.items()}

    # Arbres des .layer : un masque par type, déjà dans l'orientation finale (nord en haut). À partir de
    # 8192 px un arbre est une croix de 5 px (houppier), un buisson un point
    plants = {}
    if use_trees:
        scale = size / float(terrain_size_m)
        col = np.asarray(trees["x"], np.float32) * scale
        row = (float(terrain_size_m) - np.asarray(trees["z"], np.float32)) * scale
        kind = np.asarray(trees["kind"])
        inside = (col >= 0) & (col < size) & (row >= 0) & (row < size)
        col, row, kind = col[inside].astype(np.int32), row[inside].astype(np.int32), kind[inside]
        crown = TREE_CROWN_8K if size >= 8192 else [(0, 0)]
        for key, k in (("coniferous", CONIFER), ("deciduous", DECIDUOUS), ("bush", BUSH)):
            sel = kind == k
            mask = np.zeros((size, size), bool)
            for dy, dx in (crown if key != "bush" else [(0, 0)]):
                mask[np.clip(row[sel] + dy, 0, size - 1), np.clip(col[sel] + dx, 0, size - 1)] = True
            # Léger flou (comme la carte générée par Workbench) : points plus doux, même couleur moyenne
            img = Image.fromarray(mask.astype(np.uint8) * 255)
            plants[key] = np.asarray(img.filter(ImageFilter.GaussianBlur(VEG_BLUR_PX * size / 8192)))
        log(f"[CARTE2D] Végétation des .layer : {int(inside.sum())} arbres et buissons placés")

    # Mer : altitude < 0 dans la heightmap du projet, contour adouci
    sea = None
    if heights is not None:
        h = np.nan_to_num(np.asarray(heights, np.float32), nan=0.0)
        sea_img = Image.fromarray(((h < 0) * 255).astype(np.uint8)).resize((size, size), Image.BILINEAR)
        sea = np.asarray(sea_img.filter(ImageFilter.GaussianBlur(max(size / 4096, 0.5))))
        del h, sea_img

    # Rendu par bandes de lignes (mémoire bornée en 8192 px)
    az, alt = np.radians(LIGHT_AZIMUTH_DEG), np.radians(LIGHT_ALTITUDE_DEG)
    lx, ly, lz = np.cos(alt) * np.sin(az), np.cos(alt) * np.cos(az), np.sin(alt)
    gamma = SHADE_GAMMA * max(relief_strength, 0.0)
    water = np.array(SEA_COLOR, np.float32)
    rng = np.random.default_rng(seed)   # graine fixe : la même carte à chaque génération
    crowns = size >= 8192
    out = np.empty((size, size, 3), np.uint8)
    band = 1024
    for r in range(0, size, band):
        sx, sy = nx[r:r + band], ny[r:r + band]
        sz = np.sqrt(np.clip(1.0 - sx * sx - sy * sy, 0, 1))
        lam = np.clip(sx * lx + sy * ly + sz * lz, 0, 1)
        # Ombrage « igor » : plat = blanc, seules les pentes opposées à la lumière s'assombrissent
        q = np.clip(lam / lz, 0, 1)
        shade = SHADE_FLOOR + (1.0 - SHADE_FLOOR) * q ** gamma
        rgb = np.repeat((shade * 255)[..., None], 3, axis=2)
        # Végétation : arbres semés selon la densité de forêt ; à partir de 8192 px un arbre est une
        # croix de 5 px (houppier), semée 5 fois moins souvent pour garder la même couverture
        for kind, dens in veg.items():
            d = dens[r:r + band].astype(np.float32) / 255.0
            dots = rng.random(d.shape, dtype=np.float32) < d * VEG_DOT_DENSITY / (5 if crowns else 1)
            if crowns:
                seeds = dots.copy()
                dots[1:] |= seeds[:-1]
                dots[:-1] |= seeds[1:]
                dots[:, 1:] |= seeds[:, :-1]
                dots[:, :-1] |= seeds[:, 1:]
            col = np.array(VEG_COLORS[kind], np.float32)
            rgb[dots] = rgb[dots] * (1 - VEG_DOT_ALPHA) + col * shade[dots][:, None] * VEG_DOT_ALPHA
        # Arbres et buissons des .layer (buissons d'abord, arbres par-dessus)
        for key in ("bush", "deciduous", "coniferous"):
            if key in plants:
                cover = plants[key][r:r + band, :, None].astype(np.float32) / 255.0
                c = np.array(BUSH_COLOR if key == "bush" else VEG_COLORS[key], np.float32)
                a = cover * (VEG_BUSH_ALPHA if key == "bush" else VEG_DOT_ALPHA)
                rgb = rgb * (1 - a) + c * shade[..., None] * a
        # Mer sombre, un peu du relief sous la surface
        if sea is not None:
            s_ = sea[r:r + band, :, None].astype(np.float32) / 255.0
            rgb = rgb * (1 - s_) + water * (0.75 + 0.25 * shade[..., None]) * s_
        out[r:r + band] = np.clip(rgb, 0, 255).astype(np.uint8)
    del nx, ny, veg, sea, plants
    out = Image.fromarray(out)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_path.with_name(output_path.stem + ".tmp.png")
    out.save(tmp)
    tmp.replace(output_path)
    seconds = round(time.time() - t0, 1)
    log(f"[CARTE2D] Écrite : {output_path} ({seconds} s)")
    source = ("layers" if use_trees else "textures") if vegetation else None
    return {"ok": True, "path": str(output_path), "size": size, "tiles": placed, "seconds": seconds,
            "vegetation_source": source}
