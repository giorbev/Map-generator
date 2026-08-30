"""ESRI ASCII Grid (ASC) heightmap exporter."""
from __future__ import annotations

import numpy as np


class AscExporter:
    """
    Export a 2-D heightmap array to ESRI ASCII Grid format.

    The exporter preserves raw altitude values (no normalisation).
    It is free of any UI dependency — callers must handle exceptions.
    """

    def export(
        self,
        heightmap_array: np.ndarray,
        output_path: str,
        cellsize: float = 1.0,
        nodata_value: float = -9999,
    ) -> str:
        """
        Write *heightmap_array* to *output_path* as an ASC file.

        Parameters
        ----------
        heightmap_array:
            2-D (or 3-D with a single channel) float/int array of altitude values.
        output_path:
            Destination file path (will be created or overwritten).
        cellsize:
            Pixel size in map units (default 1.0).
        nodata_value:
            Value to use for missing data cells.

        Returns
        -------
        str
            The *output_path* that was written.

        Raises
        ------
        IOError
            On any write error.
        """
        if heightmap_array.ndim == 3:
            heightmap_array = heightmap_array[:, :, 0]

        heightmap = heightmap_array.astype(np.float32)
        nrows, ncols = heightmap.shape

        header = (
            f"ncols         {ncols}\n"
            f"nrows         {nrows}\n"
            f"xllcorner     0.0\n"
            f"yllcorner     0.0\n"
            f"cellsize      {cellsize}\n"
            f"NODATA_value  {nodata_value}\n"
        )

        with open(output_path, "w", encoding="utf-8") as fh:
            fh.write(header)
            for row in heightmap:
                fh.write(" ".join(f"{v:.2f}" for v in row) + "\n")

        return output_path
