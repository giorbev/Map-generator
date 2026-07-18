"""
Vegetation Generator — carte 2D de végétation potentielle.

Calcule un type de végétation dominant par pixel à partir des signaux
morphologiques (altitude, pentes, exposition, flow, distance eau).
Les types correspondent aux prefabs WEGenerators de Reforger vanilla.
"""
from __future__ import annotations

import numpy as np
from scipy.ndimage import distance_transform_edt, gaussian_filter


# ── Définition des types de végétation ───────────────────────────────────────

VEG_TYPES: list[dict] = [
    # Zones fermées (splines de surface)
    {"id": "foret_bouleaux",   "label": "Forêt de bouleaux",    "color": (168, 216, 168), "linear": False},
    {"id": "foret_pins",       "label": "Forêt de pins",         "color": ( 74, 122,  74), "linear": False},
    {"id": "foret_epiceas",    "label": "Forêt d'épicéas",       "color": ( 45,  90,  45), "linear": False},
    {"id": "foret_mixte",      "label": "Forêt mixte",           "color": ( 92, 140,  92), "linear": False},
    {"id": "foret_charmes",    "label": "Forêt de charmes",      "color": (122, 154,  90), "linear": False},
    {"id": "clairiere",        "label": "Clairière",             "color": (200, 232, 168), "linear": False},
    {"id": "maquis_dense",     "label": "Maquis dense",          "color": (138, 122,  90), "linear": False},
    {"id": "maquis_sparse",    "label": "Maquis sparse",         "color": (184, 168, 120), "linear": False},
    {"id": "epicea_montagne",  "label": "Épicéa montagne",       "color": ( 26,  74,  58), "linear": False},
    {"id": "saule_humide",     "label": "Saule / zone humide",   "color": ( 90, 138, 122), "linear": False},
    {"id": "roseaux",          "label": "Roseaux",               "color": (168, 200,  72), "linear": False},
    {"id": "genevrier",        "label": "Genévrier",             "color": (106, 122,  90), "linear": False},
    {"id": "pierres",          "label": "Pierres / galets",      "color": (160, 160, 155), "linear": False},
    # Éléments linéaires (splines ouvertes)
    {"id": "haie",             "label": "Haie (noisetier)",      "color": (120, 144,  96), "linear": True},
    {"id": "roseaux_lineaires","label": "Roseaux (linéaire)",    "color": (200, 216,  96), "linear": True},
    {"id": "lisiere",          "label": "Lisière",               "color": (152, 184, 120), "linear": True},
]

VEG_COLORS: dict[str, tuple] = {v["id"]: v["color"] for v in VEG_TYPES}
VEG_LABELS: dict[str, str]   = {v["id"]: v["label"] for v in VEG_TYPES}


def _bell(arr: np.ndarray, lo: float, hi: float, slope: float = 0.08) -> np.ndarray:
    """Score sigmoïde : 1 dans [lo, hi], décroît en dehors."""
    center = (lo + hi) / 2.0
    half   = (hi - lo) / 2.0 + 1e-6
    dist   = np.abs(arr - center) - half
    return np.clip(1.0 - dist / (slope + 1e-6), 0.0, 1.0).astype(np.float32)


class VegetationGenerator:
    """
    Génère une carte 2D de végétation potentielle.

    Utilise les signaux morphologiques d'un NatureMapBiomesGenerator
    déjà instancié.
    """

    def __init__(self, nat_gen, cell_m: float):
        self.nat_gen = nat_gen
        self.cell_m  = cell_m
        self.H, self.W = nat_gen.height, nat_gen.width

    # ── Calcul des signaux de base ────────────────────────────────────────────

    def _build_signals(self, mask_water: np.ndarray) -> dict:
        h    = self.nat_gen.heightmap_original.astype(np.float32)
        land = ~mask_water

        h_lo = float(np.percentile(h[land], 2))  if land.any() else float(h.min())
        h_hi = float(np.percentile(h[land], 98)) if land.any() else float(h.max())
        alt  = np.clip((h - h_lo) / max(h_hi - h_lo, 1.0), 0.0, 1.0).astype(np.float32)
        alt  = np.where(mask_water, 0.0, alt)

        slopes = self.nat_gen.slopes.astype(np.float32)

        aspect_rad = np.radians(self.nat_gen.aspect.astype(np.float32))
        north_f    = np.clip( np.cos(aspect_rad), 0.0, 1.0)
        south_f    = np.clip(-np.cos(aspect_rad), 0.0, 1.0)

        flow   = self.nat_gen.flow_accumulation.astype(np.float32)
        f_p99  = float(np.percentile(flow[land], 99)) if land.any() else 1.0
        flow_n = np.clip(flow / (f_p99 + 1e-6), 0.0, 1.0)

        dist_water_m = distance_transform_edt(land.astype(np.uint8)).astype(np.float32) * self.cell_m

        # Humidité proxy : flow élevé + proche de l'eau
        humid = np.clip(
            flow_n * 0.6 + np.clip(1.0 - dist_water_m / 300.0, 0.0, 1.0) * 0.4,
            0.0, 1.0,
        )

        flat   = np.clip(1.0 - slopes / 15.0, 0.0, 1.0)
        steep  = np.clip((slopes - 25.0) / 20.0, 0.0, 1.0)

        not_water = land.astype(np.float32)

        return {
            "alt":          alt,
            "slopes":       slopes,
            "north_f":      north_f,
            "south_f":      south_f,
            "flow_n":       flow_n,
            "dist_water_m": dist_water_m,
            "humid":        humid,
            "flat":         flat,
            "steep":        steep,
            "not_water":    not_water,
            "land":         land,
        }

    # ── Scores par type ───────────────────────────────────────────────────────

    def compute(
        self,
        mask_water: np.ndarray,
        lock_masks: dict[str, np.ndarray] | None = None,
    ) -> dict[str, np.ndarray]:
        """
        Calcule un score [0-1] par type de végétation pour chaque pixel.

        lock_masks : {nom_fichier_stem -> array} zones verrouillées (champs,
                     urbain…) où la végétation naturelle ne pousse pas.
        Retourne : {type_id: array float32 H×W}
        """
        s = self._build_signals(mask_water)
        alt      = s["alt"]
        slopes   = s["slopes"]
        north_f  = s["north_f"]
        south_f  = s["south_f"]
        flow_n   = s["flow_n"]
        dist_w   = s["dist_water_m"]
        humid    = s["humid"]
        flat     = s["flat"]
        steep    = s["steep"]
        nw       = s["not_water"]
        land     = s["land"]

        # Masque zones verrouillées (urbain, champs…)
        if lock_masks:
            from PIL import Image as _PIL_Image
            lock = np.zeros((self.H, self.W), np.float32)
            for arr in lock_masks.values():
                if arr.shape != (self.H, self.W):
                    arr = np.array(
                        _PIL_Image.fromarray(arr).resize(
                            (self.W, self.H), _PIL_Image.LANCZOS
                        )
                    )
                np.maximum(lock, arr.astype(np.float32) / 255.0, out=lock)
            free = np.clip(1.0 - lock, 0.0, 1.0)
        else:
            free = nw.copy()

        def _score(alt_range, slope_max, orient=None, humid_w=0.0, extra=None):
            """Calcule un score de base combinant altitude, pente, orientation, humidité."""
            sc  = _bell(alt, alt_range[0], alt_range[1])
            sc *= np.clip(1.0 - slopes / max(slope_max, 1.0), 0.0, 1.0)
            if orient == "north":
                sc *= (north_f * 0.5 + 0.5)
            elif orient == "south":
                sc *= (south_f * 0.5 + 0.5)
            if humid_w > 0:
                sc *= (humid * humid_w + (1.0 - humid_w))
            if extra is not None:
                sc *= extra
            return (sc * nw * free).astype(np.float32)

        scores: dict[str, np.ndarray] = {}

        # ── Zones fermées ─────────────────────────────────────────────────────

        # Forêt de bouleaux : basse–moyenne alt, tous aspects, humidité normale
        scores["foret_bouleaux"] = _score((0.05, 0.55), slope_max=25)

        # Forêt de pins : basse–moyenne alt, exposition sud, sol sec
        scores["foret_pins"] = _score((0.05, 0.50), slope_max=25, orient="south",
                                      extra=np.clip(1.0 - humid * 0.6, 0.2, 1.0))

        # Forêt d'épicéas : moyenne–haute alt, exposition nord, fraîche
        scores["foret_epiceas"] = _score((0.30, 0.80), slope_max=25, orient="north", humid_w=0.3)

        # Forêt mixte : zone de transition bouleau/épicéa (altitude intermédiaire)
        scores["foret_mixte"] = _score((0.20, 0.50), slope_max=20)

        # Forêt de charmes : basse alt, exposition nord, humide, pente douce
        scores["foret_charmes"] = _score((0.05, 0.35), slope_max=15, orient="north", humid_w=0.5)

        # Clairière : toutes altitudes, très plat (≤ 10°)
        scores["clairiere"] = (
            _bell(alt, 0.05, 0.70)
            * np.clip(1.0 - slopes / 10.0, 0.0, 1.0)
            * nw * free
        ).astype(np.float32)

        # Maquis dense : altitude moyenne, pente modérée
        slope_mid = np.clip((slopes - 8.0) / 18.0, 0.0, 1.0) * np.clip(1.0 - slopes / 28.0, 0.0, 1.0)
        scores["maquis_dense"] = (
            _bell(alt, 0.20, 0.60) * slope_mid * nw * free
        ).astype(np.float32)

        # Maquis sparse : altitude moyenne–haute, pentes raides, exposition sud
        slope_steep = np.clip((slopes - 15.0) / 20.0, 0.0, 1.0) * np.clip(1.0 - slopes / 35.0, 0.0, 1.0)
        scores["maquis_sparse"] = (
            _bell(alt, 0.30, 0.75) * slope_steep * (south_f * 0.4 + 0.6) * nw * free
        ).astype(np.float32)

        # Épicéa montagne : haute altitude, pente modérée, exposition nord
        scores["epicea_montagne"] = _score((0.55, 0.90), slope_max=30, orient="north")

        # Saule / zone humide : basse altitude, très humide, quasi plat
        scores["saule_humide"] = (
            _bell(alt, 0.0, 0.30)
            * np.clip(1.0 - slopes / 12.0, 0.0, 1.0)
            * humid
            * nw * free
        ).astype(np.float32)

        # Roseaux : bord d'eau direct (< 80m), très plat
        near_water = np.clip(1.0 - dist_w / 80.0, 0.0, 1.0)
        scores["roseaux"] = (
            near_water
            * np.clip(1.0 - slopes / 6.0, 0.0, 1.0)
            * _bell(alt, 0.0, 0.20)
            * nw * free
        ).astype(np.float32)

        # Genévrier : altitude moyenne, pentes raides, exposition sud, sec
        scores["genevrier"] = (
            _bell(alt, 0.25, 0.65)
            * np.clip((slopes - 18.0) / 15.0, 0.0, 1.0)
            * (south_f * 0.5 + 0.5)
            * np.clip(1.0 - humid * 0.7, 0.2, 1.0)
            * nw * free
        ).astype(np.float32)

        # Pierres : côtier (< 150m mer) OU lit de rivière (flow élevé + basse alt)
        #           OU pied de zone rocheuse (alt moyenne, pente décroissante)
        coastal_stones = np.clip(1.0 - dist_w / 150.0, 0.0, 1.0) * nw
        river_stones   = flow_n * _bell(alt, 0.0, 0.30) * nw
        rock_foot      = _bell(alt, 0.20, 0.55) * np.clip((slopes - 10.0) / 20.0, 0.0, 1.0) * nw
        scores["pierres"] = np.clip(
            coastal_stones * 0.5 + river_stones * 0.35 + rock_foot * 0.15,
            0.0, 1.0,
        ).astype(np.float32)

        # ── Éléments linéaires ────────────────────────────────────────────────

        # Haie : bordure zones agricoles (lock_masks présents -> érodé = lisière)
        if lock_masks:
            from scipy.ndimage import binary_dilation, binary_erosion
            lock_bin = (lock >= 0.3)
            haie_mask = binary_dilation(lock_bin, iterations=3) & ~lock_bin & land
            scores["haie"] = haie_mask.astype(np.float32)
        else:
            scores["haie"] = np.zeros((self.H, self.W), np.float32)

        # Roseaux linéaires : axe de flow élevé (> 60e percentile) + altitude basse
        flow_thr = float(np.percentile(flow_n[land], 60)) if land.any() else 0.5
        scores["roseaux_lineaires"] = (
            np.clip((flow_n - flow_thr) / (1.0 - flow_thr + 1e-6), 0.0, 1.0)
            * _bell(alt, 0.0, 0.30)
            * nw
        ).astype(np.float32)

        # Lisière : transition forêt / clairière — contour des zones boisées
        foret_sum = (
            scores["foret_bouleaux"] + scores["foret_pins"] +
            scores["foret_epiceas"] + scores["foret_mixte"] + scores["foret_charmes"]
        )
        from scipy.ndimage import uniform_filter
        foret_blur  = uniform_filter(foret_sum.astype(np.float64), size=5).astype(np.float32)
        lisiere_raw = foret_blur * (1.0 - np.clip(foret_sum / (foret_blur + 1e-6), 0.0, 1.0))
        scores["lisiere"] = np.clip(lisiere_raw, 0.0, 1.0).astype(np.float32)

        # Lissage spatial léger pour éviter le bruit pixel
        _smooth = {
            "foret_bouleaux": 3.0, "foret_pins": 3.0, "foret_epiceas": 3.0,
            "foret_mixte": 2.5, "foret_charmes": 2.5, "clairiere": 2.0,
            "maquis_dense": 2.5, "maquis_sparse": 2.5, "epicea_montagne": 3.0,
            "saule_humide": 2.0, "roseaux": 1.5, "genevrier": 2.0, "pierres": 1.5,
        }
        for k, sig in _smooth.items():
            scores[k] = gaussian_filter(
                scores[k].astype(np.float64), sigma=sig
            ).astype(np.float32)

        return scores

    # ── Rendu RGB ─────────────────────────────────────────────────────────────

    def render_rgb(
        self,
        scores: dict[str, np.ndarray],
        mask_water: np.ndarray | None = None,
        min_score: float = 0.15,
        blend: bool = True,
    ) -> np.ndarray:
        """
        Génère une image RGB H×W×3.

        blend=True  : mélange pondéré des couleurs (dégradé aux frontières).
        blend=False : couleur du type dominant uniquement (carte nette).
        min_score   : score minimum pour qu'un type soit visible.
        mask_water  : si fourni, colorie l'eau en bleu.
        """
        _COLOR_WATER   = np.array([ 55,  90, 140], dtype=np.float32)  # bleu foncé
        _COLOR_NO_VEG  = np.array([ 60,  55,  50], dtype=np.float32)  # brun très sombre

        rgb = np.zeros((self.H, self.W, 3), dtype=np.float32)

        zone_ids = [v["id"] for v in VEG_TYPES]

        if blend:
            weight_sum = np.zeros((self.H, self.W), dtype=np.float32)
            for vid in zone_ids:
                if vid not in scores:
                    continue
                sc = np.clip(scores[vid], 0.0, 1.0)
                sc = np.where(sc >= min_score, sc, 0.0)
                c  = np.array(VEG_COLORS[vid], dtype=np.float32)
                rgb        += sc[..., np.newaxis] * c
                weight_sum += sc
            has_veg = weight_sum > 1e-6
            rgb[has_veg]  /= weight_sum[has_veg, np.newaxis]
            rgb[~has_veg]  = _COLOR_NO_VEG
        else:
            best_score = np.full((self.H, self.W), min_score, dtype=np.float32)
            rgb[:] = _COLOR_NO_VEG
            for vid in zone_ids:
                if vid not in scores:
                    continue
                sc = scores[vid]
                better = sc > best_score
                best_score[better] = sc[better]
                rgb[better] = np.array(VEG_COLORS[vid], dtype=np.float32)

        # Eau en bleu par-dessus tout
        if mask_water is not None:
            rgb[mask_water] = _COLOR_WATER

        return np.clip(rgb, 0, 255).astype(np.uint8)
