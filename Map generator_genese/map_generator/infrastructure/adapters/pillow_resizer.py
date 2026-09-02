from typing import Optional, Tuple

import numpy as np
from PIL import Image

from map_generator.domain.models.satmap import AlignmentReport


class PillowRgbAligner:
    def align(self, rgb: np.ndarray, target_shape: Optional[Tuple[int, int]]) -> tuple[np.ndarray, AlignmentReport]:
        if rgb is None or rgb.ndim != 3 or rgb.shape[2] != 3:
            raise ValueError("SatMap invalide: doit etre RGB (H, W, 3).")

        sat_h, sat_w = rgb.shape[:2]
        if target_shape is None:
            report = AlignmentReport(
                status="ok",
                message=f"SatMap {sat_w}x{sat_h} px (pas de reference HM)",
                source_shape=(sat_h, sat_w),
                target_shape=(sat_h, sat_w),
            )
            return rgb, report

        tgt_h, tgt_w = target_shape
        if (sat_h, sat_w) == (tgt_h, tgt_w):
            report = AlignmentReport(
                status="ok",
                message=f"Dimensions identiques : {sat_w}x{sat_h} px - OK",
                source_shape=(sat_h, sat_w),
                target_shape=(tgt_h, tgt_w),
            )
            return rgb, report

        img_pil = Image.fromarray(rgb.astype(np.uint8), mode="RGB")
        aligned = np.array(img_pil.resize((tgt_w, tgt_h), Image.BILINEAR), dtype=np.uint8)
        report = AlignmentReport(
            status="resized",
            message=f"SatMap redimensionnee : {sat_w}x{sat_h} -> {tgt_w}x{tgt_h} px",
            source_shape=(sat_h, sat_w),
            target_shape=(tgt_h, tgt_w),
        )
        return aligned, report
