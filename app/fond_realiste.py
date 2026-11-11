# -*- coding: utf-8 -*-
"""
fond_realiste.py — Fond de la carte du jeu (topo) au style « satellite réaliste »

Vue satellite dessinée par-dessus la satmap du projet (prototype validé par Jordi le 11/11/2026,
à 2 m/px) :

  sol        satmap la plus fine du projet (champs compris), tons moyens légèrement éclaircis
  eau        mer, lacs et rivières à la couleur de la mer du jeu (fond_topo.colorer_eau)
  routes     chaussées du .topo (bloc ROAD, LOD 0 : quadrilatères à la vraie largeur), revêtement d'après
             le générateur de route des .layer le plus proche : asphalte gris foncé, béton (pavés compris)
             gris clair, terre beige ; terre dessinée d'abord, asphalte par-dessus
  arbres     un arbre par arbre des .layer : ombre portée au sud-est puis couronne éclairée au nord-ouest
             (conifère, feuillu, buisson = petit arbre), taille et teinte légèrement variées
  toits      emprises des bâtiments du .topo (classes 0 et 1 du bloc BULD, sans les murs) : maisons en
             rouge, bâtiments industriels en gris (catégorie du prefab le plus proche dans les .layer, à
             défaut plus de 300 m² = industriel), deux pans clair / sombre, faîtage, ombre portée
             (hauteur fixe de 6 m)

Rendu par tuiles en double résolution puis réduit (une couronne de 2 à 4 px reste ronde à 2 m/px) ;
le hasard est tiré une fois pour toute la carte, les tuiles se raccordent sans couture.
"""

import struct
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROUGES = ((158, 66, 50), (140, 58, 45), (170, 82, 60), (128, 60, 48))
GRIS = ((120, 120, 122), (100, 102, 105), (140, 140, 138), (88, 90, 94))
ROUTES = ((82, 83, 86), (168, 165, 158), (150, 128, 98))          # asphalte, béton, terre
ARBRES = ((38, 58, 34), (58, 82, 40), (70, 88, 46))                # conifère, feuillu, buisson
RAYONS = (2.6, 3.8, 1.4)                                           # rayon moyen de couronne (m)
SOLEIL = np.array([1.0, 1.0]) / np.sqrt(2)                         # ombres vers le sud-est (colonne, ligne)
HAUTEUR_BAT = 6.0                                                  # m, pour l'ombre des bâtiments
GAMMA = 0.85
SS = 2                                                             # suréchantillonnage
TUILE = 1024                                                       # px de sortie par tuile
MARGE = 16                                                         # px de sortie autour d'une tuile


def find_satmap_fine(generated_dir):
    """Satmap du projet la plus grande (satmap_v2_textured_*.png, hors temporaires), la plus récente à égalité."""
    best = None
    Image.MAX_IMAGE_PIXELS = None            # satmap native : 16 384 px ou plus
    for p in Path(generated_dir).glob("satmap_v2_textured_*.png"):
        if "temp" in p.stem:
            continue
        try:
            with Image.open(p) as im:
                key = (im.size[0], p.stat().st_mtime)
        except Exception:
            continue
        if best is None or key > best[0]:
            best = (key, p)
    return best[1] if best else None


def read_topo_roads(path, lod=0) -> list:
    """Routes du bloc ROAD du .topo au niveau de détail lod : [(classe, quads (k, 4, 2))], coordonnées fichier."""
    d = Path(path).read_bytes()
    u = lambda o: struct.unpack_from("<I", d, o)[0]
    o, blocks = 20, {}
    while o < len(d) - 8:
        blocks[d[o:o + 4]] = o + 20
        o = u(o + 12)
    if b"ROAD" not in blocks:
        return []
    o = blocks[b"ROAD"] + 32                # 8 compteurs par classe
    nlod = u(o)
    o += 4
    out = []
    for L in range(nlod):
        nr = u(o)
        o += 4
        for _ in range(nr):
            cls, n = d[o], u(o + 1)
            if L == lod:
                out.append((cls, np.frombuffer(d, "<f4", 2 * n, o + 5).reshape(-1, 4, 2).astype(np.float64)))
            o += 5 + 8 * n
            o += 4 + 4 * u(o)               # routes connectées
        if L == lod:
            break
    return out


def _revetements(roads, objets, side):
    """Revêtement de chaque route du .topo : vote des points de route des .layer à moins de 15 m."""
    from scipy.spatial import cKDTree
    defaut = lambda cls: 0 if cls <= 2 else 2
    if objets is None or not len(objets["route_type"]):
        return [defaut(c) for c, _ in roads]
    pts, typ = [], []
    xz, off = objets["route_xz"].astype(np.float64), objets["route_off"]
    for i, t in enumerate(objets["route_type"]):
        pl = xz[off[i]:off[i + 1]]
        for a, b in zip(pl[:-1], pl[1:]):
            k = max(1, int(np.linalg.norm(b - a) / 2))
            pts.append(a + (b - a) * np.linspace(0, 1, k + 1)[:, None])
            typ += [int(t)] * (k + 1)
    pts = np.concatenate(pts)
    pts[:, 1] = side - pts[:, 1]            # z monde → coordonnée fichier du .topo
    arbre, typ = cKDTree(pts), np.asarray(typ)
    rev = []
    for cls, q in roads:
        dist, idx = arbre.query(q.mean(1), distance_upper_bound=15)
        ok = np.isfinite(dist)
        rev.append(int(np.bincount(typ[idx[ok]], minlength=3).argmax()) if ok.any() else defaut(cls))
    return rev


def _categories(buildings, objets, side):
    """True (industriel) / False (maison) pour chaque emprise : prefab le plus proche, sinon la taille."""
    from scipy.spatial import cKDTree
    aire = np.array([0.5 * abs(np.dot(p[:, 0], np.roll(p[:, 1], 1)) - np.dot(p[:, 1], np.roll(p[:, 0], 1)))
                     for p in buildings])
    indus = aire > 300
    sans = len(buildings)
    if objets is not None and len(objets["bat_type"]):
        bxz = objets["bat_xz"].astype(np.float64)
        bxz[:, 1] = side - bxz[:, 1]
        arbre = cKDTree(bxz)
        centres = np.array([p.mean(0) for p in buildings])
        rayon = np.maximum(6.0, 0.5 * np.sqrt(aire))
        sans = 0
        for i, (c, r) in enumerate(zip(centres, rayon)):
            dist, j = arbre.query(c, distance_upper_bound=r)
            if np.isfinite(dist):
                indus[i] = bool(objets["bat_type"][j])
            else:
                sans += 1
    return indus, sans


def generate_fond_realiste(satmap_path, heights, output_path, terrain_size_m, size=8192, trees=None,
                           buildings=None, roads=None, objets=None, water=None, log=print) -> dict:
    """Écrit le fond « satellite réaliste » (PNG RGB, nord en haut, taille multiple de 4).

    trees : {"x", "z", "kind"} de layer_vegetation.load_vegetation ou None ; buildings : polygones de
    fond_militaire.read_topo_buildings ou None ; roads : read_topo_roads ou None ; objets : layer_objets.load_objets
    ou None ; water : water_layers.load_water()["bodies"] ou None.
    Renvoie {"ok", "path", "size", "arbres", "maisons", "industriels", "routes" [asphalte, béton, terre],
    "sea_pct", "water_ha", "seconds"}.
    """
    from fond_topo import colorer_eau
    t0 = time.time()
    n = max(4, int(size) // 4 * 4)
    side = float(terrain_size_m)
    px = side / n                            # m par pixel de sortie
    rng = np.random.default_rng(1)

    # Sol et eau à la taille de sortie
    Image.MAX_IMAGE_PIXELS = None
    with Image.open(satmap_path) as im:
        log(f"[TOPO] Satmap {Path(satmap_path).name} : {im.size[0]} x {im.size[1]} px")
        f = np.asarray(im.convert("RGB").resize((n, n), Image.LANCZOS), dtype=np.float32)
    f = 255.0 * (f / 255.0) ** GAMMA
    f, sea_pct, water_ha = colorer_eau(f, heights, water, side, log=log)
    base = np.clip(f, 0, 255).astype(np.uint8)
    del f

    # Routes : quads en pixels de sortie, revêtement, ordre terre → béton → asphalte
    roads = roads or []
    rev = _revetements(roads, objets, side) if roads else []
    nb_routes = [rev.count(k) for k in range(3)]
    ordre = {2: 0, 1: 1, 0: 2}
    rq = [(q / px, rev[i]) for i, (_, q) in sorted(enumerate(roads), key=lambda e: ordre[rev[e[0]]])]
    rbox = np.array([(q[..., 0].min(), q[..., 1].min(), q[..., 0].max(), q[..., 1].max()) for q, _ in rq]).reshape(-1, 4)

    # Bâtiments : polygones en pixels de sortie, catégorie, couleur tirée une fois
    buildings = [np.asarray(p, np.float64) for p in (buildings or []) if len(p) >= 3]
    indus, sans = _categories(buildings, objets, side) if buildings else (np.zeros(0, bool), 0)
    bp = [p / px for p in buildings]
    bbox = np.array([(p[:, 0].min(), p[:, 1].min(), p[:, 0].max(), p[:, 1].max()) for p in bp]).reshape(-1, 4)
    bcoul = np.array([(GRIS if i else ROUGES)[rng.integers(4)] for i in indus], np.float32).reshape(-1, 3)
    bcoul *= rng.uniform(0.9, 1.08, (len(bp), 1))
    log(f"[TOPO] {len(rq)} routes (asphalte {nb_routes[0]}, béton {nb_routes[1]}, terre {nb_routes[2]}), "
        f"{len(bp)} bâtiments ({int((~indus).sum())} maisons, {int(indus.sum())} industriels, "
        f"{sans} classés par la taille)")

    # Arbres : position en pixels de sortie, rayon et teinte tirés une fois, ordre de dessin global
    if trees is not None and len(trees["x"]):
        tc = np.asarray(trees["x"], np.float64) / px
        tr = (side - np.asarray(trees["z"], np.float64)) / px
        tk = np.asarray(trees["kind"], np.int64).clip(0, 2)
        tR = np.asarray(RAYONS)[tk] * rng.uniform(0.75, 1.3, len(tk))
        tcoul = np.asarray(ARBRES, np.float32)[tk] * rng.uniform(0.8, 1.2, (len(tk), 1)).astype(np.float32)
        o = np.lexsort((-tR, tr))           # du nord au sud, petits par-dessus
        tc, tr, tk, tR, tcoul = tc[o], tr[o], tk[o], tR[o], tcoul[o]
    else:
        tc = tr = tR = np.zeros(0)
        tcoul = np.zeros((0, 3), np.float32)
    log(f"[TOPO] Fond satellite réaliste {n} px : {len(tc)} arbres, rendu par tuiles…")

    out = np.empty_like(base)
    sh = 16 * SS                             # sous-pixels (shift=4) par pixel de sortie
    tuiles = [(y, x) for y in range(0, n, TUILE) for x in range(0, n, TUILE)]
    for it, (y0, x0) in enumerate(tuiles):
        y1, x1 = min(y0 + TUILE, n), min(x0 + TUILE, n)
        ya, xa, yb, xb = y0 - MARGE, x0 - MARGE, y1 + MARGE, x1 + MARGE
        tile = base[max(ya, 0):min(yb, n), max(xa, 0):min(xb, n)]
        tile = cv2.copyMakeBorder(tile, max(-ya, 0), max(yb - n, 0), max(-xa, 0), max(xb - n, 0), cv2.BORDER_REPLICATE)
        H, W = (yb - ya) * SS, (xb - xa) * SS
        img = cv2.resize(tile, (W, H), interpolation=cv2.INTER_CUBIC).astype(np.float32)
        org = np.array([xa, ya], np.float64)
        P = lambda a: np.round((a - org) * sh).astype(np.int32)        # pixels de sortie → sous-pixels de tuile
        dans = lambda b: (b[:, 2] >= xa) & (b[:, 0] <= xb) & (b[:, 3] >= ya) & (b[:, 1] <= yb)

        # Routes : liseré sombre puis chaussée
        sel = np.nonzero(dans(rbox))[0] if len(rq) else []
        lw = max(1, int(round(0.6 / px * SS)))
        for passe in (0, 1):
            for i in sel:
                q, t = rq[i]
                c = (np.array(ROUTES[t], np.float32) * (0.8 if passe == 0 else 1.0)).tolist()
                poly = list(P(q))
                if passe == 0:
                    cv2.polylines(img, poly, True, c, lw, cv2.LINE_AA, shift=4)
                else:
                    cv2.fillPoly(img, poly, c, cv2.LINE_AA, shift=4)

        # Arbres : ombres portées puis couronnes
        m = (tc >= xa - 8) & (tc <= xb + 8) & (tr >= ya - 8) & (tr <= yb + 8)
        ic = np.nonzero(m)[0]
        if len(ic):
            ombre = np.zeros((H, W), np.float32)
            cc, rr, RR = (tc[ic] - xa) * SS, (tr[ic] - ya) * SS, tR[ic] / px * SS
            dc, dr = SOLEIL[0] * RR * 1.1, SOLEIL[1] * RR * 1.1
            for c, r, R in zip((cc + dc).astype(int), (rr + dr).astype(int), np.maximum(RR, 1).astype(int)):
                cv2.circle(ombre, (int(c), int(r)), int(R), 1.0, -1, cv2.LINE_AA)
            ombre = cv2.GaussianBlur(ombre, (0, 0), max(0.6 / px * SS, 0.5))
            img *= (1 - 0.55 * np.clip(ombre, 0, 1))[..., None]
            for c, r, R, col in zip(cc, rr, np.maximum(RR, 1.0), tcoul[ic]):
                c, r = int(c), int(r)
                cv2.circle(img, (c, r), int(R), (col * 0.7).tolist(), -1, cv2.LINE_AA)
                cv2.circle(img, (int(c - R * 0.2), int(r - R * 0.2)), max(1, int(R * 0.7)), col.tolist(), -1, cv2.LINE_AA)
                cv2.circle(img, (int(c - R * 0.35), int(r - R * 0.35)), max(1, int(R * 0.35)), (col * 1.3).tolist(),
                           -1, cv2.LINE_AA)

        # Toits : ombres portées, puis deux pans et faîtage
        sel = np.nonzero(dans(bbox))[0] if len(bp) else []
        if len(sel):
            ombre = np.zeros((H, W), np.float32)
            dec = SOLEIL * HAUTEUR_BAT * 0.8 / px
            for i in sel:
                cv2.fillPoly(ombre, [P(bp[i] + dec)], 1.0, cv2.LINE_AA, shift=4)
            img *= (1 - 0.5 * np.clip(cv2.GaussianBlur(ombre, (0, 0), max(0.4 / px * SS, 0.5)), 0, 1))[..., None]
            for i in sel:
                p, col = bp[i], bcoul[i]
                cv2.fillPoly(img, [P(p)], col.tolist(), cv2.LINE_AA, shift=4)
                if len(p) < 4:
                    continue
                a, b, c_, d_ = p[:4]
                if np.linalg.norm(b - a) > np.linalg.norm(c_ - b):      # faîtage selon le grand axe
                    m1, m2 = (a + d_) / 2, (b + c_) / 2
                    pan = np.array([a, b, m2, m1])
                else:
                    m1, m2 = (a + b) / 2, (d_ + c_) / 2
                    pan = np.array([a, m1, m2, d_])
                k = 0.78 if pan.mean(0) @ SOLEIL > p.mean(0) @ SOLEIL else 1.15   # pan au sud-est à l'ombre
                cv2.fillPoly(img, [P(pan)], (col * k).tolist(), cv2.LINE_AA, shift=4)
                cv2.line(img, tuple(int(v) for v in P(m1)), tuple(int(v) for v in P(m2)), (col * 0.6).tolist(), 1,
                         cv2.LINE_AA, shift=4)

        small = cv2.resize(np.clip(img, 0, 255).astype(np.uint8), (xb - xa, yb - ya), interpolation=cv2.INTER_AREA)
        out[y0:y1, x0:x1] = small[MARGE:MARGE + (y1 - y0), MARGE:MARGE + (x1 - x0)]
        if (it + 1) % 8 == 0 or it + 1 == len(tuiles):
            log(f"[TOPO] Tuiles {it + 1} / {len(tuiles)} ({round(time.time() - t0)} s)")

    dst = Path(output_path)
    dst.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(out).save(dst)
    secs = round(time.time() - t0, 1)
    res = {"ok": True, "path": str(dst), "size": n, "arbres": int(len(tc)), "maisons": int((~indus).sum()),
           "industriels": int(indus.sum()), "routes": nb_routes, "sea_pct": sea_pct, "water_ha": water_ha,
           "seconds": secs}
    log(f"[TOPO] Fond satellite réaliste écrit : {dst.name} ({n} px, {secs} s)")
    return res
