# -*- coding: utf-8 -*-
"""
layer_port.py — Objets de port (quais, murs, escaliers, cales, bollards, pontons, digues) des .layer d'un monde

Chaque objet est rendu par son emprise au sol : boîte du modèle du jeu (port_prefabs.py, généré par
tools/build_port_prefabs.py) tournée du lacet de l'objet. Un prefab de l'addon inconnu de la table est
résolu par son prefab parent (héritage .et dans l'addon). Même lecture des repères que layer_vegetation
(coords + lacet des entités parentes) ; le lacet de l'objet est pris à la fermeture de son bloc.

Genres : « dalle » (quai en béton), « mur » (mur de quai), « escalier » (escaliers, cales, échelles),
« bollard », « bois » (pontons en bois), « digue » (blocs de pierre). Les défenses (pneus, planches),
cordes, bouées et cabanes sont ignorées.
"""

import math
import re
from pathlib import Path

import numpy as np

from layer_vegetation import _signature

_ENTITY = re.compile(r'^\s*(\$grp\s+)?(\w+)(?:\s+\w+)?\s*:\s*"\{[0-9A-Fa-f]+\}([^"]+)"\s*\{\s*$')
_COORDS = re.compile(r'^\s*coords\s+(\S+)\s+(\S+)\s+(\S+)')
_ANGLES = re.compile(r'^\s*angles\s+(\S+)\s+(\S+)\s+(\S+)')
_PARENT = re.compile(r'^\s*\w+\s*:\s*"\{[0-9A-Fa-f]+\}([^"]+\.et)"')

GENRES = ("dalle", "mur", "escalier", "bollard", "bois", "digue")


def genre_port(stem: str):
    """Genre d'un prefab de port d'après son nom, ou None (défenses, cordes, bouées, cabanes…)."""
    s = stem.lower()
    if "bollard" in s:
        return "bollard"
    if "stairs" in s or "slipway" in s or "ladder" in s:
        return None if "cradle" in s else "escalier"
    if "breakwater" in s:
        return "digue"
    if "wall" in s and "pierconcrete" in s:
        return "mur"
    if "pierwooden" in s:
        return None if "pole" in s else "bois"
    if "pierconcrete" in s or re.fullmatch(r"pier_0\d.*", s):
        return "dalle"
    return None


def _table():
    from port_prefabs import PORT_PREFABS
    return PORT_PREFABS


def _addon_root(world_dir: Path) -> Path:
    root = world_dir
    while root.parent != root and not (root / "addon.gproj").is_file():
        root = root.parent
    return root if (root / "addon.gproj").is_file() else world_dir


def _resoudre(prefab: str, root: Path, table: dict, cache: dict):
    """Clé de la table pour un chemin de prefab (nom, sinon prefab parent dans l'addon), ou None."""
    if prefab in cache:
        return cache[prefab]
    stem = Path(prefab).stem
    res = None
    if stem in table:
        res = stem
    elif genre_port(stem) is not None or "naval" in prefab.lower():
        p, vus = root / prefab, 0
        while p.is_file() and vus < 6:
            m = _PARENT.match(p.read_text(encoding="utf-8", errors="ignore"))
            if not m:
                break
            if Path(m.group(1)).stem in table:
                res = Path(m.group(1)).stem
                break
            p, vus = root / m.group(1), vus + 1
    cache[prefab] = res
    return res


def parse_layer(path, root: Path, table: dict, cache: dict) -> list:
    """[(clé de table, x, z, lacet)] des objets de port d'un fichier .layer, coordonnées monde."""
    out = []
    stack = [dict(key=None, grp=False, data=False, local=None, yaw=0.0, world=(0.0, 0.0, 0.0))]

    def world(i):
        fr = stack[i]
        if fr["world"] is None:
            px, pz, pyaw = world(i - 1)
            lx, lz = fr["local"] or (0.0, 0.0)
            a = math.radians(pyaw)
            c, s = math.cos(a), math.sin(a)
            fr["world"] = (px + lx * c + lz * s, pz - lx * s + lz * c, pyaw + fr["yaw"])
        return fr["world"]

    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            st = line.strip()
            if not st:
                continue
            if st == "}":
                if len(stack) > 1:
                    fr = stack[-1]
                    if fr["key"] and fr["local"] is not None and not fr["grp"]:
                        x, z, yaw = world(len(stack) - 1)
                        out.append((fr["key"], x, z, yaw))
                    stack.pop()
                continue
            if st.endswith("{"):
                parent = stack[-1]
                new = dict(key=None, grp=False, data=True, local=None, yaw=0.0, world=None)
                if not parent["data"]:
                    m = _ENTITY.match(line)
                    if m:
                        new.update(data=False, grp=bool(m.group(1)), key=_resoudre(m.group(3), root, table, cache))
                    elif st == "{":
                        # Instance d'un $grp (hérite de son prefab) ou conteneur d'entités enfants
                        new.update(data=False, key=parent["key"] if parent["grp"] else None)
                    elif st.startswith("$grp") or st.split()[0].endswith("Entity"):
                        new.update(data=False, grp=st.startswith("$grp"))
                stack.append(new)
                continue
            fr = stack[-1]
            if fr["data"] or fr["grp"]:
                continue
            m = _COORDS.match(st)
            if m:
                try:
                    fr["local"] = (float(m.group(1)), float(m.group(3)))
                except ValueError:
                    pass
                continue
            m = _ANGLES.match(st)
            if m:
                try:
                    fr["yaw"] = float(m.group(2))
                except ValueError:
                    pass
    return out


def emprise(key: str, x: float, z: float, yaw: float, table=None) -> np.ndarray:
    """Coins (4, 2) de l'emprise au sol d'un objet, coordonnées monde (x, z), dans l'ordre du contour."""
    _, x0, z0, x1, z1 = (table or _table())[key]
    a = math.radians(yaw)
    c, s = math.cos(a), math.sin(a)
    return np.array([(x + lx * c + lz * s, z - lx * s + lz * c) for lx, lz in ((x0, z0), (x1, z0), (x1, z1), (x0, z1))])


def load_port(world_dir, cache_path=None, log=print) -> dict:
    """Objets de port de tous les .layer de world_dir (récursif), avec cache .npz facultatif.

    Retourne {"ok", "genre" (n,) str, "poly" (n, 4, 2) coordonnées monde, "files", "cached"} ou {"ok": False, "error"}.
    """
    world_dir = Path(world_dir)
    files = sorted(world_dir.rglob("*.layer")) if world_dir.is_dir() else []
    if not files:
        return {"ok": False, "error": f"Aucun fichier .layer dans {world_dir}"}
    table = _table()
    sig = _signature(files) + f"|{len(table)}"
    if cache_path is not None and Path(cache_path).is_file():
        try:
            with np.load(cache_path) as d:
                if str(d["signature"]) == sig:
                    return {"ok": True, "genre": d["genre"], "poly": d["poly"], "files": len(files), "cached": True}
        except Exception:
            pass
    root, cache, objs = _addon_root(world_dir), {}, []
    for f in files:
        try:
            objs += parse_layer(f, root, table, cache)
        except Exception as e:
            log(f"[TOPO] .layer illisible, ignoré : {f.name} ({type(e).__name__}: {e})")
    genre = np.array([table[k][0] for k, *_ in objs], dtype="<U8")
    poly = np.array([emprise(k, x, z, yaw, table) for k, x, z, yaw in objs], np.float64).reshape(-1, 4, 2)
    res = {"ok": True, "genre": genre, "poly": poly, "files": len(files), "cached": False}
    if cache_path is not None:
        cache_path = Path(cache_path)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_path.with_name(cache_path.stem + ".tmp.npz")
        np.savez_compressed(tmp, genre=genre, poly=poly, signature=np.array(sig))
        tmp.replace(cache_path)
    return res
