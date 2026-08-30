"""
Use case: generate a terrain texture preview image.

Orchestrates NatureMapBiomesGenerator, TerrainScoreService and
SatMapAnalyzer to produce a TerrainPreviewResult.
"""
from __future__ import annotations

from PIL import Image

from map_generator.domain.models.terrain import TerrainPreviewRequest, TerrainPreviewResult
from map_generator.domain.services.terrain_score_service import TerrainScoreService


class GenerateTerrainPreviewUseCase:
    """
    Entry point for terrain texture preview generation.

    Usage::

        use_case = GenerateTerrainPreviewUseCase()
        result   = use_case.execute(request)
        pil_img  = Image.fromarray(result.preview_image, mode='RGB')
    """

    def __init__(self) -> None:
        self._service = TerrainScoreService()

    # ── Public API ────────────────────────────────────────────────────────

    def execute(self, request: TerrainPreviewRequest) -> TerrainPreviewResult:
        """Run the full pipeline and return a TerrainPreviewResult."""
        # Lazy imports to avoid forcing Streamlit / heavy libs at module level
        from naturemap_biomes_generator import NatureMapBiomesGenerator

        nat_gen = NatureMapBiomesGenerator(
            request.heightmap_path,
            output_dir=request.output_dir,
            png_alt_max=request.png_alt_max,
            png_cellsize=request.png_cellsize,
        )

        # ── Morphological base scores ─────────────────────────────────────
        morpho = self._service.compute_morpho_scores(
            nat_gen,
            request.climate_profile,
            request.preview_snow_pct,
            request.preview_soil_flow_pct,
        )

        raw_s_rock  = morpho["raw_s_rock"]
        raw_s_soil  = morpho["raw_s_soil"]
        raw_s_grass = morpho["raw_s_grass"]
        mask_water  = morpho["mask_water"]
        mask_snow   = morpho["mask_snow"]
        visual_ocean = morpho["visual_ocean"]
        blur_sigma   = morpho["blur_sigma"]
        total_px     = morpho["total_px"]

        base_s_rock, base_s_soil, base_s_grass = self._service.normalize_scores(
            raw_s_rock.copy(), raw_s_soil.copy(), raw_s_grass.copy(), blur_sigma
        )

        # ── Initialise display scores + mode tracking ─────────────────────
        display_s_rock, display_s_soil, display_s_grass = base_s_rock, base_s_soil, base_s_grass
        render_water  = mask_water
        render_snow   = mask_snow
        hydro_overlay = True
        preview_mode_used = "morpho"
        sat_status  = "not_used"
        sat_message = "Mode morphologique uniquement"
        comparison_payload  = None
        sat_preview_images  = None
        sat_crop_info: dict | None = None

        # ── Optional SatMap guidance ──────────────────────────────────────
        sat_arr = request.sat_array
        mode    = request.preview_mode

        if sat_arr is not None and mode in ("Morphologique + SatMap", "SatMap (indépendant)"):
            from satmap_analyzer import SatMapAnalyzer

            analyzer    = SatMapAnalyzer(sat_arr, target_shape=(nat_gen.height, nat_gen.width))
            sat_indices = analyzer.compute()
            sat_veg     = sat_indices["veg_index"]
            sat_wet     = sat_indices["wet_index"]
            sat_min     = sat_indices["mineral_index"]

            sat_preview_images = {
                "veg_index":     SatMapAnalyzer.to_preview_image(sat_veg, colormap="Greens"),
                "wet_index":     SatMapAnalyzer.to_preview_image(sat_wet, colormap="Blues"),
                "mineral_index": SatMapAnalyzer.to_preview_image(sat_min, colormap="copper"),
            }
            sat_status  = sat_indices.get("status", "ok")
            sat_message = sat_indices.get("message", "")

            if mode == "Morphologique + SatMap":
                sr, ss, sg = self._service.apply_sat_guidance(
                    raw_s_rock.copy(), raw_s_soil.copy(), raw_s_grass.copy(),
                    sat_indices, request.sat_guidance_strength,
                )
                display_s_rock, display_s_soil, display_s_grass = self._service.normalize_scores(
                    sr, ss, sg, blur_sigma
                )
                comparison_payload = {
                    "morpho_stats": self._service.coverage_from_scores(
                        base_s_rock, base_s_soil, base_s_grass, mask_water, mask_snow, total_px
                    ),
                    "sat_stats": self._service.coverage_from_scores(
                        display_s_rock, display_s_soil, display_s_grass, mask_water, mask_snow, total_px
                    ),
                    "morpho_img": Image.fromarray(
                        self._service.compose_texture(
                            base_s_rock, base_s_soil, base_s_grass,
                            mask_water, mask_snow, nat_gen, visual_ocean,
                        ),
                        mode="RGB",
                    ),
                }
                preview_mode_used = "morpho_sat"

            else:  # SatMap (indépendant)
                sr, ss, sg, rw, rs, crop_smooth = self._service.compute_sat_only_scores(
                    sat_indices, request.sat_guidance_strength
                )
                display_s_rock, display_s_soil, display_s_grass = self._service.normalize_scores(
                    sr, ss, sg, blur_sigma
                )
                render_water   = rw
                render_snow    = rs
                hydro_overlay  = False
                preview_mode_used = "sat_only"
                sat_crop_info  = {
                    "crop_smooth": crop_smooth,
                    "sat_indices": sat_indices,
                    "mask_dry":    ~(rw | rs),
                }

        elif sat_arr is None and mode in ("Morphologique + SatMap", "SatMap (indépendant)"):
            sat_status  = "missing"
            sat_message = "SatMap absente en session"

        # ── Compose final texture ─────────────────────────────────────────
        texture = self._service.compose_texture(
            display_s_rock, display_s_soil, display_s_grass,
            render_water, render_snow, nat_gen, visual_ocean, hydro_overlay,
        )

        if preview_mode_used == "sat_only" and sat_crop_info is not None:
            texture = self._service.apply_crop_overlay(
                texture,
                sat_crop_info["crop_smooth"],
                sat_crop_info["mask_dry"],
                sat_crop_info["sat_indices"],
            )

        # ── Coverage statistics ───────────────────────────────────────────
        if preview_mode_used in ("morpho_sat", "sat_only"):
            cov = self._service.coverage_from_scores(
                display_s_rock, display_s_soil, display_s_grass,
                render_water, render_snow, total_px,
            )
            coverage_basis = "scores_sat" if preview_mode_used == "morpho_sat" else "scores_sat_only"
        else:
            import numpy as _np
            cov = {
                "eau_pct":   float(_np.sum(mask_water) / total_px * 100),
                "terre_pct": float(_np.sum(morpho["mask_soil"]) / total_px * 100),
                "herbe_pct": float(_np.sum(morpho["mask_grass"]) / total_px * 100),
                "roche_pct": float(_np.sum(morpho["mask_rock"]) / total_px * 100),
                "neige_pct": float(_np.sum(mask_snow) / total_px * 100),
            }
            coverage_basis = "masks_morpho"

        stats = {
            "eau_pct":             cov["eau_pct"],
            "terre_pct":           cov["terre_pct"],
            "herbe_pct":           cov["herbe_pct"],
            "roche_pct":           cov["roche_pct"],
            "neige_pct":           cov["neige_pct"],
            "snow_enabled":        bool(morpho["snow_enabled"]),
            "snowline_abs_m":      float(morpho["snowline_abs"]),
            "snow_threshold_pct_m": float(morpho["snow_threshold"]),
            "snow_threshold_used_m": float(morpho["snow_threshold"]),
            "h_max_m":             float(morpho["h_max"]),
            "relief_m":            float(morpho["relief"]),
            "climate_profile":     morpho["climate_profile"],
            "humidity":            float(morpho["humidity"]),
            "rock_slope_used":     float(morpho["rock_slope_cal"]),
            "flow_pct_used":       float(morpho["adjusted_flow_pct"]),
            "preview_mode":        preview_mode_used,
            "sat_status":          sat_status,
            "sat_message":         sat_message,
            "sat_strength":        float(request.sat_guidance_strength),
            "coverage_basis":      coverage_basis,
            "targets": (
                {}
                if preview_mode_used == "sat_only"
                else {k: list(v) for k, v in morpho["targets"].items()}
            ),
            "roche_pass1":         float(morpho["rock_pct_pass1"]),
            "cellsize_m":          float(nat_gen.cellsize),
            "tpi_windows_m":       nat_gen.tpi_windows_m,
            "lithology_distribution": {
                k: float(v / total_px * 100)
                for k, v in nat_gen.lithology_distribution.items()
            },
            "streams_pct": float(__import__("numpy").sum(nat_gen.stream_network) / total_px * 100),
            "lakes_pct":   float(__import__("numpy").sum(nat_gen.lake_mask)      / total_px * 100),
        }

        return TerrainPreviewResult(
            preview_image=texture,
            stats=stats,
            comparison_payload=comparison_payload,
            sat_preview_images=sat_preview_images,
        )
