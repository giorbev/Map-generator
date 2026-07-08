"""
Terrain texture score computation service.

Contains all pure-numpy logic for morphological + SatMap scoring,
normalisation, composition and coverage statistics.  No UI/Streamlit
dependency — all exceptions propagate to the caller.
"""
from __future__ import annotations

from typing import Optional, Tuple

import numpy as np
from scipy.ndimage import gaussian_filter, uniform_filter

# ── Constantes ────────────────────────────────────────────────────────────────

CLIMATE_TABLE = {
    "Tempéré": {
        "snowline_m":     1500.0,
        "humidity":       0.65,
        "rock_slope_base": 38.0,
        "soil_tpi_base":  -3.5,
        "targets": {
            "herbe": (50, 68), "terre": (14, 26),
            "roche": (5, 14),  "neige": (0, 3),
        },
    },
    "Aride": {
        "snowline_m":     2600.0,
        "humidity":       0.18,
        "rock_slope_base": 30.0,
        "soil_tpi_base":  -1.0,
        "targets": {
            "herbe": (18, 38), "terre": (32, 52),
            "roche": (14, 32), "neige": (0, 1),
        },
    },
    "Continental": {
        "snowline_m":     1700.0,
        "humidity":       0.45,
        "rock_slope_base": 36.0,
        "soil_tpi_base":  -3.0,
        "targets": {
            "herbe": (42, 58), "terre": (18, 30),
            "roche": (8, 18),  "neige": (0, 6),
        },
    },
    "Tropical": {
        "snowline_m":     4200.0,
        "humidity":       0.78,
        "rock_slope_base": 40.0,
        "soil_tpi_base":  -4.5,
        "targets": {
            "herbe": (55, 72), "terre": (12, 22),
            "roche": (4, 12),  "neige": (0, 1),
        },
    },
    "Subarctique": {
        "snowline_m":     700.0,
        "humidity":       0.38,
        "rock_slope_base": 34.0,
        "soil_tpi_base":  -2.5,
        "targets": {
            "herbe": (28, 46), "terre": (18, 30),
            "roche": (14, 28), "neige": (2, 12),
        },
    },
    "Alpin": {
        "snowline_m":     2000.0,
        "humidity":       0.52,
        "rock_slope_base": 32.0,
        "soil_tpi_base":  -2.0,
        "targets": {
            "herbe": (28, 46), "terre": (14, 24),
            "roche": (20, 38), "neige": (3, 18),
        },
    },
}

C_ROCK  = np.array([160, 160, 160], dtype=np.float32)
C_SOIL  = np.array([139,  94,  60], dtype=np.float32)
C_GRASS = np.array([ 76, 170,  78], dtype=np.float32)
C_CROP  = np.array([185, 195, 100], dtype=np.float32)


# ── Service ───────────────────────────────────────────────────────────────────

class TerrainScoreService:
    """
    Compute rock / soil / grass texture scores from morphological data.

    All methods are stateless and operate purely on numpy arrays.
    """

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _sig(x: np.ndarray, center: float, width: float = 6.0) -> np.ndarray:
        """Logistic sigmoid returning float32 values in [0, 1]."""
        return (1.0 / (1.0 + np.exp(
            -(x - center) / max(float(width) / 6.0, 1e-4)
        ))).astype(np.float32)

    @staticmethod
    def _detect_visual_ocean(nat_gen) -> Optional[np.ndarray]:
        """Return a boolean mask for border-connected ocean / nodata pixels."""
        nd = nat_gen.nodata_mask
        if nd is not None and np.any(nd):
            return nd.copy()

        from scipy.ndimage import label as _lbl

        h = nat_gen.heightmap_original
        flat = (h <= 0.0)
        if not np.any(flat):
            return None

        labeled, _ = _lbl(flat)
        border = set()
        border.update(labeled[0, :].tolist())
        border.update(labeled[-1, :].tolist())
        border.update(labeled[:, 0].tolist())
        border.update(labeled[:, -1].tolist())
        border.discard(0)
        if not border:
            return None
        return np.isin(labeled, list(border))

    # ── Core score computation ─────────────────────────────────────────────

    def compute_morpho_scores(
        self,
        nat_gen,
        climate_profile: str,
        preview_snow_pct: int,
        preview_soil_flow_pct: int,
    ) -> dict:
        """
        Compute base morphological scores (rock, soil, grass, water, snow).

        Returns a dict with keys:
            raw_s_rock, raw_s_soil, raw_s_grass,
            mask_water, mask_snow,
            visual_ocean, blur_sigma,
            rock_slope_cal, rock_pct_pass1,
            snow_enabled, snowline_abs, snow_threshold,
            adjusted_flow_pct, humidity,
            h_max, relief, climate_profile, targets,
            flow_threshold, total_px, nat_gen_ref
        """
        cp = CLIMATE_TABLE.get(climate_profile, CLIMATE_TABLE["Tempéré"])
        snowline_abs     = float(cp["snowline_m"])
        humidity         = float(cp["humidity"])
        rock_slope_cal   = float(cp["rock_slope_base"])
        soil_tpi_threshold = float(cp["soil_tpi_base"])
        targets          = cp["targets"]

        h      = nat_gen.heightmap_original
        slopes = nat_gen.slopes
        water_mask = nat_gen.water_mask
        flow   = nat_gen.flow_accumulation
        tpi    = nat_gen.tpi
        litho  = nat_gen.lithology_proxy
        total_px = nat_gen.height * nat_gen.width

        litho_alluvial   = (litho == 0)
        litho_alteration = (litho == 1)
        litho_hard_rock  = (litho == 3)

        snow_threshold_pct = float(np.percentile(h, preview_snow_pct))
        h_max   = float(np.max(h))
        relief  = float(np.max(h) - np.min(h))

        snow_enabled    = h_max >= (snowline_abs - 120.0)
        snow_threshold  = max(snowline_abs, snow_threshold_pct)

        flow_percentile_adjust = (0.5 - humidity) * 8.0
        adjusted_flow_pct = float(np.clip(preview_soil_flow_pct + flow_percentile_adjust, 70.0, 98.0))
        flow_threshold = np.percentile(flow, adjusted_flow_pct)
        dry_soil_support = (humidity < 0.35) & (slopes < 14.0)

        def _classify(rock_s, flow_thr, tpi_thr, dry_s):
            m_water = water_mask
            m_snow = (
                (h >= snow_threshold) & ((slopes >= 10.0) | (tpi > 2.0)) & (~m_water)
                if snow_enabled
                else np.zeros_like(m_water, dtype=bool)
            )
            rock_s_hard = max(rock_s - 6.0, 18.0)
            m_rock = (
                ((slopes >= rock_s) | (litho_hard_rock & (slopes >= rock_s_hard)))
                & (~m_water) & (~m_snow) & (~litho_alluvial)
            )
            m_soil = (
                ((flow >= flow_thr) | (tpi < tpi_thr) | dry_s | litho_alluvial)
                & (slopes < rock_s)
                & (~m_water) & (~m_snow) & (~m_rock)
            )
            m_grass = ~(m_water | m_snow | m_rock | m_soil)
            alteration_to_grass = litho_alteration & m_soil & (flow < flow_thr)
            m_soil  = m_soil  & ~alteration_to_grass
            m_grass = m_grass | alteration_to_grass
            return m_water, m_snow, m_rock, m_soil, m_grass

        m_water, m_snow, m_rock, m_soil, m_grass = _classify(
            rock_slope_cal, flow_threshold, soil_tpi_threshold, dry_soil_support
        )

        # Auto-calibration roche (passe 2)
        rock_min_tgt, rock_max_tgt = targets["roche"]
        rock_pct_pass1 = float(np.sum(m_rock) / total_px * 100)

        if rock_pct_pass1 > rock_max_tgt:
            for delta in range(1, 18):
                _, _, m_rock_c, m_soil_c, m_grass_c = _classify(
                    rock_slope_cal + delta, flow_threshold, soil_tpi_threshold, dry_soil_support
                )
                if np.sum(m_rock_c) / total_px * 100 <= rock_max_tgt:
                    m_rock, m_soil, m_grass = m_rock_c, m_soil_c, m_grass_c
                    rock_slope_cal += delta
                    break
        elif rock_pct_pass1 < rock_min_tgt:
            for delta in range(1, 18):
                _, _, m_rock_c, m_soil_c, m_grass_c = _classify(
                    rock_slope_cal - delta, flow_threshold, soil_tpi_threshold, dry_soil_support
                )
                if np.sum(m_rock_c) / total_px * 100 >= rock_min_tgt:
                    m_rock, m_soil, m_grass = m_rock_c, m_soil_c, m_grass_c
                    rock_slope_cal -= delta
                    break

        mask_water = m_water
        mask_snow  = m_snow

        # Continuous multi-criteria scores
        tpi_loc  = nat_gen.tpi_local.astype(np.float32)
        sl       = slopes.astype(np.float32)
        h_f      = h.astype(np.float32)

        flow_min  = float(np.min(flow))
        flow_rng  = float(np.max(flow) - flow_min) + 1e-6
        flow_norm = ((flow - flow_min) / flow_rng).astype(np.float32)
        flow_thr_norm = float((flow_threshold - flow_min) / flow_rng)

        cell = float(nat_gen.cellsize)
        curv = (
            np.gradient(np.gradient(h_f, cell, axis=1), cell, axis=1)
            + np.gradient(np.gradient(h_f, cell, axis=0), cell, axis=0)
        ).astype(np.float32)
        curv_std  = float(np.std(curv)) + 1e-6
        curv_norm = np.clip(curv / curv_std, -3.0, 3.0) / 3.0

        asp         = nat_gen.aspect.astype(np.float32)
        north_bonus = (np.cos(np.radians(asp)) + 1.0) * 0.5

        h_sq_mean = uniform_filter(h_f ** 2, size=5)
        h_mean_sq = uniform_filter(h_f, size=5) ** 2
        roughness = np.sqrt(np.clip(h_sq_mean - h_mean_sq, 0.0, None))
        rough_max = float(np.percentile(roughness, 99)) + 1e-6
        rough_norm = np.clip(roughness / rough_max, 0.0, 1.0).astype(np.float32)

        rng   = np.random.default_rng(seed=42)
        noise = rng.standard_normal((nat_gen.height, nat_gen.width)).astype(np.float32)
        noise = gaussian_filter(noise, sigma=6.0) * 0.12

        s_rock = (
            0.50 * self._sig(sl, rock_slope_cal, width=10.0)
            + 0.15 * np.clip( curv_norm, 0.0, 1.0)
            + 0.12 * litho_hard_rock.astype(np.float32)
            + 0.10 * rough_norm
            - 0.08 * flow_norm
            + 0.05 * noise
        )
        s_rock = np.clip(s_rock, 0.0, 1.0)
        s_rock *= np.where(litho_alluvial, 0.15, 1.0).astype(np.float32)

        s_soil = (
            0.32 * self._sig(flow_norm, flow_thr_norm, width=0.15)
            + 0.22 * np.clip(-curv_norm, 0.0, 1.0)
            + 0.18 * litho_alluvial.astype(np.float32)
            + 0.12 * float(1.0 - humidity) * self._sig(sl, 5.0, width=8.0)
            + 0.05 * noise
        )
        s_soil = np.clip(s_soil, 0.0, 1.0)

        s_grass = (
            0.38 * np.ones((nat_gen.height, nat_gen.width), dtype=np.float32)
            + 0.20 * litho_alteration.astype(np.float32)
            + 0.12 * float(humidity)
            + 0.08 * north_bonus * float(humidity)
            - 0.18 * self._sig(sl, rock_slope_cal * 0.6, width=8.0)
            - 0.08 * flow_norm
            + 0.05 * noise
        )
        s_grass = np.clip(s_grass, 0.0, 1.0)

        blur_sigma = max(1.0, 50.0 / cell)

        return {
            "raw_s_rock":       s_rock,
            "raw_s_soil":       s_soil,
            "raw_s_grass":      s_grass,
            "mask_water":       mask_water,
            "mask_snow":        mask_snow,
            "mask_rock":        m_rock,
            "mask_soil":        m_soil,
            "mask_grass":       m_grass,
            "visual_ocean":     self._detect_visual_ocean(nat_gen),
            "blur_sigma":       blur_sigma,
            "rock_slope_cal":   rock_slope_cal,
            "rock_pct_pass1":   rock_pct_pass1,
            "snow_enabled":     snow_enabled,
            "snowline_abs":     snowline_abs,
            "snow_threshold":   snow_threshold,
            "adjusted_flow_pct": adjusted_flow_pct,
            "humidity":         humidity,
            "h_max":            h_max,
            "relief":           relief,
            "climate_profile":  climate_profile,
            "targets":          targets,
            "flow_threshold":   flow_threshold,
            "total_px":         total_px,
        }

    # ── Normalisation + composition ────────────────────────────────────────

    def normalize_scores(
        self,
        s_rock: np.ndarray,
        s_soil: np.ndarray,
        s_grass: np.ndarray,
        blur_sigma: float,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Normalise three score maps (sum->1) then apply Gaussian blur."""
        total = s_rock + s_soil + s_grass + 1e-6
        s_rock  = (s_rock  / total).astype(np.float32)
        s_soil  = (s_soil  / total).astype(np.float32)
        s_grass = (s_grass / total).astype(np.float32)

        s_rock  = gaussian_filter(s_rock,  sigma=blur_sigma).astype(np.float32)
        s_soil  = gaussian_filter(s_soil,  sigma=blur_sigma).astype(np.float32)
        s_grass = gaussian_filter(s_grass, sigma=blur_sigma).astype(np.float32)

        total = s_rock + s_soil + s_grass + 1e-6
        s_rock  = (s_rock  / total).astype(np.float32)
        s_soil  = (s_soil  / total).astype(np.float32)
        s_grass = (s_grass / total).astype(np.float32)
        return s_rock, s_soil, s_grass

    def compose_texture(
        self,
        s_rock: np.ndarray,
        s_soil: np.ndarray,
        s_grass: np.ndarray,
        mask_water: np.ndarray,
        mask_snow: np.ndarray,
        nat_gen,
        visual_ocean: Optional[np.ndarray],
        hydro_overlay: bool = True,
    ) -> np.ndarray:
        """Blend score maps into an RGB uint8 image."""
        texture_f = (
            s_rock[..., np.newaxis]  * C_ROCK
            + s_soil[..., np.newaxis]  * C_SOIL
            + s_grass[..., np.newaxis] * C_GRASS
        )
        texture = np.clip(texture_f, 0, 255).astype(np.uint8)
        texture[mask_snow]  = [245, 245, 245]
        texture[mask_water] = [ 50, 120, 220]
        if hydro_overlay:
            texture[nat_gen.stream_network & ~mask_water] = [ 30,  80, 180]
            texture[nat_gen.lake_mask      & ~mask_water] = [ 90, 160, 220]
        if visual_ocean is not None and np.any(visual_ocean):
            texture[visual_ocean] = [30, 90, 160]
        return texture

    def coverage_from_scores(
        self,
        s_rock: np.ndarray,
        s_soil: np.ndarray,
        s_grass: np.ndarray,
        mask_water: np.ndarray,
        mask_snow: np.ndarray,
        total_px: int,
    ) -> dict:
        """Compute percentage coverage per material from continuous scores."""
        non_water      = ~mask_water
        non_water_total = max(float(np.sum(non_water)), 1.0)
        dry             = non_water & (~mask_snow)
        dry_total       = max(float(np.sum(dry)), 1.0)
        return {
            "eau_pct":   float(np.sum(mask_water) / total_px * 100),
            "neige_pct": float(np.sum(mask_snow)  / non_water_total * 100),
            "terre_pct": float(np.sum(s_soil [dry]) / dry_total * 100),
            "herbe_pct": float(np.sum(s_grass[dry]) / dry_total * 100),
            "roche_pct": float(np.sum(s_rock [dry]) / dry_total * 100),
        }

    # ── SatMap guidance (morpho + sat) ─────────────────────────────────────

    def apply_sat_guidance(
        self,
        raw_s_rock: np.ndarray,
        raw_s_soil: np.ndarray,
        raw_s_grass: np.ndarray,
        sat_indices: dict,
        sat_strength: float,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Blend morphological scores with SatMap spectral indices."""
        sat_veg = sat_indices["veg_index"]
        sat_wet = sat_indices["wet_index"]
        sat_min = sat_indices["mineral_index"]
        k = float(np.clip(sat_strength, 0.0, 1.0))

        s_rock  = np.clip(raw_s_rock  + k * ( 0.35 * sat_min - 0.20 * sat_veg - 0.08 * sat_wet), 0.0, 1.0)
        s_soil  = np.clip(raw_s_soil  + k * ( 0.22 * sat_wet + 0.10 * (1.0 - sat_veg) - 0.08 * sat_min), 0.0, 1.0)
        s_grass = np.clip(raw_s_grass + k * ( 0.30 * sat_veg + 0.12 * sat_wet - 0.18 * sat_min), 0.0, 1.0)
        return s_rock, s_soil, s_grass

    # ── SatMap-only scores ─────────────────────────────────────────────────

    def compute_sat_only_scores(
        self,
        sat_indices: dict,
        sat_strength: float,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Compute scores purely from SatMap spectral indices (no morphology).

        Returns
        -------
        s_rock, s_soil, s_grass, mask_water, mask_snow, crop_smooth
        """
        sat_veg  = sat_indices["veg_index"]
        sat_wet  = sat_indices["wet_index"]
        sat_min  = sat_indices["mineral_index"]
        sat_bri  = sat_indices["bright_index"]
        sat_crop = sat_indices.get("crop_index", np.zeros_like(sat_veg))

        c_boost = float(np.clip(0.55 + sat_strength, 0.0, 2.0))

        mask_water = (sat_bri < 0.18) & (sat_veg < 0.42)
        mask_snow  = (
            (sat_bri > 0.82) & (sat_wet < 0.42) & (sat_min < 0.30)
            & (sat_veg < 0.45) & (~mask_water)
        )

        s_grass = np.clip((
            0.68 * sat_veg + 0.14 * sat_wet - 0.22 * sat_min
            - 0.04 * sat_bri - 0.18 * sat_crop
        ) * c_boost, 0.0, 1.0)
        s_soil = np.clip((
            0.44 * (1.0 - sat_veg) + 0.32 * sat_min + 0.16 * sat_bri
            - 0.08 * sat_wet - 0.10 * sat_crop
        ) * c_boost, 0.0, 1.0)
        s_rock = np.clip((
            0.38 * sat_min + 0.32 * sat_bri + 0.18 * (1.0 - sat_veg)
            - 0.28 * sat_wet
        ) * c_boost, 0.0, 1.0)

        dry = ~(mask_water | mask_snow)
        s_grass = np.where(dry, s_grass, 0.0).astype(np.float32)
        s_soil  = np.where(dry, s_soil,  0.0).astype(np.float32)
        s_rock  = np.where(dry, s_rock,  0.0).astype(np.float32)

        crop_smooth = gaussian_filter(sat_crop, sigma=3.0)
        return s_rock, s_soil, s_grass, mask_water, mask_snow, crop_smooth

    def apply_crop_overlay(
        self,
        texture: np.ndarray,
        crop_smooth: np.ndarray,
        mask_dry: np.ndarray,
        sat_indices: dict,
    ) -> np.ndarray:
        """Apply a yellow-green crop overlay on the texture image."""
        sat_veg = sat_indices["veg_index"]
        sat_min = sat_indices["mineral_index"]
        crop_mask = (
            mask_dry
            & (crop_smooth > 0.45)
            & (sat_veg < 0.62)
            & (sat_min < 0.55)
        )
        if not np.any(crop_mask):
            return texture
        alpha = np.clip(crop_smooth * 1.4, 0.0, 0.72)
        alpha_m = np.where(crop_mask, alpha, 0.0)[..., np.newaxis]
        tex_f   = texture.astype(np.float32)
        tex_f   = tex_f * (1.0 - alpha_m) + C_CROP * alpha_m
        return np.clip(tex_f, 0, 255).astype(np.uint8)
