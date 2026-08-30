"""Domain models for Reforger texture mask generation."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class MaskGenerationRequest:
    """Inputs required to generate Reforger texture masks."""

    heightmap_path: str
    output_dir: str = "output"
    profile: str = "europe_temperee"
    enforce_blocks: bool = True
    dynamic_budget: bool = True
    sat_indices: Optional[Dict[str, Any]] = None  # from SatMapAnalyzer.compute()
    sat_strength: float = 0.35
    png_alt_max: float = 1000.0
    png_cellsize: float = 10.0


@dataclass
class MaskGenerationResult:
    """Output produced by GenerateMasksUseCase."""

    masks: Dict[str, Any]              # {key: float32 array [0,1], shape (H,W)}
    export_paths: Dict[str, str]       # {key: filepath}
    report: Dict[str, Any]            # JSON-serialisable metadata
