"""
pipeline_core.py
================
Pipeline Reforger — cœur algorithmique sans UI.
Ingestion → Masques matériaux → Squeezing QTRE → Export PNG 16 bits.

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
# Le moteur l'affiche partout où aucun masque n'a de poids → pas de fichier exporté.
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


def _terrain_profile(h_land_norm: np.ndarray) -> dict:
    """
    Analyse la forme de la courbe hypsométrique des pixels terrestres normalisés [0-1].
    Retourne le type de profil et les niveaux de percentile adaptés pour chaque zone clé.

    Types détectés :
      'flat'     — terrain plat/côtier, majorité basse altitude
      'balanced' — distribution équilibrée (île volcanique type ZBK) → défauts actuels
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
        # → alpine très rare, prairie étendue, zone côtière plus large
        terrain_type       = 'flat'
        highland_start_pct = 75
        lowland_end_pct    = 62
        coastal_end_pct    = 15

    elif mean_h > 0.55 or spread > 0.65:
        # Fort relief ou altitude moyenne élevée
        # → alpine précoce, prairie compressée, côte minimale
        terrain_type       = 'mountain'
        highland_start_pct = 45
        lowland_end_pct    = 38
        coastal_end_pct    = 8

    elif mean_h > 0.48 and spread < 0.42:
        # Plateau : distribution concentrée à altitude élevée
        # → alpine anticipée, prairie réduite
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
      1. h_land_norm fourni → analyse hypsométrique complète (nouveau chemin)
         Détecte le profil terrain (flat/balanced/plateau/mountain) et adapte
         les seuils de zone en conséquence.
      2. alt_pcts fourni → percentiles pré-calculés, seuils fixes (ancien chemin)
      3. Aucun → fallback fractions de alt_max

    Le dict retourné contient en plus '_terrain_type', '_mean_norm', '_spread'
    si h_land_norm a été fourni.
    """
    sea = 0.0
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

        a_c2 = max(sea + 2.0, _p(8,               0.10))
        a_c3 = max(a_c2 + 2.0, _p(c_pct,          0.14))
        a_c4 = max(a_c3 + 5.0, _p(min(c_pct+8,35),0.23))
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
        a_c2 = max(sea + 2.0, p8);  a_c3 = max(a_c2 + 2.0, p12)
        a_c4 = max(a_c3 + 5.0, p20)
        a_l1 = max(sea + 1.0, p5);  a_l2 = p30;  a_l3 = p50;  a_l4 = p62
        a_m1 = p20;  a_m2 = p50;  a_m3 = p72;  a_m4 = p85
        a_h1 = p58;  a_h2 = p85

    else:
        # ── Fallback : fractions fixes de alt_max ────────────────────────────
        a_c2 = sea + min(R * 0.10, 80.0);  a_c3 = sea + min(R * 0.14, 112.0)
        a_c4 = sea + min(R * 0.23, 184.0)
        a_l1 = sea + R * 0.05;  a_l2 = sea + R * 0.25
        a_l3 = sea + R * 0.46;  a_l4 = sea + R * 0.63
        a_m1 = sea + R * 0.33;  a_m2 = sea + R * 0.53
        a_m3 = sea + R * 0.77;  a_m4 = sea + R * 0.95
        a_h1 = sea + R * 0.56;  a_h2 = sea + R * 0.82

    zones = {
        'a_c1': sea - 5,
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


def compute_chunk_blends(h_chunk, s_chunk, c_chunk, sed_chunk, min_alt, alt_range, zones):
    """
    zones : dict retourné par calibrate_zones() — seuils adaptés au terrain courant.
    """
    alt_m = (min_alt + h_chunk * alt_range).astype(np.float32)
    z = zones

    sub      = smoothstep( -2.0,   -12.0,   alt_m)
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

    ravine        = concave * wet
    cliff_fissure = steep   * concave
    crest         = highland * convex
    coast_flat    = coastal  * (flat + gentle * 0.6)
    coast_talus   = coastal  * moderate
    prairie_low   = lowland  * (flat + gentle) * (1.0 - steep) * (1.0 - ravine)
    prairie_mid   = midland  * (flat + gentle) * (1.0 - steep)
    alpage_dry    = highland * (flat + gentle) * dry
    alpage_wet    = highland * (flat + gentle) * (moist + wet * 0.4)
    mid_slope     = (lowland + midland) * moderate * (1.0 - steep) * (1.0 - ravine)

    rocky_highland = highland * smoothstep(z['sl_rh1'], z['sl_rh2'], s_chunk)
    rocky_outcrop  = (lowland + midland + coastal * 0.5) * moderate * convex * (1.0 - steep)
    coast_cliff    = coastal * steep

    sc = {stem: np.zeros(h_chunk.shape, dtype=np.float32) for stem in _COMPUTE_STEMS}

    # A. FOND MARIN
    sc["SeaBed_01"]        += sub

    # B. CÔTE PLATE
    sc["BeachGrass_01"]    += coast_flat * (1.0 - wet) * (1.0 - convex * 0.8) * 0.55
    sc["Grass_03_coastal"] += coast_flat * moist           * 0.28
    sc["Dirt_03"]          += coast_flat * dry             * 0.38
    sc["Pebbles_01"]       += coast_flat * wet             * 0.38

    # C. TALUS CÔTIER
    sc["Pebbles_01"]       += coast_talus                  * 0.45
    sc["Pebbles_02"]       += coast_talus * moderate       * 0.18
    sc["Grass_02"]         += coast_talus * (1.0 - steep)  * 0.24
    sc["Dirt_03"]          += coast_talus                  * 0.18

    # D. RAVINES / TALWEGS
    sc["Dirt_03"]          += ravine * (0.70 - wet * 0.22)
    sc["Debris_Rock_01"]   += ravine * (0.30 + wet * 0.22)
    sc["Pebbles_01"]       += ravine * wet                 * 0.12

    # E. PAROIS ROCHEUSES
    sc["Rock_01"]          += steep * (1.0 - cliff_fissure * 0.15) * 0.90
    sc["Debris_Rock_01"]   += cliff_fissure                * 0.18
    sc["Debris_Rock_01"]   += (lowland + midland) * steep  * 0.14
    sc["Grass_01"]         += cliff_fissure                * 0.04

    # F. CRÊTES HIGHLAND
    sc["Rock_01"]          += crest * dry * (0.38 + steep * 0.08)
    sc["Debris_Rock_01"]   += crest                        * 0.14
    sc["Dirt_02"]          += crest * (1.0 - wet)          * 0.22
    sc["MountainGrass_01"] += crest * dry                  * 0.10
    sc["Grass_01"]         += crest * (1.0 - steep) * (1.0 - wet) * 0.18

    # G. ALPAGES SECS
    sc["Heather_01"]       += alpage_dry                   * 0.34
    sc["MountainGrass_01"] += alpage_dry                   * 0.28
    sc["Grass_01"]         += alpage_dry                   * 0.16
    sc["Dirt_02"]          += alpage_dry                   * 0.14

    # H. ALPAGES HUMIDES
    sc["MountainGrass_03"] += alpage_wet * moist           * 0.44
    sc["MountainGrass_02"] += alpage_wet                   * 0.28
    sc["Grass_03"]         += alpage_wet * moist           * 0.14
    sc["Dirt_03"]          += alpage_wet * wet             * 0.15

    # I. PRAIRIES BASSES
    sc["Grass_01"]         += prairie_low * dry            * 0.28
    sc["Grass_02"]         += prairie_low * dry            * 0.38
    sc["Dirt_01"]          += prairie_low * dry            * 0.20
    sc["Dirt_02"]          += prairie_low * dry            * 0.10
    sc["Grass_02"]         += prairie_low * moist          * 0.34
    sc["Grass_03"]         += prairie_low * moist          * 0.32
    sc["Dirt_01"]          += prairie_low * moist          * 0.16
    sc["Dirt_03"]          += prairie_low * wet            * 0.18

    # J. PRAIRIES DE COLLINE
    sc["MountainGrass_02"] += prairie_mid * dry            * 0.32
    sc["MountainGrass_03"] += prairie_mid * moist          * 0.32
    sc["Grass_02"]         += prairie_mid * dry            * 0.20
    sc["Grass_03"]         += prairie_mid * moist          * 0.20
    sc["Dirt_01"]          += prairie_mid * dry            * 0.18
    sc["Dirt_02"]          += prairie_mid * dry            * 0.10
    sc["Heather_01"]       += prairie_mid * convex * dry   * 0.14

    # K. PENTES MODÉRÉES
    sc["Grass_01"]         += mid_slope * dry              * 0.20
    sc["MountainGrass_01"] += mid_slope * (1.0 - moist)   * 0.26
    sc["Dirt_02"]          += mid_slope * dry              * 0.22
    sc["Dirt_03"]          += mid_slope * moist            * 0.22
    sc["Debris_Rock_01"]   += mid_slope * dry              * 0.18
    sc["Debris_Rock_01"]   += mid_slope * dry * convex     * 0.10

    # L. PENTES HIGHLAND ROCHEUSES
    sc["Rock_01"]          += rocky_highland               * 0.52
    sc["Debris_Rock_01"]   += rocky_highland               * 0.24
    sc["Dirt_02"]          += rocky_highland               * 0.08
    sc["MountainGrass_01"] += rocky_highland * (1.0 - steep) * 0.08

    # M. AFFLEUREMENTS ROCHEUX
    sc["Rock_01"]          += rocky_outcrop                * 0.38
    sc["Debris_Rock_01"]   += rocky_outcrop                * 0.28
    sc["Dirt_01"]          += rocky_outcrop                * 0.10

    # N. FALAISES CÔTIÈRES
    sc["Rock_01"]          += coast_cliff                  * 0.60
    sc["Debris_Rock_01"]   += coast_cliff                  * 0.20
    sc["Pebbles_01"]       += coast_cliff                  * 0.12

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
    # Les maps plus grandes (ex. Zimnitrita 65025px) sont traitées à cette
    # résolution, puis upscalées nearest-neighbor à l'export PNG.
    MAX_PROCESS_PX = 32513

    def __init__(self, log_fn=None, progress_fn=None, reforger_block_limit=5,
                 biome_stems=None, stem_scales=None):
        if reforger_block_limit not in self.REFORGER_LIMITS:
            raise ValueError(f"reforger_block_limit doit être dans {self.REFORGER_LIMITS}")
        self.log_fn      = log_fn      or (lambda msg: None)
        self.progress_fn = progress_fn or (lambda pct: None)
        self.MAX_MATERIALS_PER_CHUNK = reforger_block_limit
        self.BLOCK_UNIQUE_LIMIT      = reforger_block_limit - self._RESERVED_SLOTS
        # Palette du biome actif — détermine quels masques sont générés.
        # Par défaut : 16 stems vanilla complets, pondérations neutres (1.0).
        self._biome_stems = list(biome_stems) if biome_stems else list(PIPELINE_STEMS)
        self._stem_scales = dict(stem_scales) if stem_scales else {s: 1.0 for s in self._biome_stems}

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
        grid        = proj["reforger_grid"]
        target_size = grid["surface_map_total_px"][0]
        blocs_cote  = grid["tiles_x"] * grid["blocks_per_tile_x"]
        alt_min     = grid["height_min_m"]
        alt_max     = grid["height_max_m"]
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
        assets = proj["assets"]
        hm     = assets.get("heightmap", {})
        it     = assets.get("it_masks", {})
        sat    = assets.get("satmap", {})

        hm_path = hm.get("path", "")
        if not hm_path and hm.get("filename"):
            hm_path = os.path.join(project_dir, "sources", hm["filename"])

        sat_path = sat.get("path", sat.get("filename", ""))
        if sat_path and not os.path.isabs(sat_path):
            sat_path = os.path.join(project_dir, "sources", sat_path)

        return {
            "heightmap": hm_path,
            "slope":     it.get("slopes", ""),
            "curvature": it.get("curvature", ""),
            "sediment":  it.get("sediment", ""),
            "satmap":    sat_path,
        }

    def _mask_fname(self, stem: str) -> str:
        """Nom de fichier numéroté selon la position du stem dans le biome actif."""
        return f"mask_{self._biome_stems.index(stem) + 1:02d}_{stem}"

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

    def ingest_all(self, paths_snap: dict, shape: tuple, dir_raw: str):
        """
        Charge et normalise tous les fichiers sources → .npy dans dir_raw.
        paths_snap : dict avec clés heightmap, slope, curvature, sediment, satmap.
        shape      : (H, W) cible en pixels.
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
            heightmap_norm = rescaled
            np.save(os.path.join(dir_raw, "raw_heightmap.npy"), heightmap_norm)
            del rescaled, heightmap_norm
            heightmap_norm = np.load(os.path.join(dir_raw, "raw_heightmap.npy"), mmap_mode="r")
            self._log("[HEIGHTMAP] OK")
        else:
            self._log("[HEIGHTMAP] Absent → matrice neutre.")
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
                self._log(f"[{key.upper()}] Chargement → {shape[0]} px...")
                img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
                if img is None:
                    raise ValueError(f"Lecture impossible : {path}")
                img_r = cv2.resize(img, shape, interpolation=cv2.INTER_LINEAR)
                if img_r.ndim == 3:
                    img_r = cv2.cvtColor(img_r, cv2.COLOR_BGR2GRAY)
                scale = 65535.0 if img_r.dtype == np.uint16 else 255.0
                np.save(os.path.join(dir_raw, f"raw_{key}.npy"),
                        (img_r.astype(np.float32) / scale))
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
                self._log(f"[{key.upper()}] Fallback désactivé (>{self.MAX_FALLBACK_DERIVATION_SIZE} px) → zéros.")
                np.save(os.path.join(dir_raw, f"raw_{key}.npy"), np.zeros(shape, dtype=np.float32))

            else:
                self._log(f"[{key.upper()}] Absent → matrice zéro.")
                np.save(os.path.join(dir_raw, f"raw_{key}.npy"), np.zeros(shape, dtype=np.float32))

        del heightmap_norm

    # ── Génération des masques (étape 2) ─────────────────────────────────────

    def generate_masks(self, dir_raw: str, dir_masks: str,
                       json_path: str, alt_min: float, alt_max: float):
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
        zones     = calibrate_zones(
            alt_max, slope_p90,
            h_land_norm=h_land if len(h_land) >= 100 else None,
            alt_min=alt_min,
        )
        self._log(f"[CALIBRATION] alt_max={alt_max:.0f}m  slope_p90={slope_p90:.3f}")
        _ttype = zones.get('_terrain_type')
        if _ttype:
            self._log(f"[CALIBRATION] Profil terrain : {_ttype}  "
                      f"(mean={zones['_mean_norm']:.2f}  spread={zones['_spread']:.2f})")
        self._log(f"[CALIBRATION] coastal {zones['a_c2']:.0f}→{zones['a_c4']:.0f}m  |  "
                  f"lowland {zones['a_l1']:.0f}→{zones['a_l4']:.0f}m  |  "
                  f"highland {zones['a_h1']:.0f}→{zones['a_h2']:.0f}m"
                  + ("" if _ttype else "  (fallback fractions)"))

        one_gib = shape[0] * shape[1] * 4 / 1024**3
        self._log(f"[INFO] {shape[0]}×{shape[1]} px — {one_gib:.2f} GiB/stem  "
                  f"→ {one_gib * len(self._biome_stems):.1f} GiB total ({len(self._biome_stems)} stems)")
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
            for stem in self._biome_stems
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

            scores = compute_chunk_blends(h_c, s_c, c_c, sed_c, alt_min, alt_range, zones)

            # Modulation biome : multiplier le score de chaque stem actif
            for stem in self._biome_stems:
                scale = self._stem_scales.get(stem, 1.0)
                if scale != 1.0 and stem in scores:
                    scores[stem] = scores[stem] * scale

            # Normaliser sur les stems du biome uniquement
            total = np.zeros(h_c.shape, dtype=np.float32)
            for stem in self._biome_stems:
                total += scores.get(stem, np.zeros(h_c.shape, dtype=np.float32))
            total = np.where(total == 0.0, 1.0, total)

            for stem in self._biome_stems:
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
        self._log(f"[OK] {len(self._biome_stems)} masques .npy générés.")

    # ── Validation ───────────────────────────────────────────────────────────

    def validate_material_count(self, dir_masks: str, shape: tuple,
                                 max_mats: int, label: str = "") -> int:
        stems_present = []
        mmaps_ro = {}
        for stem in self._biome_stems:
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
                active    = (stack > 0.0).sum(axis=0)
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
        stems_present = []
        mmaps_ro = {}
        for stem in self._biome_stems:
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
                n_unique = sum(
                    1 for s in stems_present
                    if mmaps_ro[s][r0:r1, c0:c1].max() > 0.0
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
        mmaps = {}
        for stem in self._biome_stems:
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
            n_active    = (w_approx > 0.0).sum(axis=0)     # (blocs_cote,)
            del w_approx
            cands       = np.where(n_active > max_unique)[0]
            del n_active

            if len(cands) == 0:                             # bande propre → skip total
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
                weights = band[:, :, c0:c1].sum(axis=(1, 2))
                active  = np.where(weights > 0.0)[0]

                if len(active) <= max_unique:
                    continue

                if len(active) > max_mats:
                    top_local  = np.argpartition(weights[active], -max_mats)[-max_mats:]
                    top_global = active[top_local]
                    keep       = np.zeros(N, dtype=bool)
                    keep[top_global] = True
                    band[:, :, c0:c1][~keep] = 0.0
                    weights    = band[:, :, c0:c1].sum(axis=(1, 2))
                    active     = np.where(weights > 0.0)[0]
                    psum       = band[:, :, c0:c1].sum(axis=0)
                    band[:, :, c0:c1] /= np.where(psum == 0.0, 1.0, psum)[np.newaxis]
                    squeezed_total += 1
                    band_modified   = True

                if len(active) > max_unique:
                    # Supprimer les n_remove matériaux les plus faibles en une passe
                    n_remove       = len(active) - max_unique
                    weakest_local  = np.argpartition(weights[active], n_remove)[:n_remove]
                    weakest_global = active[weakest_local]
                    band[:, :, c0:c1][weakest_global] = 0.0
                    psum           = band[:, :, c0:c1].sum(axis=0)
                    band[:, :, c0:c1] /= np.where(psum == 0.0, 1.0, psum)[np.newaxis]
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

        total_blocks = blocs_cote * blocs_cote
        self._log(f"[OK] {squeezed_total}/{total_blocks} blocs squeezed  |  "
                  f"{enforced_total}/{total_blocks} blocs enforced")

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
                    f"  [WARN] pypng absent → export {src_h}px "
                    f"(pip install pypng pour upscale → {tgt_h}px)"
                )
                needs_upscale = False
                tgt_h, tgt_w = src_h, src_w

            # Calque vide → pas de PNG (court-circuit avant toute allocation)
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

        self._log(f"[OK] {exported} PNG exportés, {skipped} calques vides ignorés → {dir_png}")

    # ── Point d'entrée haut niveau ────────────────────────────────────────────

    def run_pipeline(self, out_root: str,
                     target_size: int, blocs_cote: int, taille_bloc: int,
                     alt_min: float, alt_max: float,
                     paths_snap: dict, json_path: str,
                     del_npy: bool = True, process_size: int = None):
        """
        Pipeline complet : Ingestion → Masques → Squeeze QTRE → Export PNG → Nettoyage .npy.

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
                          f"(upscale ×{ratio:.2f} à l'export)")
            self._log(f"[META] Grille Enfusion: {blocs_cote}×{blocs_cote} blocs ({taille_bloc} px/bloc)")
            self._log(f"[META] Altitudes      : {alt_min} m → {alt_max} m")
            self._log(f"[META] Biome          : {len(self._biome_stems)} stems actifs"
                      + (f"  (scales ≠1 : {sum(1 for v in self._stem_scales.values() if v != 1.0)})"
                         if any(v != 1.0 for v in self._stem_scales.values()) else ""))

            import time as _time
            _run_ts  = _time.strftime("%Y%m%d_%H%M%S")
            dir_meta = os.path.join(out_root, "reports", f"run_{_run_ts}")
            dir_raw  = os.path.join(out_root, self.DIR_RAW)
            os.makedirs(dir_meta, exist_ok=True)
            os.makedirs(dir_raw,  exist_ok=True)

            self.ingest_all(paths_snap, shape, dir_raw)
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
            self._log("  ÉTAPE 3 — Export PNG 16 bits")
            self._log("=" * 62)

            dir_png = os.path.join(out_root, self.DIR_PNG)
            self.export_png(dir_masks, dir_png, export_size=target_size)

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
        scores = compute_chunk_blends(hm, slope_map, c_norm, sed_raw, alt_min, alt_range, zones)

        # Modulation biome
        for stem in self._biome_stems:
            scale = self._stem_scales.get(stem, 1.0)
            if scale != 1.0 and stem in scores:
                scores[stem] = scores[stem] * scale

        # Normaliser sur les stems du biome uniquement
        total = np.zeros(shape, dtype=np.float32)
        for stem in self._biome_stems:
            total += scores.get(stem, np.zeros(shape, dtype=np.float32))
        total = np.where(total == 0.0, 1.0, total)

        return {
            stem: scores.get(stem, np.zeros(shape, dtype=np.float32)) / total
            for stem in self._biome_stems
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
