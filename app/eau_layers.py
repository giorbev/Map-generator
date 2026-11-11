# -*- coding: utf-8 -*-
"""
eau_layers.py — Ajuste les lacs et rivières des .layer à l'eau réelle, pour la carte du jeu (topo)

Le .topo dessine la forme d'un lac et toute la bande Width d'une rivière, pas l'eau : une forme ou
une bande trop large donne une eau trop large sur la carte. On propose des formes et des Width
ajustés à l'eau calculée comme en jeu (water_layers.py), sans changer l'eau en jeu.
Méthode mise au point sur les calques de Giorbev à Zimnitrita (05/11/2026, CONCEPTION.md étape 16).

  marais    lac dont l'eau couvre moins de 30 % de la forme (eau peu profonde, en flaques) : laissé
            tel quel, la carte doit montrer l'étendue du marais
  lacs      points d'origine gardés là où l'eau touche le trait de la forme (barrage, déversoir,
            couloir) ou le longe ; rive libre refaite à MARGE m de l'eau ; au plus MAX_POINTS points
            (au-delà le générateur abandonne) ; jamais hors de l'ancienne forme ; nouveaux points
            à la hauteur du point le plus bas d'origine (le niveau de l'eau ne change pas)
  rivières  largeur de l'eau mesurée le long de la ligne ; tronçons de largeur homogène qui se
            chevauchent d'un segment ; Width = eau + MARGE m de chaque côté, jamais plus que l'ancien

Rien n'est écrit dans le mod : les .layer corrigés vont dans un dossier de sortie (même
arborescence que le monde), avec un bilan et un aperçu par lac ou rivière modifié.
"""

import math
import re
import secrets
import time
from pathlib import Path

import cv2
import numpy as np
from scipy.ndimage import map_coordinates
from scipy.spatial import cKDTree

from water_layers import _GEN, _floats, _own, _tree, _walk

MARGE = 3.0              # m d'eau en plus de chaque côté
MAX_POINTS = 60          # 150 points : « Too many points to generate » (lac sans eau) ; 59 et 88 passent
LAC_MIN_M2 = 2000        # lacs de moins de 0,2 ha d'eau laissés tels quels
FLAQUE_M2 = 30           # flaques ignorées
MARAIS_COUV = 0.30       # eau sur moins de 30 % de la forme : marais probable, forme laissée (étendue voulue sur la carte)
TOUCHE_M = MARGE + 3.0   # trait à moins de 6 m de l'eau sur tout un côté : côté gardé
RIV_WMIN = 6.0           # Width minimale
RIV_RATIO = 1.35         # écart de largeur qui ouvre un nouveau tronçon...
RIV_LMIN = 120.0         # ...s'il reste au moins 120 m de chaque côté
RIV_ECART = 5.0          # tronçons voisins à moins de 5 m d'écart de Width fusionnés
RIV_PETIT = 100          # morceaux d'eau de moins de 100 m² ignorés


# ── Lecture ────────────────────────────────────────────────────────────────────

def _bodies_of(path, rel) -> list:
    """Lacs et rivières d'un .layer avec l'emplacement de leurs blocs dans le texte."""
    raw = Path(path).read_bytes()
    nl = "\r\n" if b"\r\n" in raw else "\n"
    lines = raw.decode("utf-8", errors="ignore").split(nl)
    out = []
    for e in _walk(_tree(lines)):
        pts = next((k for k in e.kids if k.head == "Points"), None)
        if pts is None or e.b is None:
            continue
        gens = [k for k in _walk(e) if _GEN.search(k.head)]
        if not gens:
            continue
        g = gens[0]
        props, gp = _own(lines, e), _own(lines, g)
        c = _floats(props.get("coords"))
        if c is None:
            continue
        ang = _floats(props.get("angles", "0 0 0")) or [0.0, 0.0, 0.0]
        P, nodes = [], []
        for sp in pts.kids:
            pos = _floats(_own(lines, sp).get("Position"))
            if pos:
                P.append(pos)
                nodes.append(sp)
        if len(P) < 2 or len(nodes) != len(pts.kids):
            continue
        P = np.asarray(P, dtype=np.float64)
        yaw = math.radians(ang[1])
        cs, sn = math.cos(yaw), math.sin(yaw)
        head = e.head.split()
        in_grp = e.parent is not None and e.parent.head.startswith("$grp")
        cls = e.parent.head.split()[1] if in_grp else (head[0] if head else "")
        lake = "LakeGeneratorEntity" in g.head

        def num(k, d=0.0):
            try:
                return float(gp.get(k, d))
            except ValueError:
                return d
        out.append({
            "file": rel, "kind": "lake" if lake else "river", "spline": cls.startswith("SplineShape"),
            "closed": lake or props.get("IsClosed") == "1",
            "x": c[0] + P[:, 0] * cs + P[:, 2] * sn, "z": c[2] - P[:, 0] * sn + P[:, 2] * cs, "y": c[1] + P[:, 1],
            "coords": c, "angles": ang, "gdy": (_floats(gp.get("coords", "0 0 0")) or [0, 0, 0])[1],
            "offset": num("m_fWaterSurfaceOffset") if lake else num("WaterOffset") + num("SplineOffsetUp"),
            "width": None if lake or "Width" not in gp else num("Width"),
            "ent": (e.a, e.b), "pts": (pts.a, pts.b), "sp": [(n.a, n.b) for n in nodes], "gen": (g.a, g.b),
            "named": (len(head) >= 1) if in_grp else (len(head) >= 2),
            "name": (head[0] if in_grp else head[1]) if ((in_grp and head) or len(head) >= 2) else "",
        })
    return out


def find_water_layers(world_dir) -> list:
    """Chemins (relatifs à world_dir) des .layer qui contiennent un lac ou une rivière."""
    world_dir = Path(world_dir)
    out = []
    for f in sorted(world_dir.rglob("*.layer")):
        try:
            if _GEN.search(f.read_text(encoding="utf-8", errors="ignore")):
                out.append(f.relative_to(world_dir).as_posix())
        except OSError:
            pass
    return out


# ── Géométrie ──────────────────────────────────────────────────────────────────

def _sample(P, closed, spline, step=1.0):
    """Points le long de la forme (x, z) et numéro du côté d'origine de chacun (Catmull-Rom si spline)."""
    n = len(P)
    out, seg = [], []
    for i in range(n if closed else n - 1):
        p1, p2 = P[i], P[(i + 1) % n]
        k = max(int(np.hypot(p2[0] - p1[0], p2[-1] - p1[-1]) / step), 1)   # (x, z) ou (x, y, z)
        t = np.linspace(0.0, 1.0, k, endpoint=False)[:, None]
        if spline and n > 2:
            idx = (lambda j: P[j % n]) if closed else (lambda j: P[min(max(j, 0), n - 1)])
            p0, p3 = idx(i - 1), idx(i + 2)
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t ** 2
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
        else:
            out.append(p1 + (p2 - p1) * t)
        seg += [i] * k
    if not closed:
        out.append(P[-1:])
        seg.append(n - 2)
    return np.vstack(out), np.array(seg)


def _area(p):
    return 0.5 * (np.dot(p[:, 0], np.roll(p[:, 1], 1)) - np.dot(p[:, 1], np.roll(p[:, 0], 1)))


def _crossings(P) -> int:
    """Nombre de croisements entre côtés non voisins d'un polygone fermé."""
    n = len(P)
    A, B = P, np.roll(P, -1, 0)
    k = 0
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            d1, d2 = B[i] - A[i], B[j] - A[j]
            den = d1[0] * d2[1] - d1[1] * d2[0]
            if abs(den) < 1e-12:
                continue
            w = A[j] - A[i]
            t = (w[0] * d2[1] - w[1] * d2[0]) / den
            u = (w[0] * d1[1] - w[1] * d1[0]) / den
            k += 0 < t < 1 and 0 < u < 1
    return k


def _disk(r):
    r = max(int(round(r)), 1)
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def _heights(H, side, wx, wz):
    S = H.shape[0]
    hm = side / (S - 1)
    return map_coordinates(H, [(S - 1) - wz / hm, wx / hm], order=1, mode="nearest")


# ── Lacs ───────────────────────────────────────────────────────────────────────

def _lake(b, H, side) -> dict:
    O = np.c_[b["x"], b["z"]]
    n = len(O)
    level = float(b["y"].min()) + b["gdy"] + b["offset"]
    r = {"level": round(level, 2), "npts": n}
    if b["angles"][0] or b["angles"][2]:
        return {**r, "status": "incliné", "note": "forme inclinée, laissée telle quelle"}
    C, seg = _sample(O, True, b["spline"])
    x0, z1 = np.floor(C[:, 0].min()) - 20, np.ceil(C[:, 1].max()) + 20
    W, Hh = int(np.ceil(C[:, 0].max()) + 20 - x0), int(z1 - (np.floor(C[:, 1].min()) - 20))
    w2p = lambda p: np.c_[p[:, 0] - x0, z1 - p[:, 1]]
    p2w = lambda q: np.c_[x0 + q[:, 0], z1 - q[:, 1]]
    fill = lambda p: cv2.fillPoly(np.zeros((Hh, W), np.uint8), [np.round(w2p(p) * 4).astype(np.int32)], 1, shift=2)
    shp = fill(C)
    yy, xx = np.mgrid[0:Hh, 0:W]
    h = _heights(H, side, x0 + xx + .5, z1 - yy - .5)
    wet = ((h < level) & (shp == 1)).astype(np.uint8)
    nc, lab, st, _ = cv2.connectedComponentsWithStats(wet)
    keep = np.isin(lab, [i for i in range(1, nc) if st[i, 4] >= FLAQUE_M2]).astype(np.uint8)
    sizes = sorted((st[i, 4] for i in range(1, nc) if st[i, 4] >= FLAQUE_M2), reverse=True)
    r.update(eau_m2=int(keep.sum()), carte_avant_m2=int(shp.sum()),
             couverture=round(float(keep.sum()) / max(int(shp.sum()), 1), 3), morceaux=len(sizes),
             part_max=round(float(sizes[0]) / max(int(keep.sum()), 1), 3) if sizes else 0.0,
             img=dict(x0=x0, z1=z1, h=h, wet=keep, old=C))
    if keep.sum() < LAC_MIN_M2:
        return {**r, "status": "petit", "note": "moins de 0,2 ha d'eau"}
    if r["couverture"] < MARAIS_COUV:
        return {**r, "status": "marais ?",
                "note": f"l'eau ne couvre que {round(100 * r['couverture'])} % de la forme ({r['morceaux']} morceau"
                        f"{'x' if r['morceaux'] > 1 else ''}) : marais probable, forme laissée"}

    # Côtés à garder : le trait est à moins de TOUCHE_M de l'eau sur toute sa longueur
    dt = cv2.distanceTransform((1 - keep).astype(np.uint8), cv2.DIST_L2, 5)
    q = np.clip(np.round(w2p(C) - .5).astype(int), 0, [W - 1, Hh - 1])
    d = dt[q[:, 1], q[:, 0]]
    side_ok = np.array([d[seg == i].max() <= TOUCHE_M if (seg == i).any() else True for i in range(n)])
    kept = side_ok | np.roll(side_ok, 1)          # point i : côté i-1 ou côté i gardé
    if kept.all():
        return {**r, "status": "ok", "note": "forme déjà ajustée à l'eau"}

    base_cross = _crossings(O)
    old_area = abs(_area(C))
    for eps in np.arange(1.5, 15.01, 0.5):
        marge = MARGE + max(math.ceil(eps - 1.5), 0)   # simplification plus forte : marge élargie d'autant
        buf = cv2.dilate(keep, _disk(marge))
        rc = 0
        while cv2.connectedComponents(buf)[0] > 2 and rc < 60:   # plusieurs morceaux : on les relie
            rc += 3
            buf = cv2.morphologyEx(cv2.dilate(keep, _disk(marge)), cv2.MORPH_CLOSE, _disk(rc))
        buf &= cv2.dilate(shp, _disk(1))                          # jamais hors de l'ancienne forme
        cs, _ = cv2.findContours(buf, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if not cs:
            break
        Cn = p2w(max(cs, key=cv2.contourArea)[:, 0].astype(float) + .5)
        if not kept.any():                                        # tout est loin de l'eau : forme refaite
            ap = cv2.approxPolyDP(w2p(Cn).astype(np.float32).reshape(-1, 1, 2), float(eps), True)[:, 0]
            new = p2w(ap)
            if np.sign(_area(new)) != np.sign(_area(O)):
                new = new[::-1]
            seq = [("new", float(a), float(z)) for a, z in new]
        else:                                                     # rive libre refaite entre les points gardés
            seq, ok = [], True
            start = int(np.argmax(kept & ~np.roll(kept, -1)))     # dernier point gardé avant une rive libre
            i = 0
            while i < n:
                k = (start + i) % n
                if kept[k]:
                    seq.append(("orig", k))
                    i += 1
                    continue
                j = i
                while j < n and not kept[(start + j) % n]:
                    j += 1
                a, bb = (start + i - 1) % n, (start + j) % n          # points gardés de part et d'autre
                ia = int(np.argmin(np.hypot(*(Cn - O[a]).T)))
                ib = int(np.argmin(np.hypot(*(Cn - O[bb]).T)))
                m = len(Cn)
                arcs = [Cn[[(ia + t) % m for t in range((ib - ia) % m + 1)]],
                        Cn[[(ia - t) % m for t in range((ia - ib) % m + 1)]]]
                # l'arc qui suit la partie remplacée de l'ancienne forme
                old_part = C[np.isin(seg, [(a + t) % n for t in range((bb - a) % n)])]
                tree = cKDTree(old_part) if len(old_part) else None
                arc = min(arcs, key=lambda A: tree.query(A)[0].mean() if tree is not None else 0)
                if len(arc) < 2:
                    ok = False
                    break
                ap = cv2.approxPolyDP(w2p(arc).astype(np.float32).reshape(-1, 1, 2), float(eps), False)[:, 0]
                seq += [("new", float(a_), float(z_)) for a_, z_ in p2w(ap)[1:-1]]
                i = j
            if not ok:
                continue
        if len(seq) > MAX_POINTS:
            continue
        P = np.array([O[s[1]] if s[0] == "orig" else s[1:] for s in seq])
        if len(P) < 3:
            continue
        Cnew, _ = _sample(P, True, b["spline"])
        nm = fill(Cnew)
        lost = int((keep.astype(bool) & (nm == 0)).sum())
        cross = _crossings(P)
        if lost > max(20, 0.01 * keep.sum()) or cross > base_cross:
            continue
        new_area = abs(_area(Cnew))
        if new_area >= 0.9 * old_area:
            return {**r, "status": "ok", "note": "gain négligeable"}
        r["img"].update(new=Cnew, P=P, kept=O[kept])
        return {**r, "status": "modifié", "seq": seq, "npts_new": len(P), "carte_apres_m2": int(nm.sum()),
                "eau_perdue_m2": lost, "gardes": int(sum(s[0] == "orig" for s in seq)),
                "note": f"{int(sum(s[0] == 'orig' for s in seq))} points d'origine gardés"}
    return {**r, "status": "à la main", "note": "pas de forme sûre de 60 points au plus"}


# ── Rivières ───────────────────────────────────────────────────────────────────

def _river(b, H, side) -> dict:
    P = np.c_[b["x"], b["z"]]
    n = len(P)
    segL = np.hypot(*np.diff(P, axis=0).T)
    L = float(segL.sum())
    r = {"npts": n, "L": round(L), "width": b["width"]}
    if b["width"] is None:
        return {**r, "status": "sans Width", "note": "Width par défaut du prefab, laissée"}
    if b["closed"] or L < 50 or n < 3:
        return {**r, "status": "ok", "note": "boucle ou trop courte"}
    if b["angles"][0] or b["angles"][2]:
        return {**r, "status": "incliné", "note": "forme inclinée, laissée telle quelle"}
    Y = b["y"] + b["gdy"] + b["offset"]
    C3, seg = _sample(np.c_[b["x"], Y, b["z"]], False, b["spline"])
    C, Cy = C3[:, [0, 2]], C3[:, 1]
    hw = b["width"] / 2
    x0, z1 = np.floor(C[:, 0].min() - hw) - 5, np.ceil(C[:, 1].max() + hw) + 5
    W, Hh = int(np.ceil(C[:, 0].max() + hw) + 5 - x0), int(z1 - (np.floor(C[:, 1].min() - hw) - 5))
    w2p = lambda p: np.c_[p[:, 0] - x0, z1 - p[:, 1]]
    near = cv2.polylines(np.zeros((Hh, W), np.uint8), [np.round(w2p(C) * 4).astype(np.int32)], False, 1,
                         thickness=int(2 * hw) + 4, shift=2)
    rr, cc = np.nonzero(near)
    wx, wz = x0 + cc + .5, z1 - rr - .5
    d, j = cKDTree(C).query(np.c_[wx, wz])
    h = _heights(H, side, wx, wz)
    band = d <= hw
    wet = band & (h < Cy[j])
    wm = np.zeros((Hh, W), np.uint8)
    wm[rr[wet], cc[wet]] = 1
    nc, lab, st, _ = cv2.connectedComponentsWithStats(wm)
    big = np.isin(lab[rr, cc], [i for i in range(1, nc) if st[i, 4] >= RIV_PETIT]) & wet
    need = np.zeros(n - 1)
    sj = seg[j]
    for i in range(n - 1):
        v = d[big & (sj == i)]
        if len(v):
            need[i] = v.max()
    need = np.where(need > 0, need + MARGE, 0)
    need = np.clip(np.maximum(need, RIV_WMIN / 2), None, hw)   # demi-largeur voulue par côté
    grp = [[0]]
    for i in range(1, n - 1):
        g = grp[-1]
        vals = need[g + [i]]
        if vals.max() / vals.min() > RIV_RATIO and segL[g].sum() >= RIV_LMIN and segL[i:].sum() >= RIV_LMIN:
            grp.append([i])
        else:
            g.append(i)
    tr = [{"a": g[0], "b": g[-1] + 1, "Width": min(math.ceil(4 * need[g].max()) / 2, b["width"])} for g in grp]
    fus = [tr[0]]
    for t in tr[1:]:
        p = fus[-1]
        if abs(t["Width"] - p["Width"]) < RIV_ECART:
            p.update(b=t["b"], Width=max(p["Width"], t["Width"]))
        else:
            fus.append(t)
    hw_new = np.zeros(n - 1)
    for t in fus:
        hw_new[t["a"]:t["b"]] = t["Width"] / 2
    for t in fus[1:]:                                    # recouvrement d'un côté avec le tronçon précédent
        hw_new[t["a"] - 1] = max(hw_new[t["a"] - 1], t["Width"] / 2)
    band2 = d <= hw_new[sj]
    r.update(eau_m2=int(wet.sum()), carte_avant_m2=int(band.sum()), carte_apres_m2=int(band2.sum()),
             eau_perdue_m2=int((wet & ~band2).sum()))
    if big.sum() < RIV_PETIT:
        return {**r, "status": "sans eau", "note": "aucune eau calculée sous la ligne : à vérifier dans Workbench"}
    if len(fus) == 1 and fus[0]["Width"] >= b["width"]:
        return {**r, "status": "ok", "note": "Width déjà ajustée à l'eau"}
    if r["carte_apres_m2"] >= 0.9 * r["carte_avant_m2"]:
        return {**r, "status": "ok", "note": "gain négligeable"}
    r["img"] = dict(x0=x0, z1=z1, W=W, Hh=Hh, rr=rr, cc=cc, h=h, wet=wet, band=band, band2=band2, C=C)
    return {**r, "status": "modifié", "troncons": fus,
            "note": "Width " + " / ".join(f"{t['Width']:g}" for t in fus) + f" (avant {b['width']:g})"}


# ── Analyse et écriture ────────────────────────────────────────────────────────

def analyse(world_dir, files, heights, terrain_size_m, log=print) -> list:
    """Propositions pour les lacs et rivières des .layer donnés (chemins relatifs à world_dir)."""
    H = np.asarray(heights, dtype=np.float32)
    out = []
    for rel in files:
        try:
            bodies = _bodies_of(Path(world_dir) / rel, rel)
        except Exception as e:
            log(f"[EAU] {rel} illisible : {type(e).__name__}: {e}")
            continue
        for b in bodies:
            try:
                p = _lake(b, H, terrain_size_m) if b["kind"] == "lake" else _river(b, H, terrain_size_m)
            except Exception as e:
                p = {"status": "erreur", "note": f"{type(e).__name__}: {e}"}
            p.update(file=rel, kind=b["kind"], body=b, cx=round(float(np.mean(b["x"]))), cz=round(float(np.mean(b["z"]))),
                     name=b["name"])
            out.append(p)
    return out


def _hex():
    return secrets.token_hex(8).upper()


def _lake_points_block(lines, b, p):
    """Bloc Points du lac : lignes d'origine des points gardés + nouveaux points."""
    pa, pb = b["pts"]
    a0 = b["sp"][0][0]
    ind = re.match(r"\s*", lines[a0]).group(0)
    cx, cy, cz = b["coords"]
    yaw = math.radians(b["angles"][1])
    cs, sn = math.cos(yaw), math.sin(yaw)
    py = float(b["y"].min()) - cy          # hauteur du point le plus bas : le niveau de l'eau ne change pas
    blk = [lines[pa]]
    for s in p["seq"]:
        if s[0] == "orig":
            a, e = b["sp"][s[1]]
            blk += lines[a:e + 1]
        else:
            dx, dz = s[1] - cx, s[2] - cz
            blk += [f'{ind}ShapePoint "{{{_hex()}}}" {{',
                    f"{ind} Position {dx * cs - dz * sn:.3f} {py:.3f} {dx * sn + dz * cs:.3f}",
                    f"{ind}}}"]
    return blk + [lines[pb]]


def _river_block(lines, b, p):
    """Entité rivière recopiée en tronçons (points, Width, identifiants neufs pour les copies)."""
    ea, eb = b["ent"]
    pa, pb = b["pts"]
    ga, gb = b["gen"]
    out = []
    for k, t in enumerate(p["troncons"]):
        first = k == 0
        i0 = t["a"] if first else t["a"] - 1     # chevauchement d'un côté avec le tronçon précédent
        i = ea
        while i <= eb:
            ln = lines[i]
            if i == pa:
                out.append(ln)
                for a, e in b["sp"][i0:t["b"] + 1]:
                    sl = lines[a:e + 1]
                    if not first:
                        sl = [re.sub(r'ShapePoint "\{[0-9A-Fa-f]+\}"', f'ShapePoint "{{{_hex()}}}"', sl[0])] + sl[1:]
                    out += sl
                out.append(lines[pb])
                i = pb + 1
                continue
            if ga < i < gb:
                if re.match(r"\s*Width\s", ln):
                    ln = re.sub(r"Width\s+\S+", f"Width {t['Width']:g}", ln)
                elif not first and re.match(r'\s*GUID\s+"', ln):
                    ln = re.sub(r'GUID\s+"[0-9A-Fa-f]+"', f'GUID "{_hex()}"', ln)
            if not first and i == ea and b["named"] and b["name"]:
                ln = ln.replace(f'{b["name"]} {{', f'{b["name"]}_t{k + 1} {{', 1)
            out.append(ln)
            i += 1
    return out


def _apercu(p, path):
    """Image de contrôle : relief en gris, eau en bleu, ancien trait en rouge, nouveau en vert."""
    I = p["img"]
    if p["kind"] == "lake":
        h, wet = I["h"], I["wet"] == 1
        olds, news = [I["old"]], [I["new"]]
    else:
        h = np.full((I["Hh"], I["W"]), np.nan, np.float32)
        h[I["rr"], I["cc"]] = I["h"]
        wet = np.zeros(h.shape, bool)
        wet[I["rr"][I["wet"]], I["cc"][I["wet"]]] = True
        h = np.where(np.isnan(h), np.nanmedian(I["h"]), h)
    lo, hi = np.percentile(h, [2, 98])
    g = np.clip((h - lo) / max(hi - lo, 1e-6), 0, 1)
    img = cv2.cvtColor((g * 120 + 100).astype(np.uint8), cv2.COLOR_GRAY2BGR)
    img[wet] = (225, 170, 100)
    s = max(1.0, min(4.0, 900 / max(img.shape[:2])))
    img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_LINEAR)
    px = lambda q: np.round(np.c_[(q[:, 0] - I["x0"]) * s, (I["z1"] - q[:, 1]) * s] * 4).astype(np.int32)
    if p["kind"] == "lake":
        for c in olds:
            cv2.polylines(img, [px(c)], True, (60, 60, 220), 1, cv2.LINE_AA, shift=2)
        for c in news:
            cv2.polylines(img, [px(c)], True, (40, 170, 40), 2, cv2.LINE_AA, shift=2)
        for q in px(I["kept"]):
            cv2.circle(img, tuple(int(v) for v in q), 4 * 4, (40, 170, 40), -1, cv2.LINE_AA, shift=2)
    else:
        for m, col in ((I["band"], (60, 60, 220)), (I["band2"], (40, 170, 40))):
            mm = np.zeros((I["Hh"], I["W"]), np.uint8)
            mm[I["rr"][m], I["cc"][m]] = 1
            mm = cv2.resize(mm, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)
            cs, _ = cv2.findContours(mm, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
            cv2.drawContours(img, cs, -1, col, 1 if col[2] == 220 else 2, cv2.LINE_AA)
        cv2.polylines(img, [px(I["C"])], False, (40, 40, 40), 1, cv2.LINE_AA, shift=2)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), img)


def write(world_dir, out_dir, props, log=print) -> dict:
    """Écrit dans out_dir les .layer dont au moins une proposition est « modifié », plus bilan et aperçus."""
    world_dir, out_dir = Path(world_dir), Path(out_dir)
    todo = [p for p in props if p["status"] == "modifié"]
    bilan, written = [], []
    for rel in sorted({p["file"] for p in todo}):
        src = world_dir / rel
        raw = src.read_bytes()
        nl = "\r\n" if b"\r\n" in raw else "\n"
        lines = raw.decode("utf-8").split(nl)
        mine = [p for p in todo if p["file"] == rel]
        cur = {(b["ent"], b["pts"]) for b in _bodies_of(src, rel)}
        edits = []
        for p in mine:
            b = p["body"]
            if (b["ent"], b["pts"]) not in cur:
                raise RuntimeError(f"{rel} a changé depuis l'analyse : relancez l'analyse")
            if p["kind"] == "lake":
                edits.append((b["pts"][0], b["pts"][1], _lake_points_block(lines, b, p)))
            else:
                edits.append((b["ent"][0], b["ent"][1], _river_block(lines, b, p)))
        for a, e, blk in sorted(edits, key=lambda t: -t[0]):
            lines[a:e + 1] = blk
        root = _tree(lines)
        if any(n.b is None for n in _walk(root)):
            raise RuntimeError(f"{rel} : accolades déséquilibrées après correction, fichier non écrit")
        o = out_dir / rel
        o.parent.mkdir(parents=True, exist_ok=True)
        o.write_bytes(nl.join(lines).encode("utf-8"))
        written.append(rel)
        for p in mine:
            tag = f"{'lac' if p['kind'] == 'lake' else 'rivière'} x {p['cx']} z {p['cz']}"
            img = out_dir / "_apercus" / f"{Path(rel).stem}_{'lac' if p['kind'] == 'lake' else 'riviere'}_{p['cx']}_{p['cz']}.png"
            try:
                _apercu(p, img)
            except Exception as e:
                log(f"[EAU] Aperçu impossible pour {tag} : {e}")
            bilan.append(f"{rel} : {tag} — {p['note']} ; carte {p['carte_avant_m2'] / 1e4:.2f} → "
                         f"{p['carte_apres_m2'] / 1e4:.2f} ha (eau {p['eau_m2'] / 1e4:.2f} ha)")
    for p in props:
        if p["status"] not in ("modifié", "ok"):
            bilan.append(f"{p['file']} : {'lac' if p['kind'] == 'lake' else 'rivière'} x {p['cx']} z {p['cz']} — "
                         f"non modifié ({p['status']}) : {p['note']}")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "bilan.txt").write_text(
        f"Correction de l'eau — {time.strftime('%d/%m/%Y %H:%M')}\nMonde : {world_dir}\n"
        f"Copier les .layer de ce dossier à la même place dans le monde (Workbench fermé), puis vérifier dans Workbench.\n\n"
        + "\n".join(bilan) + "\n", encoding="utf-8")
    log(f"[EAU] {len(written)} calques écrits dans {out_dir}")
    return {"ok": True, "out_dir": str(out_dir), "files": written, "modified": len(todo)}
