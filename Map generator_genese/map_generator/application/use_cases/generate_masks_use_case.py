"""
Use case: generate Reforger texture masks.

Delegates to ReforgerMaskGenerator (legacy class) and returns
a structured MaskGenerationResult.
"""
from __future__ import annotations

from datetime import datetime

from map_generator.domain.models.mask import MaskGenerationRequest, MaskGenerationResult


class GenerateMasksUseCase:
    """
    Generates and exports Reforger texture masks for a given heightmap.

    Usage::

        req    = MaskGenerationRequest(heightmap_path="input/terrain.asc")
        result = GenerateMasksUseCase().execute(req)
        # result.masks   → {key: float32 array}
        # result.export_paths → {key: filepath}
        # result.report  → JSON-serialisable metadata
    """

    def execute(self, request: MaskGenerationRequest) -> MaskGenerationResult:
        from naturemap_biomes_generator import NatureMapBiomesGenerator
        from reforger_mask_generator import ReforgerMaskGenerator

        nat_gen = NatureMapBiomesGenerator(
            request.heightmap_path,
            output_dir=request.output_dir,
            png_alt_max=request.png_alt_max,
            png_cellsize=request.png_cellsize,
        )

        generator = ReforgerMaskGenerator(nat_gen, output_dir=request.output_dir)

        masks = generator.generate_masks(
            profile=request.profile,
            enforce_blocks=request.enforce_blocks,
            dynamic_budget=request.dynamic_budget,
            sat_indices=request.sat_indices,
            sat_strength=request.sat_strength,
        )

        export_paths = generator.export_masks(masks, request.profile)

        report = {
            "generated_at": datetime.utcnow().isoformat(),
            "profile":       request.profile,
            "enforce_blocks": request.enforce_blocks,
            "dynamic_budget": request.dynamic_budget,
            "sat_guided":    request.sat_indices is not None,
            "sat_strength":  request.sat_strength,
            "heightmap":     request.heightmap_path,
            "resolution":    {"width": nat_gen.width, "height": nat_gen.height},
            "cellsize_m":    float(nat_gen.cellsize),
            "mask_keys":     list(masks.keys()),
            "export_paths":  export_paths,
        }

        return MaskGenerationResult(masks=masks, export_paths=export_paths, report=report)
