# -*- coding: utf-8 -*-
"""
talus.py — Pentes fortes du terrain pour le fond de carte militaire

Ombrage gris-brun des pentes au-delà d'un seuil (proposition de l'équipe du 15/11/2026, comparée à 25, 30 et
35° sur trois secteurs : 30° par défaut). Il remplace les hachures du haut des talus (v5), qui saturaient les
vallées. L'ombre monte progressivement du seuil à seuil + RAMPE degrés, puis reste pleine ; elle assombrit aussi
les forêts et les cultures (multiplication), l'eau est posée par-dessus.

La pente est calculée sur la grille d'altitude ramenée à 4 m (moyenne), pour lisser le bruit des mailles fines.

  ombre_pentes(H, side, size, seuil) → force de l'ombre (size x size, 0..1, nord en haut)
  ombrer(img, a)                     → applique l'ombre sur img (float32, RVB)
"""

import cv2
import numpy as np

SEUILS = (25.0, 30.0, 35.0)
SEUIL = 30.0                       # degrés, défaut
RAMPE = 10.0                       # degrés entre le début de l'ombre et l'ombre pleine
MAILLE = 4.0                       # m
TEINTE = (152, 140, 120)           # couleur multipliée à pleine ombre (papier crème → gris-brun)


def grille(H, side):
    """Altitudes ramenées à une maille d'au moins MAILLE mètres (moyenne)."""
    H = np.ascontiguousarray(H, dtype=np.float32)
    if side / (H.shape[0] - 1) < MAILLE * 0.99:
        n = int(round(side / MAILLE)) + 1
        H = cv2.resize(H, (n, n), interpolation=cv2.INTER_AREA)
    return H


def pentes(H, side) -> np.ndarray:
    """Pente en degrés sur la grille(H, side)."""
    H = grille(H, side)
    cell = side / (H.shape[0] - 1)
    gy, gx = np.gradient(H, cell)
    return np.degrees(np.arctan(np.hypot(gx, gy))).astype(np.float32)


def ombre_pentes(H, side, size, seuil=SEUIL) -> np.ndarray:
    """Force de l'ombre (size x size, 0..1) : 0 sous le seuil, 1 à seuil + RAMPE et au-delà, transition douce."""
    p = cv2.resize(pentes(H, side), (size, size), interpolation=cv2.INTER_LINEAR)
    a = np.clip((p - float(seuil)) / RAMPE, 0.0, 1.0)
    return a * a * (3.0 - 2.0 * a)


def ombrer(img, a):
    """Multiplie img (float32 RVB, 0..255) par TEINTE là où l'ombre a (0..1) est forte."""
    t = np.asarray(TEINTE, np.float32) / 255.0
    img *= 1.0 - a[..., None] * (1.0 - t)
