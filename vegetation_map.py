# -*- coding: utf-8 -*-
"""
Vegetation Map Generator
========================

Génère une carte de végétation potentielle depuis les signaux terrain
calculés par pipeline_v2.py.

Réutilise les calculs existants (slope, curvature, TPI, flow, aspect, etc.)
sans recalcul.

Usage:
    scores = compute_vegetation_scores(heightmap, slope, curvature, ...)
    rgb = render_vegetation_rgb(scores, min_score=0.15)
    export_vegetation_png(rgb, output_path)
"""

import numpy as np
from pathlib import Path
from PIL import Image
from scipy.ndimage import gaussian_filter


# ══════════════════════════════════════════════════════════════════════════════
# TYPES DE VÉGÉTATION ET COULEURS
# ══════════════════════════════════════════════════════════════════════════════

VEGETATION_TYPES = {
    "foret_feuillue": {
        "color": (45, 90, 27),       # vert foncé (deciduous dense)
        "label": "Forêt feuillue dense"
    },
    "foret_clearing_deciduous": {
        "color": (75, 135, 60),      # vert clair (deciduous clairsemée)
        "label": "Forêt feuillue clairsemée"
    },
    "foret_pins": {
        "color": (43, 95, 74),       # vert bleuté (pins méditerranéens)
        "label": "Forêt de pins"
    },
    "foret_coniferes": {
        "color": (26, 74, 42),       # vert sombre (coniferous dense)
        "label": "Forêt de conifères dense"
    },
    "foret_clearing_coniferous": {
        "color": (61, 122, 43),      # vert moyen (coniferous clairsemée)
        "label": "Forêt de conifères clairsemée"
    },
    "maquis_landes": {
        "color": (139, 115, 85),     # brun-olive (landes/maquis plateaux)
        "label": "Maquis / Landes"
    },
    "landes_plateau": {
        "color": (155, 130, 90),     # brun-olive clair (plateaux ouest)
        "label": "Landes de plateau"
    },
    "haies_lisieres": {
        "color": (107, 139, 58),     # vert olive
        "label": "Haies / Lisières"
    },
    "prairie_humide": {
        "color": (125, 191, 90),     # vert clair
        "label": "Prairie humide"
    },
    "prairie_seche": {
        "color": (160, 170, 85),     # olive (prairies sèches plateaux)
        "label": "Prairie sèche"
    },
    "prairie_plateau": {
        "color": (181, 196, 90),     # jaune-vert (prairies plateaux ouest)
        "label": "Prairie de plateau"
    },
    "alpages": {
        "color": (200, 212, 160),    # beige-vert
        "label": "Alpages"
    },
    "roseaux_marais": {
        "color": (139, 155, 90),     # brun-vert
        "label": "Roseaux / Marais"
    },
    "ripisylve": {
        "color": (74, 155, 107),     # vert eau
        "label": "Ripisylve"
    },
    "veg_rupestre": {
        "color": (139, 155, 139),    # gris-vert
        "label": "Végétation rupestre"
    },
    "landes_rocheuses": {
        "color": (155, 155, 139),    # gris
        "label": "Landes rocheuses"
    },
}


# ══════════════════════════════════════════════════════════════════════════════
# FONCTION PRINCIPALE
# ══════════════════════════════════════════════════════════════════════════════

def compute_vegetation_scores(
    heightmap,      # array 2D altitudes
    slope,          # array 2D degrés (depuis pipeline_v2)
    curvature,      # array 2D (depuis pipeline_v2)
    tpi_local,      # array 2D (depuis pipeline_v2)
    tpi_macro,      # array 2D (depuis pipeline_v2)
    flow,           # array 2D (depuis pipeline_v2)
    aspect,         # array 2D degrés (depuis pipeline_v2)
    distance_cote,  # array 2D mètres (depuis pipeline_v2)
    params,         # dict paramètres (depuis auto_calibrate)
    cellsize        # float m/px
):
    """
    Calcule un score [0-1] par type de végétation pour chaque pixel.

    Args:
        heightmap: array 2D altitudes (float32)
        slope: array 2D pentes en degrés
        curvature: array 2D courbure normalisée [-1, 1]
        tpi_local: array 2D TPI local normalisé [-1, 1]
        tpi_macro: array 2D TPI macro normalisé [-1, 1]
        flow: array 2D flow accumulation normalisé [0, 1]
        aspect: array 2D orientation 0-360°
        distance_cote: array 2D distance côte (mètres)
        params: dict paramètres auto-calibrés
        cellsize: résolution m/px

    Returns:
        dict {type_veg: array_float32 [0-1]}
    """
    # Normaliser altitude sur terrain émergé
    land_mask = heightmap > 0
    if not land_mask.any():
        # Pas de terrain émergé
        return {k: np.zeros_like(heightmap, dtype=np.float32) for k in VEGETATION_TYPES}

    alt_min = float(np.nanmin(heightmap[land_mask]))
    alt_max = float(np.nanmax(heightmap[land_mask]))
    alt_range = alt_max - alt_min

    # Récupérer seuils depuis params
    grass_low_max = params.get('grass_low_max_m', 40)
    grass_mid_max = params.get('grass_mid_max_m', 100)
    grass_high_max = params.get('grass_high_max_m', 170)
    debris_min = params.get('debris_min_deg', 18)
    rock_min = params.get('rock_min_deg', 28)
    coastal_alt = params.get('coastal_alt_max_m', 15)
    coastal_dist = params.get('coastal_distance_max_m', 60)

    # ── Facteurs de base ────────────────────────────────────────────────────

    # Zones altitudinales (ADAPTÉES ZIMNITRITA : île 0-500m)
    # Forêt pins méditerranéens : 0-250m (étage méditerranéen bas, côtier)
    alt_pine = _bell(heightmap, 0, 250, slope=40)

    # Forêt feuillue (chênes) : 100-450m (étage collinéen/montagnard bas)
    alt_deciduous = _bell(heightmap, 150, 400, slope=50)

    # OBSOLÈTE : pas de conifères montagnards sur Zimnitrita (< 500m)
    # alt_coniferous supprimé - remplacé par différenciation pins côtiers

    # Zones génériques (pour autres végétations)
    alt_low    = np.clip(1 - (heightmap - alt_min) / (grass_low_max - alt_min + 1), 0, 1)
    alt_mid    = _bell(heightmap, grass_low_max, grass_mid_max, slope=20)
    alt_high   = _bell(heightmap, grass_mid_max, grass_high_max, slope=30)
    alt_alpine = np.clip((heightmap - grass_high_max) / (alt_range * 0.3 + 1), 0, 1)

    # Pente
    flat   = np.clip(1 - slope / debris_min, 0, 1)
    gentle = _bell(slope, 5, debris_min, slope=5)
    steep  = np.clip((slope - debris_min) / (rock_min - debris_min + 1), 0, 1)
    rocky  = np.clip((slope - rock_min) / 20, 0, 1)

    # Aspect (orientation)
    north = np.cos(np.radians(aspect))               # +1=nord, -1=sud
    north_f = np.clip((north + 1) / 2, 0, 1)        # 0=sud, 1=nord
    south_f = np.clip((-north + 1) / 2, 0, 1)       # 0=nord, 1=sud

    # Humidité proxy
    flow_n = flow  # Déjà normalisé [0-1] par pipeline_v2
    dist_w_norm = np.clip(distance_cote / 500, 0, 1)
    humid = np.clip(flow_n * 0.6 + (1 - dist_w_norm) * 0.4, 0, 1)
    dry   = np.clip(1 - humid, 0, 1)

    # TPI
    tpi_neg = np.clip(-tpi_local, 0, 1)   # creux
    tpi_pos = np.clip(tpi_local, 0, 1)    # crêtes
    tpi_mac_pos = np.clip(tpi_macro, 0, 1)  # plateau/montagne

    # Curvature
    concave = np.clip(-curvature, 0, 1)  # vallées
    convex  = np.clip(curvature, 0, 1)   # crêtes

    # Zone côtière
    coastal = ((distance_cote < coastal_dist) & (heightmap < coastal_alt)).astype(np.float32)
    non_coastal = 1 - coastal

    # Terrain émergé
    land = land_mask.astype(np.float32)

    # ══════════════════════════════════════════════════════════════════════════
    # SCORES PAR TYPE DE VÉGÉTATION
    # ══════════════════════════════════════════════════════════════════════════
    # PRINCIPE : Facteur dominant (50-60%) + Modificateurs écologiques (20-40%)
    # ══════════════════════════════════════════════════════════════════════════
    scores = {}

    # ═════════════════════════════════════════════════════════════════════════
    # FORÊTS - LOGIQUE SIMPLE (2 types : Conifères + Feuillus)
    # ═════════════════════════════════════════════════════════════════════════
    # Différenciation par : ALTITUDE + DISTANCE_CÔTE + EXPOSITION
    # ═════════════════════════════════════════════════════════════════════════

    # Facteur côtier : influence maritime décroissante avec distance
    coastal_zone = np.clip(1 - distance_cote / 800, 0, 1)     # 0-800m côtier
    interior = np.clip((distance_cote - 600) / 1200, 0, 1)    # > 600m intérieur

    # ─────────────────────────────────────────────────────────────────────────
    # CONIFÈRES (Pins méditerranéens)
    # ─────────────────────────────────────────────────────────────────────────
    # Zone : Altitude 0-250m + Proximité côte + Versant sud + Sols rocheux
    # Facteur dominant : zone côtière chaude et sèche

    base_coniferous = alt_pine * (coastal_zone * 0.7 + (1 - interior) * 0.3) * non_coastal * land

    # Modificateurs : bonus pour versant sud + sec + sols rocheux
    mod_coniferous = 0.5 + south_f * 0.30 + dry * 0.15 + rocky * 0.10

    scores["foret_coniferes"] = (
        base_coniferous * mod_coniferous * (flat * 0.6 + gentle * 0.4)
    ).astype(np.float32)

    # ─────────────────────────────────────────────────────────────────────────
    # FEUILLUS (Chênes)
    # ─────────────────────────────────────────────────────────────────────────
    # Zone : Altitude 150-450m + Intérieur + Versant nord + Sols profonds
    # Facteur dominant : altitude moyenne + intérieur protégé

    base_deciduous = alt_deciduous * (interior * 0.7 + (1 - coastal_zone) * 0.3) * non_coastal * land

    # Modificateurs : bonus pour versant nord + humidité + sols profonds
    mod_deciduous = 0.5 + north_f * 0.30 + humid * 0.15 + (1 - rocky) * 0.10

    scores["foret_feuillue"] = (
        base_deciduous * mod_deciduous * (flat * 0.6 + gentle * 0.4)
    ).astype(np.float32)

    # ─────────────────────────────────────────────────────────────────────────
    # OBSOLÈTE : Clearings supprimés (trop complexe)
    # ─────────────────────────────────────────────────────────────────────────
    scores["foret_clearing_coniferous"] = np.zeros_like(heightmap, dtype=np.float32)
    scores["foret_clearing_deciduous"] = np.zeros_like(heightmap, dtype=np.float32)
    scores["foret_pins"] = np.zeros_like(heightmap, dtype=np.float32)

    # Maquis / Landes : moyenne alt + versant sud + sec + pentes douces/plateaux
    # Réduit sur plateaux pour laisser place à landes_plateau
    anti_plateau = np.clip(1 - tpi_mac_pos * 0.3, 0.5, 1.0)
    scores["maquis_landes"] = (
        alt_mid * south_f * dry * gentle * anti_plateau * non_coastal * land
    ).astype(np.float32)

    # Landes de plateau : moyenne alt + plateau (TPI macro positif) + sec + flat/gentle
    # Cible les landes/maquis des plateaux ouest (brun-olive)
    # CONTRAINTE : majoritairement plat, gentle accepté mais réduit
    scores["landes_plateau"] = (
        alt_mid * (0.5 + 0.5 * tpi_mac_pos) * (0.5 + 0.5 * dry) * (flat * 0.8 + gentle * 0.2) * non_coastal * land
    ).astype(np.float32)

    # ─────────────────────────────────────────────────────────────────────────
    # HAIES / LISIÈRES (bordures de forêts, transitions)
    # ─────────────────────────────────────────────────────────────────────────

    # Haies/Lisières : transitions forêt ↔ prairie (TPI neutre, pente douce)
    # Facteur dominant : altitude basse/moyenne + pente douce + TPI neutre
    tpi_neutral = np.clip(1 - np.abs(tpi_local) * 1.2, 0, 1)
    base_haies = ((alt_low + alt_mid) * 0.5) * gentle * tpi_neutral * non_coastal * land

    # Modificateurs : bonus pour conditions intermédiaires (ni trop sec ni trop humide)
    # Score de base élevé pour être visible
    mod_haies = 0.7 + humid * 0.3 + (1 - np.abs(tpi_local)) * 0.2

    scores["haies_lisieres"] = (
        base_haies * mod_haies
    ).astype(np.float32)

    # ─────────────────────────────────────────────────────────────────────────
    # PRAIRIES (zones ouvertes sans forêt)
    # ─────────────────────────────────────────────────────────────────────────
    # Principe : prairies apparaissent là où forêts ne peuvent pas dominer
    # (exposition extrême, crêtes ventées, zones très sèches)

    # Prairie humide : zones plates humides NON-forestières (ex: prairies inondables)
    # Facteur dominant : altitude basse + très plat + humidité extrême (trop pour forêt)
    base_prairie_humide = alt_low * flat * non_coastal * land

    # Modificateurs : bonus énorme pour humidité + flow (zones inondables)
    # Score de base plus élevé pour compétitionner avec forêts
    mod_prairie_humide = 0.6 + humid * 0.8 + flow_n * 0.3 + tpi_neg * 0.2

    scores["prairie_humide"] = (
        base_prairie_humide * mod_prairie_humide
    ).astype(np.float32)

    # Prairie sèche : zones plates très sèches (exposition sud extrême)
    # Facteur dominant : altitude basse/moyenne + plat + sec extrême
    base_prairie_seche = ((alt_low + alt_mid) * 0.5) * flat * non_coastal * land

    # Modificateurs : boost fort pour sec + crêtes (TPI positif) + exposition sud
    # Cible zones trop sèches/ventées pour forêts
    mod_prairie_seche = 0.5 + dry * 0.6 + tpi_pos * 0.3 + south_f * 0.2

    scores["prairie_seche"] = (
        base_prairie_seche * mod_prairie_seche
    ).astype(np.float32)

    # Prairie de plateau : plateaux d'altitude avec herbe rase (ventés, pâturés)
    # Facteur dominant : altitude moyenne/haute + plateau fort + plat
    # Élargie pour couvrir 100-250m (zone typique plateaux Zimnitrita)
    alt_plateau = _bell(heightmap, 100, 250, slope=40)
    base_prairie_plateau = alt_plateau * flat * non_coastal * land

    # Modificateurs : boost énorme pour plateaux (zones ventées anti-forêt)
    mod_prairie_plateau = 0.5 + tpi_mac_pos * 0.8 + (1 - steep) * 0.2

    scores["prairie_plateau"] = (
        base_prairie_plateau * mod_prairie_plateau
    ).astype(np.float32)

    # Note : le fallback plateau a été supprimé car les formules recodées
    # génèrent maintenant des scores suffisants sans artifices

    # ─────────────────────────────────────────────────────────────────────────
    # ALPAGES (prairies d'altitude, au-dessus limite forestière)
    # ─────────────────────────────────────────────────────────────────────────

    # Alpages : haute altitude + pentes douces/modérées (zones de pâturage montagne)
    # Facteur dominant : altitude > 180m + pente douce (au-dessus limite forestière)
    # Sur Zimnitrita : seulement 19% > 170m, donc alpages = rare et haut
    alt_alpage = np.clip((heightmap - 180) / 80, 0, 1).astype(np.float32)  # 180-260m
    base_alpages = alt_alpage * (flat * 0.7 + gentle * 0.3) * land

    # Modificateurs : boost fort pour altitude + plateaux (limite supérieure forêt)
    mod_alpages = 0.7 + tpi_mac_pos * 0.4 + (1 - steep) * 0.2

    scores["alpages"] = (
        base_alpages * mod_alpages
    ).astype(np.float32)

    # Roseaux / Marais : très basse alt + très humide + très plat + forte flow
    scores["roseaux_marais"] = (
        alt_low * humid * humid * flat * flat * flow_n * land
    ).astype(np.float32)

    # Ripisylve : forte flow + creux + humide + altitude basse/moyenne
    scores["ripisylve"] = (
        flow_n * tpi_neg * humid * ((alt_low + alt_mid) / 2) * land
    ).astype(np.float32)

    # Végétation rupestre : pentes raides + haute alt + rocky
    scores["veg_rupestre"] = (
        alt_high * rocky * land
    ).astype(np.float32)

    # Landes rocheuses : TOUTES les pentes (steep + gentle)
    # Couvre moyenne/haute altitude + toutes pentes
    # Score plus élevé sur pentes sèches/convexes
    scores["landes_rocheuses"] = (
        ((alt_mid + alt_high) * 0.5) * (steep + gentle * 0.5) * (0.4 + 0.6 * dry) * (0.6 + 0.4 * convex) * non_coastal * land
    ).astype(np.float32)

    # ── FALLBACK VALLÉES : couvre vallées encaissées (TPI négatif fort) ────
    # Cible les zones noires/marron dans les creux de terrain
    vallee_fallback = (
        tpi_neg * (gentle + steep) * land
    ).astype(np.float32)

    # Distribuer entre ripisylve (humid) et landes rocheuses (dry)
    scores["ripisylve"] = np.maximum(
        scores["ripisylve"],
        (vallee_fallback * 0.6 * humid).astype(np.float32)
    )

    scores["landes_rocheuses"] = np.maximum(
        scores["landes_rocheuses"],
        (vallee_fallback * 0.5 * dry).astype(np.float32)
    )

    # ── Lissage spatial pour réduire bruit ─────────────────────────────────
    smoothing_sigmas = {
        "foret_feuillue": 2.5,
        "foret_clearing_deciduous": 2.0,
        "foret_pins": 2.5,
        "foret_coniferes": 2.5,
        "foret_clearing_coniferous": 2.0,
        "maquis_landes": 2.0,
        "landes_plateau": 2.0,
        "haies_lisieres": 1.5,
        "prairie_humide": 2.0,
        "prairie_seche": 2.0,
        "prairie_plateau": 2.0,
        "alpages": 2.5,
        "roseaux_marais": 1.5,
        "ripisylve": 1.0,
        "veg_rupestre": 1.5,
        "landes_rocheuses": 1.5,
    }

    for veg_type, sigma in smoothing_sigmas.items():
        if veg_type in scores:
            scores[veg_type] = gaussian_filter(scores[veg_type], sigma=sigma).astype(np.float32)

    return scores


def _bell(arr, lo, hi, slope=10.0):
    """
    Fonction en cloche : score maximal dans [lo, hi], décroît en dehors.

    Args:
        arr: array d'entrée
        lo, hi: intervalle optimal
        slope: vitesse de décroissance

    Returns:
        array [0-1]
    """
    center = (lo + hi) / 2.0
    half = (hi - lo) / 2.0 + 1e-6
    dist = np.abs(arr - center) - half
    return np.clip(1.0 - dist / (slope + 1e-6), 0.0, 1.0)


# ══════════════════════════════════════════════════════════════════════════════
# RENDU RGB
# ══════════════════════════════════════════════════════════════════════════════

def render_vegetation_rgb(
    scores,
    heightmap=None,
    min_score=0.15,
    blend=True
):
    """
    Génère une image RGB de la carte de végétation.

    Args:
        scores: dict {type_veg: array_float32}
        heightmap: array 2D altitudes (pour masquer eau)
        min_score: seuil minimum pour afficher un type
        blend: True=mélange pondéré, False=type dominant

    Returns:
        array uint8 shape (H, W, 3)
    """
    first_score = next(iter(scores.values()))
    H, W = first_score.shape

    COLOR_WATER = np.array([55, 90, 140], dtype=np.float32)  # bleu
    COLOR_NO_VEG = np.array([60, 55, 50], dtype=np.float32)  # brun sombre

    rgb = np.zeros((H, W, 3), dtype=np.float32)

    if blend:
        # Mélange pondéré
        weight_sum = np.zeros((H, W), dtype=np.float32)
        for veg_type, score_arr in scores.items():
            sc = np.clip(score_arr, 0.0, 1.0)
            sc = np.where(sc >= min_score, sc, 0.0)
            color = np.array(VEGETATION_TYPES[veg_type]["color"], dtype=np.float32)
            rgb += sc[..., np.newaxis] * color
            weight_sum += sc

        has_veg = weight_sum > 1e-6
        rgb[has_veg] /= weight_sum[has_veg, np.newaxis]
        rgb[~has_veg] = COLOR_NO_VEG
    else:
        # Type dominant
        best_score = np.full((H, W), min_score, dtype=np.float32)
        rgb[:] = COLOR_NO_VEG

        for veg_type, score_arr in scores.items():
            better = score_arr > best_score
            best_score[better] = score_arr[better]
            color = np.array(VEGETATION_TYPES[veg_type]["color"], dtype=np.float32)
            rgb[better] = color

    # Eau en bleu
    if heightmap is not None:
        water_mask = heightmap < 0
        rgb[water_mask] = COLOR_WATER

    return np.clip(rgb, 0, 255).astype(np.uint8)


# ══════════════════════════════════════════════════════════════════════════════
# EXPORT PNG
# ══════════════════════════════════════════════════════════════════════════════

def export_vegetation_png(rgb_array, output_path):
    """
    Exporte image RGB en PNG.

    Args:
        rgb_array: array uint8 (H, W, 3)
        output_path: chemin fichier de sortie

    Returns:
        str: chemin absolu du fichier créé
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    img = Image.fromarray(rgb_array, mode='RGB')
    img.save(output_path)

    return str(output_path.absolute())


def export_vegetation_masks(scores, output_dir, min_score=0.1):
    """
    Exporte les masques de végétation en PNG 16-bit (ZONES EXCLUSIVES).

    Génère un fichier PNG 16-bit BINAIRE par type de végétation :
    - Chaque pixel appartient à UN SEUL type (celui avec le score maximal)
    - Valeur = 65535 si ce type gagne, 0 sinon
    - Pixels avec tous scores < min_score = 0 partout (pas de végétation)

    Args:
        scores: dict {type_veg: array_float32 [0-1]}
        output_dir: répertoire de sortie
        min_score: seuil minimum (défaut 0.1)

    Returns:
        dict {type_veg: chemin_fichier}
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Récupérer dimensions
    first_score = next(iter(scores.values()))
    H, W = first_score.shape

    # Trouver le type dominant pour chaque pixel (winner-takes-all)
    best_score = np.full((H, W), min_score, dtype=np.float32)
    best_type = np.full((H, W), -1, dtype=np.int32)  # -1 = pas de végétation

    type_indices = {veg_type: idx for idx, veg_type in enumerate(scores.keys())}

    for veg_type, score_arr in scores.items():
        idx = type_indices[veg_type]
        score_clipped = np.clip(score_arr, 0.0, 1.0)

        # Ce type devient dominant là où son score dépasse le meilleur actuel
        better = score_clipped > best_score
        best_score[better] = score_clipped[better]
        best_type[better] = idx

    # Créer masques binaires
    exported_files = {}

    for veg_type, idx in type_indices.items():
        # Masque binaire : 65535 là où ce type est dominant, 0 ailleurs
        mask_binary = np.where(best_type == idx, 65535, 0).astype(np.uint16)

        # Sauvegarder PNG 16-bit
        output_path = output_dir / f"mask_{veg_type}.png"
        img = Image.fromarray(mask_binary, mode='I;16')
        img.save(output_path)

        exported_files[veg_type] = str(output_path.absolute())

    return exported_files


# ══════════════════════════════════════════════════════════════════════════════
# STATISTIQUES
# ══════════════════════════════════════════════════════════════════════════════

def compute_vegetation_stats(scores, cellsize, min_score=0.15):
    """
    Calcule statistiques par type de végétation.

    Args:
        scores: dict {type_veg: array_float32}
        cellsize: résolution m/px
        min_score: seuil minimum

    Returns:
        dict {type_veg: {'pixels': int, 'area_m2': float, 'coverage_pct': float}}
    """
    first_score = next(iter(scores.values()))
    total_pixels = first_score.size
    cell_area_m2 = cellsize * cellsize

    stats = {}
    for veg_type, score_arr in scores.items():
        pixels = int(np.sum(score_arr >= min_score))
        area_m2 = pixels * cell_area_m2
        coverage_pct = (pixels / total_pixels) * 100

        stats[veg_type] = {
            'label': VEGETATION_TYPES[veg_type]['label'],
            'pixels': pixels,
            'area_m2': area_m2,
            'area_ha': area_m2 / 10000,
            'coverage_pct': coverage_pct
        }

    return stats


# ══════════════════════════════════════════════════════════════════════════════
# TESTS
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Test basique
    print("Vegetation Map Generator")
    print(f"{len(VEGETATION_TYPES)} types de végétation définis:")
    for veg_type, info in VEGETATION_TYPES.items():
        print(f"  - {info['label']} : RGB{info['color']}")

    # Test _bell
    test_arr = np.array([0, 25, 50, 75, 100])
    bell_result = _bell(test_arr, 25, 75, slope=10)
    print(f"\nTest _bell(25-75): {bell_result}")
    assert bell_result[1] > 0.9  # Dans la plage
    assert bell_result[2] > 0.9  # Dans la plage
    assert bell_result[0] < 0.5  # En dehors

    print("\n[OK] Tests passés")
