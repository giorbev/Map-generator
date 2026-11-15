# -*- coding: utf-8 -*-
"""
biomes_climat.py — Biomes climatiques : masques posés par des règles propres à chaque biome (PROTOTYPE, 15/11/2026)

Idée (CONCEPTION.md, biomes dans Generation) : le biome ne se contente plus de changer les textures des mêmes
masques ; il définit ses propres classes de sol génériques (sable, reg, éboulis, neige…) et leurs règles de pose
d'après le terrain. Les masques sont calculés directement en niveaux de gris, puis passent dans la normalisation
par soustraction du pipeline v5 (un pixel = une classe, ordre = priorité). L'aperçu colore les classes avec des
couleurs génériques sur le relief ombré : aucune texture n'est nécessaire. Le choix d'un .emat par classe vient
ensuite (tableau dans Generation).

Signaux du terrain (cache terrain_data.npz de terrain_analysis, ramené à la taille de travail) :
  altitude (m), altitude_rel (0 = mer, 1 = 99e centile des terres), pente (degrés),
  soleil (-1 versant nord raide … +1 versant sud raide), tpi_local / tpi_macro (-1 creux … +1 bosse),
  ecoulement (rang 0..1 parmi les terres, d'après l'accumulation des eaux), cote (m de la mer)

Règles (data/biomes_climat/<biome>.json) : liste ordonnée {classe, si: {signal: [a, b, c, d]}, seuil, bruit} ;
trapèze 0 sous a, 1 de b à c, 0 au-delà de d (null = pas de borne) ; conditions multipliées ; bruit lent ajouté
au score pour des limites naturelles ; lissage_m (général ou par règle) floute le score avant le seuil ; « defaut » prend les terres restantes.

  charger_biome(nom)                        → dict du biome
  signaux(cache_npz, taille)                → dict des signaux (taille x taille, nord en haut)
  masques_biome(sig, biome)                 → (ordre des classes, {classe: masque 0..1}) après normalisation
  apercu(sig, ordre, masques, chemin)       → PNG en couleurs génériques sur relief ombré
  bilan(ordre, masques, bloc_px)            → % par classe et textures par bloc
  suggestion(classe, textures)              → texture du projet proposée pour une classe
  par_texture(ordre, masques, association)  → masques regroupés par texture (fusion des classes)
  limiter_budget(ordre, masques, budget, bloc_px) → au plus budget textures par bloc (corrige les masques)
  exporter_masques_16(ordre, masques, dossier)    → PNG 16 bits par texture
"""

import json
import sys
from pathlib import Path

import cv2
import numpy as np

# Règles des biomes : data/biomes_climat/ du dépôt, ou du dossier de l'exe (PyInstaller)
_RACINE = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
DOSSIER = _RACINE / "data" / "biomes_climat"

# Classes génériques : libellé, couleur d'aperçu, texture vanilla la plus proche (proposition, à choisir ensuite)
CLASSES = {
    "mer":           ("Mer, fond marin",          (64, 104, 132),  "SeaBed_01"),
    "plage":         ("Plage, sable côtier",      (228, 210, 168), "Pebbles_01"),
    "sable":         ("Sable, dunes",             (234, 202, 142), "Dirt_02"),
    "reg":           ("Reg (plaine de graviers)", (172, 152, 128), "Pebbles_02"),
    "hamada":        ("Hamada (plateau rocheux)", (128, 108, 92),  "Debris_Rock_01_V2"),
    "sol_nu":        ("Sol nu, argile sèche",     (212, 164, 112), "Dirt_01"),
    "lit_oued":      ("Lit d'oued (graviers)",    (168, 160, 146), "Pebbles_02b"),
    "oasis":         ("Oasis, végétation",        (92, 128, 60),   "Grass_01_aut"),
    "eboulis":       ("Éboulis",                  (152, 136, 116), "Debris_Rock_01"),
    "roche_exposee": ("Roche nue au soleil",      (170, 124, 88),  "Rock_02"),
    "falaise":       ("Falaise, paroi",           (108, 94, 84),   "Rock_01"),
    "herbe_seche":   ("Herbe sèche",              (176, 168, 96),  "Grass_01_aut"),
    "prairie":       ("Prairie",                  (110, 150, 70),  "Grass_02"),
    "foret":         ("Forêt",                    (52, 92, 46),    "ForestDeciduous_01_Base"),
    "neige":         ("Neige",                    (240, 244, 248), ""),
    "neve":          ("Névé, neige sale",         (214, 220, 226), ""),
    "glace":         ("Glace",                    (190, 216, 232), ""),
}
SIGNAUX = ("altitude", "altitude_rel", "pente", "soleil", "tpi_local", "tpi_macro", "ecoulement", "cote")


def charger_biome(nom: str) -> dict:
    with open(DOSSIER / f"{nom}.json", encoding="utf-8") as f:
        return json.load(f)


def trapeze(x, a, b, c, d):
    """0 sous a, monte jusqu'à 1 en b, 1 jusqu'à c, redescend à 0 en d ; None = pas de borne."""
    y = np.ones_like(x, dtype=np.float32)
    if a is not None and b is not None:
        y = np.minimum(y, np.clip((x - a) / max(b - a, 1e-6), 0, 1))
    if c is not None and d is not None:
        y = np.minimum(y, np.clip((d - x) / max(d - c, 1e-6), 0, 1))
    return y


def bruit_lent(taille, graine, echelle_px):
    """Bruit fractal lent dans [-1, 1] (3 octaves), même résultat à chaque appel pour une graine donnée."""
    rng = np.random.default_rng(graine)
    n = np.zeros((taille, taille), np.float32)
    amp, tot = 1.0, 0.0
    for k in range(3):
        s = max(4, int(taille / (echelle_px / 2 ** k)))
        g = rng.standard_normal((s, s)).astype(np.float32)
        n += amp * cv2.resize(g, (taille, taille), interpolation=cv2.INTER_CUBIC)
        tot += amp
        amp *= 0.5
    n /= tot
    return np.clip(n / (np.abs(n).max() + 1e-6), -1, 1)


def signaux(cache_npz, taille=4096) -> dict:
    """Signaux du terrain à taille x taille d'après le cache terrain_data.npz (nord en haut)."""
    area = lambda a: cv2.resize(np.nan_to_num(np.asarray(a, np.float32)), (taille, taille), interpolation=cv2.INTER_AREA)
    with np.load(cache_npz) as d:
        cote_m = float(d["heightmap"].shape[0] - 1)            # maille de 1 m dans le cache (cellsize)
        H = area(d["heightmap"])
        Hs = area(d["heightmap_smooth"])
        tpi_l, tpi_m = area(d["tpi_local"]), area(d["tpi_macro"])
        flow = area(np.log1p(np.nan_to_num(d["flow"]) * 1e6))
        cote = area(d["distance_cote"])
    terre = H > 0
    px = cote_m / taille
    # pente sur l'altitude lissée sur ~4 m : efface les paliers de la heightmap sans adoucir les falaises
    gy, gx = np.gradient(cv2.GaussianBlur(H, (0, 0), max(4.0 / px, 0.5)), px)
    pente = np.degrees(np.arctan(np.hypot(gx, gy))).astype(np.float32)
    gy, gx = np.gradient(Hs, px)
    g = np.hypot(gx, gy)
    sud = -gy / (g + 1e-9)                                   # +1 quand le terrain descend vers le sud
    soleil = np.sin(np.arctan(g)) * sud
    p99 = float(np.percentile(H[terre], 99)) if terre.any() else 1.0
    ecoul = np.zeros_like(H)
    if terre.any():
        v = flow[terre]
        rang = np.empty(v.size, np.float32)
        rang[np.argsort(v, kind="stable")] = np.linspace(0, 1, v.size, dtype=np.float32)
        ecoul[terre] = rang
    return {"altitude": H, "altitude_rel": np.clip(H / max(p99, 1e-6), 0, 1.5), "pente": pente, "soleil": soleil,
            "tpi_local": tpi_l, "tpi_macro": tpi_m, "ecoulement": ecoul, "cote": cote, "terre": terre,
            "px": px, "cote_m": cote_m}


def masques_biome(sig, biome):
    """Masques des classes du biome, normalisés par soustraction (ordre des règles = priorité).

    Renvoie (ordre, masques) ; la mer et la classe par défaut sont ajoutées (mer en premier, défaut en dernier).
    """
    from pipeline_v5 import module_normalize
    taille = sig["terre"].shape[0]
    terre = sig["terre"].astype(np.float32)
    brut = {"mer": (~sig["terre"]).astype(np.float32)}
    ordre = ["mer"]
    for i, r in enumerate(biome["regles"]):
        score = np.ones((taille, taille), np.float32)
        for nom, t in r.get("si", {}).items():
            if nom not in SIGNAUX:
                raise ValueError(f"Signal inconnu dans la règle {r['classe']} : {nom}")
            score *= trapeze(sig[nom], *t)
        k = float(r.get("bruit", 0))
        if k:
            score = np.clip(score + k * bruit_lent(taille, 100 + i, taille / 24), 0, 1)
        lissage = float(r.get("lissage_m", biome.get("lissage_m", 0)))
        if lissage > 0:                                      # zones d'un seul tenant, moins de taches isolées
            score = cv2.GaussianBlur(score, (0, 0), max(lissage / sig["px"], 0.5))
        m = np.where(score >= float(r.get("seuil", 0.5)), score, 0.0).astype(np.float32) * terre
        if r["classe"] in brut:
            brut[r["classe"]] = np.maximum(brut[r["classe"]], m)
        else:
            brut[r["classe"]] = m
            ordre.append(r["classe"])
    norm = module_normalize(brut, [(c, None, None) for c in ordre])
    defaut = biome.get("defaut", "sol_nu")
    pris = np.zeros((taille, taille), bool)
    for c in ordre:
        pris |= norm[c] > 0
    norm[defaut] = np.maximum(norm.get(defaut, 0), ((~pris) & sig["terre"]).astype(np.float32))
    if defaut not in ordre:
        ordre.append(defaut)
    return ordre, norm


def classe_par_pixel(ordre, masques):
    """Indice (dans ordre) de la classe de chaque pixel, -1 si aucune."""
    taille = next(iter(masques.values())).shape[0]
    idx = np.full((taille, taille), -1, np.int16)
    for i, c in enumerate(ordre):
        idx[(masques[c] > 0) & (idx < 0)] = i
    return idx


def apercu(sig, ordre, masques, chemin, legende=True):
    """Aperçu en couleurs génériques sur relief ombré (lumière nord-ouest), avec légende des classes présentes."""
    idx = classe_par_pixel(ordre, masques)
    cols = np.array([CLASSES[c][1] for c in ordre] + [(0, 0, 0)], np.float32)
    img = cols[idx]
    H, px = sig["altitude"], sig["px"]
    gy, gx = np.gradient(cv2.GaussianBlur(H, (0, 0), 1.0), px)
    az, alt = np.radians(315), np.radians(45)
    lx, ly, lz = np.cos(alt) * np.sin(az), np.cos(alt) * np.cos(az), np.sin(alt)
    lam = np.clip((-gx * lx + gy * ly + lz) / np.sqrt(gx * gx + gy * gy + 1.0), 0, 1)
    img *= (0.55 + 0.45 * lam)[..., None] * np.where(sig["terre"], 1.0, 0.0)[..., None] + \
        np.where(sig["terre"], 0.0, 1.0)[..., None]
    img = np.clip(img, 0, 255).astype(np.uint8)
    if legende:
        n = img.shape[0]
        pres = [c for c in ordre if (idx == ordre.index(c)).any()]
        pas, x0, y0 = max(18, n // 90), n // 60, n // 60
        h = pas * (len(pres) + 1)
        cv2.rectangle(img, (x0 - pas // 3, y0 - pas // 3), (x0 + pas * 12, y0 + h), (250, 248, 240), -1)
        for k, c in enumerate(pres):
            y = y0 + k * pas
            cv2.rectangle(img, (x0, y), (x0 + pas - 4, y + pas - 4), CLASSES[c][1], -1)
            pct = 100.0 * float((idx == ordre.index(c)).mean())
            cv2.putText(img, f"{c} ({pct:.1f} %)", (x0 + pas + 4, y + pas - 6), cv2.FONT_HERSHEY_SIMPLEX,
                        pas / 30, (30, 30, 30), max(1, pas // 16), cv2.LINE_AA)
    cv2.imwrite(str(chemin), cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
    return chemin


def bilan(ordre, masques, bloc_px):
    """% de chaque classe (sur toute l'image) et nombre de classes par bloc de bloc_px pixels."""
    idx = classe_par_pixel(ordre, masques)
    n = idx.shape[0] // bloc_px * bloc_px
    b = idx[:n, :n].reshape(n // bloc_px, bloc_px, n // bloc_px, bloc_px).transpose(0, 2, 1, 3).reshape(-1, bloc_px * bloc_px)
    present = np.zeros((b.shape[0], len(ordre)), bool)
    for i in range(len(ordre)):
        present[:, i] = (b == i).any(1)
    par_bloc = present.sum(1)
    return {"pct": {c: round(100.0 * float((idx == i).mean()), 2) for i, c in enumerate(ordre)},
            "blocs": int(len(par_bloc)), "classes_par_bloc_max": int(par_bloc.max()),
            "histogramme": {int(k): int((par_bloc == k).sum()) for k in np.unique(par_bloc)}}


def suggestion(classe, textures):
    """Texture du projet proposée pour une classe : la vanilla la plus proche si le projet l'a, sinon une texture
    dont le nom contient un mot-clé de la classe, sinon "" (à choisir ou à fusionner)."""
    vanilla = CLASSES.get(classe, ("", (0, 0, 0), ""))[2]
    if vanilla and vanilla in textures:
        return vanilla
    mots = {"mer": ("seabed",), "plage": ("beach", "sand", "pebble"), "sable": ("sand", "dune"),
            "reg": ("pebble", "gravel"), "hamada": ("debris", "rock"), "sol_nu": ("dirt", "soil", "clay"),
            "lit_oued": ("pebble", "gravel"), "oasis": ("grass",), "eboulis": ("debris", "scree"),
            "roche_exposee": ("rock",), "falaise": ("rock", "cliff"), "herbe_seche": ("grass",),
            "prairie": ("grass",), "foret": ("forest",), "neige": ("snow",), "neve": ("snow",), "glace": ("ice",)}
    for m in mots.get(classe, ()):
        for t in textures:
            if m in t.lower():
                return t
    return ""


def par_texture(ordre, masques, association):
    """Regroupe les classes par texture : deux classes associées à la même texture n'en font plus qu'une
    (fusion, un slot de moins dans les blocs). association : {classe: texture} ; toute classe doit en avoir une.

    Renvoie (ordre des textures, {texture: masque}).
    """
    manquantes = [c for c in ordre if not association.get(c)]
    if manquantes:
        raise ValueError("Classes sans texture : " + ", ".join(manquantes))
    textures, out = [], {}
    for c in ordre:
        t = association[c]
        if t in out:
            out[t] = np.maximum(out[t], masques[c])          # pixels exclusifs : le max vaut la somme
        else:
            out[t] = masques[c].copy()
            textures.append(t)
    return textures, out


def limiter_budget(ordre, masques, budget, bloc_px):
    """Au plus budget masques par bloc de bloc_px pixels : les masques les moins étendus du bloc sont rendus
    au masque dominant du bloc. Modifie masques sur place ; renvoie le nombre de blocs corrigés."""
    idx = classe_par_pixel(ordre, masques)
    n = idx.shape[0] // bloc_px * bloc_px
    nb = n // bloc_px
    blocs = idx[:n, :n].reshape(nb, bloc_px, nb, bloc_px).transpose(0, 2, 1, 3).reshape(nb, nb, -1)
    present = np.zeros((nb, nb), np.int32)
    for i in range(len(ordre)):
        present += (blocs == i).any(-1)
    corriges = 0
    for by, bx in zip(*np.nonzero(present > budget)):
        y, x = int(by) * bloc_px, int(bx) * bloc_px
        b = idx[y:y + bloc_px, x:x + bloc_px]
        vals, cnt = np.unique(b[b >= 0], return_counts=True)
        garde = vals[np.argsort(-cnt)[:budget]]
        dominant = ordre[int(garde[0])]
        for v in vals:
            if v in garde:
                continue
            m = masques[ordre[int(v)]][y:y + bloc_px, x:x + bloc_px]
            sel = m > 0
            masques[dominant][y:y + bloc_px, x:x + bloc_px][sel] = 1.0
            m[sel] = 0.0
        corriges += 1
    return corriges


def exporter_masques_16(ordre, masques, dossier):
    """Masques par texture en PNG 16 bits (comme l'export du pipeline v5), numérotés dans l'ordre de priorité."""
    dossier = Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    for f in dossier.glob("*.png"):
        f.unlink()
    for i, t in enumerate(ordre):
        cv2.imwrite(str(dossier / f"{i + 1:02d}_{t}.png"), (np.clip(masques[t], 0, 1) * 65535).astype(np.uint16))
    return dossier


def exporter_masques(ordre, masques, dossier):
    """Masques en niveaux de gris (PNG 8 bits), numérotés dans l'ordre de priorité."""
    dossier = Path(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    for i, c in enumerate(ordre):
        cv2.imwrite(str(dossier / f"{i + 1:02d}_{c}.png"), np.clip(masques[c] * 255, 0, 255).astype(np.uint8))
    return dossier
