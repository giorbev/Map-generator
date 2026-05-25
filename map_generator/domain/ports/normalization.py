from typing import Protocol

import numpy as np


class NormalizationStrategy(Protocol):
    def normalize(self, values: np.ndarray) -> np.ndarray:
        ...
