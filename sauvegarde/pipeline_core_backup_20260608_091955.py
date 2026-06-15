"""
pipeline_core.py
================
Pipeline Reforger — cœur algorithmique sans UI.
Ingestion -> Masques matériaux -> Squeezing QTRE -> Export PNG 16 bits.

Utilisation :
    pipeline = TexturePipeline(log_fn=print, progress_fn=lambda p: None)
    target_size, process_size, blocs_cote, taille_bloc, alt_min, alt_max = \
        TexturePipeline.derive_grid_from_project(project_data)
    paths = TexturePipeline.build_paths_from_project(project_data, project_dir)
    pipeline.run_pipeline(out_root, target_size, blocs_cote, taille_bloc,
                          alt_min, alt_max, paths, material_lib_path,
                          process_size=process_size)
"""

import os
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import cv2
import numpy as np

try:
    import imageio as _imageio
    _HAS_IMAGEIO = True
except ImportError:
    _HAS_IMAGEIO = False

try:
    import png as _png
    _HAS_PNG = True
except ImportError:
    _HAS_PNG = False


# ---------------------------------------------------------------------------
# Algorithme géologique — fonctions pures (indépendantes de l'UI)
# ---------------------------------------------------------------------------

# Texture de base Enfusion : couvre 100 % du terrain par défaut.
# Le moteur l'affiche partout où aucun masque n'a de poids -> pas de fichier exporté.
BASE_STEM = "Grass_02"

# Couches exportées, ordonnées par profondeur d'application Enfusion
# (couche 01 = la plus basse / couverte, couche 16 = la plus haute / dominante).
PIPELINE_STEMS = [
    "SeaBed_01",          # 01 — fond marin (sous l'eau)
    "BeachGrass_01",      # 02 — herbe côtière basse
    "Grass_03_coastal",   # 03 — herbe côtière intermédiaire
    "Pebbles_01",         # 04 — galets fins (côte & érosion)
    "Pebbles_02",         # 05 — galets grossiers
    "Grass_01",           # 06 — herbe standard basses terres
    "Grass_03",           # 07 — herbe intermédiaire / humide
    "MountainGrass_01",   # 08 — herbe de montagne rase
    "MountainGrass_02",   # 09 — herbe de montagne dense
    "MountainGrass_03",   # 10 — herbe alpine humide
    "Heather_01",         # 11 — lande / bruyère
    "Dirt_01",            # 12 — terre meuble
    "Dirt_02",            # 13 — limon / loess
    "Dirt_03",            # 14 — terre sableuse côtière
    "Debris_Rock_01",     # 15 — débris rocheux / éboulis
    "Rock_01",            # 16 — roche nue (couche dominante)
]

_COMPUTE_STEMS = PIPELINE_STEMS + [BASE_STEM]

# Rôle écologique de chaque stem pipeline — utilisé par resolve_biome pour
# convertir les role_scales du biome en stem_scales individuels.
STEM_ROLES: dict = {
    "SeaBed_01":        "fond_marin",
    "BeachGrass_01":    "cotier",
    "Grass_03_coastal": "cotier",
    "Pebbles_01":       "galets",
    "Pebbles_02":       "galets",
    "Grass_01":         "prairie",
    "Grass_03":         "prairie",
    "MountainGrass_01": "lande",
    "MountainGrass_02": "lande",
    "MountainGrass_03": "lande",
    "Heather_01":       "lande",
    "Dirt_01":          "terre",
    "Dirt_02":          "terre",
    "Dirt_03":          "erosion",
    "Debris_Rock_01":   "erosion",
    "Rock_01":          "roche",
}


def smoothstep(edge0, edge1, x):
    if edge0 == edge1:
        return np.where(x >= edge1, 1.0, 0.0).astype(np.float32)
    t = np.clip((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return (t * t * (3.0 - 2.0 * t)).astype(np.float32)


# ---------------------------------------------------------------------------
# Système tableaux biomes — Vote par masque (altitude/slope/sediment/curvature)
# ---------------------------------------------------------------------------

_BIOME_CACHE = {}

def load_biome_config(biome_name='temperate'):
    """
    Charge la configuration d'un biome depuis data/biomes/<biome_name>.json
    Retourne dict avec clés : 'biome', 'textures', 'thresholds', 'notes'
    """
    # DÉSACTIVÉ TEMPORAIREMENT : Force rechargement pour tests
    # if biome_name in _BIOME_CACHE:
    #     return _BIOME_CACHE[biome_name]

    # Chemin relatif au script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    biome_path = os.path.join(script_dir, 'data', 'biomes', f'{biome_name}.json')

    if not os.path.exists(biome_path):
        raise FileNotFoundError(f"Fichier biome introuvable : {biome_path}")

    with open(biome_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    _BIOME_CACHE[biome_name] = config
    return config


def get_altitude_zone(altitude, zones):
    """
    Détermine la zone altitudinale : 'coastal', 'lowland', 'midland', 'highland'

    zones : dict retourné par calibrate_zones()
    altitude : altitude en mètres (scalaire ou array)

    Retourne : string (si scalaire) ou array de strings (si array)
    """
    # Seuils
    coastal_end = zones['a_c4']    # Fin coastal (~50m)
    lowland_end = zones['a_l3']    # Fin lowland (~P50)
    midland_end = zones['a_m3']    # Fin midland (~P75)

    if np.isscalar(altitude):
        if altitude < coastal_end:
            return 'coastal'
        elif altitude < lowland_end:
            return 'lowland'
        elif altitude < midland_end:
            return 'midland'
        else:
            return 'highland'
    else:
        # Array : retourner array de zones
        result = np.empty(altitude.shape, dtype=object)
        result[altitude < coastal_end] = 'coastal'
        result[(altitude >= coastal_end) & (altitude < lowland_end)] = 'lowland'
        result[(altitude >= lowland_end) & (altitude < midland_end)] = 'midland'
        result[altitude >= midland_end] = 'highland'
        return result


def get_slope_zone(slope_deg, slope_p90):
    """
    Détermine la zone de pente : 'flat', 'gentle', 'moderate', 'steep'

    slope_deg : pente en degrés (scalaire ou array)
    slope_p90 : percentile 90 des pentes (calibration adaptative)

    Retourne : string (si scalaire) ou array de strings (si array)

    Seuils HYBRIDES :
    - flat adaptatif (selon terrain, max 12°) -> chaque carte a son "plat"
    - gentle/moderate/steep fixes (universels géologiques) -> Rock dès 20° partout
    """
    # flat adaptatif (max 12° pour éviter trop large sur cartes montagneuses)
    flat_thresh = min(slope_p90 * 0.36, 12.0)

    # Seuils fixes universels (calibrés selon tests utilisateur ZBK)
    gentle_end = 20.0    # Pentes douces
    moderate_end = 35.0  # Zones rocheuses principales 20-35° (au lieu de 30°)
    # steep : >= 35° zones très pentues

    if np.isscalar(slope_deg):
        if slope_deg < flat_thresh:
            return 'flat'
        elif slope_deg < gentle_end:
            return 'gentle'
        elif slope_deg < moderate_end:
            return 'moderate'
        else:
            return 'steep'
    else:
        # Array
        result = np.empty(slope_deg.shape, dtype=object)
        result[slope_deg < flat_thresh] = 'flat'
        result[(slope_deg >= flat_thresh) & (slope_deg < gentle_end)] = 'gentle'
        result[(slope_deg >= gentle_end) & (slope_deg < moderate_end)] = 'moderate'
        result[slope_deg >= moderate_end] = 'steep'
        return result


def get_sediment_zone(sediment):
    """
    Détermine la zone d'humidité : 'dry', 'moist', 'wet'

    sediment : valeur sediment 0-1 (scalaire ou array)

    Retourne : string (si scalaire) ou array de strings (si array)
    """
    # Seuils fixes (écologiques)
    if np.isscalar(sediment):
        if sediment < 0.35:
            return 'dry'
        elif sediment < 0.65:
            return 'moist'
        else:
            return 'wet'
    else:
        # Array
        result = np.empty(sediment.shape, dtype=object)
        result[sediment < 0.35] = 'dry'
        result[(sediment >= 0.35) & (sediment < 0.65)] = 'moist'
        result[sediment >= 0.65] = 'wet'
        return result


def get_curvature_zone(curvature):
    """
    Détermine la zone de courbure : 'concave', 'neutral', 'convex'

    curvature : valeur curvature -1 à +1 (scalaire ou array)

    Retourne : string (si scalaire) ou array de strings (si array)
    """
    # Seuils fixes (topographiques)
    if np.isscalar(curvature):
        if curvature < -0.15:
            return 'concave'
        elif curvature <= 0.15:
            return 'neutral'
        else:
            return 'convex'
    else:
        # Array
        result = np.empty(curvature.shape, dtype=object)
        result[curvature < -0.15] = 'concave'
        result[(curvature >= -0.15) & (curvature <= 0.15)] = 'neutral'
        result[curvature > 0.15] = 'convex'
        return result


def generate_perlin_noise_2d(shape, scale=0.05, seed=42):
    """
    Génère un bruit Perlin-like 2D simplifié pour variations organiques.

    Args:
        shape: (H, W) dimensions du tableau
        scale: échelle du bruit (0.01=grandes zones, 0.5=petites taches)
        seed: graine aléatoire pour reproductibilité

    Returns:
        np.array float32 [0-1]
    """
    np.random.seed(seed)
    H, W = shape

    # Grille basse résolution
    grid_size = max(2, int(min(H, W) * scale))
    grid_h = max(2, H // grid_size)
    grid_w = max(2, W // grid_size)

    # Générer valeurs aléatoires sur grille
    grid = np.random.rand(grid_h, grid_w).astype(np.float32)

    # Interpolation bilinéaire pour agrandir (via cv2.resize)
    noise = cv2.resize(grid, (W, H), interpolation=cv2.INTER_LINEAR)

    # Normaliser 0-1
    noise = (noise - noise.min()) / (noise.max() - noise.min() + 1e-8)

    return noise


def compute_texture_scores_simple(h_chunk, s_chunk, c_chunk, min_alt, alt_range, biome_config):
    """
    Système SIMPLIFIÉ style UE5 : slope + altitude + curvature, conditions min/max.

    Pas de vote, pas de normalisation complexe.
    Chaque texture a des conditions (min/max), et une priority.
    Les textures qui matchent sont triées par priority, top-3 gardés, normalisés.

    NOUVEAU : Applique du bruit Perlin pour transitions organiques (±10% variation).

    Args:
        h_chunk: heightmap normalisée 0-1
        s_chunk: slope en degrés 0-90
        c_chunk: curvature normalisée -1 à +1
        min_alt, alt_range: pour convertir heightmap en altitude réelle
        biome_config: dict avec textures et leurs conditions

    Returns:
        dict {texture_stem: np.array float32 [0-1]}
    """
    H, W = h_chunk.shape

    # Altitude normalisée 0-1
    alt_norm = h_chunk.astype(np.float32)

    # Slope en degrés
    slope_deg = s_chunk.astype(np.float32)

    # Curvature -1 à +1 (convexe positif, concave négatif)
    curv = c_chunk.astype(np.float32)

    # Pour chaque texture, calculer son "match score" (0 ou intensity)
    texture_matches = {}
    texture_priorities = {}

    textures_config = biome_config.get('textures', {})

    for tex_name, tex_config in textures_config.items():
        # Initialiser match à 1.0 partout
        match = np.ones((H, W), dtype=np.float32)

        # Vérifier conditions altitude
        # Support NOUVEAU format (altitude_min_meters absolu) ET ANCIEN (altitude_min normalisé)
        if 'altitude_min_meters' in tex_config:
            # Convertir mètres absolu -> normalisé selon carte
            alt_min_norm = (tex_config['altitude_min_meters'] - min_alt) / alt_range
            match = np.where(alt_norm >= alt_min_norm, match, 0.0)
        elif 'altitude_min' in tex_config:
            # Ancien format (déjà normalisé)
            match = np.where(alt_norm >= tex_config['altitude_min'], match, 0.0)

        if 'altitude_max_meters' in tex_config:
            # Convertir mètres absolu -> normalisé selon carte
            alt_max_norm = (tex_config['altitude_max_meters'] - min_alt) / alt_range
            match = np.where(alt_norm <= alt_max_norm, match, 0.0)
        elif 'altitude_max' in tex_config:
            # Ancien format (déjà normalisé)
            match = np.where(alt_norm <= tex_config['altitude_max'], match, 0.0)

        # Vérifier conditions slope
        if 'slope_min' in tex_config:
            match = np.where(slope_deg >= tex_config['slope_min'], match, 0.0)
        if 'slope_max' in tex_config:
            match = np.where(slope_deg <= tex_config['slope_max'], match, 0.0)

        # Vérifier conditions curvature
        if 'curvature_min' in tex_config:
            match = np.where(curv >= tex_config['curvature_min'], match, 0.0)
        if 'curvature_max' in tex_config:
            match = np.where(curv <= tex_config['curvature_max'], match, 0.0)

        # Multiplier par intensity
        intensity = tex_config.get('intensity', 1.0)
        match *= intensity

        texture_matches[tex_name] = match
        texture_priorities[tex_name] = tex_config.get('priority', 0)

    # ── Appliquer bruit Perlin pour transitions organiques ──────────────────
    # Génère un bruit différent par texture pour variation naturelle
    # MAIS pas pour SeaBed/Rock (doivent être uniformes)
    noise_amplitude = 0.1  # ±10% variation (réduit de 0.3 pour éviter trous)
    textures_sans_bruit = {'SeaBed_01', 'Rock_01', 'Grass_03_coastal'}  # Uniformes, pas de variation

    for i, (tex_name, match) in enumerate(texture_matches.items()):
        if tex_name in textures_sans_bruit:
            continue  # Pas de bruit pour ces textures

        # Seed différent par texture pour éviter corrélation
        noise = generate_perlin_noise_2d((H, W), scale=0.05, seed=42 + i)
        # Appliquer variation : score × (0.7 à 1.3)
        noise_factor = (1.0 - noise_amplitude) + (2.0 * noise_amplitude * noise)
        texture_matches[tex_name] = match * noise_factor

    # Pour chaque pixel, garder top-3 par priority puis normaliser
    result = {}
    for stem in texture_matches.keys():
        result[stem] = np.zeros((H, W), dtype=np.float32)

    # Traiter par chunks pour performance
    CHUNK_SIZE = 256
    for r0 in range(0, H, CHUNK_SIZE):
        r1 = min(r0 + CHUNK_SIZE, H)
        for c0 in range(0, W, CHUNK_SIZE):
            c1 = min(c0 + CHUNK_SIZE, W)

            # Extraire chunk
            chunk_matches = {stem: texture_matches[stem][r0:r1, c0:c1]
                            for stem in texture_matches.keys()}

            # Pour chaque pixel du chunk
            for r in range(r1 - r0):
                for c in range(c1 - c0):
                    # Collecter textures actives (match > 0)
                    active = []
                    for stem, match_array in chunk_matches.items():
                        score = match_array[r, c]
                        if score > 0.0:
                            active.append((stem, score, texture_priorities[stem]))

                    if not active:
                        # Aucune texture match -> laisser à 0
                        # SeaBed sera override après pour les zones < 0m
                        continue

                    # Trier par priority (haute -> basse), puis par score
                    active.sort(key=lambda x: (x[2], x[1]), reverse=True)

                    # Garder top-3
                    top3 = active[:3]

                    # Normaliser (somme = 1.0)
                    total = sum(x[1] for x in top3)
                    if total > 0:
                        for stem, score, _ in top3:
                            result[stem][r0 + r, c0 + c] = score / total

    return result


def compute_texture_scores_biome(h_chunk, s_chunk, c_chunk, sed_chunk,
                                   min_alt, alt_range, zones, slope_p90,
                                   biome_config):
    """
    Calcule les scores de textures via système de vote par masque (biome).

    Chaque masque (altitude, slope, sediment, curvature) vote pour 2-4 textures.
    NOUVEAU (2026-06-03) : Pas de filtrage par altitude.
    - altitude : textures spécifiques zone (Pebbles coastal, MountainGrass highland)
    - slope : logique GLOBALE Rock (pentes raides -> Rock partout)
    - sediment : logique GLOBALE humidité
    - curvature : logique GLOBALE accumulation/érosion
    Les scores sont additionnés puis normalisés.

    Retourne : dict {stem: array_2D} avec scores normalisés
    """
    # Conversion des données brutes
    alt_m = (min_alt + h_chunk * alt_range).astype(np.float32)
    slope_deg = s_chunk  # Déjà en degrés après ×90
    curv = c_chunk       # Déjà remappé -1/+1
    sed = sed_chunk      # 0-1

    # Déterminer zones pour chaque pixel
    alt_zones = get_altitude_zone(alt_m, zones)
    slope_zones = get_slope_zone(slope_deg, slope_p90)
    sed_zones = get_sediment_zone(sed)
    curv_zones = get_curvature_zone(curv)

    # Tableaux du biome
    biome_textures = biome_config['textures']

    # Initialiser scores
    shape = h_chunk.shape
    scores = {}

    # Parcourir chaque pixel et accumuler votes
    # NOTE: Pour performance, on va vectoriser par zone dominante
    # Pour l'instant, version simple pixel par pixel (optimisation future)

    # Zones uniques
    unique_alt = np.unique(alt_zones)
    unique_slope = np.unique(slope_zones)
    unique_sed = np.unique(sed_zones)
    unique_curv = np.unique(curv_zones)

    # Pour chaque combinaison de zones, calculer votes
    for az in unique_alt:
        for sz in unique_slope:
            for sedz in unique_sed:
                for cz in unique_curv:
                    # Masque pixels avec cette combinaison
                    mask = (alt_zones == az) & (slope_zones == sz) & (sed_zones == sedz) & (curv_zones == cz)

                    if not np.any(mask):
                        continue

                    # Accumuler votes des 4 masques
                    pixel_scores = {}

                    # Vote ALTITUDE (textures spécifiques zone)
                    for texture, weight in biome_textures['altitude'][az].items():
                        if texture.startswith('_'):  # Skip comments
                            continue
                        pixel_scores[texture] = pixel_scores.get(texture, 0.0) + weight

                    # Vote SLOPE (logique GLOBALE Rock - s'applique partout)
                    for texture, weight in biome_textures['slope'][sz].items():
                        if texture.startswith('_'):
                            continue
                        pixel_scores[texture] = pixel_scores.get(texture, 0.0) + weight

                    # Vote SEDIMENT (logique GLOBALE humidité)
                    for texture, weight in biome_textures['sediment'][sedz].items():
                        if texture.startswith('_'):
                            continue
                        pixel_scores[texture] = pixel_scores.get(texture, 0.0) + weight

                    # Vote CURVATURE (logique GLOBALE accumulation/érosion)
                    for texture, weight in biome_textures['curvature'][cz].items():
                        if texture.startswith('_'):
                            continue
                        pixel_scores[texture] = pixel_scores.get(texture, 0.0) + weight

                    # Appliquer scores à ce groupe de pixels
                    for texture, score in pixel_scores.items():
                        if texture not in scores:
                            scores[texture] = np.zeros(shape, dtype=np.float32)
                        scores[texture][mask] = score

    # Normaliser scores (somme = 1.0 par pixel)
    # Calculer somme totale par pixel
    total = np.zeros(shape, dtype=np.float32)
    for texture_scores in scores.values():
        total += texture_scores

    # Éviter division par zéro
    total = np.maximum(total, 1e-6)

    # Normaliser
    for texture in scores:
        scores[texture] /= total

    return scores


def _terrain_profile(h_land_norm: np.ndarray) -> dict:
    """
    Analyse la forme de la courbe hypsométrique des pixels terrestres normalisés [0-1].
    Retourne le type de profil et les niveaux de percentile adaptés pour chaque zone clé.

    Types détectés :
      'flat'     — terrain plat/côtier, majorité basse altitude
      'balanced' — distribution équilibrée (île volcanique type ZBK) -> défauts actuels
      'plateau'  — masse concentrée à moyenne/haute altitude
      'mountain' — fort relief ou altitude moyenne élevée
    """
    if len(h_land_norm) < 100:
        return {'type': 'balanced', 'highland_start_pct': 58,
                'lowland_end_pct': 50, 'coastal_end_pct': 12,
                'mean_norm': 0.0, 'spread': 0.0}

    p15      = float(np.percentile(h_land_norm, 15))
    p85      = float(np.percentile(h_land_norm, 85))
    mean_h   = float(np.mean(h_land_norm))
    spread   = p85 - p15   # plage contenant 70 % des pixels terrestres (0-1)

    if mean_h < 0.32 and spread < 0.45:
        # Plaine côtière : majorité des pixels basse altitude, peu de relief
        # -> alpine très rare, prairie étendue, zone côtière plus large
        terrain_type       = 'flat'
        highland_start_pct = 75
        lowland_end_pct    = 62
        coastal_end_pct    = 15

    elif mean_h > 0.55 or spread > 0.65:
        # Fort relief ou altitude moyenne élevée
        # -> alpine précoce, prairie compressée, côte minimale
        terrain_type       = 'mountain'
        highland_start_pct = 45
        lowland_end_pct    = 38
        coastal_end_pct    = 8

    elif mean_h > 0.48 and spread < 0.42:
        # Plateau : distribution concentrée à altitude élevée
        # -> alpine anticipée, prairie réduite
        terrain_type       = 'plateau'
        highland_start_pct = 50
        lowland_end_pct    = 40
        coastal_end_pct    = 10

    else:
        # Distribution équilibrée — valeurs calibrées sur ZBK
        terrain_type       = 'balanced'
        highland_start_pct = 58
        lowland_end_pct    = 50
        coastal_end_pct    = 12

    return {
        'type':                terrain_type,
        'highland_start_pct':  highland_start_pct,
        'lowland_end_pct':     lowland_end_pct,
        'coastal_end_pct':     coastal_end_pct,
        'mean_norm':           round(mean_h, 3),
        'spread':              round(spread, 3),
    }


def calibrate_zones(alt_max: float, slope_p90: float,
                    alt_pcts: dict = None,
                    h_land_norm: np.ndarray = None,
                    alt_min: float = 0.0) -> dict:
    """
    Calcule les seuils géologiques adaptés au terrain courant.

    Priorité :
      1. h_land_norm fourni -> analyse hypsométrique complète (nouveau chemin)
         Détecte le profil terrain (flat/balanced/plateau/mountain) et adapte
         les seuils de zone en conséquence.
      2. alt_pcts fourni -> percentiles pré-calculés, seuils fixes (ancien chemin)
      3. Aucun -> fallback fractions de alt_max

    Le dict retourné contient en plus '_terrain_type', '_mean_norm', '_spread'
    si h_land_norm a été fourni.
    """
    # Auto-détection niveau mer (pour cartes avec mer enfouie)
    # Si la carte a beaucoup de pixels très négatifs (mer profonde), détecter le vrai niveau
    if h_land_norm is not None and len(h_land_norm) >= 100:
        h_sorted = np.sort(h_land_norm)
        p7 = float(h_sorted[int(len(h_sorted) * 0.073)])  # 7.3% percentile
        p10 = float(h_sorted[int(len(h_sorted) * 0.10)])
        p20 = float(h_sorted[int(len(h_sorted) * 0.20)])

        # Convertir en altitude réelle
        p7_alt = alt_min + p7 * (alt_max - alt_min)
        p10_alt = alt_min + p10 * (alt_max - alt_min)
        p20_alt = alt_min + p20 * (alt_max - alt_min)

        # Si p7 < -20m ET saut brusque vers p10/p20 -> mer enfouie détectée
        if p7_alt < -20.0 and (p10_alt - p7_alt) > 10.0:
            sea = float(p7_alt)  # Niveau mer = percentile 7% (plateau bathymétrique)
        else:
            sea = 0.0  # Niveau mer standard
    else:
        sea = 0.0  # Pas de données pour analyse, supposer 0m

    R   = max(alt_max - alt_min, 1.0)
    sp  = max(slope_p90, 0.05)
    tprof = None

    if h_land_norm is not None and len(h_land_norm) >= 100:
        # ── Chemin adaptatif : analyse de la courbe hypsométrique ────────────
        tprof  = _terrain_profile(h_land_norm)
        h_pct  = tprof['highland_start_pct']   # ex. 45 / 58 / 75
        l_pct  = tprof['lowland_end_pct']       # ex. 38 / 50 / 62
        c_pct  = tprof['coastal_end_pct']       # ex. 8  / 12 / 15

        # Calcul à la demande de tous les niveaux nécessaires
        needed = sorted(set([
            5, 8, c_pct, min(c_pct + 8, 35),
            20, 30, l_pct, min(l_pct + 12, 90),
            h_pct, 85,
        ]))
        pct_vals = np.percentile(h_land_norm, needed)
        pm = {p: float(alt_min + v * R) for p, v in zip(needed, pct_vals)}

        def _p(lvl, frac):
            return pm.get(lvl, alt_min + R * frac)

        # Zone coastal = littoral 0-30m ABSOLU (niveau Reforger, pas détection auto)
        # Sur maps avec mer creusée (Zimnitrita < 0m), 0m = niveau eau Reforger
        a_c1 = 0.0         # Début littoral (0m Reforger)
        a_c2 = 10.0        # Montée transition
        a_c3 = 25.0        # Descente transition
        a_c4 = 30.0        # Fin littoral
        a_l1 = max(sea + 1.0,  _p(5,               0.05))
        a_l2 = _p(30,                               0.25)
        a_l3 = _p(l_pct,                            0.46)
        a_l4 = _p(min(l_pct + 12, 90),             0.63)
        a_m1 = _p(20,                               0.33)
        a_m2 = _p(l_pct,                            0.53)
        a_m3 = _p(min(l_pct + 22, 90),             0.77)
        a_m4 = _p(85,                               0.95)
        a_h1 = _p(h_pct,                            0.56)
        a_h2 = _p(85,                               0.82)

    elif alt_pcts:
        # ── Chemin classique : percentiles pré-calculés (rétro-compatibilité) ─
        p5  = alt_pcts['p5'];  p8  = alt_pcts['p8'];  p12 = alt_pcts['p12']
        p20 = alt_pcts['p20']; p30 = alt_pcts['p30']; p50 = alt_pcts['p50']
        p58 = alt_pcts['p58']; p62 = alt_pcts['p62']; p72 = alt_pcts['p72']
        p85 = alt_pcts['p85']
        # Zone coastal fixe (littoral 0-30m ABSOLU)
        a_c1 = 0.0;  a_c2 = 10.0;  a_c3 = 25.0;  a_c4 = 30.0
        a_l1 = max(sea + 1.0, p5);  a_l2 = p30;  a_l3 = p50;  a_l4 = p62
        a_m1 = p20;  a_m2 = p50;  a_m3 = p72;  a_m4 = p85
        a_h1 = p58;  a_h2 = p85

    else:
        # ── Fallback : fractions fixes de alt_max ────────────────────────────
        # Zone coastal fixe (littoral 0-30m ABSOLU)
        a_c1 = 0.0;  a_c2 = 10.0;  a_c3 = 25.0;  a_c4 = 30.0
        a_l1 = sea + R * 0.05;  a_l2 = sea + R * 0.25
        a_l3 = sea + R * 0.46;  a_l4 = sea + R * 0.63
        a_m1 = sea + R * 0.33;  a_m2 = sea + R * 0.53
        a_m3 = sea + R * 0.77;  a_m4 = sea + R * 0.95
        a_h1 = sea + R * 0.56;  a_h2 = sea + R * 0.82

    zones = {
        'a_sea': sea,     # Niveau mer auto-détecté
        'a_c1': a_c1,     # Début coastal (littoral 0m)
        'a_c2': a_c2,  'a_c3': a_c3,  'a_c4': a_c4,
        'a_l1': a_l1,  'a_l2': a_l2,  'a_l3': a_l3,  'a_l4': a_l4,
        'a_m1': a_m1,  'a_m2': a_m2,  'a_m3': a_m3,  'a_m4': a_m4,
        'a_h1': a_h1,  'a_h2': a_h2,
        'sl_flat':      sp * 0.36,
        'sl_g1':  sp * 0.14,  'sl_g2': sp * 0.50,  'sl_g3': sp * 0.72,  'sl_g4': sp * 1.00,
        'sl_mo1': sp * 0.50,  'sl_mo2': sp * 0.93,
        'sl_mo3': sp * 1.36,  'sl_mo4': sp * 1.79,
        'sl_st1': sp * 0.72,  'sl_st2': sp * 1.30,
        'sl_rh1': sp * 0.22,  'sl_rh2': sp * 0.65,
    }
    if tprof:
        zones['_terrain_type'] = tprof['type']
        zones['_mean_norm']    = tprof['mean_norm']
        zones['_spread']       = tprof['spread']
    return zones


def compute_chunk_blends(h_chunk, s_chunk, c_chunk, sed_chunk, min_alt, alt_range, zones, biome_config=None):
    """
    zones : dict retourné par calibrate_zones() — seuils adaptés au terrain courant.
    biome_config : dict biome (nouveau format v2) ou None (charge temperate_simple par défaut)
    """
    alt_m = (min_alt + h_chunk * alt_range).astype(np.float32)
    z = zones

    # Signal sous-marin : basé sur niveau mer auto-détecté
    sub      = smoothstep(z['a_sea'] - 2.0, z['a_sea'] - 12.0, alt_m)
    coastal  = smoothstep(z['a_c1'], z['a_c2'], alt_m) * (1.0 - smoothstep(z['a_c3'], z['a_c4'], alt_m))
    lowland  = smoothstep(z['a_l1'], z['a_l2'], alt_m) * (1.0 - smoothstep(z['a_l3'], z['a_l4'], alt_m))
    midland  = smoothstep(z['a_m1'], z['a_m2'], alt_m) * (1.0 - smoothstep(z['a_m3'], z['a_m4'], alt_m))
    highland = smoothstep(z['a_h1'], z['a_h2'], alt_m)

    flat     = 1.0 - smoothstep(0.0,         z['sl_flat'], s_chunk)
    gentle   = smoothstep(z['sl_g1'],  z['sl_g2'],  s_chunk) * (1.0 - smoothstep(z['sl_g3'],  z['sl_g4'],  s_chunk))
    moderate = smoothstep(z['sl_mo1'], z['sl_mo2'], s_chunk) * (1.0 - smoothstep(z['sl_mo3'], z['sl_mo4'], s_chunk))
    steep    = smoothstep(z['sl_st1'], z['sl_st2'], s_chunk)

    convex   = smoothstep(0.08, 0.45,  c_chunk)
    concave  = smoothstep(0.08, 0.45, -c_chunk)

    dry      = 1.0 - smoothstep(0.10, 0.35, sed_chunk)
    moist    = smoothstep(0.12, 0.40, sed_chunk) * (1.0 - smoothstep(0.58, 0.82, sed_chunk))
    wet      = smoothstep(0.48, 0.78, sed_chunk)

    ravine        = concave * wet                          # Ravines très humides (fond talweg)
    valley        = concave * (moist + wet * 0.5)        # Vallées/creux généraux (accumulation)
    cliff_fissure = steep   * concave
    crest         = highland * convex
    # Élargir coastal pour inclure pentes modérées (sinon BeachGrass = 0 sur côtes réelles)
    coast_flat    = coastal  * (flat + gentle * 0.9 + moderate * 0.5)
    coast_talus   = coastal  * (moderate + steep * 0.3)
    coast_gentle  = coastal * smoothstep(5.0, 10.0, s_chunk) * (1.0 - smoothstep(12.0, 20.0, s_chunk))
    prairie_low   = lowland  * (flat + gentle) * (1.0 - steep) * (1.0 - ravine) * (1.0 - valley * 0.5)
    prairie_mid   = midland  * (flat + gentle) * (1.0 - steep) * (1.0 - valley * 0.5)
    alpage_dry    = highland * (flat + gentle) * dry
    alpage_wet    = highland * (flat + gentle) * (moist + wet * 0.4)
    mid_slope     = (lowland + midland) * moderate * (1.0 - steep) * (1.0 - ravine)

    # ═══════════════════════════════════════════════════════════════════════════
    # NOUVEAU SYSTÈME : Vote par masque (biome config)
    # ═══════════════════════════════════════════════════════════════════════════

    # Si biome_config non fourni, charger temperate_simple par défaut
    if biome_config is None:
        biome_config = load_biome_config('temperate_simple')

    # Calculer scores via système SIMPLE (slope + altitude + curvature)
    sc = compute_texture_scores_simple(
        h_chunk, s_chunk, c_chunk,
        min_alt, alt_range,
        biome_config
    )

    # Ajouter textures manquantes (SeaBed, Grass_02 base)
    if "SeaBed_01" not in sc:
        sc["SeaBed_01"] = np.zeros(h_chunk.shape, dtype=np.float32)
    if BASE_STEM not in sc:
        sc[BASE_STEM] = np.zeros(h_chunk.shape, dtype=np.float32)

    # Signal sous-marin : appliqué APRÈS vote (override)
    # SeaBed pour toute altitude < 0m (niveau eau Reforger, pas détection auto)
    # Transition douce 0m -> -10m
    altitude_meters = (min_alt + h_chunk * alt_range).astype(np.float32)
    sub = smoothstep(0.0, -10.0, altitude_meters)
    sc["SeaBed_01"] = sub  # Override : SeaBed dominant sous l'eau

    # MERGER Pebbles + BeachGrass -> Coastal_Mix (réduction nombre de textures)
    if "Pebbles_01" in sc and "BeachGrass_01" in sc:
        # Combiner les deux masques côtiers en un seul
        sc["Coastal_Mix"] = sc["Pebbles_01"] + sc["BeachGrass_01"]
        del sc["Pebbles_01"]
        del sc["BeachGrass_01"]

    # Remplir pixels vides (somme = 0) avec texture de base
    # Reforger CRASH si des pixels n'ont aucune texture
    total = sum(sc.values())
    empty_mask = (total == 0)
    if np.any(empty_mask):
        # Utiliser Grass_02 comme fallback (texture neutre)
        sc[BASE_STEM] = np.where(empty_mask, 1.0, sc[BASE_STEM])

    return sc


# ---------------------------------------------------------------------------
# Pipeline sans UI — callbacks injectables
# ---------------------------------------------------------------------------

class TexturePipeline:
    MAX_FALLBACK_DERIVATION_SIZE = 12000
    CHUNK_ROWS         = 256
    SQUEEZE_CHUNK_SIZE = 32
    N_WORKERS          = max(1, (os.cpu_count() or 4) - 2)
    DIR_RAW   = os.path.join("pipeline_temp", "01_Raw_Matrices")
    DIR_MASKS = os.path.join("pipeline_temp", "02_Masks_NPY")
    DIR_PNG   = os.path.join("generated",     "terrain_masks")

    # Limites Reforger supportées et marge réservée (base + mapper interne)
    REFORGER_LIMITS   = (5, 7)
    _RESERVED_SLOTS   = 2

    # Résolution maximale de traitement interne (RAM).
    # 4096 = réduit pour GPU avec 16 GB VRAM (évite crash Reforger)
    # 8192 nécessite ~21 GB VRAM lors de l'import masques
    # RAM : ~64 MiB/stem à 4096px -> ~1 GiB pic temporaire (16 stems actifs).
    MAX_PROCESS_PX = 4096  # Réduit de 8192 pour compatibilité VRAM

    def __init__(self, log_fn=None, progress_fn=None, reforger_block_limit=4,
                 biome_stems=None, stem_scales=None, biome_config=None):
        if reforger_block_limit not in self.REFORGER_LIMITS:
            raise ValueError(f"reforger_block_limit doit être dans {self.REFORGER_LIMITS}")
        self.log_fn      = log_fn      or (lambda msg: None)
        self.progress_fn = progress_fn or (lambda pct: None)
        self.MAX_MATERIALS_PER_CHUNK = reforger_block_limit
        self.BLOCK_UNIQUE_LIMIT      = reforger_block_limit - self._RESERVED_SLOTS

        # NOUVEAU SYSTÈME (v2) : biome_config dict avec conditions min/max
        if biome_config:
            self._biome_config = biome_config
            self._use_new_system = True
            self._biome_stems = None
            self._stem_scales = None
        else:
            # ANCIEN SYSTÈME (v1) : stems + role_scales
            self._biome_config = None
            self._use_new_system = False
            self._biome_stems = list(biome_stems) if biome_stems else list(PIPELINE_STEMS)
            self._stem_scales = dict(stem_scales) if stem_scales else {s: 1.0 for s in self._biome_stems}

        # Stats de calibration (sauvegardées pour affichage dans UI)
        self.calibration_stats = {}

    @property
    def active_stems(self):
        """Retourne la liste des stems actifs selon le système (nouveau ou ancien)"""
        if self._use_new_system:
            return list(self._biome_config['textures'].keys())
        else:
            return self._biome_stems

    def _log(self, msg):
        try:
            self.log_fn(msg)
        except Exception:
            pass

    def _progress(self, value):
        try:
            self.progress_fn(value)
        except Exception:
            pass

    # ── Helpers project.json ─────────────────────────────────────────────────

    @staticmethod
    def derive_grid_from_project(proj: dict):
        """
        Extrait target_size, process_size, blocs_cote, taille_bloc, alt_min, alt_max
        depuis la section reforger_grid du project.json.

        process_size = min(target_size, MAX_PROCESS_PX) — résolution effective de
        traitement. Sur les maps > 32513px (Zimnitrita 65025px), toutes les étapes
        sauf l'export utilisent cette résolution réduite.
        taille_bloc est dérivé de process_size afin que chaque bloc de traitement
        corresponde au même volume physique que le bloc Reforger 32m×32m cible.
        """
        grid = proj["reforger_grid"]
        # Deux schémas possibles selon la version du projet
        surf = grid.get("surface_map_total_px") or grid.get("surface_total_px")
        target_size = surf[0] if surf else grid["total_vertices"][0]
        tiles_x      = grid.get("tiles_x") or grid.get("tiles", [0])[0]
        bpt_x        = grid.get("blocks_per_tile_x") or grid.get("blocks_per_tile", [0])[0]
        blocs_cote   = tiles_x * bpt_x
        alt_min      = grid["height_min_m"]
        alt_max      = grid["height_max_m"]
        process_size = min(target_size, TexturePipeline.MAX_PROCESS_PX)
        taille_bloc  = (process_size - 1) // blocs_cote + 1
        return target_size, process_size, blocs_cote, taille_bloc, alt_min, alt_max

    @staticmethod
    def build_paths_from_project(proj: dict, project_dir: str) -> dict:
        """
        Construit le dict de chemins attendu par run_pipeline/ingest_all
        depuis les assets du project.json.
        Clés retournées : heightmap, slope, curvature, sediment, satmap.
        """
        def _resolve(p_str):
            if not p_str:
                return ""
            p = os.path.normpath(p_str)
            return p if os.path.isabs(p) else os.path.normpath(os.path.join(project_dir, p))

        assets = proj["assets"]
        hm     = assets.get("heightmap", {})
        it     = assets.get("it_masks", {})
        sat    = assets.get("satmap", {})

        hm_path = hm.get("path", "")
        if not hm_path and hm.get("filename"):
            hm_path = os.path.join(project_dir, "sources", hm["filename"])
        else:
            hm_path = _resolve(hm_path)

        sat_path = _resolve(sat.get("path", sat.get("filename", "")))

        return {
            "heightmap": hm_path,
            "slope":     _resolve(it.get("slopes", "")),
            "curvature": _resolve(it.get("curvature", "")),
            "sediment":  _resolve(it.get("sediment", "")),
            "satmap":    sat_path,
        }

    def _mask_fname(self, stem: str) -> str:
        """Nom de fichier numéroté selon la position du stem dans le biome actif."""
        return f"mask_{self.active_stems.index(stem) + 1:02d}_{stem}"

    @staticmethod
    def resolve_biome(biome_id: str, biomes_path: str):
        """
        Charge un biome depuis biomes.json et retourne (stems, stem_scales).

        stems       : liste ordonnée des stems actifs pour ce biome.
        stem_scales : dict {stem: float} — multiplicateur de score par stem,
                      calculé depuis role_scales du biome via STEM_ROLES.
        """
        with open(biomes_path, "r", encoding="utf-8") as fh:
            biomes_data = json.load(fh)
        biome = biomes_data.get("biomes", {}).get(biome_id)
        if not biome:
            raise ValueError(f"Biome '{biome_id}' introuvable dans {biomes_path}")
        stems = list(biome.get("stems", PIPELINE_STEMS))
        role_scales = biome.get("role_scales", {})
        stem_scales = {
            s: role_scales.get(STEM_ROLES.get(s, ""), 1.0)
            for s in stems
        }
        return stems, stem_scales

    @staticmethod
    def apply_auto_calibration(biome_config: dict, calibration: dict) -> dict:
        """
        Applique la calibration automatique aux seuils du biome.

        Remplace les altitude_min/max_meters par les valeurs calibrées.
        """
        if not calibration or 'coastal' not in calibration:
            return biome_config

        # Copier pour ne pas modifier l'original
        biome = biome_config.copy()
        biome['textures'] = biome_config['textures'].copy()

        coastal_cal = calibration['coastal']
        lowland_cal = calibration.get('lowland', {})
        midland_cal = calibration.get('midland', {})
        highland_cal = calibration.get('highland', {})

        # Appliquer calibration à chaque texture
        for tex_name, tex_config in biome['textures'].items():
            tex_copy = tex_config.copy()

            # Détecter zone (coastal, lowland, midland, highland)
            # Côtière : si altitude_max_meters <= 30m dans le JSON original
            if 'altitude_max_meters' in tex_config and tex_config['altitude_max_meters'] <= 30:
                # Texture côtière : appliquer seuils coastal
                tex_copy['altitude_min_meters'] = coastal_cal.get('altitude_min_meters', tex_config.get('altitude_min_meters', 0))
                tex_copy['altitude_max_meters'] = coastal_cal.get('altitude_max_meters', tex_config.get('altitude_max_meters'))
                tex_copy['_calibrated'] = 'coastal'

            biome['textures'][tex_name] = tex_copy

        return biome

    @staticmethod
    def load_biome_config(biome_id: str, biomes_path: str, project_path: str = None):
        """
        Charge un biome (nouveau format v2 avec biome_file).

        Si project_path fourni et calibration.json existe,
        applique automatiquement les seuils calibrés.

        Args:
            biome_id: ID du biome à charger
            biomes_path: Chemin vers biomes.json
            project_path: Chemin vers le projet (optionnel, pour auto-calibration)

        Retourne:
            dict biome_config si nouveau format (biome_file existe)
            None si ancien format (stems + role_scales)
        """
        with open(biomes_path, "r", encoding="utf-8") as fh:
            biomes_data = json.load(fh)
        biome = biomes_data.get("biomes", {}).get(biome_id)
        if not biome:
            raise ValueError(f"Biome '{biome_id}' introuvable dans {biomes_path}")

        # NOUVEAU FORMAT : biome_file pointe vers data/biomes/*.json
        if "biome_file" in biome:
            biome_file = biome["biome_file"]
            # Résoudre chemin relatif depuis biomes.json
            if not os.path.isabs(biome_file):
                biomes_dir = os.path.dirname(biomes_path)
                biome_file = os.path.join(biomes_dir, biome_file)

            if not os.path.exists(biome_file):
                raise FileNotFoundError(f"Fichier biome introuvable : {biome_file}")

            with open(biome_file, "r", encoding="utf-8") as f:
                biome_config = json.load(f)

            # AUTO-CALIBRATION : charger calibration.json si disponible
            if project_path:
                calibration_file = os.path.join(project_path, 'calibration.json')
                if os.path.exists(calibration_file):
                    with open(calibration_file, "r", encoding="utf-8") as f:
                        calibration = json.load(f)
                    biome_config = TexturePipeline.apply_auto_calibration(biome_config, calibration)
                    biome_config['_auto_calibrated'] = True

            return biome_config

        # ANCIEN FORMAT : pas de biome_file
        return None

    @staticmethod
    def list_biomes(biomes_path: str) -> dict:
        """Retourne {biome_id: label} depuis biomes.json. Vide si fichier absent."""
        if not os.path.exists(biomes_path):
            return {}
        with open(biomes_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return {bid: b.get("label", bid) for bid, b in data.get("biomes", {}).items()}

    # ── Normalisation ────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_01(matrix):
        lo, hi = float(np.min(matrix)), float(np.max(matrix))
        return (matrix - lo) / (hi - lo if hi > lo else 1.0)

    # ── Ingestion (étape 1) ──────────────────────────────────────────────────

    def ingest_all(self, paths_snap: dict, shape: tuple, dir_raw: str, alt_min: float = 0.0, alt_max: float = 1.0):
        """
        Charge et normalise tous les fichiers sources -> .npy dans dir_raw.
        paths_snap : dict avec clés heightmap, slope, curvature, sediment, satmap.
        shape      : (H, W) cible en pixels.
        alt_min, alt_max : altitudes min/max en mètres (pour normalisation PNG).
        """
        heightmap_norm = None

        h_path = paths_snap.get("heightmap", "")
        if h_path and os.path.exists(h_path):
            _h_ext = os.path.splitext(h_path)[1].lower()
            if _h_ext == ".asc":
                self._log("[HEIGHTMAP] Ingestion .asc (lent)...")
                raw_h   = np.loadtxt(h_path, skiprows=6)
                raw_h32 = raw_h.astype(np.float32)
                del raw_h
                rescaled = cv2.resize(raw_h32, shape, interpolation=cv2.INTER_CUBIC)
                del raw_h32
                np.save(os.path.join(dir_raw, "raw_heightmap_real_meters.npy"), rescaled)
                _lo = float(rescaled.min())
                _hi = float(rescaled.max())
                rescaled -= _lo
                if _hi > _lo:
                    rescaled /= (_hi - _lo)
                np.clip(rescaled, 0.0, 1.0, out=rescaled)
            else:
                self._log(f"[HEIGHTMAP] Ingestion {_h_ext.upper()}...")
                img = cv2.imread(h_path, cv2.IMREAD_UNCHANGED)
                if img is None:
                    raise ValueError(f"Lecture heightmap impossible : {h_path}")
                scale    = 65535.0 if img.dtype == np.uint16 else 255.0
                img32    = img.astype(np.float32) / scale
                del img
                rescaled = cv2.resize(img32, shape, interpolation=cv2.INTER_CUBIC)
                del img32
                np.clip(rescaled, 0.0, 1.0, out=rescaled)
                # Calculer _lo/_hi en mètres (PNG 0-1 mappe sur alt_min-alt_max)
                _lo = float(alt_min + rescaled.min() * (alt_max - alt_min))
                _hi = float(alt_min + rescaled.max() * (alt_max - alt_min))
            heightmap_norm = rescaled
            np.save(os.path.join(dir_raw, "raw_heightmap.npy"), heightmap_norm)

            # Sauvegarder normalization min/max pour conversion altitude
            norm_data = {"altitude_min": _lo, "altitude_max": _hi}
            with open(os.path.join(dir_raw, "normalization.json"), "w", encoding="utf-8") as f:
                json.dump(norm_data, f, indent=2)
            self._log(f"[NORMALIZATION] {_lo:.2f}m -> {_hi:.2f}m")
            del rescaled, heightmap_norm
            heightmap_norm = np.load(os.path.join(dir_raw, "raw_heightmap.npy"), mmap_mode="r")
            self._log("[HEIGHTMAP] OK")
        else:
            self._log("[HEIGHTMAP] Absent -> matrice neutre.")
            heightmap_norm = np.zeros(shape, dtype=np.float32)
            np.save(os.path.join(dir_raw, "raw_heightmap.npy"), heightmap_norm)

        can_derive = (
            shape[0] <= self.MAX_FALLBACK_DERIVATION_SIZE  # check bon marché en premier
            and not np.all(heightmap_norm == 0.0)
        )

        # slope, curvature, sediment, satmap
        for key in ("slope", "curvature", "sediment", "satmap"):
            path = paths_snap.get(key, "")
            if path and os.path.exists(path):
                self._log(f"[{key.upper()}] Chargement -> {shape[0]} px...")
                img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
                if img is None:
                    raise ValueError(f"Lecture impossible : {path}")
                img_r = cv2.resize(img, shape, interpolation=cv2.INTER_LINEAR)
                if img_r.ndim == 3:
                    img_r = cv2.cvtColor(img_r, cv2.COLOR_BGR2GRAY)
                scale = 65535.0 if img_r.dtype == np.uint16 else 255.0
                normalized = img_r.astype(np.float32) / scale
                # Convertir slope 0-1 -> 0-90° (degrés)
                if key == "slope":
                    normalized *= 90.0
                # Convertir curvature 0-1 -> -1 à +1 (0=concave, 0.5=neutre, 1=convexe)
                elif key == "curvature":
                    normalized = (normalized - 0.5) * 2.0
                np.save(os.path.join(dir_raw, f"raw_{key}.npy"), normalized)
                self._log(f"[{key.upper()}] OK")

            elif key == "slope" and can_derive:
                self._log("[SLOPE] Calcul automatique (Sobel)...")
                sx = cv2.Sobel(heightmap_norm, cv2.CV_32F, 1, 0, ksize=3)
                sy = cv2.Sobel(heightmap_norm, cv2.CV_32F, 0, 1, ksize=3)
                grad = self._normalize_01(np.sqrt(sx**2 + sy**2)).astype(np.float32)
                np.save(os.path.join(dir_raw, "raw_slope.npy"), grad)
                self._log("[SLOPE] OK (fallback Sobel)")

            elif key == "curvature" and can_derive:
                self._log("[CURVATURE] Calcul automatique (Laplacien)...")
                lap     = cv2.Laplacian(heightmap_norm, cv2.CV_32F, ksize=3)
                concave = self._normalize_01(np.clip(-lap, 0, None)).astype(np.float32)
                np.save(os.path.join(dir_raw, "raw_curvature.npy"), concave)
                self._log("[CURVATURE] OK (fallback Laplacien)")

            elif key in ("slope", "curvature") and shape[0] > self.MAX_FALLBACK_DERIVATION_SIZE:
                self._log(f"[{key.upper()}] Fallback désactivé (>{self.MAX_FALLBACK_DERIVATION_SIZE} px) -> zéros.")
                np.save(os.path.join(dir_raw, f"raw_{key}.npy"), np.zeros(shape, dtype=np.float32))

            else:
                self._log(f"[{key.upper()}] Absent -> matrice zéro.")
                np.save(os.path.join(dir_raw, f"raw_{key}.npy"), np.zeros(shape, dtype=np.float32))

        del heightmap_norm

    # ── Génération des masques (étape 2) ─────────────────────────────────────

    def generate_masks(self, dir_raw: str, dir_masks: str,
                       json_path: str, alt_min: float, alt_max: float):
        # Charger normalization.json pour utiliser les VRAIES valeurs min/max
        norm_file = os.path.join(dir_raw, "normalization.json")
        if os.path.exists(norm_file):
            with open(norm_file, "r", encoding="utf-8") as f:
                norm_data = json.load(f)
            alt_min = norm_data["altitude_min"]
            alt_max = norm_data["altitude_max"]
            self._log(f"[NORMALIZATION] Chargé : {alt_min:.2f}m -> {alt_max:.2f}m")
        else:
            self._log(f"[NORMALIZATION] Fichier absent, utilise project.json : {alt_min:.2f}m -> {alt_max:.2f}m")

        if json_path and os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as fh:
                lib = json.load(fh)
            available = {m["stem"] for m in lib.get("materials", [])}
            missing   = [s for s in PIPELINE_STEMS if s not in available]
            if missing:
                self._log(f"[JSON] Stems absents de la bibliothèque : {missing}")
            else:
                self._log(f"[JSON] {len(PIPELINE_STEMS)} stems validés.")
        else:
            self._log("[JSON] Bibliothèque introuvable — validation ignorée.")

        heightmap = np.load(os.path.join(dir_raw, "raw_heightmap.npy"), mmap_mode="r")
        slope_map = np.load(os.path.join(dir_raw, "raw_slope.npy"),     mmap_mode="r")
        shape     = heightmap.shape

        if slope_map.shape != shape:
            raise ValueError(f"Incohérence heightmap/slope : {shape} vs {slope_map.shape}")

        curv_path = os.path.join(dir_raw, "raw_curvature.npy")
        sed_path  = os.path.join(dir_raw, "raw_sediment.npy")
        curv_raw  = np.load(curv_path, mmap_mode="r") if os.path.exists(curv_path) else None
        sed_raw   = np.load(sed_path,  mmap_mode="r") if os.path.exists(sed_path)  else None

        c_pivot   = (float(np.percentile(np.abs(curv_raw), 99)) or 1.0) if curv_raw is not None else 1.0
        alt_range = alt_max - alt_min if alt_max > alt_min else 1.0

        # Échantillon pixels terrestres (normalisé 0-1) pour analyse hypsométrique
        stride_s  = max(1, shape[0] // 512)
        h_sample  = np.asarray(heightmap[::stride_s, ::stride_s], dtype=np.float32).ravel()
        h_sea_thr = float(np.clip((-alt_min) / alt_range, 0.0, 1.0))
        h_land    = h_sample[h_sample > h_sea_thr]

        slope_p90 = float(np.percentile(slope_map[slope_map > 0.01], 90)) if slope_map.max() > 0.01 else 0.30

        # Calculer stats complètes pour affichage
        slope_stats = {
            'min': float(slope_map.min()),
            'max': float(slope_map.max()),
            'mean': float(slope_map.mean()),
            'p50': float(np.percentile(slope_map, 50)),
            'p75': float(np.percentile(slope_map, 75)),
            'p90': slope_p90,
            'p95': float(np.percentile(slope_map, 95)),
        }

        curv_stats = {}
        if curv_raw is not None:
            curv_stats = {
                'min': float(curv_raw.min()),
                'max': float(curv_raw.max()),
                'mean': float(curv_raw.mean()),
                'concave_pct': float((curv_raw < -0.01).sum() / curv_raw.size * 100),
                'convex_pct': float((curv_raw > 0.01).sum() / curv_raw.size * 100),
                'flat_pct': float((np.abs(curv_raw) <= 0.01).sum() / curv_raw.size * 100),
            }

        sed_stats = {}
        if sed_raw is not None:
            sed_stats = {
                'min': float(sed_raw.min()),
                'max': float(sed_raw.max()),
                'mean': float(sed_raw.mean()),
                'p50': float(np.percentile(sed_raw, 50)),
                'p75': float(np.percentile(sed_raw, 75)),
                'p90': float(np.percentile(sed_raw, 90)),
            }

        zones     = calibrate_zones(
            alt_max, slope_p90,
            h_land_norm=h_land if len(h_land) >= 100 else None,
            alt_min=alt_min,
        )

        # Sauvegarder stats de calibration pour affichage UI
        self.calibration_stats = {
            'alt_min': alt_min,
            'alt_max': alt_max,
            'alt_range': alt_range,
            'slope': slope_stats,
            'curvature': curv_stats,
            'sediment': sed_stats,
            'zones': zones,
            'terrain_type': zones.get('_terrain_type'),
        }

        self._log(f"[CALIBRATION] alt_max={alt_max:.0f}m  slope_p90={slope_p90:.3f}")

        # Afficher niveau mer si différent de 0
        sea_level = zones.get('a_sea', 0.0)
        if sea_level < -5.0:
            self._log(f"[CALIBRATION] Niveau mer auto-détecté : {sea_level:.0f}m (mer enfouie)")

        _ttype = zones.get('_terrain_type')
        if _ttype:
            self._log(f"[CALIBRATION] Profil terrain : {_ttype}  "
                      f"(mean={zones['_mean_norm']:.2f}  spread={zones['_spread']:.2f})")
        self._log(f"[CALIBRATION] coastal {zones['a_c2']:.0f}->{zones['a_c4']:.0f}m  |  "
                  f"lowland {zones['a_l1']:.0f}->{zones['a_l4']:.0f}m  |  "
                  f"highland {zones['a_h1']:.0f}->{zones['a_h2']:.0f}m"
                  + ("" if _ttype else "  (fallback fractions)"))

        one_gib = shape[0] * shape[1] * 4 / 1024**3
        self._log(f"[INFO] {shape[0]}×{shape[1]} px — {one_gib:.2f} GiB/stem  "
                  f"-> {one_gib * len(self.active_stems):.1f} GiB total ({len(self.active_stems)} stems)")
        if curv_raw is None:
            self._log("[INFO] Courbure non disponible — channel zéros.")
        if sed_raw is None:
            self._log("[INFO] Sédiments non disponibles — channel zéros.")

        os.makedirs(dir_masks, exist_ok=True)
        out_maps = {
            stem: np.lib.format.open_memmap(
                os.path.join(dir_masks, f"{self._mask_fname(stem)}.npy"),
                mode="w+", dtype=np.float32, shape=shape,
            )
            for stem in self.active_stems
        }

        rows         = shape[0]
        total_chunks = (rows + self.CHUNK_ROWS - 1) // self.CHUNK_ROWS
        done_count   = [0]
        lock         = threading.Lock()

        self._log(f"[INFO] Génération parallèle — {self.N_WORKERS} workers")

        def _process_row(row_start):
            row_end = min(row_start + self.CHUNK_ROWS, rows)
            h_c = np.asarray(heightmap[row_start:row_end], dtype=np.float32)
            s_c = np.asarray(slope_map[row_start:row_end], dtype=np.float32)
            c_c = (
                np.clip(np.asarray(curv_raw[row_start:row_end], dtype=np.float32) / c_pivot, -1.0, 1.0)
                if curv_raw is not None
                else np.zeros(h_c.shape, dtype=np.float32)
            )
            sed_c = (
                np.asarray(sed_raw[row_start:row_end], dtype=np.float32)
                if sed_raw is not None
                else np.zeros(h_c.shape, dtype=np.float32)
            )

            scores = compute_chunk_blends(h_c, s_c, c_c, sed_c, alt_min, alt_range, zones, self._biome_config)

            # Modulation biome (ANCIEN SYSTÈME v1 seulement)
            if not self._use_new_system:
                for stem in self.active_stems:
                    scale = self._stem_scales.get(stem, 1.0)
                    if scale != 1.0 and stem in scores:
                        scores[stem] = scores[stem] * scale

            # Normaliser sur les stems du biome actif
            active_stems = self.active_stems

            total = np.zeros(h_c.shape, dtype=np.float32)
            for stem in active_stems:
                total += scores.get(stem, np.zeros(h_c.shape, dtype=np.float32))
            total = np.where(total == 0.0, 1.0, total)

            for stem in active_stems:
                out_maps[stem][row_start:row_end] = (
                    scores.get(stem, np.zeros(h_c.shape, dtype=np.float32)) / total
                )

            with lock:
                done_count[0] += 1
                n   = done_count[0]
                pct = 15.0 + n / total_chunks * 60.0
                self._progress(pct)
                if n % 16 == 0 or n == total_chunks:
                    self._log(f"  [{pct:5.1f}%]  chunk {n:4d} / {total_chunks}")

        row_starts = list(range(0, rows, self.CHUNK_ROWS))
        with ThreadPoolExecutor(max_workers=self.N_WORKERS) as ex:
            futures = [ex.submit(_process_row, rs) for rs in row_starts]
            for f in as_completed(futures):
                f.result()

        for m in out_maps.values():
            m.flush()
        self._log(f"[OK] {len(self.active_stems)} masques .npy générés.")

    # ── Validation ───────────────────────────────────────────────────────────

    def validate_material_count(self, dir_masks: str, shape: tuple,
                                 max_mats: int, label: str = "") -> int:
        # Seuil QTRE : même que Reforger
        QTRE_THRESHOLD = 1.0 / 65535.0 * 128.0

        stems_present = []
        mmaps_ro = {}
        for stem in self.active_stems:
            p = os.path.join(dir_masks, f"{self._mask_fname(stem)}.npy")
            if os.path.exists(p):
                stems_present.append(stem)
                mmaps_ro[stem] = np.load(p, mmap_mode="r")

        if not stems_present:
            return 0

        H, W            = shape
        blk             = self.SQUEEZE_CHUNK_SIZE
        n_ch            = (H + blk - 1) // blk
        n_cw            = (W + blk - 1) // blk
        total_pixels    = H * W
        violation_count = 0
        global_max      = 0

        for ci in range(n_ch):
            r0, r1 = ci * blk, min((ci + 1) * blk, H)
            for cj in range(n_cw):
                c0, c1 = cj * blk, min((cj + 1) * blk, W)
                stack  = np.stack(
                    [mmaps_ro[s][r0:r1, c0:c1] for s in stems_present], axis=0
                )
                # Utiliser seuil QTRE réel au lieu de 0.0
                active    = (stack > QTRE_THRESHOLD).sum(axis=0)
                chunk_max = int(active.max())
                if chunk_max > global_max:
                    global_max = chunk_max
                violation_count += int((active > max_mats).sum())

        pct_viol = violation_count / total_pixels * 100.0 if total_pixels else 0.0
        tag = f"[{label}] " if label else ""
        self._log(
            f"{tag}Validation : max {global_max} mats/pixel  |  "
            f"{violation_count:,} pixels en violation (>{max_mats})  "
            f"= {pct_viol:.2f}% de la carte"
        )
        return violation_count

    def validate_block_unique(self, dir_masks: str, shape: tuple,
                               taille_bloc: int, blocs_cote: int,
                               max_unique: int, label: str = "") -> int:
        # Seuil QTRE : même que Reforger
        QTRE_THRESHOLD = 1.0 / 65535.0 * 128.0

        stems_present = []
        mmaps_ro = {}
        for stem in self.active_stems:
            p = os.path.join(dir_masks, f"{self._mask_fname(stem)}.npy")
            if os.path.exists(p):
                stems_present.append(stem)
                mmaps_ro[stem] = np.load(p, mmap_mode="r")

        if not stems_present:
            return 0

        H, W             = shape
        violation_blocks = 0
        max_seen         = 0
        total_blocks     = blocs_cote * blocs_cote
        stride           = taille_bloc - 1

        for bi in range(blocs_cote):
            r0 = bi * stride
            r1 = min(r0 + taille_bloc, H)
            for bj in range(blocs_cote):
                c0 = bj * stride
                c1 = min(c0 + taille_bloc, W)
                # Utiliser seuil QTRE réel : poids moyen > QTRE_THRESHOLD
                bloc_pixels = (r1 - r0) * (c1 - c0)
                n_unique = sum(
                    1 for s in stems_present
                    if mmaps_ro[s][r0:r1, c0:c1].sum() > QTRE_THRESHOLD * bloc_pixels
                )
                if n_unique > max_seen:
                    max_seen = n_unique
                if n_unique > max_unique:
                    violation_blocks += 1

        pct = violation_blocks / total_blocks * 100.0 if total_blocks else 0.0
        tag = f"[{label}] " if label else ""
        self._log(
            f"{tag}Blocs Enfusion : max {max_seen} mats/bloc  |  "
            f"{violation_blocks:,} blocs en violation (>{max_unique})  "
            f"= {pct:.2f}%"
        )
        return violation_blocks

    # ── Squeeze + Enforce QTRE (étape 2b) ────────────────────────────────────

    def squeeze_and_enforce_bands(self, dir_masks: str, shape: tuple,
                                   taille_bloc: int, blocs_cote: int,
                                   max_mats: int, max_unique: int):
        """
        Squeeze (top-max_mats) + enforce (≤max_unique uniques) en un seul passage
        par bandes horizontales — lecture séquentielle pour éviter les accès
        aléatoires sur 16 fichiers de plusieurs Go.
        """
        # Seuil QTRE : même que Reforger (1/65535 * 128)
        QTRE_THRESHOLD = 1.0 / 65535.0 * 128.0  # ≈ 0.00195

        mmaps = {}
        for stem in self.active_stems:
            p = os.path.join(dir_masks, f"{self._mask_fname(stem)}.npy")
            if os.path.exists(p):
                mmaps[stem] = np.load(p, mmap_mode="r+")

        if not mmaps:
            self._log("[SQUEEZE] Aucun masque .npy trouvé — étape ignorée.")
            return

        stems_list = list(mmaps.keys())
        N          = len(stems_list)
        H, W       = shape
        stride     = taille_bloc - 1

        squeezed_total = 0
        enforced_total = 0

        # Positions des blocs colonnes précalculées (constantes pour toutes les bandes)
        c0s = (np.arange(blocs_cote) * stride).astype(np.int32)
        c1s = np.minimum(c0s + taille_bloc, W).astype(np.int32)

        self._log(f"[SQUEEZE+ENFORCE] {blocs_cote} bandes {taille_bloc}px×{W}px  |  "
                  f"top-{max_mats} puis ≤{max_unique} uniques/bloc  |  1 passe séquentielle")

        for ci in range(blocs_cote):
            r0 = ci * stride
            r1 = min(r0 + taille_bloc, H)

            band = np.empty((N, r1 - r0, W), dtype=np.float32)
            for i, s in enumerate(stems_list):
                band[i] = mmaps[s][r0:r1, :]

            # ── Pré-screening vectorisé via cumsum ────────────────────────────
            # Calcule les poids approx. de tous les blocs en une seule passe
            # au lieu de 256 boucles Python avec sum(axis=(1,2)).
            col_sum = band.sum(axis=1)                      # (N, W)
            cum = np.zeros((N, W + 1), dtype=np.float32)
            np.cumsum(col_sum, axis=1, out=cum[:, 1:])
            del col_sum
            w_approx    = cum[:, c1s] - cum[:, c0s]        # (N, blocs_cote)
            del cum
            # Utiliser le seuil QTRE réel au lieu de 0.0
            n_active    = (w_approx > QTRE_THRESHOLD * taille_bloc * taille_bloc).sum(axis=0)
            del w_approx
            cands       = np.where(n_active > max_unique)[0]
            del n_active

            if len(cands) == 0:                             # bande propre -> skip total
                del band
                continue

            # Inclure les voisins immédiats (overlap 1px entre blocs adjacents)
            work_set = np.unique(np.clip(
                np.concatenate([cands, cands - 1, cands + 1]), 0, blocs_cote - 1
            ))

            band_modified = False

            for cj in work_set:
                c0, c1 = int(c0s[cj]), int(c1s[cj])
                # Poids depuis l'état courant (propagation correcte des corrections précédentes)
                bloc_pixels = (r1 - r0) * (c1 - c0)
                weights = band[:, :, c0:c1].sum(axis=(1, 2))
                # Utiliser seuil QTRE réel : poids moyen > QTRE_THRESHOLD
                active = np.where(weights > QTRE_THRESHOLD * bloc_pixels)[0]

                if len(active) <= max_unique:
                    continue

                if len(active) > max_mats:
                    top_local  = np.argpartition(weights[active], -max_mats)[-max_mats:]
                    top_global = active[top_local]
                    keep       = np.zeros(N, dtype=bool)
                    keep[top_global] = True
                    band[:, :, c0:c1][~keep] = 0.0
                    weights    = band[:, :, c0:c1].sum(axis=(1, 2))
                    # Re-calculer active avec seuil QTRE
                    active = np.where(weights > QTRE_THRESHOLD * bloc_pixels)[0]
                    # Re-normalisation STRICTE pour garantir somme = 1.0
                    psum       = band[:, :, c0:c1].sum(axis=0, keepdims=True)
                    band[:, :, c0:c1] = np.where(
                        psum > 0.0,
                        band[:, :, c0:c1] / psum,
                        0.0
                    )
                    squeezed_total += 1
                    band_modified   = True

                if len(active) > max_unique:
                    # Supprimer les n_remove matériaux les plus faibles en une passe
                    n_remove       = len(active) - max_unique
                    weakest_local  = np.argpartition(weights[active], n_remove)[:n_remove]
                    weakest_global = active[weakest_local]
                    band[:, :, c0:c1][weakest_global] = 0.0
                    # Re-normalisation STRICTE pour garantir somme = 1.0
                    psum           = band[:, :, c0:c1].sum(axis=0, keepdims=True)
                    # Éviter division par zéro ET forcer somme exacte = 1.0
                    band[:, :, c0:c1] = np.where(
                        psum > 0.0,
                        band[:, :, c0:c1] / psum,
                        0.0
                    )
                    enforced_total += 1
                    band_modified   = True

            if band_modified:
                for i, s in enumerate(stems_list):
                    mmaps[s][r0:r1, :] = band[i]

            del band

            pct = 75.0 + (ci + 1) / blocs_cote * 15.0
            self._progress(pct)
            if (ci + 1) % max(1, blocs_cote // 8) == 0 or ci == blocs_cote - 1:
                self._log(f"  [{pct:5.1f}%]  bande {ci+1:3d}/{blocs_cote}  "
                          f"(squeeze: {squeezed_total}, enforce: {enforced_total})")

        for m in mmaps.values():
            m.flush()
        for k in list(mmaps.keys()):
            del mmaps[k]
        mmaps.clear()

        # ── Passe de correction finale itérative jusqu'à 0 violations ─────────
        self._log(f"[POST-SQUEEZE] Correction itérative jusqu'à 0 violations...")

        # Recharger les mmaps en mode r+ pour correction
        mmaps = {}
        for stem in self.active_stems:
            p = os.path.join(dir_masks, f"{self._mask_fname(stem)}.npy")
            if os.path.exists(p):
                mmaps[stem] = np.load(p, mmap_mode="r+")

        if mmaps:
            stems_list = list(mmaps.keys())
            N = len(stems_list)
            iteration = 0
            max_iterations = 5  # Limite de sécurité

            while iteration < max_iterations:
                iteration += 1
                corrected = 0
                violations_remaining = 0

                # Parcourir tous les blocs
                for bi in range(blocs_cote):
                    r0 = bi * stride
                    r1 = min(r0 + taille_bloc, H)
                    for bj in range(blocs_cote):
                        c0 = bj * stride
                        c1 = min(c0 + taille_bloc, W)

                        # Calculer poids moyens de chaque texture dans ce bloc
                        bloc_pixels = (r1 - r0) * (c1 - c0)
                        weights = np.array([
                            mmaps[s][r0:r1, c0:c1].sum() for s in stems_list
                        ])

                        # Détecter textures actives avec seuil QTRE
                        active = np.where(weights > QTRE_THRESHOLD * bloc_pixels)[0]

                        if len(active) > max_unique:
                            violations_remaining += 1

                            # Garder top-max_unique
                            n_remove = len(active) - max_unique
                            weakest_local = np.argpartition(weights[active], n_remove)[:n_remove]
                            weakest_global = active[weakest_local]

                            # Mettre à 0 les textures faibles
                            for idx in weakest_global:
                                mmaps[stems_list[idx]][r0:r1, c0:c1] = 0.0

                            # Renormaliser le bloc
                            bloc_sum = np.zeros((r1 - r0, c1 - c0), dtype=np.float32)
                            for s in stems_list:
                                bloc_sum += mmaps[s][r0:r1, c0:c1]

                            bloc_sum_safe = np.where(bloc_sum > 0.0, bloc_sum, 1.0)
                            for s in stems_list:
                                mmaps[s][r0:r1, c0:c1] /= bloc_sum_safe

                            corrected += 1

                # Flush après chaque itération
                for m in mmaps.values():
                    m.flush()

                self._log(f"[POST-SQUEEZE] Itération {iteration}: {corrected} blocs corrigés, "
                         f"{violations_remaining} violations restantes")

                # Si 0 violations, on a fini
                if violations_remaining == 0:
                    self._log(f"[POST-SQUEEZE] ✓ 0 violations atteint après {iteration} itération(s)")
                    break

            else:
                # Max iterations atteint
                self._log(f"[POST-SQUEEZE] ⚠️ {violations_remaining} violations restent après {max_iterations} itérations")

            # Cleanup
            for k in list(mmaps.keys()):
                del mmaps[k]
            mmaps.clear()

        total_blocks = blocs_cote * blocs_cote
        self._log(f"[OK] {squeezed_total}/{total_blocks} blocs squeezed  |  "
                  f"{enforced_total}/{total_blocks} blocs enforced")

    # ── Filtrage masques vides (< 1% remplissage) ─────────────────────────────

    def filter_empty_masks(self, dir_masks: str, min_fill_pct: float = 1.0):
        """
        Supprime les masques avec < min_fill_pct de pixels actifs (> QTRE_THRESHOLD).

        Args:
            dir_masks: Dossier contenant les .npy
            min_fill_pct: Seuil minimum de remplissage (défaut: 1%)

        Returns:
            (kept_count, removed_list): nombre de masques gardés, liste des stems supprimés
        """
        QTRE_THRESHOLD = 1.0 / 65535.0 * 128.0

        npy_files = sorted([f for f in os.listdir(dir_masks) if f.lower().endswith(".npy")])
        if not npy_files:
            return 0, []

        kept = 0
        removed = []

        # Stems à toujours garder (même si < 1%) — textures marines essentielles
        ESSENTIAL_STEMS = {'SeaBed', 'Sea_', 'Ocean'}

        for fname in npy_files:
            fpath = os.path.join(dir_masks, fname)
            stem = os.path.splitext(fname)[0]

            # Extraire stem réel (enlever préfixe "mask_XX_")
            stem_real = stem.split('_', 2)[-1] if stem.count('_') >= 2 else stem

            # Charger le masque en mmap
            mat = np.load(fpath, mmap_mode="r")
            total_pixels = mat.size

            # Compter pixels actifs (> QTRE_THRESHOLD)
            active_pixels = (mat > QTRE_THRESHOLD).sum()
            fill_pct = (active_pixels / total_pixels) * 100.0

            # Garder si >= min_fill_pct OU si stem essentiel (marine)
            is_essential = any(ess in stem_real for ess in ESSENTIAL_STEMS)

            if fill_pct < min_fill_pct and not is_essential:
                # Supprimer le masque
                del mat  # Fermer le mmap avant suppression
                os.remove(fpath)
                removed.append(stem)
                self._log(f"  ❌ {stem:30}  {fill_pct:5.2f}% < {min_fill_pct}% -> supprimé")
            else:
                kept += 1
                if is_essential and fill_pct < min_fill_pct:
                    self._log(f"  ✓ {stem:30}  {fill_pct:5.2f}% < {min_fill_pct}% -> gardé (essentiel)")

        return kept, removed

    # ── Export PNG 16 bits (étape 3) ──────────────────────────────────────────

    def export_png(self, dir_masks: str, dir_png: str, export_size: int = None):
        """
        export_size : taille cible du PNG en pixels (ex. 65025 pour Zimnitrita).
                      Si différent de la taille des .npy, upscale nearest-neighbor
                      via pypng ligne par ligne (pic RAM ~200 Mo au lieu de 8,4 Go).
                      Si pypng absent, export à la résolution de traitement avec avertissement.
        """
        npy_files = sorted(f for f in os.listdir(dir_masks) if f.lower().endswith(".npy"))
        if not npy_files:
            self._log("[ATTENTION] Aucun .npy trouvé dans le dossier masques.")
            return
        os.makedirs(dir_png, exist_ok=True)
        total    = len(npy_files)
        exported = 0
        skipped  = 0

        for i, fname in enumerate(npy_files, 1):
            src = os.path.join(dir_masks, fname)
            dst = os.path.join(dir_png, os.path.splitext(fname)[0] + ".png")
            t0  = time.perf_counter()

            mat = np.load(src, mmap_mode="r")
            src_h, src_w = mat.shape

            # Résolution d'export (upscale si map > MAX_PROCESS_PX)
            tgt_h = export_size if export_size else src_h
            tgt_w = export_size if export_size else src_w
            needs_upscale = (tgt_h != src_h or tgt_w != src_w)
            if needs_upscale and not _HAS_PNG:
                self._log(
                    f"  [WARN] pypng absent -> export {src_h}px "
                    f"(pip install pypng pour upscale -> {tgt_h}px)"
                )
                needs_upscale = False
                tgt_h, tgt_w = src_h, src_w

            # Calque vide -> pas de PNG (court-circuit avant toute allocation)
            if not np.any(mat > 0.0):
                skipped += 1
                self._log(f"  [{i:2d}/{total}]  {fname:<36}  SKIP (vide)")
                self._progress(90.0 + i / total * 10.0)
                continue

            ok = False
            if needs_upscale:
                # Écriture pypng ligne par ligne + upscale nearest-neighbor.
                # Pic RAM : ~1 ligne source (~130 Ko) + buffer pypng — jamais d'array complet.
                _writer = _png.Writer(width=tgt_w, height=tgt_h, bitdepth=16, greyscale=True)

                def _row_gen(_mat=mat, _sh=src_h, _sw=src_w, _th=tgt_h, _tw=tgt_w):
                    for _r_out in range(_th):
                        _r_src = _r_out * _sh // _th   # nearest-neighbor vertical
                        _row_f = np.clip(_mat[_r_src], 0.0, 1.0).astype(np.float32)
                        _row_u16 = (_row_f * 65535.0 + 0.5).astype(np.uint16)
                        if _tw != _sw:                  # nearest-neighbor horizontal
                            _row_u16 = cv2.resize(
                                _row_u16.reshape(1, _sw),
                                (_tw, 1), interpolation=cv2.INTER_NEAREST,
                            ).reshape(-1)
                        yield _row_u16.tolist()

                with open(dst, "wb") as _fout:
                    _writer.write(_fout, _row_gen())
                ok = True

            else:
                # Conversion par bandes : pic ~2,1 Go (uint16) + ~67 Mo (bande float)
                h_px, w_px = src_h, src_w
                mat_u16 = np.empty((h_px, w_px), dtype=np.uint16)
                _STRIPE = 512
                for _r0 in range(0, h_px, _STRIPE):
                    _band = np.clip(mat[_r0:_r0 + _STRIPE], 0.0, 1.0).astype(np.float32)
                    mat_u16[_r0:_r0 + _STRIPE] = (_band * 65535.0 + 0.5).astype(np.uint16)
                    del _band

                ok = cv2.imwrite(dst, mat_u16)
                if not ok and _HAS_IMAGEIO:
                    _imageio.imwrite(dst, mat_u16)
                    ok = True

            elapsed  = time.perf_counter() - t0
            size_mib = os.path.getsize(dst) / 1024**2 if ok else 0.0
            tag      = f"{tgt_h}px↑" if needs_upscale else f"{tgt_h}px"
            status   = "OK" if ok else "ERREUR"
            self._log(
                f"  [{i:2d}/{total}]  {fname:<36}  {elapsed:5.1f}s  "
                f"{size_mib:6.0f} MiB  {tag}  [{status}]"
            )
            exported += 1
            self._progress(90.0 + i / total * 10.0)

        self._log(f"[OK] {exported} PNG exportés, {skipped} calques vides ignorés -> {dir_png}")

    # ── Point d'entrée haut niveau ────────────────────────────────────────────

    def run_pipeline(self, out_root: str,
                     target_size: int, blocs_cote: int, taille_bloc: int,
                     alt_min: float, alt_max: float,
                     paths_snap: dict, json_path: str,
                     del_npy: bool = True, process_size: int = None):
        """
        Pipeline complet : Ingestion -> Masques -> Squeeze QTRE -> Export PNG -> Nettoyage .npy.

        paths_snap   : dict avec clés heightmap, slope, curvature, sediment, satmap.
        process_size : résolution interne (ingest/masques/squeeze). Si None, calculé
                       comme min(target_size, MAX_PROCESS_PX). Pour les maps > 32513px,
                       les masques sont traités à process_size puis upscalés à l'export.
        Retourne (success: bool, message: str).
        """
        try:
            if process_size is None:
                process_size = min(target_size, self.MAX_PROCESS_PX)
            shape = (process_size, process_size)

            self._log("=" * 62)
            self._log("  ÉTAPE 1 — Ingestion & normalisation")
            self._log("=" * 62)
            self._progress(2.0)
            self._log(f"[META] Surface Map    : {target_size}×{target_size} px")
            if process_size < target_size:
                ratio = target_size / process_size
                self._log(f"[META] Traitement     : {process_size}×{process_size} px "
                          f"(export direct sans upscale — Reforger upscale auto à l'import)")
            self._log(f"[META] Grille Enfusion: {blocs_cote}×{blocs_cote} blocs ({taille_bloc} px/bloc)")
            self._log(f"[META] Altitudes      : {alt_min} m -> {alt_max} m")
            biome_info = f"{len(self.active_stems)} stems actifs"
            # Ajouter info scales si ancien système
            if not self._use_new_system and self._stem_scales:
                scales_neq_1 = sum(1 for v in self._stem_scales.values() if v != 1.0)
                if scales_neq_1 > 0:
                    biome_info += f"  (scales ≠1 : {scales_neq_1})"
            self._log(f"[META] Biome          : {biome_info}")

            import time as _time
            _run_ts  = _time.strftime("%Y%m%d_%H%M%S")
            dir_meta = os.path.join(out_root, "reports", f"run_{_run_ts}")
            dir_raw  = os.path.join(out_root, self.DIR_RAW)
            os.makedirs(dir_meta, exist_ok=True)
            os.makedirs(dir_raw,  exist_ok=True)

            self.ingest_all(paths_snap, shape, dir_raw, alt_min, alt_max)
            self._progress(15.0)

            with open(os.path.join(dir_meta, "map_parameters.txt"), "w", encoding="utf-8") as fh:
                fh.write(f"SURFACE_TOTAL={target_size}\n")
                fh.write(f"PROCESS_SIZE={process_size}\n")
                fh.write(f"BLOCS_TOTAL={blocs_cote}\n")
                fh.write(f"TAILLE_BLOC={taille_bloc}\n")
                fh.write(f"ALT_MIN={alt_min}\n")
                fh.write(f"ALT_MAX={alt_max}\n")
            self._log("[OK] map_parameters.txt écrit.\n")

            self._log("=" * 62)
            self._log(f"  ÉTAPE 2 — Micro-mélanges géologiques ({len(PIPELINE_STEMS)} masques)")
            self._log("=" * 62)

            dir_masks = os.path.join(out_root, self.DIR_MASKS)
            self.generate_masks(dir_raw, dir_masks, json_path, alt_min, alt_max)

            self._log("")
            self._log("=" * 62)
            self._log(f"  SQUEEZING — top-{self.MAX_MATERIALS_PER_CHUNK} / ≤{self.BLOCK_UNIQUE_LIMIT} uniques")
            self._log("=" * 62)
            self.validate_material_count(dir_masks, shape, self.MAX_MATERIALS_PER_CHUNK, label="AVANT")
            self.squeeze_and_enforce_bands(
                dir_masks, shape, taille_bloc, blocs_cote,
                self.MAX_MATERIALS_PER_CHUNK, self.BLOCK_UNIQUE_LIMIT,
            )
            self.validate_block_unique(
                dir_masks, shape, taille_bloc, blocs_cote,
                self.BLOCK_UNIQUE_LIMIT, label="APRÈS"
            )

            self._log("")
            self._log("=" * 62)
            self._log("  FILTRAGE — Élimination masques vides (0.00%)")
            self._log("=" * 62)
            kept, removed = self.filter_empty_masks(dir_masks, min_fill_pct=0.0001)
            if removed:
                self._log(f"[OK] {kept} masques gardés, {len(removed)} éliminés : {', '.join(removed)}")
            else:
                self._log(f"[OK] {kept} masques gardés, aucun éliminé")

            self._log("")
            self._log("=" * 62)
            self._log("  ÉTAPE 3 — Export PNG 16 bits")
            self._log("=" * 62)

            dir_png = os.path.join(out_root, self.DIR_PNG)
            # Export à process_size (8192 max) — Reforger upscale à l'import
            self.export_png(dir_masks, dir_png, export_size=process_size)

            freed_mb = 0.0
            if del_npy:
                self._log("\n[NETTOYAGE] Suppression des fichiers .npy temporaires...")
                for _npy_dir in (dir_masks, dir_raw):
                    if os.path.isdir(_npy_dir):
                        for fname in os.listdir(_npy_dir):
                            if fname.lower().endswith(".npy"):
                                fpath = os.path.join(_npy_dir, fname)
                                freed_mb += os.path.getsize(fpath) / 1024**2
                                os.remove(fpath)
                self._log(f"[NETTOYAGE] {freed_mb / 1024:.1f} Go libérés.")

            msg = (f"Pipeline terminé !\nPNG prêts : {dir_png}"
                   + (f"\n{freed_mb / 1024:.1f} Go de .npy supprimés." if del_npy else ""))
            return True, msg

        except Exception as exc:
            import traceback
            self._log(f"\n[ERREUR FATALE] {exc}")
            self._log(traceback.format_exc())
            return False, str(exc)

    # ── Preview (résolution réduite, pas d'export) ────────────────────────────

    def compute_preview(self, paths_snap: dict, alt_min: float, alt_max: float,
                        resolution: int = 1024,
                        hm_array: np.ndarray = None) -> dict:
        """
        Calcule les scores de texture sur une version downscalée (resolution×resolution).
        Retourne un dict {stem: ndarray float32} normalisé, sans écrire sur disque.

        hm_array : heightmap normalisée 0-1 déjà en mémoire (évite le rechargement .asc).
                   Si None, charge depuis paths_snap["heightmap"].
        """
        shape = (resolution, resolution)

        def _load_img(path):
            if not path or not os.path.exists(path):
                return np.zeros(shape, dtype=np.float32)
            img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
            if img is None:
                return np.zeros(shape, dtype=np.float32)
            img = cv2.resize(img, shape, interpolation=cv2.INTER_LINEAR)
            if img.ndim == 3:
                img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            scale = 65535.0 if img.dtype == np.uint16 else 255.0
            return img.astype(np.float32) / scale

        if hm_array is not None:
            # Utiliser le tableau déjà chargé — downscale uniquement
            hm = cv2.resize(hm_array.astype(np.float32), shape, interpolation=cv2.INTER_CUBIC)
            hm = np.clip(hm, 0.0, 1.0)
        else:
            hm_path = paths_snap.get("heightmap", "")
            if hm_path and os.path.exists(hm_path) and hm_path.lower().endswith(".asc"):
                self._log("[PREVIEW] Chargement .asc (peut prendre du temps sur grande map)...")
                raw_h = np.loadtxt(hm_path, skiprows=6)
                hm = cv2.resize(raw_h.astype(np.float32), shape, interpolation=cv2.INTER_CUBIC)
                hm = self._normalize_01(hm).astype(np.float32)
            else:
                hm = _load_img(paths_snap.get("heightmap", ""))

        slope_map = _load_img(paths_snap.get("slope", ""))
        curv_raw  = _load_img(paths_snap.get("curvature", ""))
        sed_raw   = _load_img(paths_snap.get("sediment", ""))

        alt_range = alt_max - alt_min if alt_max > alt_min else 1.0
        c_pivot   = float(np.percentile(np.abs(curv_raw), 99)) or 1.0
        c_norm    = np.clip(curv_raw / c_pivot, -1.0, 1.0)

        slope_p90 = float(np.percentile(slope_map[slope_map > 0.01], 90)) if slope_map.max() > 0.01 else 0.30

        h_sea_thr = float(np.clip((-alt_min) / alt_range, 0.0, 1.0))
        h_land    = hm[hm > h_sea_thr].ravel()
        zones = calibrate_zones(
            alt_max, slope_p90,
            h_land_norm=h_land if len(h_land) >= 100 else None,
            alt_min=alt_min,
        )
        scores = compute_chunk_blends(hm, slope_map, c_norm, sed_raw, alt_min, alt_range, zones, self._biome_config)

        # Modulation biome (ANCIEN SYSTÈME v1 seulement)
        if not self._use_new_system:
            for stem in self.active_stems:
                scale = self._stem_scales.get(stem, 1.0)
                if scale != 1.0 and stem in scores:
                    scores[stem] = scores[stem] * scale

        # Normaliser sur les stems du biome uniquement
        total = np.zeros(shape, dtype=np.float32)
        for stem in self.active_stems:
            total += scores.get(stem, np.zeros(shape, dtype=np.float32))
        total = np.where(total == 0.0, 1.0, total)

        return {
            stem: scores.get(stem, np.zeros(shape, dtype=np.float32)) / total
            for stem in self.active_stems
        }


# ---------------------------------------------------------------------------
# Rendu visuel
# ---------------------------------------------------------------------------

# Couleur RGB dominante par stem (pour le rendu preview)
STEM_COLORS: dict = {
    "SeaBed_01":        ( 55, 100, 155),
    "BeachGrass_01":    (108, 142,  72),
    "Grass_03_coastal": (100, 135,  65),
    "Pebbles_01":       (155, 148, 130),
    "Pebbles_02":       (138, 131, 112),
    "Grass_01":         ( 68, 125,  52),
    "Grass_03":         ( 75, 118,  50),
    "MountainGrass_01": ( 88, 108,  68),
    "MountainGrass_02": ( 78,  98,  60),
    "MountainGrass_03": ( 70,  90,  55),
    "Heather_01":       (115,  90,  82),
    "Dirt_01":          (139, 105,  70),
    "Dirt_02":          (155, 120,  85),
    "Dirt_03":          (130, 108,  78),
    "Debris_Rock_01":   (122, 105,  82),
    "Rock_01":          (108, 105,  98),
}


def render_preview_rgb(scores: dict,
                       heightmap: np.ndarray = None,
                       hillshade_strength: float = 0.35) -> np.ndarray:
    """
    Génère une image RGB uint8 depuis les scores de texture.
    scores : {stem: ndarray float32 H×W}
    heightmap : ndarray float32 normalisé 0-1, même shape ou None
    """
    stems = [s for s in PIPELINE_STEMS if s in scores]
    if not stems:
        return np.zeros((256, 256, 3), dtype=np.uint8)

    H, W = next(iter(scores.values())).shape

    stack   = np.stack([scores[s] for s in stems], axis=0)   # (N, H, W)
    dom_idx = np.argmax(stack, axis=0)                        # (H, W)

    palette = np.array([STEM_COLORS[s] for s in stems], dtype=np.uint8)
    rgb     = palette[dom_idx].astype(np.float32)             # (H, W, 3)

    if heightmap is not None and hillshade_strength > 0.0:
        hm = heightmap.astype(np.float32)
        if hm.shape != (H, W):
            hm = cv2.resize(hm, (W, H), interpolation=cv2.INTER_LINEAR)
        sx    = cv2.Sobel(hm, cv2.CV_32F, 1, 0, ksize=3)
        sy    = cv2.Sobel(hm, cv2.CV_32F, 0, 1, ksize=3)
        sigma = float(np.std(sx - sy)) or 1.0
        shade = np.clip(1.0 - hillshade_strength * (sx - sy) / sigma, 0.4, 1.6)
        rgb  *= shade[:, :, np.newaxis]

    return np.clip(rgb, 0, 255).astype(np.uint8)
