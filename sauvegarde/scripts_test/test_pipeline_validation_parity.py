"""Tests de parite entre pipeline_validation.py et data/tools/mask_verif.py."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import MethodType, SimpleNamespace

import cv2
import numpy as np

import pipeline_validation as pv


def _load_mask_verif_module():
    mask_verif_path = Path("data/tools/mask_verif.py")
    spec = importlib.util.spec_from_file_location("mask_verif_module", mask_verif_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Impossible de charger data/tools/mask_verif.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def _dummy_app(mask_verif_mod, threshold, masks):
    dummy = SimpleNamespace()
    dummy.conflict_threshold_var = _FakeVar(threshold)
    dummy.masks = masks
    dummy._get_conflict_threshold = MethodType(mask_verif_mod.MaskOverlapApp._get_conflict_threshold, dummy)
    dummy._build_conflict_stack = MethodType(mask_verif_mod.MaskOverlapApp._build_conflict_stack, dummy)
    dummy._compute_qtre_conflict_mask = MethodType(mask_verif_mod.MaskOverlapApp._compute_qtre_conflict_mask, dummy)
    dummy._count_conflict_pixels = MethodType(mask_verif_mod.MaskOverlapApp._count_conflict_pixels, dummy)
    return dummy


def _ref_load_error_masks_from_arrays(arrays, target_shape):
    target_h, target_w = target_shape
    loaded = []
    resize_count = 0
    for arr in arrays:
        if arr.ndim == 3:
            arr = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)

        if arr.dtype == np.uint16:
            err_mask = (arr > 0).astype(np.uint8)
        elif arr.dtype == np.uint8:
            err_mask = (arr > 0).astype(np.uint8)
        else:
            continue

        if err_mask.shape != (target_h, target_w):
            err_mask = cv2.resize(err_mask, (target_w, target_h), interpolation=cv2.INTER_NEAREST)
            resize_count += 1

        loaded.append(err_mask.astype(bool))

    return loaded, resize_count


def _ref_overlay(masks, reforger_error_combined, threshold):
    stack = np.stack([(m.astype(np.float32) / 65535.0) > threshold for m in masks], axis=0)
    overlap_count = np.sum(stack, axis=0)
    qtre_mask = overlap_count >= 2

    reforger_mask = reforger_error_combined
    both = qtre_mask & reforger_mask
    qtre_only = qtre_mask & (~reforger_mask)
    cyan_only = reforger_mask & (~qtre_mask)

    base_intensity = np.clip((overlap_count.astype(np.float32) / max(2, len(masks))) * 80.0, 0, 80).astype(np.uint8)
    combined = np.stack([base_intensity, base_intensity, base_intensity], axis=-1)

    combined[qtre_only] = np.array([255, 0, 0], dtype=np.uint8)
    combined[cyan_only] = np.array([0, 255, 255], dtype=np.uint8)
    combined[both] = np.array([255, 0, 255], dtype=np.uint8)

    return overlap_count, qtre_mask, both, qtre_only, cyan_only, combined


def _ref_correct_masks_on_magenta(masks, magenta_mask, threshold):
    stack = np.stack([(m.astype(np.float32) / 65535.0) > threshold for m in masks], axis=0)
    before_conflicts = int(np.count_nonzero(np.sum(stack, axis=0) >= 2))

    stack_values = np.stack(masks, axis=0).astype(np.uint16)
    dominant_idx = np.argmax(stack_values, axis=0)
    corrected_stack = stack_values.copy()
    for idx in range(corrected_stack.shape[0]):
        non_dominant = magenta_mask & (dominant_idx != idx)
        corrected_stack[idx, non_dominant] = 0

    corrected_masks = [corrected_stack[idx] for idx in range(corrected_stack.shape[0])]
    stack2 = np.stack([(m.astype(np.float32) / 65535.0) > threshold for m in corrected_masks], axis=0)
    after_conflicts = int(np.count_nonzero(np.sum(stack2, axis=0) >= 2))

    return corrected_masks, before_conflicts, after_conflicts


def main():
    mask_verif_mod = _load_mask_verif_module()

    rng = np.random.default_rng(20260613)
    h, w = 64, 96
    masks = [rng.integers(0, 65536, size=(h, w), dtype=np.uint16) for _ in range(4)]

    # 1) Parite normalisation seuil
    for raw_threshold in [0.15, 15, 1.2, -0.4, "abc", None]:
        dummy = _dummy_app(mask_verif_mod, raw_threshold, masks)
        ref = dummy._get_conflict_threshold()
        got = pv.normalize_conflict_threshold(raw_threshold)
        assert abs(ref - got) < 1e-12, f"Seuil mismatch: {raw_threshold} -> ref={ref}, got={got}"

    # 2) Parite _build_conflict_stack / compute_qtre / count
    raw_threshold = 15
    dummy = _dummy_app(mask_verif_mod, raw_threshold, masks)
    ref_stack, ref_thr = dummy._build_conflict_stack(masks)
    got_stack, got_thr = pv.build_conflict_stack(masks, threshold=raw_threshold)
    assert ref_thr == got_thr, "Threshold normalise mismatch"
    assert np.array_equal(ref_stack, got_stack), "Conflict stack mismatch"

    ref_overlap, ref_qtre, ref_thr2 = dummy._compute_qtre_conflict_mask()
    got_overlap, got_qtre, got_thr2 = pv.compute_qtre_conflict_mask(masks, threshold=raw_threshold)
    assert ref_thr2 == got_thr2, "QTRE threshold mismatch"
    assert np.array_equal(ref_overlap, got_overlap), "Overlap mismatch"
    assert np.array_equal(ref_qtre, got_qtre), "QTRE mask mismatch"

    ref_count = dummy._count_conflict_pixels(masks)
    got_count = pv.count_conflict_pixels(masks, threshold=raw_threshold)
    assert ref_count == got_count, "Conflict count mismatch"

    # 3) Parite chargement masks erreur (arrays)
    arr_u8 = rng.integers(0, 256, size=(32, 48), dtype=np.uint8)
    arr_u16 = rng.integers(0, 65536, size=(64, 96), dtype=np.uint16)
    arr_rgb = rng.integers(0, 256, size=(40, 50, 3), dtype=np.uint8)
    arr_bad = rng.random((16, 16), dtype=np.float32)

    ref_loaded, ref_resize = _ref_load_error_masks_from_arrays([arr_u8, arr_u16, arr_rgb, arr_bad], (h, w))
    got_loaded, got_resize = pv.load_reforger_error_masks_from_arrays([arr_u8, arr_u16, arr_rgb, arr_bad], (h, w))
    assert ref_resize == got_resize, "Resize count mismatch"
    assert len(ref_loaded) == len(got_loaded), "Loaded mask count mismatch"
    for i, (a, b) in enumerate(zip(ref_loaded, got_loaded)):
        assert np.array_equal(a, b), f"Error mask mismatch idx={i}"

    # 4) Parite overlay QTRE/Reforger
    reforger_combined = np.any(np.stack(got_loaded, axis=0), axis=0)
    thr = pv.normalize_conflict_threshold(raw_threshold)
    ref_ov = _ref_overlay(masks, reforger_combined, thr)
    got_ov = pv.compute_qtre_reforger_overlay(masks, reforger_combined, threshold=raw_threshold)

    assert np.array_equal(ref_ov[0], got_ov["overlap_count"]), "Overlay overlap mismatch"
    assert np.array_equal(ref_ov[1], got_ov["qtre_mask"]), "Overlay qtre mask mismatch"
    assert np.array_equal(ref_ov[2], got_ov["both"]), "Overlay both mismatch"
    assert np.array_equal(ref_ov[3], got_ov["qtre_only"]), "Overlay qtre_only mismatch"
    assert np.array_equal(ref_ov[4], got_ov["cyan_only"]), "Overlay cyan_only mismatch"
    assert np.array_equal(ref_ov[5], got_ov["combined_heatmap"]), "Overlay heatmap mismatch"

    # 5) Parite correction magenta
    magenta_mask = pv.extract_magenta_mask(got_ov["combined_heatmap"])
    ref_corr_masks, ref_before, ref_after = _ref_correct_masks_on_magenta(masks, magenta_mask, thr)
    got_corr = pv.correct_masks_on_magenta(masks, magenta_mask, threshold=raw_threshold)

    assert ref_before == got_corr["before_conflicts"], "Before conflicts mismatch"
    assert ref_after == got_corr["after_conflicts"], "After conflicts mismatch"
    assert len(ref_corr_masks) == len(got_corr["corrected_masks"]), "Corrected count mismatch"
    for i, (a, b) in enumerate(zip(ref_corr_masks, got_corr["corrected_masks"])):
        assert np.array_equal(a, b), f"Corrected mask mismatch idx={i}"

    print("OK: parite pipeline_validation.py vs mask_verif.py verifiee.")


if __name__ == "__main__":
    main()
