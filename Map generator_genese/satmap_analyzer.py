"""Legacy-compatible SatMap analyzer backed by modular architecture."""

from typing import Optional, Tuple

import numpy as np
from PIL import Image

from map_generator.application.factories.satmap_factory import SatMapFactory
from map_generator.domain.models.satmap import SatMapInput


class SatMapAnalyzer:
    """Facade de compatibilite avec l'API historique utilisee par app.py."""

    def __init__(self, sat_array: np.ndarray, target_shape: Optional[Tuple[int, int]] = None):
        self._raw = sat_array
        self._target_shape = target_shape
        self._use_case = SatMapFactory.create_use_case()
        self._aligned = None
        self._report = None
        self.shape_status = None
        self.shape_message = ""

    def align(self) -> np.ndarray:
        payload = SatMapInput(rgb=self._raw, target_shape=self._target_shape)
        aligned_rgb, report = self._use_case.align(payload)
        self._aligned = aligned_rgb.astype(np.float32) / 255.0
        self._report = report
        self.shape_status = report.status
        self.shape_message = report.message
        return self._aligned

    def compute(self) -> dict:
        payload = SatMapInput(rgb=self._raw, target_shape=self._target_shape)
        aligned_rgb, report = self._use_case.align(payload)
        indices = self._use_case.execute_from_aligned(aligned_rgb, report)
        self._report = indices.report
        self.shape_status = indices.report.status
        self.shape_message = indices.report.message
        self._aligned = aligned_rgb.astype(np.float32) / 255.0
        return indices.to_legacy_dict()

    @staticmethod
    def to_preview_image(index_arr, colormap='viridis'):
        try:
            import matplotlib.cm as cm
            cmap = cm.get_cmap(colormap)
            rgba = cmap(index_arr)
            rgb = (rgba[:, :, :3] * 255).astype(np.uint8)
            return Image.fromarray(rgb, mode='RGB')
        except ImportError:
            g = (np.clip(index_arr, 0.0, 1.0) * 255).astype(np.uint8)
            rgb = np.stack([np.zeros_like(g), g, np.zeros_like(g)], axis=2)
            return Image.fromarray(rgb, mode='RGB')