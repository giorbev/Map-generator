"""
Reforger Texture Mask Generator v2
Generates grayscale PNG masks (8-bit) for Reforger terrain texturing.

Features:
  - 4 biographic profiles: europe_temperee, boreal, mediterraneen, arctique
  - Morphological analysis (altitude, slope, aspect, TPI, flow)
  - Soft transitions between textures (gaussian blur on edges)
  - Block-level arbiter: enforces Reforger 5-texture-per-block limit
  - Export at heightmap resolution + color preview
  - Generation report with apply order

Block math (default Reforger 4m resolution):
  128m block / 4m per pixel = 32 pixels per block
  -> 128 blocks for a 4097-vertex (4096m) heightmap
"""

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, label as _nd_label
import os
import json
from datetime import datetime


class ReforgerMaskGenerator:
    """
    Generates terrain texture masks for Arma Reforger surface maps.
    Requires a NatureMapBiomesGenerator instance as morphological data source.
    """

    # ── 4 Texture Profiles ────────────────────────────────────────────────
    # Each texture: (internal_key, emat_filename, apply_priority)
    # apply_priority: 1=first (base, lowest), 7=last (top override)
    PROFILES = {
        'europe_temperee': {
            'label': 'Europe Temperee',
            'desc':  'Prairie, foret decidue, roche, humide, galets cotes.',
            'block_px': 32,
            'fallback': 'grass_base',
            'textures': [
                ('grass_base',    'Grass_02.emat',                 1),
                ('grass_dry',     'Grass_03.emat',                 2),
                ('forest_floor',  'ForestDeciduous_01_Base.emat',  3),
                ('wet_soil',      'Dirt_03.emat',                  4),
                ('pebbles',       'Pebbles_01.emat',               5),
                ('rock',          'Rock_01.emat',                  6),
                ('seabed',        'SeaBed_01.emat',                7),
            ],
        },
        'boreal': {
            'label': 'Boreal / Scandinave',
            'desc':  'Taiga, tourbieres, lande subalpine, toundra boreale.',
            'block_px': 32,
            'fallback': 'grass_base',
            'textures': [
                ('grass_base',    'Grass_01.emat',                 1),
                ('forest_floor',  'ForestConiferous_01_Base.emat', 2),
                ('peat',          'Dirt_02.emat',                  3),
                ('heather',       'Heather_01.emat',               4),
                ('pebbles',       'Pebbles_01.emat',               5),
                ('rock',          'Rock_01.emat',                  6),
                ('seabed',        'SeaBed_01.emat',                7),
            ],
        },
        'mediterraneen': {
            'label': 'Mediterraneen',
            'desc':  'Garrigue, maquis, chenaie seche, eboulis arides, pelouse altitude.',
            'block_px': 32,
            'fallback': 'dry_soil',
            'textures': [
                ('dry_soil',       'Dirt_01.emat',                 1),
                ('grass_base',     'Grass_03.emat',                2),
                ('forest_floor',   'ForestDeciduous_01_Base.emat', 3),
                ('mountain_grass', 'MountainGrass_01.emat',        4),
                ('pebbles',        'Pebbles_02.emat',              5),
                ('rock',           'Rock_01.emat',                 6),
                ('seabed',         'SeaBed_01.emat',               7),
            ],
        },
        'arctique': {
            'label': 'Arctique / Toundra',
            'desc':  'Toundra, tourbieres polaires, moraines, greve arctique.',
            'block_px': 32,
            'fallback': 'peat',
            'textures': [
                ('peat',        'Dirt_02.emat',            1),
                ('grass_base',  'MountainGrass_01.emat',   2),
                ('grass_low',   'Grass_01.emat',           3),
                ('pebbles',     'Pebbles_01.emat',         4),
                ('debris',      'Debris_Rock_01.emat',     5),
                ('rock',        'Rock_01.emat',            6),
                ('seabed',      'SeaBed_01.emat',          7),
            ],
        },
    }

    # Preview colors per internal key (RGB)
    _PREVIEW_COLORS = {
        'grass_base':    ( 80, 160,  60),
        'grass_dry':     (170, 185,  75),
        'grass_low':     (110, 155,  70),
        'forest_floor':  ( 40,  80,  30),
        'wet_soil':      ( 60,  90,  50),
        'peat':          ( 75, 100,  45),
        'dry_soil':      (195, 165,  95),
        'heather':       (155,  90, 145),
        'mountain_grass':(140, 165,  90),
        'pebbles':       (200, 185, 145),
        'debris':        (175, 158, 130),
        'rock':          (150, 140, 130),
        'seabed':        ( 30,  90, 160),
    }

    def __init__(self, nat_gen, output_dir='output'):
        """
        nat_gen: NatureMapBiomesGenerator instance (already initialized).
        """
        self.nat_gen    = nat_gen
        self.output_dir = output_dir
        self.masks_dir  = os.path.join(output_dir, 'texture_masks')
        os.makedirs(self.masks_dir, exist_ok=True)

        self.H = nat_gen.height
        self.W = nat_gen.width

        # Morphological data aliases
        self.h         = nat_gen.heightmap_original.astype(np.float32)
        self.sl        = nat_gen.slopes.astype(np.float32)
        self.asp       = nat_gen.aspect.astype(np.float32)
        self.tpi       = nat_gen.tpi.astype(np.float32)
        self.flow      = nat_gen.flow_accumulation.astype(np.float32)

        self.north_factor = np.cos(np.radians(self.asp))
        flow_p99          = float(np.percentile(self.flow, 99)) + 1e-6
        self.flow_norm    = np.clip(self.flow / flow_p99, 0.0, 1.0).astype(np.float32)

        # Données multi-échelle depuis nat_gen (si disponibles)
        self.tpi_local = nat_gen.tpi_local.astype(np.float32) \
            if hasattr(nat_gen, 'tpi_local') else self.tpi
        self.tpi_large = nat_gen.tpi_large.astype(np.float32) \
            if hasattr(nat_gen, 'tpi_large') else self.tpi
        self.depression_mask = nat_gen.depression_mask.astype(np.float32) \
            if hasattr(nat_gen, 'depression_mask') else np.zeros((self.H, self.W), dtype=np.float32)

        # TPI normalisés [-1,+1] par percentile 95 (indépendant du relief absolu)
        _tpi_scale       = float(np.percentile(np.abs(self.tpi),       95)) + 1e-6
        _tpi_l_scale     = float(np.percentile(np.abs(self.tpi_local), 95)) + 1e-6
        _tpi_lg_scale    = float(np.percentile(np.abs(self.tpi_large), 95)) + 1e-6
        self.tpi_norm       = np.clip(self.tpi       / _tpi_scale,    -1.0, 1.0).astype(np.float32)
        self.tpi_local_norm = np.clip(self.tpi_local / _tpi_l_scale,  -1.0, 1.0).astype(np.float32)
        self.tpi_large_norm = np.clip(self.tpi_large / _tpi_lg_scale, -1.0, 1.0).astype(np.float32)

        # Continuous erosion signal used to break uniform rock/soil regions.
        tpi_scale = _tpi_scale
        slope_norm = np.clip(self.sl / 35.0, 0.0, 1.0).astype(np.float32)
        tpi_pos = np.clip(self.tpi / tpi_scale, 0.0, 1.0).astype(np.float32)
        self.erosion_idx = np.clip(
            0.50 * slope_norm + 0.30 * tpi_pos + 0.20 * self.flow_norm,
            0.0,
            1.0,
        ).astype(np.float32)
        # Deterministic micro-variation to avoid large flat texture plates.
        self.micro_var = np.clip(
            0.5
            + 0.35 * np.sin(np.radians(self.asp * 2.0))
            + 0.15 * np.cos(np.radians(self.asp * 5.0)),
            0.0,
            1.0,
        ).astype(np.float32)

        # Ocean + water masks
        self._build_water_masks()

        # Altitude percentiles (on valid pixels only)
        valid = ~(nat_gen.nodata_mask if nat_gen.nodata_mask is not None
                  else np.zeros((self.H, self.W), dtype=bool))
        h_v = self.h[valid]
        def _p(q): return float(np.percentile(h_v, q)) if h_v.size else 0.0
        self.p10 = _p(10); self.p15 = _p(15); self.p30 = _p(30)
        self.p55 = _p(55); self.p75 = _p(75); self.p90 = _p(90)

        print(f"[MASQUES] Pret: {self.W}x{self.H}px — "
              f"alt p15={self.p15:.0f} p75={self.p75:.0f} p90={self.p90:.0f}")

    # ── Internal helpers ──────────────────────────────────────────────────

    def _build_water_masks(self):
        """Detect ocean (border-connected h<=0) and interior water."""
        nd = self.nat_gen.nodata_mask
        if nd is not None and np.any(nd):
            self.ocean_mask = nd.copy()
        else:
            flat = (self.h <= 0.0)
            if np.any(flat):
                labeled, _ = _nd_label(flat)
                bl = set()
                for edge in [labeled[0, :], labeled[-1, :],
                             labeled[:, 0], labeled[:, -1]]:
                    bl.update(edge.tolist())
                bl.discard(0)
                self.ocean_mask = (np.isin(labeled, list(bl)) if bl
                                   else np.zeros((self.H, self.W), dtype=bool))
            else:
                self.ocean_mask = np.zeros((self.H, self.W), dtype=bool)

        self.water_mask = ((self.nat_gen.water_mask | self.nat_gen.lake_mask)
                           & ~self.ocean_mask)

    def _s(self, mask, sigma=2.0):
        """Smooth binary mask → float32 [0,1] with soft edges."""
        return gaussian_filter(mask.astype(np.float32), sigma=sigma)

    def _base(self):
        """Valid land pixels (not ocean, not water)."""
        return ~self.ocean_mask & ~self.water_mask

    @staticmethod
    def _ramp(arr, lo, hi):
        """Transition lineaire douce : arr < lo -> 0, arr > hi -> 1."""
        return np.clip((arr - lo) / max(hi - lo, 1e-6), 0.0, 1.0).astype(np.float32)

    def _apply_erosion_mix(self, masks, base_key, soil_key=None):
        """
        Apply finer rock/soil mixing driven by erosion signals.

        - Increases mineral textures on steep/eroded areas.
        - Moves part of soil texture into rock around transition slopes.
        - Keeps low-slope plains softer to preserve future manual texture slots.
        """
        land = self._base().astype(np.float32)
        slope_mix = np.clip((self.sl - 8.0) / 14.0, 0.0, 1.0).astype(np.float32)
        steep = np.clip((self.sl - 18.0) / 16.0, 0.0, 1.0).astype(np.float32)
        erosion = self.erosion_idx * land
        micro = self.micro_var * land

        if 'rock' in masks:
            rock_boost = (0.18 * erosion + 0.12 * steep) * (0.80 + 0.40 * micro)
            masks['rock'] = np.clip(masks['rock'] + rock_boost, 0.0, 1.0)

        if 'pebbles' in masks:
            channel = np.clip(0.65 * self.flow_norm + 0.35 * erosion, 0.0, 1.0)
            masks['pebbles'] = np.clip(
                masks['pebbles'] + 0.22 * channel * slope_mix,
                0.0,
                1.0,
            )

        if soil_key and soil_key in masks and 'rock' in masks:
            transfer = masks[soil_key] * slope_mix * (0.14 + 0.20 * micro)
            masks[soil_key] = np.clip(masks[soil_key] - 0.70 * transfer, 0.0, 1.0)
            masks['rock'] = np.clip(masks['rock'] + transfer, 0.0, 1.0)

        if base_key in masks:
            # Plains keep more grass; steep areas lose part of base cover.
            base_keep = np.clip(1.0 - (0.06 + 0.16 * steep + 0.10 * erosion), 0.55, 1.0)
            masks[base_key] = np.clip(masks[base_key] * base_keep, 0.0, 1.0)

        # Slope → pebbles : gaussienne centrée sur 27° (éboulis typiques), σ=8°.
        # Évite d'activer pebbles sur les pentes douces ou les parois verticales.
        if 'pebbles' in masks:
            slope_gauss = np.exp(-0.5 * ((self.sl - 27.0) / 8.0) ** 2).astype(np.float32)
            masks['pebbles'] = np.clip(masks['pebbles'] + 0.35 * slope_gauss * land, 0.0, 1.0)

        # Hollow → wet_soil : gaussienne sur la concavité TPI centrée à 0.45 (creux modérés), σ=0.18.
        # Les légères dépressions et les parois extrêmes sont moins sollicitées.
        if 'wet_soil' in masks:
            tpi_scale = float(np.percentile(np.abs(self.tpi), 95)) + 1e-6
            tpi_norm  = (self.tpi / tpi_scale).astype(np.float32)
            concave   = np.clip(-tpi_norm, 0.0, 1.0)
            hollow_gauss = np.exp(-0.5 * ((concave - 0.45) / 0.18) ** 2).astype(np.float32)
            hollow = np.clip(hollow_gauss * concave + self.flow_norm * 0.25, 0.0, 1.0)
            masks['wet_soil'] = np.clip(masks['wet_soil'] + 0.28 * hollow * land, 0.0, 1.0)

        return masks

    # ── Per-profile mask computation ──────────────────────────────────────

    def _masks_europe_temperee(self):
        h, sl, fn, nf = self.h, self.sl, self.flow_norm, self.north_factor
        tpi_n = self.tpi_norm           # TPI médium [-1,+1]
        tpi_l = self.tpi_local_norm     # TPI local  [-1,+1] (texture de détail)
        depr  = self.depression_mask
        p10, p15, p30, p55, p75, p90 = self.p10, self.p15, self.p30, self.p55, self.p75, self.p90
        base  = self._base().astype(np.float32)
        R     = self._ramp

        seabed = self.ocean_mask.astype(np.float32)
        inland = self.water_mask.astype(np.float32)

        # ROCHE : pente forte (transition 15°-32°) + bonus crêtes convexes (TPI local+)
        rock = R(sl, 15.0, 32.0) * base
        rock_crest = R(tpi_l, 0.30, 0.70) * R(sl, 10.0, 20.0) * base
        rock = np.clip(rock + 0.50 * rock_crest, 0.0, 1.0)
        rock = np.clip(rock + 0.40 * inland * R(sl, 8.0, 15.0), 0.0, 1.0)

        # GALETS : zone littorale basse, pente douce
        pebbles = R(h, 0.0, p10) * (1.0 - R(h, p10, p15)) * (1.0 - R(sl, 5.0, 12.0)) * base
        pebbles = np.clip(pebbles + 0.90 * inland, 0.0, 1.0)

        # SOL HUMIDE : flux hydraulique + dépressions
        wet = R(fn, 0.45, 0.72) * (1.0 - R(h, p15, p30)) * (1.0 - R(sl, 8.0, 16.0)) * base
        wet = np.clip(wet + 0.55 * depr * (1.0 - R(sl, 5.0, 12.0)) * base, 0.0, 1.0)

        # FORÊT : altitude médiane, versants abrités (TPI neutre/concave), pente modérée
        forest = (
            R(h, p15, p30) * (1.0 - R(h, p55, p75)) *
            (1.0 - R(tpi_n, 0.20, 0.55)) *
            (1.0 - R(sl, 18.0, 30.0)) * base
        )

        # HERBE SÈCHE : expositions chaudes (nf négatif = sud), altitude intermédiaire-haute
        dry = np.clip(
            R(h, p55, p75) * (1.0 - R(h, p75, p90)) * (1.0 - R(sl, 20.0, 32.0)) * base
            + R(h, p30, p55) * R(-nf, 0.10, 0.40) * (1.0 - R(sl, 18.0, 28.0)) * base * 0.65,
            0.0, 1.0,
        )

        grass = np.clip(base - rock - pebbles - wet - forest - dry, 0.0, 1.0)

        masks = {'seabed': seabed, 'rock': rock, 'pebbles': pebbles,
                 'wet_soil': wet, 'forest_floor': forest,
                 'grass_dry': dry, 'grass_base': grass}
        return self._apply_erosion_mix(masks, base_key='grass_base', soil_key='wet_soil')

    def _masks_boreal(self):
        h, sl, fn = self.h, self.sl, self.flow_norm
        tpi_n = self.tpi_norm
        tpi_l = self.tpi_local_norm
        depr  = self.depression_mask
        p15, p30, p75, p90 = self.p15, self.p30, self.p75, self.p90
        base  = self._base().astype(np.float32)
        R     = self._ramp

        seabed = self.ocean_mask.astype(np.float32)
        inland = self.water_mask.astype(np.float32)

        # ROCHE : pentes fortes + crêtes
        rock = R(sl, 18.0, 35.0) * base
        rock_crest = R(tpi_l, 0.35, 0.70) * R(sl, 12.0, 22.0) * base
        rock = np.clip(rock + 0.45 * rock_crest, 0.0, 1.0)
        rock = np.clip(rock + 0.40 * inland * R(sl, 8.0, 15.0), 0.0, 1.0)

        # GALETS : rivages bas, pente douce
        pebbles = R(h, 0.0, p15) * (1.0 - R(h, p15, p30)) * (1.0 - R(sl, 4.0, 10.0)) * base
        pebbles = np.clip(pebbles + 0.90 * inland, 0.0, 1.0)

        # TOURBE/PEAT : zones plates, basses, humides + dépressions
        peat = R(fn, 0.35, 0.60) * (1.0 - R(h, p15, p30)) * (1.0 - R(sl, 3.0, 8.0)) * base
        peat = np.clip(peat + 0.60 * depr * (1.0 - R(sl, 4.0, 10.0)) * base, 0.0, 1.0)

        # LANDE/HEATHER : altitude haute, pentes modérées
        heather = R(h, p75, p90) * (1.0 - R(sl, 22.0, 32.0)) * base

        # FORÊT : altitude médiane, versants (TPI neutre/concave)
        forest = (
            R(h, p15, p30) * (1.0 - R(h, p75, p90)) *
            (1.0 - R(tpi_n, 0.30, 0.60)) *
            (1.0 - R(sl, 22.0, 32.0)) * base
        )

        grass = np.clip(base - rock - pebbles - peat - heather - forest, 0.0, 1.0)

        masks = {'seabed': seabed, 'rock': rock, 'pebbles': pebbles,
                 'peat': peat, 'heather': heather,
                 'forest_floor': forest, 'grass_base': grass}
        return self._apply_erosion_mix(masks, base_key='grass_base', soil_key='peat')

    def _masks_mediterraneen(self):
        h, sl, fn, nf = self.h, self.sl, self.flow_norm, self.north_factor
        tpi_n = self.tpi_norm
        tpi_l = self.tpi_local_norm
        depr  = self.depression_mask
        p10, p15, p55, p75, p90 = self.p10, self.p15, self.p55, self.p75, self.p90
        base  = self._base().astype(np.float32)
        R     = self._ramp

        seabed = self.ocean_mask.astype(np.float32)
        inland = self.water_mask.astype(np.float32)

        # ROCHE : pentes fortes + crêtes exposées
        rock = R(sl, 18.0, 35.0) * base
        rock_crest = R(tpi_l, 0.35, 0.70) * R(sl, 12.0, 22.0) * base
        rock = np.clip(rock + 0.50 * rock_crest, 0.0, 1.0)
        rock = np.clip(rock + 0.40 * inland * R(sl, 8.0, 15.0), 0.0, 1.0)

        # GALETS/ÉBOULIS : rivage + bas-fond sec
        pebbles = R(h, 0.0, p10) * (1.0 - R(h, p10, p15)) * (1.0 - R(sl, 6.0, 14.0)) * base
        pebbles = np.clip(pebbles + 0.90 * inland, 0.0, 1.0)

        # SOL SEC/GARRIGUE : versants chauds (nf négatif = sud/ouest), altitude basse-médiane
        dry_soil = np.clip(
            R(h, p15, p55) * (1.0 - R(h, p55, p75)) *
            R(-nf, 0.05, 0.28) *
            (1.0 - R(sl, 20.0, 30.0)) * base,
            0.0, 1.0,
        )

        # PRAIRIE MONTAGNE : altitude haute, pente modérée
        mtn = R(h, p75, p90) * (1.0 - R(sl, 22.0, 32.0)) * base

        # FORÊT : versants frais (nf positif = nord), altitude médiane
        forest = np.clip(
            R(h, p15, p55) * (1.0 - R(h, p55, p75)) *
            (1.0 - R(-nf, 0.05, 0.28)) *
            (1.0 - R(tpi_n, 0.30, 0.60)) *
            (1.0 - R(sl, 20.0, 30.0)) * base,
            0.0, 1.0,
        )

        grass = np.clip(base - rock - pebbles - dry_soil - mtn - forest, 0.0, 1.0)

        masks = {'seabed': seabed, 'rock': rock, 'pebbles': pebbles,
                 'dry_soil': dry_soil, 'mountain_grass': mtn,
                 'forest_floor': forest, 'grass_base': grass}
        return self._apply_erosion_mix(masks, base_key='grass_base', soil_key='dry_soil')

    def _masks_arctique(self):
        h, sl, fn = self.h, self.sl, self.flow_norm
        tpi_n = self.tpi_norm
        tpi_l = self.tpi_local_norm
        depr  = self.depression_mask
        p15, p30, p75, p90 = self.p15, self.p30, self.p75, self.p90
        base  = self._base().astype(np.float32)
        R     = self._ramp

        seabed = self.ocean_mask.astype(np.float32)
        inland = self.water_mask.astype(np.float32)

        # ROCHE : pentes fortes + crêtes (seuils plus agressifs en milieu arctique)
        rock = R(sl, 20.0, 38.0) * base
        rock_crest = R(tpi_l, 0.40, 0.75) * R(sl, 15.0, 25.0) * base
        rock = np.clip(rock + 0.50 * rock_crest, 0.0, 1.0)
        rock = np.clip(rock + 0.40 * inland * R(sl, 8.0, 15.0), 0.0, 1.0)

        # GALETS/MORAINES : rivage arctique bas
        pebbles = R(h, 0.0, p15) * (1.0 - R(h, p15, p30)) * (1.0 - R(sl, 5.0, 12.0)) * base
        pebbles = np.clip(pebbles + 0.90 * inland, 0.0, 1.0)

        # TOURBE polaire : dépressions + flux + zones plates basses
        peat = R(fn, 0.30, 0.55) * (1.0 - R(h, p15, p30)) * (1.0 - R(sl, 3.0, 8.0)) * base
        peat = np.clip(peat + 0.65 * depr * (1.0 - R(sl, 4.0, 10.0)) * base, 0.0, 1.0)

        # DÉBRIS/ÉBOULIS : altitude haute, pentes modérées-fortes
        debris = R(h, p75, p90) * R(sl, 12.0, 22.0) * (1.0 - R(sl, 32.0, 42.0)) * base

        # PRAIRIE BASSE : versants intermédiaires
        grass_lw = (
            R(h, p30, p75) * (1.0 - R(h, p75, p90)) *
            (1.0 - R(sl, 18.0, 28.0)) * base
        )

        grass = np.clip(base - rock - pebbles - peat - debris - grass_lw, 0.0, 1.0)

        masks = {'seabed': seabed, 'rock': rock, 'pebbles': pebbles,
                 'peat': peat, 'debris': debris,
                 'grass_low': grass_lw, 'grass_base': grass}
        return self._apply_erosion_mix(masks, base_key='grass_base', soil_key='peat')

    # ── Priority-peel normalization ───────────────────────────────────────

    def normalize_priority_peel(self, masks, profile):
        """
        Normalize overlay textures via priority-peel, then force fallback (grass_base)
        to 1.0 on all terrain pixels.

        High-priority textures (rock, seabed, pebbles…) are peeled so their sum
        stays <= 1.0 per pixel. The fallback is set to 1.0 on every non-ocean pixel
        so no pixel is ever left without coverage (prevents Reforger "default texture").

        Reforger normalizes the alpha sum internally at render time, so having
        fallback=1.0 alongside other textures is the standard approach.
        """
        prof     = self.PROFILES[profile]
        fallback = prof['fallback']

        # Build priority order: descending apply_priority
        tex_order    = sorted(prof['textures'], key=lambda t: -t[2])
        ordered_keys = [t[0] for t in tex_order if t[0] in masks]

        result    = {k: np.zeros_like(v) for k, v in masks.items()}
        remaining = np.ones((self.H, self.W), dtype=np.float32)

        # seabed owns ocean pixels fully
        if 'seabed' in masks:
            sb = np.clip(masks['seabed'], 0.0, 1.0).astype(np.float32)
            result['seabed'] = sb
            remaining = np.maximum(0.0, remaining - sb)

        for key in ordered_keys:
            if key in ('seabed', fallback):
                continue
            val = np.clip(masks[key], 0.0, remaining)
            result[key] = val
            remaining   = np.maximum(0.0, remaining - val)

        # Fallback = 1.0 on all terrain pixels (not ocean) — guaranteed background.
        # Reforger normalises the sum at render time; this prevents any pixel from
        # being left uncovered and showing the engine default texture.
        if fallback in masks:
            terrain = self._base().astype(np.float32)  # 1.0 on land, 0 on ocean/water
            result[fallback] = terrain

        covered = sum(result.values())
        uncovered_px = int(np.sum(covered < 0.01))
        print(f"[NORM] Priority-peel: pixels sans couverture = {uncovered_px} (cible 0)")
        return result


    # ── Block arbiter ─────────────────────────────────────────────────────

    def _block_budget(self, slope_mean_deg, max_tex=5):
        """
        Dynamic texture budget by slope to preserve manual editing room.
        Returns: (reserve_slots, max_auto_textures)
        """
        if slope_mean_deg <= 5.0:
            reserve_slots = 3
        elif slope_mean_deg <= 10.0:
            reserve_slots = 2
        elif slope_mean_deg <= 18.0:
            reserve_slots = 1
        else:
            reserve_slots = 0

        max_auto = max(1, min(max_tex, 5 - reserve_slots))
        return reserve_slots, max_auto

    def enforce_block_limit(self, masks, profile, max_tex=5, dynamic_budget=True):
        """
        For each terrain block, keep only the top max_tex textures by mean
        intensity. Dropped textures are redistributed to the fallback key.
        Returns a new dict of float32 arrays.
        """
        prof     = self.PROFILES[profile]
        block_px = prof['block_px']
        fallback = prof['fallback']
        keys     = list(masks.keys())

        result = {k: v.copy() for k, v in masks.items()}
        blocks_fixed = 0
        budget_hist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        drop_counts = {k: 0 for k in keys}
        pressure_map = np.zeros((self.H, self.W), dtype=np.float32)

        for row in range(0, self.H, block_px):
            for col in range(0, self.W, block_px):
                r2 = min(row + block_px, self.H)
                c2 = min(col + block_px, self.W)

                if dynamic_budget:
                    slope_mean = float(np.mean(self.sl[row:r2, col:c2]))
                    _, block_max = self._block_budget(slope_mean, max_tex=max_tex)
                else:
                    block_max = max_tex
                budget_hist[block_max] += 1

                # Mean intensity per texture in this block
                scores = {k: float(np.mean(masks[k][row:r2, col:c2])) for k in keys}
                active = {k: v for k, v in scores.items() if v > 0.015}

                pressure_map[row:r2, col:c2] = float(len(active))

                if len(active) <= block_max:
                    continue

                # Keep top N by score, where N is dynamic by block slope.
                sorted_k = sorted(active, key=lambda k: -active[k])
                keep = set(sorted_k[:block_max])
                drop = set(sorted_k[block_max:])

                for k in drop:
                    dropped = result[k][row:r2, col:c2].copy()
                    result[k][row:r2, col:c2] = 0.0
                    if fallback in result:
                        result[fallback][row:r2, col:c2] = np.clip(
                            result[fallback][row:r2, col:c2] + dropped, 0.0, 1.0)
                    drop_counts[k] += 1
                blocks_fixed += 1

        if blocks_fixed:
            print(f"[MASQUES] Arbitrage: {blocks_fixed} blocs corriges")
        if dynamic_budget:
            print("[MASQUES] Budget dynamique (max textures par bloc): "
                  f"1={budget_hist[1]} 2={budget_hist[2]} 3={budget_hist[3]} "
                  f"4={budget_hist[4]} 5={budget_hist[5]}")
        self._last_budget_hist = budget_hist
        self._diag = {
            'blocks_total':  sum(budget_hist.values()),
            'blocks_over':   blocks_fixed,
            'drop_counts':   drop_counts,
            'pressure_map':  pressure_map,
        }
        return result

    # ── Public API ────────────────────────────────────────────────────────

    def _apply_sat_guidance(self, masks, sat_indices, strength=0.35):
        """
        Modulate texture masks using satellite image indices.

        veg_index   (high = dense vegetation) → boosts grass/forest, reduces rock/pebbles
        wet_index   (high = humid/cool areas) → boosts wet_soil/peat, reduces dry_soil
        mineral_index (high = bare soil/rock) → boosts rock/pebbles, reduces grass/forest

        strength: blending factor [0,1]. 0 = morpho only, 1 = strong satellite guidance.
        """
        s = float(np.clip(strength, 0.0, 1.0))
        if s == 0.0 or sat_indices is None:
            return masks

        from scipy.ndimage import gaussian_filter as _gf
        veg = sat_indices.get('veg_index')
        wet = sat_indices.get('wet_index')
        mineral = sat_indices.get('mineral_index')

        # Resize indices to mask resolution if needed
        def _align(arr):
            if arr is None:
                return None
            mh, mw = self.H, self.W
            if arr.shape != (mh, mw):
                from PIL import Image as _PIL
                img_pil = _PIL.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8), mode='L')
                img_pil = img_pil.resize((mw, mh), _PIL.BILINEAR)
                arr = np.array(img_pil, dtype=np.float32) / 255.0
            return arr.astype(np.float32)

        veg = _align(veg)
        wet = _align(wet)
        mineral = _align(mineral)

        # ── Végétation haute → herbe + forêt
        if veg is not None:
            for key in ('grass_base', 'grass_dry', 'grass_low', 'forest_floor'):
                if key in masks:
                    masks[key] = np.clip(masks[key] + s * 0.25 * veg, 0.0, 1.0)
            for key in ('rock', 'pebbles', 'debris'):
                if key in masks:
                    masks[key] = np.clip(masks[key] - s * 0.20 * veg, 0.0, 1.0)

        # ── Humidité → zones humides
        if wet is not None:
            for key in ('wet_soil', 'peat'):
                if key in masks:
                    masks[key] = np.clip(masks[key] + s * 0.28 * wet, 0.0, 1.0)
            for key in ('dry_soil', 'grass_dry', 'mountain_grass'):
                if key in masks:
                    masks[key] = np.clip(masks[key] - s * 0.18 * wet, 0.0, 1.0)

        # ── Minéral/sol nu → roche + galets
        if mineral is not None:
            for key in ('rock', 'pebbles', 'debris'):
                if key in masks:
                    masks[key] = np.clip(masks[key] + s * 0.30 * mineral, 0.0, 1.0)
            for key in ('grass_base', 'forest_floor', 'wet_soil', 'peat'):
                if key in masks:
                    masks[key] = np.clip(masks[key] - s * 0.20 * mineral, 0.0, 1.0)

        print(f"[MASQUES] Guidance SatMap appliquée (force={s:.2f})")
        return masks

    def generate_masks(self, profile='europe_temperee', enforce_blocks=True,
                       dynamic_budget=True, sat_indices=None, sat_strength=0.35,
                       max_tex=4):
        """
        Generate and return all texture masks for the given profile.

        Parameters
        ----------
        sat_indices : dict, optional
            Indices SatMap calculés par SatMapAnalyzer.compute().
            Si fourni, la guidance satellite est fusionnée avec les masques morphologiques.
        sat_strength : float
            Force du guidage SatMap [0,1]. Ignoré si sat_indices est None.

        Returns: dict {key: float32 array [0,1], shape (H,W)}
        """
        _compute = {
            'europe_temperee': self._masks_europe_temperee,
            'boreal':          self._masks_boreal,
            'mediterraneen':   self._masks_mediterraneen,
            'arctique':        self._masks_arctique,
        }
        if profile not in _compute:
            raise ValueError(f"Profil inconnu: {profile}")

        print(f"[MASQUES] Calcul: {profile}...")
        masks = _compute[profile]()

        if sat_indices is not None:
            masks = self._apply_sat_guidance(masks, sat_indices, strength=sat_strength)

        print(f"[MASQUES] Normalisation priority-peel...")
        masks = self.normalize_priority_peel(masks, profile)

        if enforce_blocks:
            print(f"[MASQUES] Arbitrage blocs ({self.PROFILES[profile]['block_px']}px x {self.PROFILES[profile]['block_px']}px)...")
            masks = self.enforce_block_limit(
                masks,
                profile,
                max_tex=max_tex,
                dynamic_budget=dynamic_budget,
            )

        print(f"[MASQUES] {len(masks)} calques generes.")
        return masks

    def export_masks(self, masks, profile, output_dir=None):
        """
        Save each mask as 8-bit grayscale PNG at heightmap resolution.
        Returns: dict {key: filepath}
        """
        prof    = self.PROFILES[profile]
        tex_map = {t[0]: t[1] for t in prof['textures']}
        out_dir = output_dir or os.path.join(self.masks_dir, profile)
        os.makedirs(out_dir, exist_ok=True)

        paths = {}
        for key, arr in masks.items():
            img8  = (np.clip(arr, 0.0, 1.0) * 255).astype(np.uint8)
            img   = Image.fromarray(img8, mode='L')
            fname = f"{tex_map.get(key, key).replace('.emat','')}_mask.png"
            fpath = os.path.join(out_dir, fname)
            img.save(fpath)
            paths[key] = fpath
            print(f"[MASQUES] Export: {fname}")

        # Save report JSON
        report = self.generate_report(masks, profile)
        rpath  = os.path.join(out_dir, 'report.json')
        with open(rpath, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=True)

        print(f"[MASQUES] Export termine: {out_dir}")
        return paths

    def generate_report(self, masks, profile):
        """
        Returns a report dict with per-texture stats and Workbench apply order.
        """
        prof    = self.PROFILES[profile]
        tex_map = {t[0]: (t[1], t[2]) for t in prof['textures']}
        total   = self.H * self.W

        report = {
            'profile':        profile,
            'label':          prof['label'],
            'heightmap_size': f"{self.W}x{self.H}",
            'block_px':       prof['block_px'],
            'generated_at':   datetime.now().strftime('%Y-%m-%d %H:%M'),
            'budget_hist':    getattr(self, '_last_budget_hist', None),
            'textures':       {},
            'workbench_order': [],
        }

        tex_stats = []
        for key, arr in masks.items():
            fname, prio = tex_map.get(key, (key, 99))
            coverage     = float(np.mean(arr > 0.1) * 100)
            mean_val     = float(np.mean(arr) * 100)
            tex_stats.append((prio, key, fname, coverage, mean_val))
            report['textures'][key] = {
                'file':          fname,
                'apply_priority': prio,
                'coverage_pct':  round(coverage, 1),
                'mean_intensity': round(mean_val, 1),
            }

        # Workbench order: sorted by apply_priority ascending
        tex_stats.sort(key=lambda x: x[0])
        report['workbench_order'] = [
            {'step': i + 1, 'texture': f, 'key': k, 'coverage_pct': round(c, 1)}
            for i, (_, k, f, c, _) in enumerate(tex_stats)
        ]
        return report

    def generate_preview(self, masks, profile):
        """
        Returns a color RGB PIL Image combining all texture masks.
        Textures are composited in apply_priority order (highest on top).
        """
        prof    = self.PROFILES[profile]
        prio_map = {t[0]: t[2] for t in prof['textures']}

        # Sort: lowest priority first (base layers), highest last (on top)
        sorted_keys = sorted(masks.keys(), key=lambda k: prio_map.get(k, 5))

        canvas = np.zeros((self.H, self.W, 3), dtype=np.float32)
        for key in sorted_keys:
            alpha = masks[key][:, :, np.newaxis]
            rgb   = np.array(self._PREVIEW_COLORS.get(key, (128, 128, 128)),
                             dtype=np.float32) / 255.0
            canvas = canvas * (1.0 - alpha) + rgb * alpha

        return Image.fromarray((canvas * 255).astype(np.uint8), mode='RGB')
