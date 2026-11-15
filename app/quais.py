# -*- coding: utf-8 -*-
"""
quais.py — Objets de port des .layer sur les fonds de carte TOPO : emprises en pixels, eau sous les quais

Commun aux trois styles (militaire, satellite, satellite réaliste). Le terrain continue souvent sous un quai,
la dalle débordant au-dessus de l'eau : l'eau calculée d'après le terrain passe alors sous le quai. On la rend
à la terre (règle mise au point sur le fond militaire, 11/2026) :

  sous les quais    pixels couverts par une dalle, un mur de quai, un escalier ou une digue
  liseré            bandes d'eau de moins de 9 m à moins de 6 m d'un quai (eau coincée derrière lui)
  flaques           restes de moins de 200 m² à moins de 12 m d'un quai

Les murs de soutènement en béton (genre « soutenement » de layer_port.load_port) deviennent des berges
bétonnées (« berge ») s'ils sont à moins de 8 m de l'eau, et sont ignorés sinon.

  emprises(port, eau, side, size)  → (P, G) : emprises (n, 4, 2) en pixels (colonne, ligne) et genres
  retirer_eau(eau, P, G, px)       → masque d'eau sans l'eau sous les quais (eau modifiée sur place)
"""

import cv2
import numpy as np

SOL = ("dalle", "mur", "escalier", "digue")        # genres qui recouvrent l'eau


def disque(rayon_m, px):
    """Élément structurant circulaire de rayon_m mètres pour une image à px mètres par pixel."""
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (max(int(rayon_m / px), 1) * 2 + 1,) * 2)


def emprises(port, eau, side, size):
    """Emprises en pixels des objets de port dans l'image, et leurs genres (soutènements classés berge ou retirés).

    port : layer_port.load_port ; eau : masque d'eau (size x size, uint8, nord en haut) ; side : côté du terrain (m).
    """
    px = side / size
    P = np.asarray(port["poly"], np.float64) / px
    P[..., 1] = side / px - P[..., 1]                       # z monde → ligne d'image
    G = np.asarray(port["genre"]).astype("<U12")
    dedans = (P[..., 0].max(1) >= 0) & (P[..., 0].min(1) < size) & (P[..., 1].max(1) >= 0) & (P[..., 1].min(1) < size)
    # murs de soutènement : quais de canal s'ils touchent l'eau (à moins de 8 m), ignorés sinon
    sout = G == "soutenement"
    if sout.any():
        pres_eau = cv2.dilate(eau, disque(8, px)).astype(bool)
        c = np.clip(P[sout].mean(1).astype(int), 0, size - 1)
        garde = pres_eau[c[:, 1], c[:, 0]]
        idx = np.nonzero(sout)[0]
        dedans[idx[~garde]] = False
        G[idx[garde]] = "berge"
    return P[dedans], G[dedans]


def masque_sol(P, G, size):
    """Masque (uint8) des pixels couverts par les dalles, murs de quai, escaliers et digues."""
    sol = np.zeros((size, size), np.uint8)
    for q, g in zip(P, G):
        if g in SOL:
            cv2.fillPoly(sol, [np.round(q * 4).astype(np.int32)], 1, shift=2)
    return sol


def retirer_eau(eau, P, G, px):
    """Rend à la terre l'eau sous les quais, le liseré derrière eux et les petites flaques voisines.

    eau : masque uint8 (size x size), modifié sur place et renvoyé.
    """
    sol = masque_sol(P, G, eau.shape[0])
    if not sol.any():
        return eau
    eau[sol == 1] = 0
    ouvert = cv2.morphologyEx(eau, cv2.MORPH_OPEN, disque(4.5, px))
    eau[(eau == 1) & (cv2.dilate(sol, disque(6, px)) == 1) & (ouvert == 0)] = 0
    # restes : flaques de moins de 200 m² à moins de 12 m d'un quai
    _, lab, st, _ = cv2.connectedComponentsWithStats(eau)
    pres = np.unique(lab[(cv2.dilate(sol, disque(12, px)) == 1) & (eau == 1)])
    petites = [i for i in pres if i and st[i, 4] * px * px < 200]
    if petites:
        eau[np.isin(lab, petites)] = 0
    return eau
