"""Protocol for heightmap exporters."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class HeightmapExporter(Protocol):
    """Export a 2-D heightmap array to a file."""

    def export(self, heightmap_array: np.ndarray, output_path: str, **kwargs) -> str:
        """
        Persist *heightmap_array* to *output_path*.

        Returns the path of the written file.
        Raises ``IOError`` on failure (never swallows exceptions).
        """
        ...
