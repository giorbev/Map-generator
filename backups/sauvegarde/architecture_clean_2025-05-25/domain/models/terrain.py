"""Domain models for terrain preview generation."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import numpy as np


@dataclass
class TerrainPreviewRequest:
    """All inputs needed to generate a terrain texture preview."""

    heightmap_path: str
    output_dir: str = "output"
    climate_profile: str = "Tempéré"
    preview_mode: str = "Morphologique (actuel)"
    preview_snow_pct: int = 92
    preview_soil_flow_pct: int = 88
    sat_guidance_strength: float = 0.35
    sat_array: Optional[np.ndarray] = None
    png_alt_max: float = 1000.0
    png_cellsize: float = 10.0


@dataclass
class TerrainPreviewResult:
    """Output produced by GenerateTerrainPreviewUseCase."""

    preview_image: np.ndarray          # RGB H×W×3 uint8
    stats: Dict[str, Any]              # Identical to old session_state payload
    comparison_payload: Optional[Dict[str, Any]] = None
    sat_preview_images: Optional[Dict[str, Any]] = None
