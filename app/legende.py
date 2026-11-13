# -*- coding: utf-8 -*-
"""
legende.py — Légende du fond de carte au style militaire années 80 (cartouche)

Ne montre que ce que le fond dessine (forêts en 3 densités, cultures, eau, quais et ports, murs et clôtures
si l'option est cochée), plus une ligne sur le relief et sur ce que le jeu dessine lui-même (courbes de
niveau de la config générée par MGP, routes, bâtiments, noms). Mêmes couleurs que fond_militaire.

  dessiner_legende(murs, lang, largeur)      → image RGB (numpy) du cartouche
  placer_legende(img, cartouche, libre)      → incruste le cartouche dans le coin le plus libre (mer, vide)
"""

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import fond_militaire as fm

TEXTES = {
    "FR": {
        "titre": "LÉGENDE",
        "foret": ("Forêt clairsemée", "Forêt moyenne", "Forêt dense"),
        "champ": "Cultures",
        "eau": "Mer, lac, rivière",
        "quai": "Quai, mur de quai (dents côté eau)",
        "berge": "Berge bétonnée",
        "escalier": "Escalier, cale",
        "bollard": "Bollard",
        "bois": "Ponton en bois",
        "digue": "Digue en blocs",
        "mur": "Mur (pierre, brique, béton)",
        "palissade": "Palissade (tôle, métal, bois)",
        "cloture": "Clôture (poteaux, grillage, bois)",
        "talus": "Talus (plus de 2 m, pente forte)",
        "relief": "Relief estompé, lumière nord-ouest",
        "courbes": "Courbes : 5 / 10 / 20 / 50 m selon le zoom",
        "jeu": "Routes, bâtiments, noms : carte du jeu",
    },
    "EN": {
        "titre": "LEGEND",
        "foret": ("Sparse forest", "Medium forest", "Dense forest"),
        "champ": "Fields",
        "eau": "Sea, lake, river",
        "quai": "Quay, quay wall (teeth on water side)",
        "berge": "Concrete bank",
        "escalier": "Stairs, slipway",
        "bollard": "Bollard",
        "bois": "Wooden jetty",
        "digue": "Breakwater",
        "mur": "Wall (stone, brick, concrete)",
        "palissade": "Solid fence (tin, metal, wood)",
        "cloture": "Fence (poles, mesh, wood)",
        "talus": "Bank (over 2 m, steep)",
        "relief": "Hillshade, light from north-west",
        "courbes": "Contours: 5 / 10 / 20 / 50 m by zoom",
        "jeu": "Roads, buildings, names: game map",
    },
}
CADRE = (40, 36, 30)


def _police(taille):
    for nom in ("bahnschrift.ttf", "segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(nom, taille)
        except OSError:
            continue
    return ImageFont.load_default(size=taille)


def dessiner_legende(murs: bool = False, lang: str = "FR", largeur: int = 620, talus: bool = False) -> np.ndarray:
    """Cartouche de légende (RGB uint8), largeur en pixels ; la hauteur suit le nombre de lignes."""
    T = TEXTES.get(str(lang).upper(), TEXTES["FR"])
    k = largeur / 620.0
    pas, marge, sw, sh = int(46 * k), int(24 * k), int(64 * k), int(30 * k)
    f_titre, f_txt, f_note = _police(int(30 * k)), _police(int(23 * k)), _police(int(20 * k))
    lignes = [("foret", 0), ("foret", 1), ("foret", 2), ("champ", None), ("eau", None), ("quai", None), ("berge", None),
              ("escalier", None), ("bollard", None), ("bois", None), ("digue", None)]
    if murs:
        lignes += [("mur", None), ("palissade", None), ("cloture", None)]
    if talus:
        lignes += [("talus", None)]
    notes = [T["relief"], T["courbes"], T["jeu"]]
    h = marge * 2 + int(48 * k) + pas * len(lignes) + int(14 * k) + int(30 * k) * len(notes)
    im = Image.new("RGB", (largeur, h), fm.PAPIER)
    d = ImageDraw.Draw(im)
    ep = max(2, int(3 * k))
    d.rectangle([0, 0, largeur - 1, h - 1], outline=CADRE, width=ep)
    d.rectangle([ep * 2, ep * 2, largeur - 1 - ep * 2, h - 1 - ep * 2], outline=CADRE, width=max(1, ep // 2))
    d.text((marge, marge), T["titre"], fill=CADRE, font=f_titre)
    y = marge + int(48 * k)
    x0, x1 = marge, marge + sw
    for cle, i in lignes:
        ym, y0, y1 = y + pas // 2, y + (pas - sh) // 2, y + (pas + sh) // 2
        if cle == "foret":
            d.rectangle([x0, y0, x1, y1], fill=(fm.FORET_CLAIR, fm.FORET, fm.FORET_DENSE)[i], outline=fm.FORET_BORD)
            txt = T["foret"][i]
        elif cle == "champ":
            d.rectangle([x0, y0, x1, y1], fill=fm.CHAMP, outline=fm.CHAMP_BORD)
            txt = T["champ"]
        elif cle == "eau":
            d.rectangle([x0, y0, x1, y1], fill=fm.EAU, outline=fm.EAU_BORD, width=max(1, int(2 * k)))
            txt = T["eau"]
        elif cle == "quai":
            d.rectangle([x0, y0, x1, ym], fill=fm.QUAI)
            d.rectangle([x0, ym, x1, y1], fill=fm.EAU)
            d.line([x0, ym, x1, ym], fill=fm.QUAI_TRAIT, width=max(2, int(3 * k)))
            for xx in range(x0 + int(4 * k), x1, max(4, int(9 * k))):
                d.line([xx, ym, xx, ym + int(7 * k)], fill=fm.QUAI_TRAIT, width=max(1, int(1.5 * k)))
            txt = T["quai"]
        elif cle == "berge":
            d.rectangle([x0, y0, x1, ym], fill=fm.PAPIER)
            d.rectangle([x0, ym, x1, y1], fill=fm.EAU)
            d.line([x0, ym, x1, ym], fill=fm.QUAI_TRAIT, width=max(3, int(4 * k)))
            txt = T["berge"]
        elif cle == "escalier":
            d.rectangle([x0, y0, x1, ym], fill=fm.QUAI)
            d.rectangle([x0, ym, x1, y1], fill=fm.EAU)
            d.line([x0, ym, x1, ym], fill=fm.QUAI_TRAIT, width=max(2, int(3 * k)))
            ex0, ex1 = x0 + sw // 3, x0 + 2 * sw // 3
            d.rectangle([ex0, y0 + int(4 * k), ex1, y1 - int(2 * k)], fill=fm.ESCALIER, outline=(90, 90, 90))
            for f in (0.35, 0.55, 0.75):
                yy = int(y0 + (y1 - y0) * f)
                d.line([ex0, yy, ex1, yy], fill=(90, 90, 90), width=1)
            txt = T["escalier"]
        elif cle == "bollard":
            d.rectangle([x0, y0, x1, y1], fill=fm.QUAI)
            r = max(3, int(5 * k))
            d.ellipse([x0 + sw // 2 - r, ym - r, x0 + sw // 2 + r, ym + r], fill=fm.QUAI_TRAIT)
            txt = T["bollard"]
        elif cle == "bois":
            d.rectangle([x0, y0, x1, y1], fill=fm.EAU)
            d.rectangle([x0 + int(6 * k), ym - int(6 * k), x1 - int(6 * k), ym + int(6 * k)], fill=fm.BOIS, outline=fm.BOIS_BORD)
            txt = T["bois"]
        elif cle == "digue":
            d.rectangle([x0, y0, x1, y1], fill=fm.EAU)
            d.rectangle([x0, y0 + int(6 * k), x1, y1 - int(6 * k)], fill=fm.DIGUE)
            txt = T["digue"]
        elif cle == "talus":
            from talus import TRAIT
            d.line([x0, y0 + int(6 * k), x1, y0 + int(6 * k)], fill=TRAIT, width=max(2, int(2.5 * k)))
            for xx in range(x0 + int(4 * k), x1, max(5, int(10 * k))):
                d.line([xx, y0 + int(6 * k), xx, y1 - int(4 * k)], fill=TRAIT, width=max(1, int(1.5 * k)))
            txt = T["talus"]
        else:                                                    # murs et clôtures
            col = fm.MURS[cle]
            if cle == "cloture":
                pd = max(6, int(12 * k))
                for xx in range(x0, x1, pd):
                    d.line([xx, ym, min(xx + int(pd * 0.6), x1), ym], fill=col, width=max(2, int(2.5 * k)))
            else:
                d.line([x0, ym, x1, ym], fill=col, width=max(2, int((3 if cle == "mur" else 2.5) * k)))
            txt = T[cle]
        bb = d.textbbox((0, 0), txt, font=f_txt)
        d.text((x1 + int(18 * k), ym - (bb[3] + bb[1]) // 2), txt, fill=CADRE, font=f_txt)
        y += pas
    y += int(14 * k)
    d.line([marge, y - int(7 * k), largeur - marge, y - int(7 * k)], fill=CADRE, width=1)
    for n in notes:
        d.text((marge, y), n, fill=CADRE, font=f_note)
        y += int(30 * k)
    return np.asarray(im)


def placer_legende(img: np.ndarray, cartouche: np.ndarray, libre: np.ndarray, marge: int = None):
    """Incruste le cartouche là où libre (masque booléen : mer ou vide) couvre le plus sa surface.

    Toutes les positions sont essayées (pas de 1/64 de l'image, table de sommes cumulées) ; à part libre égale
    (à 0,5 % près), la plus proche d'un bord de l'image l'emporte. Renvoie (position, part_libre) ; position
    est un coin (« NO », « NE », « SO », « SE ») si le cartouche y touche, sinon « x,y » en pixels.
    """
    n = img.shape[0]
    h, w = cartouche.shape[:2]
    m = marge if marge is not None else max(8, n // 200)
    S = np.pad(np.cumsum(np.cumsum(libre.astype(np.float64), 0), 1), ((1, 0), (1, 0)))
    pas = max(1, n // 64)
    ys = sorted(set(list(range(m, n - h - m + 1, pas)) + [n - h - m]))
    xs = sorted(set(list(range(m, n - w - m + 1, pas)) + [n - w - m]))
    best = None
    for y in ys:
        for x in xs:
            part = (S[y + h, x + w] - S[y, x + w] - S[y + h, x] + S[y, x]) / (h * w)
            bord = min(y - m, x - m, n - h - m - y, n - w - m - x)
            cle = (round(part, 3) // 0.005, -bord)
            if best is None or cle > best[0]:
                best = (cle, y, x, part)
    _, y, x, part = best
    img[y:y + h, x:x + w] = cartouche
    coins = {(m, m): "NO", (m, n - w - m): "NE", (n - h - m, m): "SO", (n - h - m, n - w - m): "SE"}
    return coins.get((y, x), f"{x},{y}"), round(part * 100, 1)
