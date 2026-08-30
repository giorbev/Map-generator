"""
heightmap_roughness.py
======================
Adds surface variety to heightmaps before slope/mask computation.
Three independent strategies, combinable:

  1. slope_perturbation  — perturbs the slope signal with fBm noise (non-destructive)
  2. domain_warp         — warps heightmap coordinates before any gradient computation
  3. additive_roughness  — adds fBm displacement directly to the heightmap

CLI
---
  python heightmap_roughness.py input.png output.png --mode slope_perturb
  python heightmap_roughness.py input.png output.png --mode domain_warp --warp-strength 25
  python heightmap_roughness.py input.png output.png --mode additive --amplitude 1.5
  python heightmap_roughness.py input.png output.png --mode all --preview

API
---
  from heightmap_roughness import SlopeRoughnessProcessor
  proc = SlopeRoughnessProcessor(cell_size=4.0)
  slope = proc.slope_perturb(heightmap, noise_amplitude=8.0)
  # or:
  warped_hm = proc.domain_warp(heightmap, warp_strength=20)
  slope = proc.compute_slope(warped_hm)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Literal

import numpy as np
from scipy.ndimage import map_coordinates, uniform_filter

# ---------------------------------------------------------------------------
# Optional: fast Perlin via `noise` library; fall back to scipy fBm otherwise
# ---------------------------------------------------------------------------
try:
    from noise import pnoise2
    _HAS_PNOISE = True
except ImportError:
    _HAS_PNOISE = False


# ---------------------------------------------------------------------------
# fBm helpers
# ---------------------------------------------------------------------------

def _fbm_pnoise(h: int, w: int, scale: float, octaves: int, seed: int) -> np.ndarray:
    """Fractal Brownian Motion via the `noise` library (fast)."""
    offset_x = seed * 1000.17
    offset_y = seed * 999.31
    out = np.empty((h, w), dtype=np.float32)
    for y in range(h):
        for x in range(w):
            out[y, x] = pnoise2(
                x * scale + offset_x,
                y * scale + offset_y,
                octaves=octaves,
                persistence=0.5,
                lacunarity=2.0,
            )
    return out


def _fbm_scipy(h: int, w: int, scale: float, octaves: int, seed: int) -> np.ndarray:
    """Fractal Brownian Motion using Gaussian-filtered white noise (no deps)."""
    rng = np.random.default_rng(seed)
    out = np.zeros((h, w), dtype=np.float32)
    amplitude = 1.0
    frequency = 1.0
    sigma_base = max(1, int(1.0 / (scale * frequency * max(h, w))))
    for _ in range(octaves):
        layer = rng.standard_normal((h, w)).astype(np.float32)
        sigma = max(0.5, sigma_base / frequency)
        layer = uniform_filter(layer, size=int(sigma * 3) | 1)
        # normalise layer to [-1, 1]
        mx = np.abs(layer).max()
        if mx > 0:
            layer /= mx
        out += layer * amplitude
        amplitude *= 0.5
        frequency *= 2.0
    mx = np.abs(out).max()
    return out / mx if mx > 0 else out


def generate_fbm(h: int, w: int, scale: float = 0.005, octaves: int = 6,
                 seed: int = 0) -> np.ndarray:
    """Returns fBm array in [-1, 1], shape (h, w)."""
    if _HAS_PNOISE:
        return _fbm_pnoise(h, w, scale, octaves, seed)
    return _fbm_scipy(h, w, scale, octaves, seed)


# ---------------------------------------------------------------------------
# Core processor
# ---------------------------------------------------------------------------

class SlopeRoughnessProcessor:
    """
    Parameters
    ----------
    cell_size : float
        Horizontal distance per pixel in metres (Zimnitrita = 4.0 m/cell).
    """

    def __init__(self, cell_size: float = 4.0):
        self.cell_size = cell_size

    # --- slope / curvature primitives --------------------------------------

    def compute_slope(self, heightmap: np.ndarray) -> np.ndarray:
        """Returns slope in degrees, shape == heightmap.shape."""
        dy, dx = np.gradient(heightmap.astype(np.float32), self.cell_size)
        return np.degrees(np.arctan(np.sqrt(dx ** 2 + dy ** 2)))

    def compute_curvature(self, heightmap: np.ndarray) -> np.ndarray:
        """Returns Zevenbergen & Thorne curvature (signed), shape == heightmap.shape."""
        hm = heightmap.astype(np.float32)
        c = self.cell_size
        # Second-order finite differences
        curv_x = (np.roll(hm, -1, axis=1) - 2 * hm + np.roll(hm, 1, axis=1)) / (c ** 2)
        curv_y = (np.roll(hm, -1, axis=0) - 2 * hm + np.roll(hm, 1, axis=0)) / (c ** 2)
        return curv_x + curv_y

    # --- Strategy 1: slope perturbation ------------------------------------

    def slope_perturb(
        self,
        heightmap: np.ndarray,
        noise_amplitude: float = 8.0,
        noise_scale: float = 0.008,
        octaves: int = 6,
        seed: int = 0,
    ) -> np.ndarray:
        """
        Non-destructive: compute slope normally, then add fBm noise *to the slope
        signal* before thresholding.  The heightmap itself is unchanged.

        Parameters
        ----------
        noise_amplitude : float
            Max degrees of slope perturbation (±).  8° works well for hilly terrain.
        noise_scale : float
            Spatial frequency of the perturbation.  Lower = broader patches.
        """
        h, w = heightmap.shape
        slope = self.compute_slope(heightmap)
        noise = generate_fbm(h, w, scale=noise_scale, octaves=octaves, seed=seed)
        return slope + noise * noise_amplitude

    # --- Strategy 2: domain warp ------------------------------------------

    def domain_warp(
        self,
        heightmap: np.ndarray,
        warp_strength: float = 20.0,
        warp_scale: float = 0.006,
        octaves: int = 5,
        seed: int = 0,
    ) -> np.ndarray:
        """
        Warp the heightmap coordinate space before any computation.  Returns a
        *new heightmap* with organically deformed slopes.  Run compute_slope() on
        the result to get a naturally varied slope map.

        Parameters
        ----------
        warp_strength : float
            Max pixel displacement (metres / cell_size gives you real metres).
        warp_scale : float
            Spatial scale of the warp noise.
        """
        h, w = heightmap.shape
        ys, xs = np.mgrid[0:h, 0:w]

        warp_x = generate_fbm(h, w, scale=warp_scale, octaves=octaves, seed=seed)
        warp_y = generate_fbm(h, w, scale=warp_scale, octaves=octaves, seed=seed + 99)

        src_x = np.clip(xs + warp_x * warp_strength, 0, w - 1)
        src_y = np.clip(ys + warp_y * warp_strength, 0, h - 1)

        warped = map_coordinates(
            heightmap.astype(np.float64),
            [src_y.ravel(), src_x.ravel()],
            order=1,
            mode="nearest",
        ).reshape(h, w)
        return warped.astype(heightmap.dtype)

    # --- Strategy 3: additive roughness -----------------------------------

    def additive_roughness(
        self,
        heightmap: np.ndarray,
        amplitude: float = 1.5,
        scale: float = 0.012,
        octaves: int = 7,
        seed: int = 0,
        blend_with_slope: bool = True,
        slope_blend_power: float = 1.5,
    ) -> np.ndarray:
        """
        Add fBm displacement directly to the heightmap.  Optionally modulated
        by existing slope so flat areas stay flat and only slopes get roughness.

        Parameters
        ----------
        amplitude : float
            Max height displacement in heightmap units.
        blend_with_slope : bool
            If True, roughness is multiplied by a normalised slope weight so
            flat areas are not affected.
        slope_blend_power : float
            Sharpness of the slope-weight ramp.  Higher = roughness only on steep areas.
        """
        h, w = heightmap.shape
        noise = generate_fbm(h, w, scale=scale, octaves=octaves, seed=seed)

        if blend_with_slope:
            slope_norm = self.compute_slope(heightmap)
            slope_norm = slope_norm / slope_norm.max()
            slope_norm = slope_norm ** slope_blend_power
            noise = noise * slope_norm

        return (heightmap.astype(np.float32) + noise * amplitude).astype(heightmap.dtype)

    # --- Rock mask helper -------------------------------------------------

    def rock_mask(
        self,
        heightmap: np.ndarray,
        slope_threshold: float = 20.0,
        curvature_weight: float = 0.0,
        curvature_min: float = 0.002,
        perturb_slope: bool = True,
        **perturb_kwargs,
    ) -> np.ndarray:
        """
        Combined rock mask: slope (optionally perturbed) AND optional curvature gate.

        Parameters
        ----------
        slope_threshold : float
            Degrees above which a pixel is considered rock.
        curvature_weight : float
            0 = ignore curvature; 1 = require curvature_min as hard gate.
        curvature_min : float
            Minimum absolute curvature for the curvature gate.
        perturb_slope : bool
            Apply slope_perturb() before thresholding.
        """
        if perturb_slope:
            slope = self.slope_perturb(heightmap, **perturb_kwargs)
        else:
            slope = self.compute_slope(heightmap)

        rock = slope > slope_threshold

        if curvature_weight > 0:
            curv = np.abs(self.compute_curvature(heightmap))
            curv_gate = curv > curvature_min
            # blend: full gate at weight=1, pure slope at weight=0
            if curvature_weight >= 1.0:
                rock = rock & curv_gate
            else:
                rock = rock & (curv_gate | (np.random.rand(*rock.shape) > curvature_weight))

        return rock.astype(np.uint8)


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def load_heightmap(path: str | Path) -> tuple[np.ndarray, dict]:
    """Load heightmap from PNG/TIF/R32 raw. Returns (array_float32, meta)."""
    import importlib
    path = Path(path)
    meta: dict = {"path": str(path), "dtype": None, "shape": None}

    if path.suffix.lower() in {".png", ".tif", ".tiff", ".jpg"}:
        try:
            from PIL import Image
            img = Image.open(path)
            arr = np.array(img, dtype=np.float32)
            if arr.ndim == 3:
                arr = arr[..., 0]  # use red channel if RGB
        except ImportError:
            import imageio
            arr = np.array(imageio.imread(path), dtype=np.float32)
    elif path.suffix.lower() == ".raw":
        arr = np.fromfile(path, dtype=np.float32)
        side = int(np.sqrt(len(arr)))
        arr = arr.reshape(side, side)
    else:
        raise ValueError(f"Unsupported heightmap format: {path.suffix}")

    meta["dtype"] = str(arr.dtype)
    meta["shape"] = arr.shape
    return arr, meta


def save_heightmap(arr: np.ndarray, path: str | Path):
    path = Path(path)
    try:
        from PIL import Image
        # normalise to uint16 for lossless PNG
        mn, mx = arr.min(), arr.max()
        norm = ((arr - mn) / (mx - mn + 1e-9) * 65535).astype(np.uint16)
        Image.fromarray(norm).save(path)
    except ImportError:
        import imageio
        imageio.imwrite(str(path), arr.astype(np.float32))


def _preview(heightmap, perturbed_slope, warped_slope, rock_mask, out_path: Path):
    """Save a 4-panel comparison PNG."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle("heightmap_roughness — preview", fontsize=14)

        base_slope = SlopeRoughnessProcessor(cell_size=4.0).compute_slope(heightmap)

        axes[0, 0].imshow(base_slope, cmap="magma", vmin=0, vmax=45)
        axes[0, 0].set_title("Slope — original")
        axes[0, 0].axis("off")

        axes[0, 1].imshow(perturbed_slope, cmap="magma", vmin=0, vmax=45)
        axes[0, 1].set_title("Slope — perturbed (strategy 1)")
        axes[0, 1].axis("off")

        axes[1, 0].imshow(warped_slope, cmap="magma", vmin=0, vmax=45)
        axes[1, 0].set_title("Slope — domain warped (strategy 2)")
        axes[1, 0].axis("off")

        im = axes[1, 1].imshow(rock_mask, cmap="Reds", vmin=0, vmax=1)
        axes[1, 1].set_title("Rock mask (slope_perturb + curvature gate)")
        axes[1, 1].axis("off")

        plt.tight_layout()
        preview_path = out_path.with_name(out_path.stem + "_preview.png")
        plt.savefig(preview_path, dpi=120)
        print(f"Preview saved → {preview_path}")
    except ImportError:
        print("matplotlib not available — skipping preview")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Add surface roughness variety to a heightmap for mask generation."
    )
    parser.add_argument("input", help="Input heightmap (PNG / TIF / raw float32)")
    parser.add_argument("output", help="Output path")
    parser.add_argument(
        "--mode",
        choices=["slope_perturb", "domain_warp", "additive", "all"],
        default="slope_perturb",
        help="Roughness strategy (default: slope_perturb)",
    )
    parser.add_argument("--cell-size", type=float, default=4.0,
                        help="Metres per pixel (default 4.0 for Zimnitrita)")
    # slope_perturb params
    parser.add_argument("--noise-amplitude", type=float, default=8.0,
                        help="Slope perturbation amplitude in degrees (default 8)")
    parser.add_argument("--noise-scale", type=float, default=0.008,
                        help="Spatial scale of perturbation noise (default 0.008)")
    # domain_warp params
    parser.add_argument("--warp-strength", type=float, default=20.0,
                        help="Domain warp pixel displacement (default 20)")
    parser.add_argument("--warp-scale", type=float, default=0.006,
                        help="Spatial scale of warp noise (default 0.006)")
    # additive params
    parser.add_argument("--amplitude", type=float, default=1.5,
                        help="Additive roughness amplitude in height units (default 1.5)")
    # rock mask params
    parser.add_argument("--slope-threshold", type=float, default=20.0,
                        help="Rock mask slope threshold in degrees (default 20)")
    parser.add_argument("--curvature-weight", type=float, default=0.5,
                        help="Curvature gate weight 0-1 (default 0.5)")
    # misc
    parser.add_argument("--octaves", type=int, default=6,
                        help="fBm octaves (default 6)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed (default 42)")
    parser.add_argument("--preview", action="store_true",
                        help="Save a 4-panel comparison PNG alongside output")

    args = parser.parse_args()

    print(f"Loading heightmap: {args.input}")
    hm, meta = load_heightmap(args.input)
    print(f"  shape={meta['shape']}, dtype={meta['dtype']}")

    proc = SlopeRoughnessProcessor(cell_size=args.cell_size)
    out_path = Path(args.output)

    if args.mode == "slope_perturb":
        result = proc.slope_perturb(
            hm,
            noise_amplitude=args.noise_amplitude,
            noise_scale=args.noise_scale,
            octaves=args.octaves,
            seed=args.seed,
        )
        print(f"Slope perturbation done — slope range: {result.min():.1f}°–{result.max():.1f}°")
        # Save as float32 raw for downstream use
        result.astype(np.float32).tofile(out_path.with_suffix(".slope.raw"))
        print(f"Slope array saved → {out_path.with_suffix('.slope.raw')}")

    elif args.mode == "domain_warp":
        result = proc.domain_warp(
            hm,
            warp_strength=args.warp_strength,
            warp_scale=args.warp_scale,
            octaves=args.octaves,
            seed=args.seed,
        )
        save_heightmap(result, out_path)
        print(f"Domain-warped heightmap saved → {out_path}")

    elif args.mode == "additive":
        result = proc.additive_roughness(
            hm,
            amplitude=args.amplitude,
            octaves=args.octaves,
            seed=args.seed,
        )
        save_heightmap(result, out_path)
        print(f"Roughened heightmap saved → {out_path}")

    elif args.mode == "all":
        perturbed_slope = proc.slope_perturb(
            hm,
            noise_amplitude=args.noise_amplitude,
            noise_scale=args.noise_scale,
            octaves=args.octaves,
            seed=args.seed,
        )
        warped_hm = proc.domain_warp(
            hm,
            warp_strength=args.warp_strength,
            warp_scale=args.warp_scale,
            octaves=args.octaves,
            seed=args.seed,
        )
        warped_slope = proc.compute_slope(warped_hm)
        rock = proc.rock_mask(
            hm,
            slope_threshold=args.slope_threshold,
            curvature_weight=args.curvature_weight,
            perturb_slope=True,
            noise_amplitude=args.noise_amplitude,
            noise_scale=args.noise_scale,
            octaves=args.octaves,
            seed=args.seed,
        )
        perturbed_slope.astype(np.float32).tofile(out_path.with_suffix(".slope_perturbed.raw"))
        warped_slope.astype(np.float32).tofile(out_path.with_suffix(".slope_warped.raw"))
        rock.astype(np.uint8).tofile(out_path.with_suffix(".rock_mask.raw"))
        print("All outputs saved.")

        if args.preview:
            _preview(hm, perturbed_slope, warped_slope, rock, out_path)


if __name__ == "__main__":
    main()
