# -*- coding: utf-8 -*-
"""
water_layers.py — Lacs et rivières des .layer d'un monde Workbench, et eau qu'ils font apparaître en jeu

Règles (vérifiées dans Workbench, voir CONCEPTION.md, étape 16) :
  lac       niveau = point le plus bas de la forme + décalage du générateur (coords y du
            LakeGeneratorEntity) + m_fWaterSurfaceOffset ; eau = terrain sous ce niveau, dans la forme
  rivière   niveau = hauteur de la ligne + décalage du générateur + WaterOffset + SplineOffsetUp ;
            eau = terrain sous ce niveau, dans la bande Width centrée sur la ligne
  forme     SplineShapeEntity = courbe passant par les points (approchée en Catmull-Rom),
            PolylineShapeEntity = segments droits ; position monde = coords + lacet (angles, 2e valeur)

Seuls les .layer qui contiennent un générateur d'eau sont analysés ; résultat mis en cache (JSON)
tant qu'aucun .layer n'a changé.
"""

import json
import math
import re
from pathlib import Path

import numpy as np

_KV = re.compile(r'^\s*(\w+)\s+(.+?)\s*$')
_GEN = re.compile(r'\b(LakeGeneratorEntity|RiverEntity)\s*:')
RIVER_DEFAULT_WIDTH = 10.0


class _Node:
    __slots__ = ("head", "a", "b", "kids", "parent")

    def __init__(self, head, a, parent):
        self.head, self.a, self.b, self.kids, self.parent = head, a, None, [], parent


def _tree(lines):
    root = _Node("", -1, None)
    cur = root
    for i, l in enumerate(lines):
        t = l.strip()
        if t.endswith("{"):
            n = _Node(t[:-1].strip(), i, cur)
            cur.kids.append(n)
            cur = n
        elif t == "}" and cur.parent is not None:
            cur.b = i
            cur = cur.parent
    return root


def _own(lines, node) -> dict:
    skip = set()
    for k in node.kids:
        skip.update(range(k.a, (k.b if k.b is not None else k.a) + 1))
    out = {}
    for i in range(node.a + 1, node.b if node.b is not None else node.a + 1):
        if i not in skip:
            m = _KV.match(lines[i])
            if m:
                out[m.group(1)] = m.group(2).strip('"')
    return out


def _walk(node):
    for k in node.kids:
        yield k
        yield from _walk(k)


def _floats(s, n=3):
    try:
        v = [float(x) for x in s.split()[:n]]
        return v if len(v) == n else None
    except (ValueError, AttributeError):
        return None


def parse_water(path) -> list:
    """Lacs et rivières d'un .layer : liste de dicts (kind, spline, closed, x, y, z, gdy, offset, width)."""
    lines = Path(path).read_text(encoding="utf-8", errors="ignore").splitlines()
    out = []
    for e in _walk(_tree(lines)):
        pts = next((k for k in e.kids if k.head == "Points"), None)
        if pts is None:
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
        P = []
        for sp in pts.kids:
            pos = _floats(_own(lines, sp).get("Position"))
            if pos:
                P.append(pos)
        if len(P) < 2:
            continue
        P = np.asarray(P, dtype=np.float64)
        yaw = math.radians(ang[1])
        cs, sn = math.cos(yaw), math.sin(yaw)
        x = c[0] + P[:, 0] * cs + P[:, 2] * sn
        z = c[2] - P[:, 0] * sn + P[:, 2] * cs
        y = c[1] + P[:, 1]
        gdy = (_floats(gp.get("coords", "0 0 0")) or [0, 0, 0])[1]
        cls = e.head.split()[1] if e.head.startswith("$grp") else (e.head.split()[0] if e.head else "")
        if not cls and e.parent is not None and e.parent.head.startswith("$grp"):
            cls = e.parent.head.split()[1]
        lake = "LakeGeneratorEntity" in g.head
        if lake and len(P) < 3:
            continue
        def num(k, d=0.0):
            try:
                return float(gp.get(k, d))
            except ValueError:
                return d
        out.append({
            "kind": "lake" if lake else "river",
            "spline": cls.startswith("SplineShape"),
            "closed": lake or props.get("IsClosed") == "1",
            "x": x.round(3).tolist(), "y": y.round(3).tolist(), "z": z.round(3).tolist(),
            "gdy": gdy,
            "offset": num("m_fWaterSurfaceOffset") if lake else num("WaterOffset") + num("SplineOffsetUp"),
            "width": None if lake else num("Width", RIVER_DEFAULT_WIDTH),
        })
    return out


def _signature(files) -> str:
    import hashlib
    h = hashlib.sha1()
    for f in files:
        st = f.stat()
        h.update(f"{f}|{st.st_size}|{st.st_mtime_ns}\n".encode())
    return h.hexdigest()


def load_water(world_dir, cache_path=None, log=print) -> dict:
    """Lacs et rivières de tous les .layer de world_dir (récursif), cache JSON facultatif.

    Retourne {"ok", "bodies", "files", "cached"} ou {"ok": False, "error"}.
    """
    world_dir = Path(world_dir)
    files = sorted(world_dir.rglob("*.layer")) if world_dir.is_dir() else []
    if not files:
        return {"ok": False, "error": f"Aucun fichier .layer dans {world_dir}"}
    sig = _signature(files)
    if cache_path is not None and Path(cache_path).is_file():
        try:
            d = json.loads(Path(cache_path).read_text(encoding="utf-8"))
            if d.get("signature") == sig:
                return {"ok": True, "bodies": d["bodies"], "files": len(files), "cached": True}
        except Exception:
            pass
    bodies = []
    for f in files:
        try:
            if not _GEN.search(f.read_text(encoding="utf-8", errors="ignore")):
                continue
            bodies.extend(parse_water(f))
        except Exception as e:
            log(f"[TOPO] .layer illisible, ignoré : {f.name} ({type(e).__name__}: {e})")
    if cache_path is not None:
        cache_path = Path(cache_path)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"signature": sig, "bodies": bodies}), encoding="utf-8")
        tmp.replace(cache_path)
    return {"ok": True, "bodies": bodies, "files": len(files), "cached": False}


def _curve(P: np.ndarray, closed: bool, spline: bool, step: float = 2.0) -> np.ndarray:
    """Points le long de la forme (x, y, z) : Catmull-Rom pour une spline, segments droits sinon."""
    n = len(P)
    segs = n if closed else n - 1
    out = []
    for i in range(segs):
        p1, p2 = P[i], P[(i + 1) % n]
        L = float(np.hypot(p2[0] - p1[0], p2[2] - p1[2]))
        k = max(int(L / step), 1)
        t = np.linspace(0.0, 1.0, k, endpoint=False)[:, None]
        if spline and n > 2:
            idx = lambda j: P[j % n] if closed else P[min(max(j, 0), n - 1)]
            p0, p3 = idx(i - 1), idx(i + 2)
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t ** 2
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
        else:
            out.append(p1 + (p2 - p1) * t)
    if not closed:
        out.append(P[-1:])
    return np.vstack(out)


def water_mask(bodies, heights, terrain_size_m: float, size: int) -> np.ndarray:
    """Masque booléen (size x size, nord en haut) de l'eau des lacs et rivières sur l'image."""
    import cv2
    from scipy.ndimage import map_coordinates
    from scipy.spatial import cKDTree
    H = np.asarray(heights, dtype=np.float32)
    S = H.shape[0]
    hm = terrain_size_m / (S - 1)               # m par échantillon d'altitude
    px = terrain_size_m / size                  # m par pixel de l'image
    mask = np.zeros((size, size), bool)
    for b in bodies:
        P = np.c_[b["x"], b["y"], b["z"]]
        C = _curve(P, b["closed"], b["spline"])
        half = 0.0 if b["kind"] == "lake" else b["width"] / 2
        x0 = max(int((C[:, 0].min() - half) / px) - 2, 0)
        x1 = min(int((C[:, 0].max() + half) / px) + 3, size)
        r0 = max(int((terrain_size_m - (C[:, 2].max() + half)) / px) - 2, 0)
        r1 = min(int((terrain_size_m - (C[:, 2].min() - half)) / px) + 3, size)
        if x1 <= x0 or r1 <= r0:
            continue
        rr, cc = np.mgrid[r0:r1, x0:x1]
        wx, wz = (cc + 0.5) * px, terrain_size_m - (rr + 0.5) * px
        h = map_coordinates(H, [(S - 1) - wz / hm, wx / hm], order=1, mode="nearest")
        if b["kind"] == "lake":
            level = float(P[:, 1].min()) + b["gdy"] + b["offset"]
            shp = np.zeros(h.shape, np.uint8)
            poly = np.round(np.c_[C[:, 0] / px - x0, (terrain_size_m - C[:, 2]) / px - r0] * 4).astype(np.int32)
            cv2.fillPoly(shp, [poly], 1, shift=2)
            wet = (shp == 1) & (h < level)
        else:
            d, j = cKDTree(C[:, [0, 2]]).query(np.c_[wx.ravel(), wz.ravel()])
            d, j = d.reshape(h.shape), j.reshape(h.shape)
            lvl = C[j, 1] + b["gdy"] + b["offset"]
            wet = (d <= half) & (h < lvl)
        mask[r0:r1, x0:x1] |= wet
    return mask
