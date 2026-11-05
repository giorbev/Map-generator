# -*- coding: utf-8 -*-
"""
fond_militaire.py — Fond de la carte du jeu au style carte topographique militaire des années 80

Le jeu dessine routes, bâtiments, courbes, quadrillage et noms par-dessus : l'image n'apporte que
ce qu'il ne sait pas faire, les aplats et le relief. Charte originale inspirée du genre (validée en
jeu sur ZBK et Zimnitrita le 05/11/2026, import en Color Space = ToSRGB) :

  papier    terrain découvert, crème, relief estompé discret (lumière nord-ouest)
  champs    poids des textures Crop_Field peintes dans les tuiles, aplat léger et limite de parcelle
  forêts    arbres des .layer (au moins un arbre pour 60 m² sur 15 m : ni haies ni arbres isolés)
            + textures de forêt peintes, aplat vert et liseré de lisière
  bâti      bâtiments du .topo (bloc BULD, classes bâtiment et château : pas les murs), zones d'au
            moins 1 ha et 5 bâtiments
  eau       mer (terrain sous 0 m) + lacs et rivières calculés comme en jeu (water_layers.py), trait de rive
"""

import re
import struct
import time
from pathlib import Path

import cv2
import numpy as np

from layer_dds_reader import read_layer_dds, extract_all_weights
from lrs2_parser import get_tile_coords_from_ttile, load_lrs2_from_ttile

PAPIER = (244, 238, 220)
CHAMP = (238, 230, 186)
CHAMP_BORD = (205, 190, 140)
FORET = (178, 212, 150)
FORET_BORD = (120, 165, 100)
BATI = (238, 196, 160)
EAU = (160, 200, 222)
EAU_BORD = (70, 130, 175)
OMBRE = 0.18                  # force de l'estompage du relief
ARBRES_PAR_M2 = 1 / 60.0      # densité minimale d'une forêt
BT_BATIMENTS = (0, 1)         # EMapBuildingType : BT_BUILDING, BT_CASTLE_BUILDING (2 et 3 = murs)


def find_topo(world_dir):
    """Chemin du .topo du monde : « Map Geometry Data » de SCR_MapEntity (default.layer), sinon le plus récent."""
    world_dir = Path(world_dir)
    root = world_dir
    while root.parent != root and not (root / "addon.gproj").is_file():
        root = root.parent
    if not (root / "addon.gproj").is_file():
        root = world_dir
    rx = re.compile(r'"Map Geometry Data"\s+"\{[0-9A-Fa-f]+\}([^"]+)"')
    for f in sorted(world_dir.rglob("default.layer")):
        m = rx.search(f.read_text(encoding="utf-8", errors="ignore"))
        if m and (root / m.group(1)).is_file():
            return root / m.group(1)
    topos = list(root.rglob("*.topo"))
    return max(topos, key=lambda p: p.stat().st_mtime) if topos else None


def read_topo_buildings(path) -> list:
    """Emprises des bâtiments du .topo : liste de tableaux (n, 2) en coordonnées fichier (x, 16384 ou 8192 - z)."""
    d = Path(path).read_bytes()
    u = lambda o: struct.unpack_from("<I", d, o)[0]
    o, blocks = 20, {}
    while o < len(d) - 8:
        blocks[d[o:o + 4]] = o + 20
        o = u(o + 12)
    o = blocks[b"BULD"]
    nc = u(o)
    o += 4
    out = []
    for c in range(nc):
        npg = u(o)
        o += 4
        for _ in range(npg):
            n = u(o)
            if c in BT_BATIMENTS:
                out.append(np.frombuffer(d, "<f4", 2 * n, o + 4).reshape(-1, 2))
            o += 4 + 8 * n
        o += 4 + 20 * u(o)      # points isolés de la classe
    return out


def _painted_weights(data_dir, editor_dir, prefix, surfaces, grid_w, num_blk, size):
    """Poids (size x size, nord en haut) des textures de forêt et de culture peintes dans les tuiles."""
    ids_f = {i for i, s in enumerate(surfaces) if "forest" in Path(str(s)).stem.lower() and "clearing" not in Path(str(s)).stem.lower()}
    ids_c = {i for i, s in enumerate(surfaces) if "crop_field" in Path(str(s)).stem.lower()}
    w_f, w_c = np.zeros((size, size), np.float32), np.zeros((size, size), np.float32)
    for tt in Path(data_dir).glob(f"{prefix}*.ttile"):
        tid = tt.stem[len(prefix):]
        if not tid.isdigit():
            continue
        lay_path = Path(editor_dir) / f"{prefix}{tid}_layer.dds"
        lay = read_layer_dds(lay_path) if lay_path.exists() else None
        c = get_tile_coords_from_ttile(tt, grid_w, num_blk) if lay is not None else None
        blocks = load_lrs2_from_ttile(tt, grid_w, num_blk) if c else None
        if not blocks:
            continue
        wts = extract_all_weights(lay)
        bs = lay.shape[0] // num_blk
        acc_f, acc_c = np.zeros(lay.shape[:2], np.float32), np.zeros(lay.shape[:2], np.float32)
        for (bx, by), ids in blocks.items():
            raw = wts[by * bs:(by + 1) * bs, bx * bs:(bx + 1) * bs]
            for k, m in enumerate(ids[:7]):
                dest = acc_f if m in ids_f else (acc_c if m in ids_c else None)
                if dest is None:
                    continue
                w = (np.clip(1 - raw.sum(-1), 0, 1) if k == 0 else raw[..., k - 1]) if raw.shape[2] == 6 else raw[..., k]
                dest[by * bs:(by + 1) * bs, bx * bs:(bx + 1) * bs] += w
        tx, ty = c
        x0, x1, y0, y1 = tx * size // grid_w, (tx + 1) * size // grid_w, ty * size // grid_w, (ty + 1) * size // grid_w
        w_f[y0:y1, x0:x1] = cv2.resize(np.clip(acc_f, 0, 1), (x1 - x0, y1 - y0), interpolation=cv2.INTER_AREA)
        w_c[y0:y1, x0:x1] = cv2.resize(np.clip(acc_c, 0, 1), (x1 - x0, y1 - y0), interpolation=cv2.INTER_AREA)
    return np.flip(w_f, 0), np.flip(w_c, 0)


def generate_fond_militaire(heights, output_path, terrain_size_m, size=4096, data_dir=None, editor_dir=None,
                            tile_prefix="", surfaces=(), grid_w=32, num_blk=4, trees=None, buildings=None,
                            water=None, log=print) -> dict:
    """Écrit le fond de carte militaire (PNG RGB, nord en haut, taille multiple de 4).

    heights : altitudes (nord en haut) ; trees : {"x", "z", "kind"} de layer_vegetation.load_vegetation ou None ;
    buildings : polygones de read_topo_buildings ou None ; water : water_layers.load_water()["bodies"] ou None.
    Renvoie {"ok", "path", "size", "foret_ha", "champs_ha", "bati_ha", "water_ha", "sea_pct", "seconds"}.
    """
    t0 = time.time()
    from water_layers import water_mask
    size = max(4, int(size) // 4 * 4)
    side = float(terrain_size_m)
    px = side / size
    ha = lambda m: round(float(m.sum()) * px * px / 1e4)
    H = np.asarray(heights, dtype=np.float32)
    Hs = cv2.resize(H, (size, size), interpolation=cv2.INTER_LINEAR)
    disk = lambda m: cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (max(int(m / px), 1) * 2 + 1,) * 2)
    grad = lambda m: cv2.morphologyEx(m, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) == 1

    def zones(m, rayon_m, min_ha):
        k = disk(rayon_m)
        m = cv2.morphologyEx(cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_CLOSE, k), cv2.MORPH_OPEN, k)
        n, lab, st, _ = cv2.connectedComponentsWithStats(m)
        return np.isin(lab, [i for i in range(1, n) if st[i, 4] * px * px >= min_ha * 1e4]).astype(np.uint8)

    img = np.empty((size, size, 3), np.float32)
    img[:] = PAPIER
    w_f, w_c = _painted_weights(data_dir, editor_dir, tile_prefix, surfaces, grid_w, num_blk, size)

    # Champs
    champ = zones(w_c > 0.5, 4, 0.5)
    img[champ == 1] = CHAMP
    img[grad(champ)] = CHAMP_BORD

    # Forêts : densité des arbres des .layer + textures peintes
    foret = zones(w_f > 0.5, 8, 0.25)
    if trees is not None:
        keep = np.asarray(trees["kind"]) != 2       # pas les buissons
        c = np.clip((np.asarray(trees["x"])[keep] / px).astype(int), 0, size - 1)
        r = np.clip(((side - np.asarray(trees["z"])[keep]) / px).astype(int), 0, size - 1)
        dens = np.zeros((size, size), np.float32)
        np.add.at(dens, (r, c), 1.0)
        dens = cv2.GaussianBlur(dens, (0, 0), max(15 / px, 1.0))
        # l'ouverture sur 12 m retire les bandes de moins de 25 m (alignements le long des champs)
        foret = np.maximum(foret, zones(dens > px * px * ARBRES_PAR_M2, 12, 0.25))
    img[foret == 1] = FORET
    img[grad(foret)] = FORET_BORD

    # Bâti : bâtiments du .topo (z stocké inversé : la ligne d'image est directement z / px), contour lissé
    bati = np.zeros((size, size), np.uint8)
    if buildings:
        bat = np.zeros((size, size), np.uint8)
        for p in buildings:
            cv2.fillPoly(bat, [np.round(p / px * 4).astype(np.int32)], 1, shift=2)
        z = cv2.morphologyEx(cv2.dilate(bat, disk(15)), cv2.MORPH_CLOSE, disk(25))
        z = (cv2.GaussianBlur(z.astype(np.float32), (0, 0), max(6 / px, 0.8)) > 0.5).astype(np.uint8)
        n, lab, st, _ = cv2.connectedComponentsWithStats(z)
        nb = cv2.connectedComponents(bat)[1]
        counts = {}
        rr = (bat == 1)
        for l_, b in set(zip(lab[rr].tolist(), nb[rr].tolist())):
            counts[l_] = counts.get(l_, 0) + 1
        bati = np.isin(lab, [i for i in range(1, n) if st[i, 4] * px * px >= 1e4 and counts.get(i, 0) >= 5]).astype(np.uint8)
        img[bati == 1] = BATI

    # Eau : mer + lacs et rivières
    eau = Hs < 0
    sea_pct = round(float(eau.mean()) * 100, 1)
    water_ha = 0.0
    if water:
        wm = water_mask(water, H, side, size)
        water_ha = round(float(wm.sum()) * px * px / 1e4, 1)
        eau = eau | wm
    eau = eau.astype(np.uint8)

    # Relief estompé (lumière nord-ouest : seules les pentes à l'ombre s'assombrissent), sauf sur l'eau
    gy, gx = np.gradient(Hs, px)
    nz = 1.0 / np.sqrt(gx * gx + gy * gy + 1.0)
    az, alt = np.radians(315), np.radians(45)
    lx, ly, lz = np.cos(alt) * np.sin(az), np.cos(alt) * np.cos(az), np.sin(alt)
    lam = np.clip((-gx * lx + gy * ly + lz) * nz / lz, 0, 1)
    img *= (1.0 - OMBRE * (1.0 - lam))[..., None]
    img[eau == 1] = EAU
    img[grad(eau)] = EAU_BORD

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), cv2.cvtColor(np.clip(img, 0, 255).astype(np.uint8), cv2.COLOR_RGB2BGR))
    secs = round(time.time() - t0, 1)
    res = {"ok": True, "path": str(out), "size": size, "foret_ha": ha(foret), "champs_ha": ha(champ), "bati_ha": ha(bati),
           "water_ha": water_ha, "sea_pct": sea_pct, "seconds": secs}
    log(f"[TOPO] Fond militaire écrit : {out.name} ({size} px, forêts {res['foret_ha']} ha, champs {res['champs_ha']} ha, "
        f"bâti {res['bati_ha']} ha, {secs} s)")
    return res
