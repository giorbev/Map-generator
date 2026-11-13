# -*- coding: utf-8 -*-
"""
talus.py — Talus (ruptures de pente) du terrain pour le fond de carte militaire

Règle validée par l'équipe (13/11/2026, après prototype) : sur la grille d'altitude du terrain,
pente >= 40°, au moins 12° de plus que la pente moyenne sur 40 m (rupture, pas un versant régulièrement
raide), dénivelé >= 2 m entre le haut et le bas de la zone raide, longueur >= 20 m. Le terrain du jeu ne peut
pas être vertical (au plus une maille de dénivelé par maille) : les parois verticales sont des objets (murs
de soutènement, quais), dessinés à part.

  detecter_talus(H, side, cache_path)   → masque des talus sur la grille d'altitude ramenée à 4 m (cache .npz
                                          tant que les altitudes ne changent pas)
  dessiner_talus(img, H, masque, side, px, exclus)
                                        → trait brun le long du haut du talus, hachures vers le bas
"""

import hashlib
from pathlib import Path

import cv2
import numpy as np

PENTE, CONTRASTE, DENIV, LONG = 40.0, 12.0, 2.0, 20.0
MAILLE = 4.0                     # m : grille sur laquelle la règle a été calée (une grille plus fine y est ramenée)
TRAIT = (110, 70, 40)


def _pentes(H, cell):
    gy, gx = np.gradient(H, cell)
    return np.degrees(np.arctan(np.hypot(gx, gy))), gy, gx


def grille(H, side):
    """Altitudes ramenées à une maille d'au moins MAILLE mètres (moyenne), comme lors du calage de la règle."""
    H = np.ascontiguousarray(H, dtype=np.float32)
    if side / (H.shape[0] - 1) < MAILLE * 0.99:
        n = int(round(side / MAILLE)) + 1
        H = cv2.resize(H, (n, n), interpolation=cv2.INTER_AREA)
    return H


def detecter_talus(H, side, cache_path=None) -> np.ndarray:
    """Masque booléen des talus sur la grille(H, side) (nord en haut), side = côté du terrain en mètres."""
    H = grille(H, side)
    sig = hashlib.sha1(H.tobytes()).hexdigest() + f"|{PENTE}|{CONTRASTE}|{DENIV}|{LONG}"
    if cache_path is not None and Path(cache_path).is_file():
        try:
            with np.load(cache_path) as d:
                if str(d["signature"]) == sig:
                    return d["masque"]
        except Exception:
            pass
    cell = side / (H.shape[0] - 1)
    pente, _, _ = _pentes(H, cell)
    autour = cv2.blur(pente, (int(40 / cell) | 1,) * 2)
    cand = ((pente >= PENTE) & (pente - autour >= CONTRASTE)).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(cand, connectivity=8)
    large = cv2.dilate(lab.astype(np.float32), np.ones((3, 3), np.uint8)).astype(np.int32)
    hmax, hmin = np.full(n, -1e9), np.full(n, 1e9)
    np.maximum.at(hmax, large.ravel(), H.ravel())
    np.minimum.at(hmin, large.ravel(), H.ravel())
    longueur = np.hypot(st[:, 2], st[:, 3]) * cell
    garde = np.zeros(n, bool)
    garde[1:] = ((hmax - hmin)[1:] >= DENIV) & (longueur[1:] >= LONG)
    masque = garde[lab]
    if cache_path is not None:
        cache_path = Path(cache_path)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_path.with_name(cache_path.stem + ".tmp.npz")
        np.savez_compressed(tmp, masque=masque, signature=np.array(sig))
        tmp.replace(cache_path)
    return masque


def dessiner_talus(img, H, masque, side, px, exclus=None) -> int:
    """Dessine les talus sur img (size x size, nord en haut) ; px = mètres par pixel de l'image.

    exclus : masque (size x size) des pixels où ne pas dessiner (quais, murs : leur trait suffit).
    Renvoie le nombre de mailles de haut de talus dessinées.
    """
    H = grille(H, side)
    cell = side / (H.shape[0] - 1)
    _, gy, gx = _pentes(H, cell)
    n = img.shape[0]
    pt = lambda v: (int(round(v[0] * 16)), int(round(v[1] * 16)))
    ep = max(1, int(round(1.0 / px)))
    rs, cs = np.nonzero(masque)
    nb = 0
    R, C = masque.shape
    for r, c in zip(rs.tolist(), cs.tolist()):
        if r == 0 or c == 0 or r == R - 1 or c == C - 1:
            continue
        d = np.array([gx[r, c], gy[r, c]], np.float64)
        d /= np.linalg.norm(d) + 1e-9                         # vers le haut, (colonne, ligne)
        if masque[int(round(r + d[1])), int(round(c + d[0]))]:
            continue                                          # pas le haut du talus
        ctr = np.array([c, r]) * cell / px
        if exclus is not None:
            ci, ri = int(ctr[0]), int(ctr[1])
            if 0 <= ri < n and 0 <= ci < n and exclus[ri, ci]:
                continue
        w = 1
        while w < 4 and masque[min(max(int(round(r - d[1] * w)), 0), R - 1), min(max(int(round(c - d[0] * w)), 0), C - 1)]:
            w += 1
        haut = ctr + d * (cell / 2) / px
        t = np.array([-d[1], d[0]])
        cv2.line(img, pt(haut - t * cell / 2 / px), pt(haut + t * cell / 2 / px), TRAIT, ep, cv2.LINE_AA, shift=4)
        if (r + c) % 2 == 0:                                  # une hachure toutes les deux mailles
            cv2.line(img, pt(haut), pt(haut - d * (w * cell) / px * 0.9), TRAIT, 1, cv2.LINE_AA, shift=4)
        nb += 1
    return nb
