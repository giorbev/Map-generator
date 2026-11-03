# -*- coding: utf-8 -*-
"""
layer_vegetation.py — Position monde des arbres et buissons enregistrés dans les .layer d'un monde Workbench

Les .layer sont des fichiers texte. Un arbre y figure de deux façons :
  - placé à la main :      $grp Tree : "{GUID}…/Vegetation/Trees/t_….et" { { coords x y z … } … }
  - produit par une forêt : PolylineShapeEntity { coords … angles … { ForestGeneratorEntity : "…" {
                              { $grp Tree : "…" { { coords … } } } } } }
    les coordonnées des arbres d'un générateur sont relatives à la polyligne (position et lacet).
La position monde se calcule en composant les repères des entités parentes (coords + lacet de
« angles », deuxième valeur, en degrés). Les blocs de données (Points, ShapePoint, Data…) sont ignorés.

Contrôle (03/11, voir CONCEPTION.md, étape 15a) : 92,7 % des arbres sur un point vert de la carte
générée par Workbench (29 % pour des points tirés au hasard sur les terres).
"""

import hashlib
import math
import re
from pathlib import Path

import numpy as np

# Types de végétation
CONIFER, DECIDUOUS, BUSH = 0, 1, 2
# Essences de conifères (nom du prefab)
CONIFER_HINTS = ("picea", "pinus", "abies", "larix", "juniperus", "taxus", "pine", "spruce", "conifer")

_ENTITY = re.compile(r'^\s*(\$grp\s+)?(\w+)\s*:\s*"\{[0-9A-Fa-f]+\}([^"]+)"\s*\{\s*$')
_COORDS = re.compile(r'^\s*coords\s+(\S+)\s+(\S+)\s+(\S+)')
_ANGLES = re.compile(r'^\s*angles\s+(\S+)\s+(\S+)\s+(\S+)')


def vegetation_type(prefab: str):
    """CONIFER, DECIDUOUS, BUSH ou None (plantes, débris, autres objets)."""
    p = prefab.replace("\\", "/")
    if "/Vegetation/" not in p:
        return None
    low = p.lower()
    if "/trees/" in low or "/tree/" in low:
        if "/debris/" in low:
            return None
        return CONIFER if any(h in Path(low).stem for h in CONIFER_HINTS) else DECIDUOUS
    if "/bush" in low:
        return BUSH
    return None


def parse_layer(path) -> list:
    """Liste (x, z, type) de la végétation d'un fichier .layer."""
    out = []
    # Cadre : [type_veg_du_prefab, est_un_$grp, bloc_de_données, local(x,z) ou None, lacet, monde(x,z,lacet) ou None]
    stack = [[None, False, False, None, 0.0, (0.0, 0.0, 0.0)]]

    def world(i):
        fr = stack[i]
        if fr[5] is None:
            px, pz, pyaw = world(i - 1)
            lx, lz = fr[3] if fr[3] else (0.0, 0.0)
            a = math.radians(pyaw)
            c, s = math.cos(a), math.sin(a)
            fr[5] = (px + lx * c + lz * s, pz - lx * s + lz * c, pyaw + fr[4])
        return fr[5]

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
                m = _ENTITY.match(line)
                if parent[2]:
                    fr = [None, False, True, None, 0.0, None]                  # dans un bloc de données
                elif m:
                    fr = [vegetation_type(m.group(3)), bool(m.group(1)), False, None, 0.0, None]
                elif st == "{":
                    # Instance d'un $grp (hérite de son prefab) ou conteneur d'entités enfants
                    fr = [parent[0] if parent[1] else None, False, False, None, 0.0, None]
                elif st.startswith("$grp") or st.split()[0].endswith("Entity"):
                    fr = [None, st.startswith("$grp"), False, None, 0.0, None]  # $grp / entité sans prefab
                else:
                    fr = [None, False, True, None, 0.0, None]                  # Points, ShapePoint, Data, components…
                stack.append(fr)
                continue
            fr = stack[-1]
            if fr[2] or fr[1]:
                continue
            m = _COORDS.match(st)
            if m:
                try:
                    fr[3] = (float(m.group(1)), float(m.group(3)))
                except ValueError:
                    continue
                if fr[0] is not None:
                    px, pz, pyaw = world(len(stack) - 2)
                    a = math.radians(pyaw)
                    c, s = math.cos(a), math.sin(a)
                    lx, lz = fr[3]
                    out.append((px + lx * c + lz * s, pz - lx * s + lz * c, fr[0]))
                continue
            m = _ANGLES.match(st)
            if m:
                try:
                    fr[4] = float(m.group(2))
                except ValueError:
                    pass
    return out


def _signature(files) -> str:
    h = hashlib.sha1()
    for f in files:
        st = f.stat()
        h.update(f"{f.as_posix()}|{st.st_size}|{int(st.st_mtime)}\n".encode("utf-8"))
    return h.hexdigest()


def load_vegetation(world_dir, cache_path=None, log=print) -> dict:
    """Végétation de tous les .layer de world_dir (récursif), avec cache .npz facultatif.

    Le cache est réutilisé tant qu'aucun .layer n'a changé (liste, taille, date).
    Retourne {"ok", "x", "z", "kind", "files", "cached"} (tableaux numpy) ou {"ok": False, "error"}.
    """
    world_dir = Path(world_dir)
    files = sorted(world_dir.rglob("*.layer")) if world_dir.is_dir() else []
    if not files:
        return {"ok": False, "error": f"Aucun fichier .layer dans {world_dir}"}
    sig = _signature(files)
    if cache_path is not None and Path(cache_path).is_file():
        try:
            with np.load(cache_path) as d:
                if str(d["signature"]) == sig:
                    return {"ok": True, "x": d["x"], "z": d["z"], "kind": d["kind"], "files": len(files), "cached": True}
        except Exception:
            pass
    pts = []
    for f in files:
        try:
            pts.extend(parse_layer(f))
        except Exception as e:
            log(f"[CARTE2D] .layer illisible, ignoré : {f.name} ({type(e).__name__}: {e})")
    arr = np.array(pts, dtype=np.float32).reshape(-1, 3)
    res = {"ok": True, "x": arr[:, 0].copy(), "z": arr[:, 1].copy(), "kind": arr[:, 2].astype(np.uint8),
           "files": len(files), "cached": False}
    if cache_path is not None:
        cache_path = Path(cache_path)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_path.with_name(cache_path.stem + ".tmp.npz")
        np.savez_compressed(tmp, x=res["x"], z=res["z"], kind=res["kind"], signature=np.array(sig))
        tmp.replace(cache_path)
    return res
