import numpy as np

from map_generator.domain.ports.normalization import NormalizationStrategy


class Percentile99Normalizer(NormalizationStrategy):
    def normalize(self, values: np.ndarray) -> np.ndarray:
        scale = float(np.percentile(values, 99)) + 1e-6
        return np.clip(values / scale, 0.0, 1.0).astype(np.float32)
