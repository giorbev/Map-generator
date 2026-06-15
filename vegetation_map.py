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
        "color": (45, 90, 27),       # vert foncé
        "label": "Forêt feuillue"
    },
    "foret_mixte": {
        "color": (61, 122, 43),      # vert moyen
        "label": "Forêt mixte"
    },
    "foret_pins": {
        "color": (43, 95, 74),       # vert bleuté
        "label": "Forêt de pins"
    },
    "foret_coniferes": {
        "color": (26, 74, 42),       # vert sombre
        "label": "Forêt de conifères"
    },
    "maquis_landes": {
        "color": (139, 115, 85),     # kaki
        "label": "Maquis / Landes"
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
        "color": (181, 196, 90),     # jaune-vert
        "label": "Prairie sèche"
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

    # Zones altitudinales
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
    scores = {}

    # Forêt feuillue : basse alt + versant nord + humide + plat/doux + creux
    scores["foret_feuillue"] = (
        alt_low * north_f * humid * flat * non_coastal * tpi_neg * land
    ).astype(np.float32)

    # Forêt mixte : basse/moyenne alt + versant nord + modérément humide
    scores["foret_mixte"] = (
        alt_mid * north_f * humid * 0.7 * flat * non_coastal * land
    ).astype(np.float32)

    # Forêt de pins : moyenne alt + versant sud + sec + plat
    scores["foret_pins"] = (
        alt_mid * south_f * dry * flat * non_coastal * land
    ).astype(np.float32)

    # Forêt de conifères : haute alt + versant nord + humide + plat
    scores["foret_coniferes"] = (
        alt_high * north_f * humid * flat * non_coastal * land
    ).astype(np.float32)

    # Maquis / Landes : moyenne alt + versant sud + sec + pentes douces/plateaux
    # Bonus pour TPI macro positif (plateaux secs)
    plateau_bonus = 0.6 + 0.4 * tpi_mac_pos
    scores["maquis_landes"] = (
        alt_mid * south_f * dry * gentle * plateau_bonus * non_coastal * land
    ).astype(np.float32)

    # Haies / Lisières : transition forêt/prairie (TPI proche de 0 + altitude basse/moyenne)
    tpi_neutral = np.clip(1 - np.abs(tpi_local) / 0.5, 0, 1)
    scores["haies_lisieres"] = (
        ((alt_low + alt_mid) / 2) * tpi_neutral * gentle * non_coastal * land
    ).astype(np.float32)

    # Prairie humide : basse alt + très humide + plat + creux
    scores["prairie_humide"] = (
        alt_low * humid * flat * tpi_neg * non_coastal * land
    ).astype(np.float32)

    # Prairie sèche : basse/moyenne alt + sec + plat (favorise plateaux)
    # Bonus pour TPI macro positif (plateaux)
    scores["prairie_seche"] = (
        ((alt_low + alt_mid) / 2) * dry * flat * (0.7 + 0.3 * tpi_mac_pos) * non_coastal * land
    ).astype(np.float32)

    # Alpages : moyenne/haute alt + plateau (TPI macro positif) + plat
    # Élargi pour inclure plateaux moyenne altitude
    scores["alpages"] = (
        ((alt_mid + alt_high + alt_alpine) / 3) * tpi_mac_pos * flat * land
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

    # Landes rocheuses : pentes raides + moyenne alt + sec + convexe
    scores["landes_rocheuses"] = (
        alt_mid * steep * dry * convex * land
    ).astype(np.float32)

    # ── Lissage spatial pour réduire bruit ─────────────────────────────────
    smoothing_sigmas = {
        "foret_feuillue": 2.5,
        "foret_mixte": 2.5,
        "foret_pins": 2.5,
        "foret_coniferes": 2.5,
        "maquis_landes": 2.0,
        "haies_lisieres": 1.5,
        "prairie_humide": 2.0,
        "prairie_seche": 2.0,
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
