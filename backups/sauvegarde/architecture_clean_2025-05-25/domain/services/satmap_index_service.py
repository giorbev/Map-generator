import numpy as np

from map_generator.domain.models.satmap import SatMapIndices
from map_generator.domain.ports.normalization import NormalizationStrategy


class SatMapIndexService:
    def __init__(self, normalizer: NormalizationStrategy):
        self._normalizer = normalizer

    def compute(self, aligned_rgb: np.ndarray, report) -> SatMapIndices:
        arr = aligned_rgb.astype(np.float32) / 255.0
        r = arr[:, :, 0]
        g = arr[:, :, 1]
        b = arr[:, :, 2]

        vari = (g - r) / (g + r - b + 1e-6)
        veg_index = np.clip((vari + 1.0) / 2.0, 0.0, 1.0).astype(np.float32)

        wet_raw = np.clip((b + 0.5 * g) - r, 0.0, 1.0)
        wet_index = self._normalizer.normalize(wet_raw)

        mineral_raw = np.clip(r - 0.5 * g - 0.3 * b, 0.0, 1.0)
        mineral_index = self._normalizer.normalize(mineral_raw)

        bright_index = np.clip(0.299 * r + 0.587 * g + 0.114 * b, 0.0, 1.0).astype(np.float32)

        crop_raw = np.clip((r * 0.55 + g * 0.45) / (b + 0.08) - 1.2, 0.0, None)
        crop_index = self._normalizer.normalize(crop_raw)

        return SatMapIndices(
            veg_index=veg_index,
            wet_index=wet_index,
            mineral_index=mineral_index,
            bright_index=bright_index,
            crop_index=crop_index,
            report=report,
        )
