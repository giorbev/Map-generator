from typing import Optional, Tuple

import numpy as np

from map_generator.application.factories.satmap_factory import SatMapFactory
from map_generator.domain.models.satmap import SatMapInput


class SatMapAnalyzerFacade:
    """Facade application-level pour centraliser l'analyse SatMap."""

    def __init__(self, sat_array: np.ndarray, target_shape: Optional[Tuple[int, int]] = None):
        self._payload = SatMapInput(rgb=sat_array, target_shape=target_shape)
        self._use_case = SatMapFactory.create_use_case()

    def compute(self) -> dict:
        indices = self._use_case.execute(self._payload)
        return indices.to_legacy_dict()
