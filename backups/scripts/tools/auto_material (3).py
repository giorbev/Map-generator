"""
auto_material.py
================
Reproduit le comportement de l'Auto Material d'Unreal Engine 5 :
à partir d'une heightmap, simule l'érosion puis génère une splatmap
et une image de prévisualisation colorée, en assignant automatiquement
une texture à chaque pixel selon :
  - l'altitude (normalisée 0-1 ou en percentile selon le mode)
  - la pente / slope (idem)
  - l'exposition (aspect : face nord vs sud)
  - la concavité / convexité

Mode percentile (use_percentiles=True dans TerrainAnalyzer) :
  Les seuils de TextureLayer deviennent des rangs dans la distribution
  réelle du terrain. altitude_min=0.65 → "les 35 % de pixels les plus
  hauts", quelle que soit l'altitude absolue. Plus robuste sur des
  terrains atypiques (plaines, îles, déserts, heightmaps partielles).

Deux types d'érosion sont appliqués en pré-traitement :
  - Érosion thermique  : effondrement des pentes trop raides
  - Érosion hydraulique: ruissellement, creusement et dépôt de sédiments

Dépendances :
    pip install numpy scipy pillow matplotlib
"""

import numpy as np
from scipy.ndimage import gaussian_filter, sobel, laplace
from PIL import Image
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from dataclasses import dataclass, field
from pathlib import Path


# ─────────────────────────────────────────────────────────────
# 1. ÉROSION
# ─────────────────────────────────────────────────────────────

@dataclass
class ErosionConfig:
    """Paramètres des deux passes d'érosion."""

    # ── Érosion thermique ──────────────────────────────────────
    thermal_iterations: int   = 60     # Nombre de passes
    thermal_talus: float      = 0.015  # Pente critique (unités normalisées)
    thermal_rate: float       = 0.4    # Fraction de matériau déplacé par passe

    # ── Érosion hydraulique ────────────────────────────────────
    hydraulic_iterations: int = 40     # Nombre de cycles eau
    rainfall: float           = 0.02   # Eau ajoutée par cycle
    evaporation: float        = 0.015  # Eau évaporée par cycle
    erosion_rate: float       = 0.04   # Vitesse de dissolution roche→sédiment
    deposition_rate: float    = 0.03   # Vitesse de dépôt sédiment→roche
    sediment_capacity: float  = 0.08   # Capacité max de transport par unité d'eau

    # ── Courbure ──────────────────────────────────────────────
    # Pondère le flux sortant par la courbure locale du terrain.
    # Valeur 0 = comportement original (pas de courbure).
    # Valeur 0.5–1.0 = les creux concaves retiennent l'eau,
    # les crêtes convexes la dispersent plus vite.
    # Sur ton terrain : pentes douces avec creux peu marqués → 0.4–0.6.
    # Augmenter si les rivières ne ressortent pas assez.
    curvature_flow_weight: float = 0.5

    # ── Cartes dérivées exportées ──────────────────────────────
    export_flow: bool = True           # Carte d'accumulation de flux (rivières)
    export_sediment: bool = True       # Carte de dépôt final


def thermal_erosion(height: np.ndarray, cfg: ErosionConfig) -> np.ndarray:
    """
    Érosion thermique (éboulement) :
    si la différence d'altitude entre deux voisins dépasse le seuil `talus`,
    une fraction de matière glisse vers le voisin le plus bas.

    Simule l'effondrement gravitationnel des falaises et l'adoucissement
    des crêtes — visible surtout sur les arêtes et les escarpements.
    """
    h = height.copy()
    dirs = [(-1, 0), (1, 0), (0, -1), (0, 1),
            (-1, -1), (-1, 1), (1, -1), (1, 1)]
    diag_scale = [1.0, 1.0, 1.0, 1.0,
                  1.414, 1.414, 1.414, 1.414]

    for _ in range(cfg.thermal_iterations):
        delta = np.zeros_like(h)
        for (dr, dc), ds in zip(dirs, diag_scale):
            neighbor = np.roll(np.roll(h, -dr, axis=0), -dc, axis=1)
            diff = h - neighbor
            talus = cfg.thermal_talus * ds
            # Pixels où la pente dépasse le seuil
            mask = diff > talus
            transfer = mask * (diff - talus) * cfg.thermal_rate * 0.5
            delta -= transfer
            # Le voisin reçoit la même quantité (conservation)
            delta += np.roll(np.roll(transfer, dr, axis=0), dc, axis=1)
        h += delta

    return np.clip(h, 0.0, 1.0)


def hydraulic_erosion(
    height: np.ndarray,
    cfg: ErosionConfig,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Érosion hydraulique avec flux pondéré par la courbure locale.

    Principe du curvature-weighted flow :
      La courbure (laplacien normalisé) mesure si un pixel est dans un
      creux (concave, laplacien > 0 avant inversion) ou sur une crête
      (convexe). On en dérive un facteur de rétention :

        retention = 1 - curvature_flow_weight × concavity

      où concavity ∈ [0, 1], 1 = creux profond.

      Le flux sortant est multiplié par ce facteur :
        - creux profond  → retention faible → l'eau sort moins → accumulation
        - crête convexe  → retention ~1     → flux normal ou légèrement amplifié

      Concrètement sur ton terrain : les pentes douces qui descendent vers
      les rivières concentreront naturellement le flux dans les creux même
      peu marqués, sans avoir besoin d'une topographie très accentuée.

    Retourne :
        (heightmap érodée, flow_map normalisée 0-1, sediment_map 0-1)
    """
    h = height.copy()
    water    = np.zeros_like(h)
    sediment = np.zeros_like(h)
    flow_acc = np.zeros_like(h)

    dirs = [(-1, 0), (1, 0), (0, -1), (0, 1)]

    # ── Carte de courbure pré-calculée ──────────────────────────
    # On utilise le laplacien de la heightmap initiale.
    # Laplacien positif = creux (les voisins sont plus hauts en moyenne)
    # On normalise en [0, 1] et on l'appelle "concavity".
    from scipy.ndimage import laplace as _laplace
    curv_raw  = _laplace(h)
    # Creux = valeurs positives, crêtes = valeurs négatives
    concavity = np.clip(curv_raw, 0.0, None)
    c_max     = concavity.max()
    if c_max > 1e-8:
        concavity /= c_max   # normalisé 0-1

    for iteration in range(cfg.hydraulic_iterations):

        # ── Mise à jour courbure ────────────────────────────────
        # On recalcule à intervalles réguliers (pas à chaque cycle
        # pour des raisons de performance) pour suivre l'évolution
        # du terrain sous l'effet de l'érosion.
        if iteration % 10 == 0 and iteration > 0:
            curv_raw  = _laplace(h)
            concavity = np.clip(curv_raw, 0.0, None)
            c_max     = concavity.max()
            if c_max > 1e-8:
                concavity /= c_max

        # Facteur de rétention : 0 = creux profond retient tout,
        # 1 = crête, flux normal.
        # On garantit un minimum de 0.1 pour éviter de bloquer
        # complètement l'eau dans les creux très marqués.
        retention = np.clip(
            1.0 - cfg.curvature_flow_weight * concavity,
            0.1, 1.0
        )

        # 1. Pluie
        water += cfg.rainfall

        # 2. Dissolution roche → sédiment
        # Dans les creux, l'eau stagne donc érode plus longtemps.
        # On amplifie légèrement la dissolution par (2 - retention)
        # : creux (retention=0.1) → facteur 1.9 × ; crête → facteur 1.0 ×
        dissolve_factor = (2.0 - retention)
        dissolve = cfg.erosion_rate * water * dissolve_factor
        h       -= dissolve
        sediment += dissolve
        h = np.clip(h, 0.0, 1.0)

        # 3. Écoulement vers les 4 voisins
        new_water    = water.copy()
        new_sediment = sediment.copy()

        for dr, dc in dirs:
            neighbor_h     = np.roll(np.roll(h,     -dr, axis=0), -dc, axis=1)
            neighbor_water = np.roll(np.roll(water, -dr, axis=0), -dc, axis=1)

            surface     = h + water
            surface_nbr = neighbor_h + neighbor_water

            diff = surface - surface_nbr
            # Flux de base, modulé par le facteur de rétention :
            # les creux laissent sortir moins d'eau.
            flow = np.clip(diff * 0.25 * retention, 0.0, water * 0.25)

            sed_flow = flow * sediment / (water + 1e-8)

            new_water    -= flow
            new_sediment -= sed_flow
            new_water    += np.roll(np.roll(flow,     dr, axis=0), dc, axis=1)
            new_sediment += np.roll(np.roll(sed_flow, dr, axis=0), dc, axis=1)

            flow_acc += flow

        water    = np.clip(new_water,    0.0, None)
        sediment = np.clip(new_sediment, 0.0, None)

        # 4. Dépôt si excès de sédiment
        capacity = cfg.sediment_capacity * water
        excess   = np.maximum(sediment - capacity, 0.0)
        deposit  = excess * cfg.deposition_rate
        h       += deposit
        sediment -= deposit

        # 5. Évaporation
        evap_frac    = np.clip(cfg.evaporation / (water + 1e-8), 0.0, 1.0)
        deposit_evap = sediment * evap_frac
        h           += deposit_evap
        sediment    -= deposit_evap
        water       *= np.clip(1.0 - evap_frac, 0.0, 1.0)

    # Normalisation log de la carte de flux (les rivières ont des valeurs
    # très élevées, le log évite qu'elles écrasent le reste)
    flow_acc  = np.log1p(flow_acc)
    flo, fhi  = flow_acc.min(), flow_acc.max()
    flow_norm = (flow_acc - flo) / (fhi - flo + 1e-8)

    h = np.clip(h, 0.0, 1.0)
    return h, flow_norm, np.clip(sediment, 0.0, 1.0)


def apply_erosion(
    height: np.ndarray,
    cfg: ErosionConfig | None = None,
    verbose: bool = True,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Applique les deux passes d'érosion dans l'ordre correct :
      1. Érosion thermique  (forme les éboulis, adoucit les crêtes)
      2. Érosion hydraulique (creuse les vallées, dépose alluvions)

    Retourne :
        (heightmap finale, flow_map, sediment_map)
    Les deux cartes secondaires peuvent être réinjectées dans l'Auto Material
    comme masques supplémentaires (zones de rivières, zones alluviales).
    """
    if cfg is None:
        cfg = ErosionConfig()

    if verbose:
        print(f"  Érosion thermique  ({cfg.thermal_iterations} passes)...")
    h = thermal_erosion(height, cfg)

    if verbose:
        print(f"  Érosion hydraulique ({cfg.hydraulic_iterations} cycles)...")
    h, flow_map, sediment_map = hydraulic_erosion(h, cfg)

    if verbose:
        delta_rms = float(np.sqrt(np.mean((h - height) ** 2)))
        print(f"  Δ RMS heightmap : {delta_rms:.4f}  (0=aucun effet, >0.05=fort)")

    return h, flow_map, sediment_map


# ─────────────────────────────────────────────────────────────
# 2. DÉFINITION DES COUCHES (calques de texture)
# ─────────────────────────────────────────────────────────────

@dataclass
class TextureLayer:
    """
    Représente une couche de texture (équivalent d'un layer dans l'Auto Material).

    Les seuils (altitude_min/max, slope_min/max) s'interprètent différemment
    selon le mode choisi dans TerrainAnalyzer :

      Mode absolu   (use_percentiles=False, défaut) :
        Valeurs normalisées 0-1 issues directement du min/max de la heightmap.

      Mode percentile (use_percentiles=True) :
        Rangs dans la distribution réelle. altitude_min=0.65 → les 35 %
        de pixels les plus hauts. S'adapte automatiquement au terrain.

    flow_weight et sediment_weight sont toujours en valeur absolue (0-1)
    car les cartes de flux et de dépôt sont déjà des distributions
    normalisées issues de l'érosion — les percentiliser n'apporterait rien.

      flow_weight > 0     : la couche est renforcée là où l'eau s'accumule
                            (creux humides, fond de vallée, lit de rivière).
                            grass3, forest_decidious_dense en bénéficient.

      sediment_weight > 0 : la couche est renforcée là où les sédiments
                            se déposent après érosion hydraulique.
                            dirt1 (mud) en est le cas principal.
    """
    name: str
    color: tuple          # Couleur de prévisualisation (R, G, B) 0-255

    # Altitude
    altitude_min: float = 0.0
    altitude_max: float = 1.0
    altitude_blend: float = 0.08

    # Pente (0 = plat, 1 = vertical)
    slope_min: float = 0.0
    slope_max: float = 1.0
    slope_blend: float = 0.08

    # Exposition (0 = nord, 0.5 = est/ouest, 1 = sud)
    aspect_min: float = 0.0
    aspect_max: float = 1.0
    aspect_weight: float = 0.0   # 0 = ignoré

    # Cartes d'érosion (0 = ignoré, 1 = influence maximale)
    flow_weight: float     = 0.0  # flux hydraulique accumulé
    sediment_weight: float = 0.0  # dépôt sédimentaire

    priority: int = 0


# ── Terrain tempéré Reforger ─────────────────────────────────
# 17 textures organisées en 5 groupes :
#   EAU      : seabed, pebble
#   SOL NU   : rock, debris_rock, dirt1, dirt2, dirt3
#   HERBE    : grass1, grass2, grass3
#   MONTAGNE : mountain_grass1, mountain_grass2, mountain_grass3
#   FORÊT    : forest_decidious_dense, forest_decidious_sparse,
#              forest_coniferous_dense, forest_coniferous_sparse
#
# Les priorités garantissent l'ordre de superposition :
#   eau (10) > roche/debris (7-8) > montagne (5-6) >
#   forêt (5) > herbe (4) > dirt (3)
#
# aspect_weight > 0 uniquement pour les forêts (nord/sud).
# Les seuils sont pensés pour use_percentiles=True.
# ─────────────────────────────────────────────────────────────

DEFAULT_LAYERS = [

    # ── EAU ──────────────────────────────────────────────────
    TextureLayer(
        name="seabed",
        color=(28, 60, 120),
        altitude_min=0.0,  altitude_max=0.07,  altitude_blend=0.02,
        slope_min=0.0,     slope_max=1.0,
        priority=10,
    ),
    TextureLayer(
        name="pebble",
        color=(160, 148, 118),
        altitude_min=0.05, altitude_max=0.13,  altitude_blend=0.03,
        slope_min=0.0,     slope_max=0.22,     slope_blend=0.04,
        priority=8,
    ),

    # ── SOL NU ───────────────────────────────────────────────
    TextureLayer(
        name="rock",
        color=(105, 95, 82),
        altitude_min=0.08, altitude_max=1.0,   altitude_blend=0.05,
        slope_min=0.30,    slope_max=1.0,      slope_blend=0.06,
        priority=7,
    ),
    TextureLayer(
        name="debris_rock",
        color=(130, 118, 100),
        altitude_min=0.30, altitude_max=1.0,   altitude_blend=0.08,
        slope_min=0.25,    slope_max=0.55,     slope_blend=0.06,
        priority=7,
    ),
    TextureLayer(
        # Mud / fond de vallée — activé par la carte de dépôt sédimentaire
        # et les pentes très douces (flow élevé géré en post via sediment_map)
        name="dirt1",
        color=(100, 72, 44),
        altitude_min=0.06, altitude_max=0.40,  altitude_blend=0.06,
        slope_min=0.0,     slope_max=0.18,     slope_blend=0.05,
        sediment_weight=0.6,   # renforcé là où les alluvions se déposent
        priority=3,
    ),
    TextureLayer(
        name="dirt2",
        color=(122, 88, 56),
        altitude_min=0.10, altitude_max=0.55,  altitude_blend=0.07,
        slope_min=0.12,    slope_max=0.32,     slope_blend=0.06,
        priority=3,
    ),
    TextureLayer(
        # Terre d'éboulis — complément de debris_rock sur pentes fortes
        name="dirt3",
        color=(110, 80, 50),
        altitude_min=0.20, altitude_max=0.80,  altitude_blend=0.08,
        slope_min=0.22,    slope_max=0.45,     slope_blend=0.06,
        priority=4,
    ),

    # ── HERBE ────────────────────────────────────────────────
    TextureLayer(
        # Herbe rase — plat exposé, crêtes, zones convexes
        name="grass1",
        color=(115, 148, 68),
        altitude_min=0.08, altitude_max=0.45,  altitude_blend=0.06,
        slope_min=0.0,     slope_max=0.18,     slope_blend=0.05,
        priority=4,
    ),
    TextureLayer(
        # Herbe moyenne — pente douce standard
        name="grass2",
        color=(88, 128, 52),
        altitude_min=0.08, altitude_max=0.50,  altitude_blend=0.07,
        slope_min=0.05,    slope_max=0.24,     slope_blend=0.06,
        priority=4,
    ),
    TextureLayer(
        # Herbe haute — creux humides, flow élevé, zones concaves
        name="grass3",
        color=(65, 108, 40),
        altitude_min=0.08, altitude_max=0.50,  altitude_blend=0.07,
        slope_min=0.0,     slope_max=0.18,     slope_blend=0.05,
        flow_weight=0.7,       # s'active fortement dans les creux où l'eau coule
        priority=5,
    ),

    # ── MONTAGNE ─────────────────────────────────────────────
    TextureLayer(
        # Herbe de plateau — haute altitude, pente douce
        name="mountain_grass1",
        color=(128, 138, 80),
        altitude_min=0.45, altitude_max=0.80,  altitude_blend=0.07,
        slope_min=0.0,     slope_max=0.22,     slope_blend=0.05,
        priority=5,
    ),
    TextureLayer(
        # Toundra caillouteuse — petits buissons, sol jaune, cailloux
        name="mountain_grass2",
        color=(148, 138, 82),
        altitude_min=0.50, altitude_max=0.85,  altitude_blend=0.07,
        slope_min=0.08,    slope_max=0.28,     slope_blend=0.06,
        priority=5,
    ),
    TextureLayer(
        # Sol terreux avec débris — transition roche/toundra
        name="mountain_grass3",
        color=(118, 105, 68),
        altitude_min=0.55, altitude_max=0.90,  altitude_blend=0.07,
        slope_min=0.10,    slope_max=0.35,     slope_blend=0.06,
        priority=6,
    ),

    # ── FORÊT ────────────────────────────────────────────────
    # Feuillus : versants sud (aspect 0.3–0.7), altitude basse-moyenne
    # Conifères : versants nord (aspect 0.0–0.3 + 0.7–1.0), altitude plus haute
    # Dense : pente < seuil bas   |   Clairsemé : pente plus marquée
    TextureLayer(
        name="forest_decidious_dense",
        color=(48, 88, 30),
        altitude_min=0.10, altitude_max=0.52,  altitude_blend=0.07,
        slope_min=0.0,     slope_max=0.18,     slope_blend=0.05,
        aspect_min=0.25,   aspect_max=0.75,    aspect_weight=0.35,
        flow_weight=0.4,       # les feuillus denses aiment les fonds de vallon humides
        priority=5,
    ),
    TextureLayer(
        name="forest_decidious_sparse",
        color=(68, 108, 45),
        altitude_min=0.10, altitude_max=0.52,  altitude_blend=0.07,
        slope_min=0.15,    slope_max=0.28,     slope_blend=0.06,
        aspect_min=0.25,   aspect_max=0.75,    aspect_weight=0.30,
        priority=5,
    ),
    TextureLayer(
        name="forest_coniferous_dense",
        color=(30, 68, 42),
        altitude_min=0.35, altitude_max=0.70,  altitude_blend=0.07,
        slope_min=0.0,     slope_max=0.20,     slope_blend=0.05,
        aspect_min=0.60,   aspect_max=1.0,     aspect_weight=0.30,
        priority=5,
    ),
    TextureLayer(
        name="forest_coniferous_sparse",
        color=(45, 85, 55),
        altitude_min=0.35, altitude_max=0.75,  altitude_blend=0.07,
        slope_min=0.18,    slope_max=0.32,     slope_blend=0.06,
        aspect_min=0.60,   aspect_max=1.0,     aspect_weight=0.25,
        priority=5,
    ),
]


# ─────────────────────────────────────────────────────────────
# 3. ANALYSE DE LA HEIGHTMAP
# ─────────────────────────────────────────────────────────────

class TerrainAnalyzer:
    """
    Calcule toutes les cartes dérivées depuis la heightmap brute.

    Args:
        heightmap       : tableau 2D float (n'importe quelle plage).
        smooth_sigma    : lissage gaussien avant dérivation.
        use_percentiles : si True, height_pct et slope_pct sont utilisées
                          dans layer_weight — seuils = rangs de distribution.
        flow_map        : carte de flux hydraulique 0-1 issue de l'érosion.
                          Si None, flow_weight dans TextureLayer est ignoré.
        sediment_map    : carte de dépôt sédimentaire 0-1 issue de l'érosion.
                          Si None, sediment_weight dans TextureLayer est ignoré.
    """

    def __init__(
        self,
        heightmap: np.ndarray,
        smooth_sigma: float = 1.5,
        use_percentiles: bool = False,
        flow_map: np.ndarray | None = None,
        sediment_map: np.ndarray | None = None,
    ):
        self.use_percentiles = use_percentiles

        lo, hi = heightmap.min(), heightmap.max()
        self.height = (heightmap - lo) / (hi - lo + 1e-8)
        self.height = gaussian_filter(self.height, sigma=smooth_sigma)

        self.rows, self.cols = self.height.shape
        self._compute_slope()
        self._compute_aspect()
        self._compute_curvature()

        self.height_pct = self._to_percentile(self.height)
        self.slope_pct  = self._to_percentile(self.slope)

        # Cartes d'érosion — lissage léger pour adoucir les transitions
        self.flow_map     = gaussian_filter(flow_map,     sigma=1.0) if flow_map     is not None else None
        self.sediment_map = gaussian_filter(sediment_map, sigma=1.0) if sediment_map is not None else None

        if use_percentiles:
            print("  Mode percentile activé.")
        if flow_map is not None:
            print("  Carte de flux chargée — flow_weight actif.")
        if sediment_map is not None:
            print("  Carte de dépôt chargée — sediment_weight actif.")

    @staticmethod
    def _to_percentile(arr: np.ndarray) -> np.ndarray:
        """
        Convertit un tableau 2D en rangs percentiles (0-1).
        Chaque pixel reçoit son rang dans la distribution de toute la carte.
        Équivalent d'un rank-transform normalisé.
        """
        flat = arr.ravel()
        order = flat.argsort()
        ranks = np.empty_like(order, dtype=float)
        ranks[order] = np.linspace(0.0, 1.0, len(flat))
        return ranks.reshape(arr.shape)

    def _compute_slope(self):
        """Pente normalisée 0-1 (0=plat, 1=vertical)."""
        gx = sobel(self.height, axis=1)
        gy = sobel(self.height, axis=0)
        self.slope = np.arctan(np.hypot(gx, gy)) / (np.pi / 2)

    def _compute_aspect(self):
        """
        Exposition : direction de la pente.
        0 = nord (gy<0), 0.5 = est/ouest, 1 = sud (gy>0).
        Normalisé 0-1 pour faciliter les comparaisons.
        """
        gx = sobel(self.height, axis=1)
        gy = sobel(self.height, axis=0)
        angle = np.arctan2(gy, gx)
        self.aspect = (angle + np.pi) / (2 * np.pi)

    def _compute_curvature(self):
        """Courbure (laplacien) : positif = convexe (crête), négatif = concave (cuvette)."""
        raw = laplace(self.height)
        lo, hi = raw.min(), raw.max()
        self.curvature = (raw - lo) / (hi - lo + 1e-8)


# ─────────────────────────────────────────────────────────────
# 4. GÉNÉRATION DE LA SPLATMAP
# ─────────────────────────────────────────────────────────────

def _smooth_step(edge0: float, edge1: float, x: np.ndarray) -> np.ndarray:
    """Interpolation cubique douce (smoothstep), analogue HLSL."""
    t = np.clip((x - edge0) / (edge1 - edge0 + 1e-8), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def layer_weight(layer: TextureLayer, analyzer: TerrainAnalyzer) -> np.ndarray:
    """
    Calcule le poids (0-1) de la couche pour chaque pixel.

    Combinaison des critères dans l'ordre :
      1. altitude × pente          → zone de base (obligatoire)
      2. × aspect                  → modulation exposition nord/sud (optionnel)
      3. × (1 + flow_boost)        → amplification dans les creux humides
      4. × (1 + sediment_boost)    → amplification sur dépôts sédimentaires

    Le flow et le sédiment *amplifient* le poids de base sans jamais
    créer de couverture là où la zone altitude/pente est nulle.
    Cela évite que grass3 apparaisse sur une crête juste parce qu'un
    pixel de flux s'y trouve par artefact.
    """
    alt = analyzer.height_pct if analyzer.use_percentiles else analyzer.height
    sl  = analyzer.slope_pct  if analyzer.use_percentiles else analyzer.slope

    # ── 1. Masque altitude ──
    w_alt = (
        _smooth_step(layer.altitude_min - layer.altitude_blend,
                     layer.altitude_min + layer.altitude_blend, alt)
        * _smooth_step(layer.altitude_max + layer.altitude_blend,
                       layer.altitude_max - layer.altitude_blend, alt)
    )

    # ── 2. Masque pente ──
    w_slope = (
        _smooth_step(layer.slope_min - layer.slope_blend,
                     layer.slope_min + layer.slope_blend, sl)
        * _smooth_step(layer.slope_max + layer.slope_blend,
                       layer.slope_max - layer.slope_blend, sl)
    )

    w = w_alt * w_slope

    # ── 3. Exposition (aspect) ──
    if layer.aspect_weight > 0:
        asp = analyzer.aspect
        w_asp = (
            _smooth_step(layer.aspect_min - 0.1, layer.aspect_min + 0.1, asp)
            * _smooth_step(layer.aspect_max + 0.1, layer.aspect_max - 0.1, asp)
        )
        w = w * (1.0 - layer.aspect_weight + layer.aspect_weight * w_asp)

    # ── 4. Flux hydraulique ──
    # Amplifie le poids jusqu'à ×(1 + flow_weight) dans les zones
    # de forte accumulation d'eau. flow_map = 0 (sec) → 1 (rivière/creux).
    if layer.flow_weight > 0.0 and analyzer.flow_map is not None:
        boost = layer.flow_weight * analyzer.flow_map
        w = w * (1.0 + boost)

    # ── 5. Dépôt sédimentaire ──
    # Amplifie là où l'érosion a laissé des alluvions.
    # sediment_map = 0 (roche nue) → 1 (forte accumulation).
    if layer.sediment_weight > 0.0 and analyzer.sediment_map is not None:
        boost = layer.sediment_weight * analyzer.sediment_map
        w = w * (1.0 + boost)

    return np.clip(w, 0.0, 1.0)


def build_splatmap(
    analyzer: TerrainAnalyzer,
    layers: list[TextureLayer],
    n_channels: int = 4,
) -> tuple[np.ndarray, list[TextureLayer]]:
    """
    Produit une splatmap (H, W, n_channels) avec les poids normalisés,
    et retourne les couches correspondant à chaque canal.

    UE5 utilise des splatmaps RGBA = 4 textures par carte.
    On peut enchaîner plusieurs splatmaps pour plus de couches.
    """
    H, W = analyzer.rows, analyzer.cols
    layers_sorted = sorted(layers, key=lambda l: l.priority, reverse=True)

    # Calcul de tous les poids bruts
    weights = np.stack([layer_weight(l, analyzer) for l in layers_sorted], axis=-1)

    # Accumulation avec priorité : une couche de haute priorité "écrase" les autres
    # Méthode : on normalise par la somme, mais en pondérant par la priorité
    priority_vec = np.array([l.priority for l in layers_sorted], dtype=float)
    # Modulation : le poids effectif = poids * priority^0.5
    weights_mod = weights * np.sqrt(priority_vec)[np.newaxis, np.newaxis, :]
    total = weights_mod.sum(axis=-1, keepdims=True)
    weights_norm = weights_mod / (total + 1e-8)

    # Sélection des n_channels premiers canaux les plus significatifs en moyenne
    mean_weights = weights_norm.mean(axis=(0, 1))
    top_idx = np.argsort(mean_weights)[::-1][:n_channels]
    top_idx = sorted(top_idx)  # conserve l'ordre d'origine

    splatmap = weights_norm[:, :, top_idx]

    # Re-normalisation sur les canaux sélectionnés
    splatmap /= (splatmap.sum(axis=-1, keepdims=True) + 1e-8)

    selected_layers = [layers_sorted[i] for i in top_idx]
    return splatmap.astype(np.float32), selected_layers


# ─────────────────────────────────────────────────────────────
# 5. VISUALISATION
# ─────────────────────────────────────────────────────────────

def preview_color(
    splatmap: np.ndarray,
    selected_layers: list[TextureLayer],
) -> np.ndarray:
    """
    Compose une image RGB de prévisualisation en mélangeant
    les couleurs des couches pondérées par la splatmap.
    """
    H, W = splatmap.shape[:2]
    result = np.zeros((H, W, 3), dtype=float)

    for i, layer in enumerate(selected_layers):
        color = np.array(layer.color, dtype=float) / 255.0
        w = splatmap[:, :, i : i + 1]
        result += w * color

    return np.clip(result, 0, 1)


def visualize_all(
    analyzer: TerrainAnalyzer,
    splatmap: np.ndarray,
    selected_layers: list[TextureLayer],
    flow_map: np.ndarray | None = None,
    sediment_map: np.ndarray | None = None,
    save_path: str = "auto_material_result.png",
):
    n = len(selected_layers)
    # Ligne 1 : terrain analysé (+ érosion si dispo)
    top_cols = max(n + 1, 4)
    fig, axes = plt.subplots(2, top_cols, figsize=(4 * top_cols, 8))
    fig.patch.set_facecolor("#111")

    def show(ax, img, title, cmap=None):
        if img is None:
            ax.axis("off")
            return
        ax.imshow(img, cmap=cmap, aspect="auto", interpolation="nearest")
        ax.set_title(title, color="white", fontsize=9, pad=4)
        ax.axis("off")

    show(axes[0, 0], analyzer.height,    "Heightmap érodée",   cmap="terrain")
    show(axes[0, 1], analyzer.slope,     "Pente",              cmap="hot")
    show(axes[0, 2], flow_map,           "Flux (rivières)",    cmap="Blues")
    show(axes[0, 3], sediment_map,       "Dépôt sédiments",    cmap="YlOrBr")
    for i in range(4, top_cols):
        axes[0, i].axis("off")

    # Ligne 2 : canaux splatmap + prévisualisation finale
    for i, layer in enumerate(selected_layers):
        show(axes[1, i], splatmap[:, :, i], layer.name, cmap="gray")
    for i in range(n, top_cols - 1):
        axes[1, i].axis("off")

    color_img = preview_color(splatmap, selected_layers)
    show(axes[1, top_cols - 1], color_img, "Prévisualisation finale")

    plt.tight_layout(pad=0.5)
    plt.savefig(save_path, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    print(f"Résultat → {save_path}")
    plt.show()


# ─────────────────────────────────────────────────────────────
# 6. EXPORT MASQUES PNG 16-BIT (1 fichier par texture)
# ─────────────────────────────────────────────────────────────

def export_masks_16bit(
    splatmap: np.ndarray,
    selected_layers: list[TextureLayer],
    output_dir: str = "masks",
) -> list[str]:
    """
    Exporte un PNG 16-bit par texture dans output_dir.

    Format : grayscale 16-bit (uint16), valeur 0-65535.
    0 = texture absente, 65535 = texture pleine couverture.

    PNG 16-bit est le format attendu par la plupart des outils
    de terrain (Reforger, World Machine, Houdini...) pour les
    masques de poids — meilleure précision que 8-bit pour les
    zones de transition.
    """
    import os
    os.makedirs(output_dir, exist_ok=True)

    paths = []
    for i, layer in enumerate(selected_layers):
        # float32 0-1 → uint16 0-65535
        channel = splatmap[:, :, i]
        mask16 = (channel * 65535).clip(0, 65535).astype(np.uint16)

        img = Image.fromarray(mask16, mode="I;16")
        path = os.path.join(output_dir, f"{layer.name}.png")
        img.save(path)
        coverage = (channel > 0.05).mean() * 100
        print(f"  {layer.name:20s} → {path}  ({coverage:.1f}% couverture)")
        paths.append(path)

    print(f"  {len(paths)} masques 16-bit → {output_dir}/")
    return paths


# ─────────────────────────────────────────────────────────────
# 7. CHARGEMENT HEIGHTMAP (PNG, ASC, TIF)
# ─────────────────────────────────────────────────────────────

def load_heightmap(path: str) -> tuple[np.ndarray, dict]:
    """
    Charge une heightmap depuis PNG, ASC (ESRI ASCII Grid) ou TIF/GeoTIFF.
    Retourne un tableau float32 normalisé 0-1 et un dict de métadonnées.

    Formats supportés :
        .png / .tif / .tiff  → via PIL (8-bit ou 16-bit)
        .asc                 → ESRI ASCII Grid, lit le header puis la grille

    Métadonnées retournées (dict) :
        format       : "png" | "asc" | "tif"
        shape        : (rows, cols)
        cellsize     : taille d'un pixel en unités terrain (ASC uniquement)
        nodata_value : valeur NODATA remplacée par 0 (ASC uniquement)
        min_elev     : altitude min brute avant normalisation
        max_elev     : altitude max brute avant normalisation
    """
    ext = path.lower().rsplit(".", 1)[-1]
    meta = {"format": ext}

    if ext == "asc":
        # ── ESRI ASCII Grid ──────────────────────────────────
        header = {}
        header_keys = {"ncols", "nrows", "xllcorner", "xllcenter",
                       "yllcorner", "yllcenter", "cellsize", "nodata_value"}
        data_start = 0

        with open(path, "r") as f:
            lines = f.readlines()

        for i, line in enumerate(lines):
            parts = line.strip().split()
            if len(parts) == 2 and parts[0].lower() in header_keys:
                header[parts[0].lower()] = parts[1]
                data_start = i + 1
            else:
                break

        ncols    = int(header["ncols"])
        nrows    = int(header["nrows"])
        cellsize = float(header.get("cellsize", 1.0))
        nodata   = float(header.get("nodata_value", -9999))

        # Lecture de la grille de valeurs
        rows = []
        for line in lines[data_start:]:
            vals = line.strip().split()
            if vals:
                rows.append([float(v) for v in vals])

        hmap = np.array(rows, dtype=np.float32)

        # Remplacement NODATA par NaN puis interpolation aux bords
        hmap[hmap == nodata] = np.nan
        if np.any(np.isnan(hmap)):
            # Remplacement simple : NaN → moyenne des voisins valides
            from scipy.ndimage import generic_filter
            def _nanmean(v):
                valid = v[~np.isnan(v)]
                return valid.mean() if len(valid) > 0 else 0.0
            mask_nan = np.isnan(hmap)
            hmap[mask_nan] = generic_filter(hmap, _nanmean, size=3,
                                             mode="nearest")[mask_nan]

        meta.update({
            "cellsize":     cellsize,
            "nodata_value": nodata,
            "ncols":        ncols,
            "nrows":        nrows,
        })
        print(f"  ASC : {nrows}×{ncols} px  cellsize={cellsize}m")

    elif ext in ("tif", "tiff"):
        # ── GeoTIFF via PIL ──────────────────────────────────
        img  = Image.open(path)
        hmap = np.array(img, dtype=np.float32)
        if hmap.ndim == 3:
            hmap = hmap[:, :, 0]   # premier canal si multi-bande
        print(f"  TIF : {hmap.shape[0]}×{hmap.shape[1]} px")

    else:
        # ── PNG 8-bit ou 16-bit ──────────────────────────────
        img  = Image.open(path)
        hmap = np.array(img, dtype=np.float32)
        if hmap.ndim == 3:
            hmap = hmap[:, :, 0]
        print(f"  PNG : {hmap.shape[0]}×{hmap.shape[1]} px  "
              f"({'16-bit' if hmap.max() > 255 else '8-bit'})")

    # Normalisation 0-1
    lo, hi = float(np.nanmin(hmap)), float(np.nanmax(hmap))
    hmap   = (hmap - lo) / (hi - lo + 1e-8)
    hmap   = hmap.astype(np.float32)

    meta.update({"shape": hmap.shape, "min_elev": lo, "max_elev": hi})
    return hmap, meta


# ─────────────────────────────────────────────────────────────
# 8. POINT D'ENTRÉE
# ─────────────────────────────────────────────────────────────

def generate_auto_material(
    heightmap_path: str,
    layers: list[TextureLayer] | None = None,
    erosion_cfg: ErosionConfig | None = None,
    smooth_sigma: float = 1.5,
    use_percentiles: bool = False,
    n_channels: int = 4,
    output_preview: str = "auto_material_result.png",
    output_masks_dir: str = "masks",
) -> tuple[np.ndarray, list[TextureLayer]]:
    """
    Pipeline complet depuis une heightmap PNG, ASC ou TIF.

    Args:
        heightmap_path  : chemin vers le fichier (.png, .asc, .tif).
        layers          : couches de texture (DEFAULT_LAYERS si None).
        erosion_cfg     : paramètres d'érosion (ErosionConfig() si None).
                          Passer ErosionConfig(thermal_iterations=0,
                          hydraulic_iterations=0) pour désactiver.
        smooth_sigma    : lissage gaussien avant analyse.
        use_percentiles : seuils interprétés comme rangs percentiles.
        n_channels      : nombre de textures dans la splatmap.
        output_preview  : chemin de sortie de la visualisation.
        output_masks_dir: dossier de sortie des masques PNG 16-bit.

    Returns:
        (splatmap, selected_layers) — splatmap float32 (H, W, n_channels)
    """
    if layers is None:
        layers = DEFAULT_LAYERS
    if erosion_cfg is None:
        erosion_cfg = ErosionConfig()

    print("→ Chargement de la heightmap...")
    hmap, meta = load_heightmap(heightmap_path)
    print(f"  altitude brute : {meta['min_elev']:.1f} → {meta['max_elev']:.1f}")

    print("→ Érosion...")
    hmap_eroded, flow_map, sediment_map = apply_erosion(hmap, erosion_cfg)

    print("→ Analyse du terrain érodé...")
    analyzer = TerrainAnalyzer(
        hmap_eroded * 255.0,
        smooth_sigma=smooth_sigma,
        use_percentiles=use_percentiles,
        flow_map=flow_map,
        sediment_map=sediment_map,
    )

    print("→ Calcul des poids par couche...")
    splatmap, selected = build_splatmap(analyzer, layers, n_channels=n_channels)

    print("→ Visualisation...")
    visualize_all(analyzer, splatmap, selected,
                  flow_map=flow_map, sediment_map=sediment_map,
                  save_path=output_preview)

    print("→ Export masques 16-bit...")
    export_masks_16bit(splatmap, selected, output_dir=output_masks_dir)

    return splatmap, selected


# ─────────────────────────────────────────────────────────────
# DEMO
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os

    demo_path = "demo_heightmap.png"
    if not os.path.exists(demo_path):
        print("Génération d'une heightmap de démonstration...")
        size = 512
        rng = np.random.default_rng(7)
        x = np.linspace(0, 6 * np.pi, size)
        y = np.linspace(0, 6 * np.pi, size)
        xx, yy = np.meshgrid(x, y)
        terrain = (
            0.45 * np.sin(xx * 0.5) * np.cos(yy * 0.4)
            + 0.30 * np.sin(xx * 1.1 + 0.5) * np.sin(yy * 0.9)
            + 0.12 * rng.random((size, size))
            + 0.10 * np.sin(xx * 2.2) * np.cos(yy * 2.0)
            + 0.08 * np.sin(xx * 0.2 + yy * 0.15)
        )
        terrain = (terrain - terrain.min()) / (terrain.max() - terrain.min())
        Image.fromarray((terrain * 255).astype(np.uint8)).save(demo_path)
        print(f"  Sauvegardée → {demo_path}")

    erosion = ErosionConfig(
        thermal_iterations=80,
        thermal_talus=0.012,
        hydraulic_iterations=50,
        rainfall=0.02,
        erosion_rate=0.035,
        deposition_rate=0.025,
        curvature_flow_weight=0.5,  # 0 = désactivé, 0.5 = modéré, 1.0 = fort
        # Sur terrain à pentes douces avec creux peu marqués : 0.4–0.6
        # Augmenter si les lits de rivière ne ressortent pas assez
    )

    splatmap, layers = generate_auto_material(
        heightmap_path=demo_path,
        erosion_cfg=erosion,
        smooth_sigma=1.5,
        use_percentiles=True,
        n_channels=17,           # toutes les textures, 1 masque PNG par texture
        output_preview="auto_material_result.png",
        output_masks_dir="masks",
    )
    print("\nTerminé.")

