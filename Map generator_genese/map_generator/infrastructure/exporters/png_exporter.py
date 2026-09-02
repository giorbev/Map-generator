"""PNG heightmap exporter (8-bit or 16-bit)."""
from __future__ import annotations

import json
import os

import numpy as np
from PIL import Image


class PngExporter:
    """
    Export a 2-D heightmap array to a normalised PNG (8-bit or 16-bit).

    A companion JSON metadata file is written alongside the PNG so that
    the original altitude range can be recovered for later denormalisation.
    """

    def export(
        self,
        heightmap_array: np.ndarray,
        output_path: str,
        bit_depth: int = 16,
    ) -> str:
        """
        Write *heightmap_array* to *output_path* as a PNG.

        Parameters
        ----------
        heightmap_array:
            2-D float/int array of altitude values.
        output_path:
            Destination file path (must end with ``.png``).
        bit_depth:
            Either 8 or 16.

        Returns
        -------
        str
            The *output_path* that was written.

        Raises
        ------
        ValueError
            If *bit_depth* is not 8 or 16.
        IOError
            On any write error.
        """
        if bit_depth not in (8, 16):
            raise ValueError("bit_depth must be 8 or 16")

        arr = heightmap_array.astype(np.float32)
        h_min = float(np.min(arr))
        h_max = float(np.max(arr))
        norm = (arr - h_min) / (h_max - h_min + 1e-8)

        if bit_depth == 8:
            out = np.clip(norm * 255.0, 0, 255).astype(np.uint8)
            img = Image.fromarray(out, mode="L")
        else:
            out = np.clip(norm * 65535.0, 0, 65535).astype(np.uint16)
            img = Image.fromarray(out, mode="I;16")

        img.save(output_path)

        meta_path = os.path.splitext(output_path)[0] + "_metadata.json"
        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump({"alt_min": h_min, "alt_max": h_max, "bit_depth": bit_depth}, fh, indent=2)

        return output_path

    def export_from_png_with_denormalization(
        self,
        png_array: np.ndarray,
        metadata_path: str,
        output_path: str,
        cellsize: float = 1.0,
    ) -> str:
        """
        Denormalise a 16-bit PNG array back to real altitudes and write an ASC.

        Parameters
        ----------
        png_array:
            16-bit array (values 0–65535).
        metadata_path:
            Path to the companion JSON file produced by :meth:`export`.
        output_path:
            Destination ASC file path.

        Returns
        -------
        str
            The *output_path* that was written.
        """
        from map_generator.infrastructure.exporters.asc_exporter import AscExporter

        with open(metadata_path, "r", encoding="utf-8") as fh:
            meta = json.load(fh)

        alt_min = meta["alt_min"]
        alt_max = meta["alt_max"]

        norm = png_array.astype(np.float32) / 65535.0
        heightmap = norm * (alt_max - alt_min) + alt_min

        return AscExporter().export(heightmap, output_path, cellsize=cellsize)
