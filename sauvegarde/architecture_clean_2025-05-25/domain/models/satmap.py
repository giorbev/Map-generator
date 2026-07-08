from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import numpy as np


@dataclass(frozen=True)
class AlignmentReport:
    status: str
    message: str
    source_shape: Tuple[int, int]
    target_shape: Tuple[int, int]


@dataclass(frozen=True)
class SatMapInput:
    rgb: np.ndarray
    target_shape: Optional[Tuple[int, int]] = None


@dataclass(frozen=True)
class SatMapIndices:
    veg_index: np.ndarray
    wet_index: np.ndarray
    mineral_index: np.ndarray
    bright_index: np.ndarray
    crop_index: np.ndarray
    report: AlignmentReport

    def to_legacy_dict(self) -> Dict[str, np.ndarray]:
        return {
            "veg_index": self.veg_index,
            "wet_index": self.wet_index,
            "mineral_index": self.mineral_index,
            "bright_index": self.bright_index,
            "crop_index": self.crop_index,
            "status": self.report.status,
            "message": self.report.message,
            "shape": self.report.target_shape,
        }
