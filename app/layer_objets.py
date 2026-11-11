# -*- coding: utf-8 -*-
"""
layer_objets.py — Routes (revêtement) et bâtiments (catégorie) enregistrés dans les .layer d'un monde Workbench

Même lecture des repères que layer_vegetation.parse_layer (coords + lacet des entités parentes).

  routes     points de la spline parente (bloc Points / ShapePoint / Position) d'un générateur de route
             (RoadGeneratorEntity ou SCR_RoadGeneratorEntity) dont le prefab est sous WEGenerators/Roads/ ;
             revêtement d'après le dossier du prefab : Asphalt → asphalte, Concrete et Cobblestone → béton,
             le reste (Dirt, Trail, Gravel, Forest, Coal…) → terre. Les décals (piste, parterres…) sont ignorés.
  bâtiments  position des prefabs Prefabs/Structures : Houses, Cultural, Commercial, Civilian, Ruins → maison ;
             Industrial (sauf conteneurs et tuyauterie), Military, Agriculture → industriel ; le reste ignoré.

Sert au fond TOPO « satellite réaliste » (fond_realiste.py) : la forme des routes et des bâtiments vient du
.topo, le revêtement et la catégorie de l'objet des .layer le plus proche.
"""

import math
import re
from pathlib import Path

import numpy as np

from layer_vegetation import _signature

ROUTE_ASPHALTE, ROUTE_BETON, ROUTE_TERRE = 0, 1, 2
BAT_MAISON, BAT_INDUSTRIEL = 0, 1

_ENTITY = re.compile(r'^\s*(\$grp\s+)?(\w+)(?:\s+\w+)?\s*:\s*"\{[0-9A-Fa-f]+\}([^"]+)"\s*\{\s*$')
_COORDS = re.compile(r'^\s*coords\s+(\S+)\s+(\S+)\s+(\S+)')
_ANGLES = re.compile(r'^\s*angles\s+(\S+)\s+(\S+)\s+(\S+)')
_POS = re.compile(r'^\s*Position\s+(\S+)\s+(\S+)\s+(\S+)')

_MAISONS = ("houses/", "cultural/", "commercial/", "civilian/", "ruins/")
_INDUSTRIELS = ("industrial/", "military/", "agriculture/")
_IGNORES = ("industrial/containers", "industrial/piping")


def type_route(prefab: str):
    """ROUTE_ASPHALTE, ROUTE_BETON, ROUTE_TERRE ou None (pas une route)."""
    p = prefab.replace("\\", "/").lower()
    if "/roads/" not in p:
        return None
    if "/asphalt/" in p:
        return ROUTE_ASPHALTE
    if "/concrete/" in p or "/cobblestone/" in p:
        return ROUTE_BETON
    return ROUTE_TERRE


def type_batiment(prefab: str):
    """BAT_MAISON, BAT_INDUSTRIEL ou None (murs, panneaux, objets…)."""
    p = prefab.replace("\\", "/").lower()
    i = p.find("/structures/")
    if i < 0:
        return None
    s = p[i + len("/structures/"):]
    if s.startswith(_IGNORES):
        return None
    if s.startswith(_MAISONS):
        return BAT_MAISON
    if s.startswith(_INDUSTRIELS):
        return BAT_INDUSTRIEL
    return None


def _frame(**kw):
    fr = dict(code=None, grp=False, data=True, local=None, yaw=0.0, world=None, kind=None, pts=None)
    fr.update(kw)
    return fr


def parse_layer(path):
    """(routes [(type, [(x, z), …])], bâtiments [(x, z, type)]) d'un fichier .layer, coordonnées monde."""
    routes, bats = [], []
    stack = [_frame(data=False, world=(0.0, 0.0, 0.0))]

    def world(i):
        fr = stack[i]
        if fr["world"] is None:
            px, pz, pyaw = world(i - 1)
            lx, lz = fr["local"] or (0.0, 0.0)
            a = math.radians(pyaw)
            c, s = math.cos(a), math.sin(a)
            fr["world"] = (px + lx * c + lz * s, pz - lx * s + lz * c, pyaw + fr["yaw"])
        return fr["world"]

    def to_world(i, lx, lz):
        px, pz, yaw = world(i)
        a = math.radians(yaw)
        c, s = math.cos(a), math.sin(a)
        return px + lx * c + lz * s, pz - lx * s + lz * c

    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            st = line.strip()
            if not st:
                continue
            if st == "}":
                if len(stack) > 1:
                    stack.pop()
                continue
            if st.endswith("{"):
                parent = stack[-1]
                new = _frame()
                if parent["kind"] == "points":
                    new["kind"] = "sp"                      # ShapePoint d'une spline
                elif parent["data"]:
                    pass                                    # dans un bloc de données
                elif st.startswith("Points"):
                    new["kind"] = "points"
                    parent["pts"] = []
                else:
                    m = _ENTITY.match(line)
                    if m:
                        new.update(data=False, grp=bool(m.group(1)))
                        if m.group(2).endswith("RoadGeneratorEntity"):
                            t = type_route(m.group(3))
                            if t is not None:
                                for j in range(len(stack) - 1, -1, -1):     # spline parente
                                    if stack[j]["pts"]:
                                        routes.append((t, [to_world(j, a, b) for a, b in stack[j]["pts"]]))
                                        break
                        else:
                            new["code"] = type_batiment(m.group(3))
                    elif st == "{":
                        # Instance d'un $grp (hérite de son prefab) ou conteneur d'entités enfants
                        new.update(data=False, code=parent["code"] if parent["grp"] else None)
                    elif st.startswith("$grp") or st.split()[0].endswith("Entity"):
                        new.update(data=False, grp=st.startswith("$grp"))
                stack.append(new)
                continue
            fr = stack[-1]
            if fr["kind"] == "sp":
                m = _POS.match(st)
                if m:
                    try:
                        stack[-3]["pts"].append((float(m.group(1)), float(m.group(3))))   # sp → Points → entité
                    except ValueError:
                        pass
                continue
            if fr["data"] or fr["grp"]:
                continue
            m = _COORDS.match(st)
            if m:
                try:
                    fr["local"] = (float(m.group(1)), float(m.group(3)))
                except ValueError:
                    continue
                if fr["code"] is not None:
                    x, z = to_world(len(stack) - 2, *fr["local"])
                    bats.append((x, z, fr["code"]))
                continue
            m = _ANGLES.match(st)
            if m:
                try:
                    fr["yaw"] = float(m.group(2))
                except ValueError:
                    pass
    return routes, bats


def load_objets(world_dir, cache_path=None, log=print) -> dict:
    """Routes et bâtiments de tous les .layer de world_dir (récursif), avec cache .npz facultatif.

    Le cache est réutilisé tant qu'aucun .layer n'a changé (liste, taille, date).
    Retourne {"ok", "route_type" (n,), "route_off" (n + 1,), "route_xz" (m, 2), "bat_xz" (k, 2), "bat_type" (k,),
    "files", "cached"} (coordonnées monde ; points de la route i = route_xz[route_off[i]:route_off[i + 1]])
    ou {"ok": False, "error"}.
    """
    world_dir = Path(world_dir)
    files = sorted(world_dir.rglob("*.layer")) if world_dir.is_dir() else []
    if not files:
        return {"ok": False, "error": f"Aucun fichier .layer dans {world_dir}"}
    sig = _signature(files)
    keys = ("route_type", "route_off", "route_xz", "bat_xz", "bat_type")
    if cache_path is not None and Path(cache_path).is_file():
        try:
            with np.load(cache_path) as d:
                if str(d["signature"]) == sig:
                    return {"ok": True, **{k: d[k] for k in keys}, "files": len(files), "cached": True}
        except Exception:
            pass
    routes, bats = [], []
    for f in files:
        try:
            r, b = parse_layer(f)
            routes += [x for x in r if len(x[1]) >= 2]
            bats += b
        except Exception as e:
            log(f"[TOPO] .layer illisible, ignoré : {f.name} ({type(e).__name__}: {e})")
    res = {
        "ok": True,
        "route_type": np.array([t for t, _ in routes], np.uint8),
        "route_off": np.concatenate([[0], np.cumsum([len(p) for _, p in routes])]).astype(np.int64),
        "route_xz": np.array([q for _, p in routes for q in p], np.float32).reshape(-1, 2),
        "bat_xz": np.array([(x, z) for x, z, _ in bats], np.float32).reshape(-1, 2),
        "bat_type": np.array([t for *_, t in bats], np.uint8),
        "files": len(files), "cached": False,
    }
    if cache_path is not None:
        cache_path = Path(cache_path)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_path.with_name(cache_path.stem + ".tmp.npz")
        np.savez_compressed(tmp, signature=np.array(sig), **{k: res[k] for k in keys})
        tmp.replace(cache_path)
    return res
