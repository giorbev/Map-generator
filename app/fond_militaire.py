# -*- coding: utf-8 -*-
"""
fond_militaire.py — Fond de la carte du jeu au style carte topographique militaire des années 80

Le jeu dessine routes, bâtiments, courbes, quadrillage et noms par-dessus : l'image n'apporte que
ce qu'il ne sait pas faire, les aplats et le relief. Charte originale inspirée du genre (validée en
jeu sur deux cartes le 05/11/2026, import en Color Space = ToSRGB) :

  papier    terrain découvert, crème, relief estompé discret (lumière nord-ouest)
  champs    poids des textures Crop_Field peintes dans les tuiles, aplat léger et limite de parcelle
  forêts    arbres des .layer (au moins un arbre pour 60 m² sur 15 m : ni haies ni arbres isolés)
            + textures de forêt peintes, liseré de lisière ; 3 verts selon la densité (arbres pour 100 m²
            sur 30 m) : clairsemé < 2, moyen 2 à 3, dense > 3 (textures peintes sans arbres : moyen)
  contours  zones lissées (forêts et champs sur 4 m, eau sur 1,5 m), aplat et trait fin anticrénelés
            (distance au contour = écart au seuil / pente du masque lissé)
  bâti      pas d'aplat sous les agglomérations (demande de l'équipe, 11/2026) : le jeu dessine les
            bâtiments du .topo par-dessus le papier
  eau       mer (terrain sous 0 m) + lacs et rivières calculés comme en jeu (water_layers.py), trait de rive
  ports     objets de port des .layer (layer_port.py), légende de l'équipe (11/2026) : quai en béton gris clair,
            trait noir épais et dents côté eau seulement (berge bétonnée, mur de quai), escaliers et cales
            interrompent le mur, bollards en points noirs, pontons en bois, digues en pierre ; l'eau du terrain
            qui déborde sous les quais (bandes de moins de 9 m à moins de 6 m d'un quai) est rendue à la terre,
            de même que les flaques de moins de 200 m² à moins de 12 m d'un quai
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
FORET = (178, 212, 150)                     # densité moyenne
FORET_CLAIR = (206, 228, 176)
FORET_DENSE = (148, 192, 122)
FORET_BORD = (120, 165, 100)
DENSITES = (2.0, 3.0)                       # arbres pour 100 m² : clairsemé | moyen | dense
EAU = (160, 200, 222)
EAU_BORD = (70, 130, 175)
OMBRE = 0.18                  # force de l'estompage du relief
ARBRES_PAR_M2 = 1 / 60.0      # densité minimale d'une forêt
BT_BATIMENTS = (0, 1)
QUAI = (212, 210, 204)
QUAI_TRAIT = (30, 30, 30)
ESCALIER = (232, 230, 224)
DIGUE = (165, 160, 150)
BOIS = (178, 148, 108)
BOIS_BORD = (110, 85, 55)         # EMapBuildingType : BT_BUILDING, BT_CASTLE_BUILDING (2 et 3 = murs)


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


def _poser(img, b, couleur, bord=None, ep=0.9):
    """Aplat anticrénelé d'un masque lissé b (0..1, seuil 0,5) et trait de contour fin (ep en pixels).

    couleur : RVB, ou image (size, size, 3) pour un aplat de couleur variable.
    """
    gy, gx = np.gradient(b)
    d = (b - 0.5) / (np.sqrt(gx * gx + gy * gy) + 1e-6)          # distance au contour en pixels, > 0 dedans
    a = np.clip(0.5 + d, 0.0, 1.0)[..., None]
    col = np.asarray(couleur, np.float32)
    img *= 1.0 - a
    img += a * col
    if bord is not None:
        _trait(img, b, bord, ep, d)


def _trait(img, b, couleur, ep=0.9, d=None):
    """Trait fin anticrénelé (ep en pixels) le long du contour d'un masque lissé b (seuil 0,5)."""
    if d is None:
        gy, gx = np.gradient(b)
        d = (b - 0.5) / (np.sqrt(gx * gx + gy * gy) + 1e-6)
    e = np.clip(ep / 2 + 0.5 - np.abs(d), 0.0, 1.0)[..., None]
    img *= 1.0 - e
    img += e * np.asarray(couleur, np.float32)


def _lisse(m, sigma_px):
    return cv2.GaussianBlur(m.astype(np.float32), (0, 0), max(sigma_px, 0.6))


def _dessiner_port(img, polys, genres, eau, px):
    """Quais, murs, escaliers, bollards, pontons et digues sur img (pixels), d'après la légende de l'équipe.

    polys : (n, 4, 2) emprises en pixels (colonne, ligne) ; eau : masque d'eau final (après retrait sous les quais).
    Le trait noir et les dents ne vont que du côté de l'eau libre : un bord est « côté eau » si au moins 3 sondes
    sur 4 (2, 4, 6, 8 m) y tombent dans l'eau hors quai.
    """
    n = img.shape[0]
    S = lambda q: [np.round(np.asarray(q) * 16).astype(np.int32)]          # sous-pixels (shift=4)
    pt = lambda v: (int(round(v[0] * 16)), int(round(v[1] * 16)))
    sol = np.zeros(eau.shape, np.uint8)
    for q, g in zip(polys, genres):
        if g in ("dalle", "mur", "escalier", "digue"):
            cv2.fillPoly(sol, S(q), 1, shift=4)
    libre = (eau == 1) & (sol == 0)
    # 1. aplats
    for q, g in zip(polys, genres):
        if g in ("dalle", "mur", "escalier"):
            cv2.fillPoly(img, S(q), QUAI, cv2.LINE_AA, shift=4)
        elif g == "digue":
            cv2.fillPoly(img, S(q), DIGUE, cv2.LINE_AA, shift=4)
        elif g == "bois":
            cv2.fillPoly(img, S(q), BOIS, cv2.LINE_AA, shift=4)
            cv2.polylines(img, S(q), True, BOIS_BORD, 1, cv2.LINE_AA, shift=4)
    # 2. bords côté eau des quais et murs : trait noir épais + dents vers l'eau
    sondes = np.array([2.0, 4.0, 6.0, 8.0]) / px
    pas, dent = max(4.0 / px, 2.5), max(2.0 / px, 1.2)
    ep = max(1, int(round(1.5 / px)))
    segs = []
    for q, g in zip(polys, genres):
        if g not in ("dalle", "mur"):
            continue
        for i in range(4):
            a, b = q[i], q[(i + 1) % 4]
            L = float(np.hypot(*(b - a)))
            if L < 0.25 / px:
                continue
            t = (b - a) / L
            nr = np.array([t[1], -t[0]])
            d = np.arange(0.5, L, max(0.5, 1.0 / px)) if L > 0.5 else np.array([L / 2])
            base = a + d[:, None] * t
            for sg in (1, -1):
                pr = base[:, None, :] + sg * nr * sondes[None, :, None]
                c = np.clip(pr[..., 0].astype(int), 0, n - 1)
                r = np.clip(pr[..., 1].astype(int), 0, n - 1)
                dans = (pr[..., 0] >= 0) & (pr[..., 0] < n) & (pr[..., 1] >= 0) & (pr[..., 1] < n)
                ok = ((libre[r, c] & dans).sum(1) >= 3)
                d0 = None
                for k, v in enumerate(list(ok) + [False]):
                    if v and d0 is None:
                        d0 = k
                    elif not v and d0 is not None:
                        u0 = max(d[d0] - 0.5, 0.0)
                        u1 = min(d[k - 1] + 0.5, L)
                        segs.append((a + t * u0, a + t * u1, t, sg * nr))
                        d0 = None
    for p0, p1, t, nr in segs:
        cv2.line(img, pt(p0), pt(p1), QUAI_TRAIT, ep, cv2.LINE_AA, shift=4)
    for p0, p1, t, nr in segs:
        L = float(np.hypot(*(p1 - p0)))
        for u in np.arange(pas / 2, L, pas):
            q0 = p0 + t * u
            cv2.line(img, pt(q0), pt(q0 + nr * dent), QUAI_TRAIT, 1, cv2.LINE_AA, shift=4)
    # 3. escaliers et cales : aplat clair qui interrompt le mur, marches si la place le permet
    for q, g in zip(polys, genres):
        if g != "escalier":
            continue
        cv2.fillPoly(img, S(q), ESCALIER, cv2.LINE_AA, shift=4)
        a, b, c, d = q
        if min(np.hypot(*(b - a)), np.hypot(*(d - a))) >= 3:
            for f in np.linspace(0.25, 0.75, 3):
                cv2.line(img, pt(a + (d - a) * f), pt(b + (c - b) * f), (90, 90, 90), 1, cv2.LINE_AA, shift=4)
    # 4. bollards : points noirs
    r = max(0.6 / px, 0.6)
    for q, g in zip(polys, genres):
        if g == "bollard":
            cv2.circle(img, pt(q.mean(0)), int(round(r * 16)), QUAI_TRAIT, -1, cv2.LINE_AA, shift=4)


def generate_fond_militaire(heights, output_path, terrain_size_m, size=4096, data_dir=None, editor_dir=None,
                            tile_prefix="", surfaces=(), grid_w=32, num_blk=4, trees=None,
                            water=None, port=None, log=print) -> dict:
    """Écrit le fond de carte militaire (PNG RGB, nord en haut, taille multiple de 4).

    heights : altitudes (nord en haut) ; trees : {"x", "z", "kind"} de layer_vegetation.load_vegetation ou None ;
    water : water_layers.load_water()["bodies"] ou None.
    port : layer_port.load_port (objets de port des .layer) ou None.
    Renvoie {"ok", "path", "size", "foret_ha", "foret_classes_ha" [clairsemé, moyen, dense], "champs_ha", "port",
    "water_ha", "sea_pct", "seconds"}.
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

    def zones(m, rayon_m, min_ha):
        k = disk(rayon_m)
        m = cv2.morphologyEx(cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_CLOSE, k), cv2.MORPH_OPEN, k)
        n, lab, st, _ = cv2.connectedComponentsWithStats(m)
        return np.isin(lab, [i for i in range(1, n) if st[i, 4] * px * px >= min_ha * 1e4]).astype(np.uint8)

    img = np.empty((size, size, 3), np.float32)
    img[:] = PAPIER
    w_f, w_c = _painted_weights(data_dir, editor_dir, tile_prefix, surfaces, grid_w, num_blk, size)

    # Champs : aplat et limite fine, contour lissé sur 4 m
    champ = zones(w_c > 0.5, 4, 0.5)
    _poser(img, _lisse(champ, 4 / px), CHAMP, CHAMP_BORD)

    # Forêts : densité des arbres des .layer + textures peintes, 3 verts selon la densité
    foret = zones(w_f > 0.5, 8, 0.25)
    classe = np.ones((size, size), np.uint8)          # moyen par défaut (textures peintes sans arbres)
    if trees is not None:
        keep = np.asarray(trees["kind"]) != 2       # pas les buissons
        c = np.clip((np.asarray(trees["x"])[keep] / px).astype(int), 0, size - 1)
        r = np.clip(((side - np.asarray(trees["z"])[keep]) / px).astype(int), 0, size - 1)
        n_arbres = np.zeros((size, size), np.float32)
        np.add.at(n_arbres, (r, c), 1.0)
        dens = cv2.GaussianBlur(n_arbres, (0, 0), max(15 / px, 1.0))
        # l'ouverture sur 12 m retire les bandes de moins de 25 m (alignements le long des champs)
        par_arbres = zones(dens > px * px * ARBRES_PAR_M2, 12, 0.25)
        foret = np.maximum(foret, par_arbres)
        d100 = cv2.GaussianBlur(n_arbres, (0, 0), max(30 / px, 1.0)) / (px * px) * 100   # arbres pour 100 m²
        cl = np.digitize(d100, DENSITES).astype(np.uint8)
        classe = np.where(par_arbres == 1, cl, classe)
        classe = cv2.medianBlur(classe, 5)
    # 3 aplats nets superposés (clair, puis moyen, puis dense), limites entre classes lissées sans trait,
    # classes de moins de 1 ha fondues dans la classe voisine
    for k in (1, 2):
        petites = zones(classe >= k, 10, 1.0)
        classe = np.where((classe >= k) & (petites == 0), k - 1, classe).astype(np.uint8)
    lisiere = _lisse(foret, 4 / px)
    _poser(img, lisiere, FORET_CLAIR)
    for k, col in ((1, FORET), (2, FORET_DENSE)):
        _poser(img, np.minimum(_lisse((classe >= k) & (foret == 1), 6 / px), lisiere), col)
    _trait(img, lisiere, FORET_BORD)
    foret_cl = [ha((foret == 1) & (classe == k)) for k in range(3)]

    # Eau : mer + lacs et rivières
    eau = Hs < 0
    sea_pct = round(float(eau.mean()) * 100, 1)
    water_ha = 0.0
    if water:
        wm = water_mask(water, H, side, size)
        water_ha = round(float(wm.sum()) * px * px / 1e4, 1)
        eau = eau | wm
    eau = eau.astype(np.uint8)

    # Ports : emprises en pixels ; l'eau sous les quais et le liseré d'eau derrière eux sont rendus à la terre
    nb_port = 0
    if port is not None and len(port["genre"]):
        P_ = (np.asarray(port["poly"], np.float64) / px)
        P_[..., 1] = side / px - P_[..., 1]                       # z monde → ligne d'image
        G_ = np.asarray(port["genre"])
        dedans = (P_[..., 0].max(1) >= 0) & (P_[..., 0].min(1) < size) & (P_[..., 1].max(1) >= 0) & (P_[..., 1].min(1) < size)
        P_, G_ = P_[dedans], G_[dedans]
        nb_port = int(len(G_))
        sol = np.zeros((size, size), np.uint8)
        for q, g in zip(P_, G_):
            if g in ("dalle", "mur", "escalier", "digue"):
                cv2.fillPoly(sol, [np.round(q * 4).astype(np.int32)], 1, shift=2)
        if sol.any():
            eau[sol == 1] = 0
            ouvert = cv2.morphologyEx(eau, cv2.MORPH_OPEN, disk(4.5))
            eau[(eau == 1) & (cv2.dilate(sol, disk(6)) == 1) & (ouvert == 0)] = 0
            # restes : flaques de moins de 200 m² à moins de 12 m d'un quai
            n_, lab, st, _ = cv2.connectedComponentsWithStats(eau)
            pres = np.unique(lab[(cv2.dilate(sol, disk(12)) == 1) & (eau == 1)])
            petites = [i for i in pres if i and st[i, 4] * px * px < 200]
            if petites:
                eau[np.isin(lab, petites)] = 0

    # Relief estompé (lumière nord-ouest : seules les pentes à l'ombre s'assombrissent), sauf sur l'eau
    gy, gx = np.gradient(Hs, px)
    nz = 1.0 / np.sqrt(gx * gx + gy * gy + 1.0)
    az, alt = np.radians(315), np.radians(45)
    lx, ly, lz = np.cos(alt) * np.sin(az), np.cos(alt) * np.cos(az), np.sin(alt)
    lam = np.clip((-gx * lx + gy * ly + lz) * nz / lz, 0, 1)
    img *= (1.0 - OMBRE * (1.0 - lam))[..., None]
    _poser(img, _lisse(eau, 1.5 / px), EAU, EAU_BORD, ep=1.2)
    if nb_port:
        _dessiner_port(img, P_, G_, eau, px)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), cv2.cvtColor(np.clip(img, 0, 255).astype(np.uint8), cv2.COLOR_RGB2BGR))
    secs = round(time.time() - t0, 1)
    res = {"ok": True, "path": str(out), "size": size, "foret_ha": ha(foret), "foret_classes_ha": foret_cl,
           "champs_ha": ha(champ), "port": nb_port,
           "water_ha": water_ha, "sea_pct": sea_pct, "seconds": secs}
    log(f"[TOPO] Fond militaire écrit : {out.name} ({size} px, forêts {res['foret_ha']} ha (clairsemé / moyen / dense "
        f"{' / '.join(str(v) for v in foret_cl)}), champs {res['champs_ha']} ha, {nb_port} objets de port, {secs} s)")
    return res
