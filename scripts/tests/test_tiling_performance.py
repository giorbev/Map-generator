"""
Benchmark tuilage vectorisé vs boucles Python
Valide les performances pour résolutions jusqu'à 8k
"""

import numpy as np
import time
from PIL import Image


def tile_texture_slow(texture, out_w, band_h, y_offset, tile_size):
    """Version boucles Python (lente)"""
    layer = np.zeros((band_h, out_w, 3), dtype=np.float32)

    for by in range(band_h):
        global_y = y_offset + by
        y_tex = global_y % tile_size

        for bx in range(out_w):
            x_tex = bx % tile_size
            layer[by, bx, :] = texture[y_tex, x_tex, :]

    return layer


def tile_texture_fast(texture, out_w, band_h, y_offset, tile_size):
    """Version vectorisée numpy (rapide)"""
    y_coords = (np.arange(band_h, dtype=np.int32)[:, None] + y_offset) % tile_size
    x_coords = np.arange(out_w, dtype=np.int32)[None, :] % tile_size
    layer = texture[y_coords, x_coords, :]
    return layer


def benchmark_tiling():
    """Benchmark différentes résolutions"""

    # Texture test (100m × 1px/m = 100×100 px)
    tile_size = 100
    texture = np.random.rand(tile_size, tile_size, 3).astype(np.float32) * 255

    test_cases = [
        ("1k × 256 lignes", 1024, 256),
        ("2k × 256 lignes", 2048, 256),
        ("4k × 512 lignes", 4096, 512),
        ("8k × 512 lignes", 8192, 512),
    ]

    print("="*80)
    print("BENCHMARK TUILAGE TEXTURE")
    print("="*80)
    print()
    print(f"Texture : {tile_size}×{tile_size} px")
    print()
    print(f"{'Test':<20} {'Pixels':<15} {'Boucles (ms)':<15} {'Vectorisé (ms)':<15} {'Speedup':<10}")
    print("-"*80)

    for test_name, out_w, band_h in test_cases:
        n_pixels = out_w * band_h
        y_offset = 0

        # Test boucles Python (seulement pour petites résolutions)
        if n_pixels <= 1_000_000:  # Max 1M pixels sinon trop lent
            t0 = time.time()
            result_slow = tile_texture_slow(texture, out_w, band_h, y_offset, tile_size)
            time_slow = (time.time() - t0) * 1000
        else:
            time_slow = None
            result_slow = None

        # Test vectorisé
        t0 = time.time()
        result_fast = tile_texture_fast(texture, out_w, band_h, y_offset, tile_size)
        time_fast = (time.time() - t0) * 1000

        # Vérifier équivalence (si boucles testées)
        if result_slow is not None:
            diff = np.abs(result_slow - result_fast).max()
            assert diff < 1e-5, f"Résultats différents ! Max diff = {diff}"

        # Speedup
        if time_slow:
            speedup = time_slow / time_fast
            speedup_str = f"{speedup:.1f}x"
        else:
            speedup_str = "N/A"

        time_slow_str = f"{time_slow:.1f}" if time_slow else "trop lent"

        print(
            f"{test_name:<20} "
            f"{n_pixels:>13,}  "
            f"{time_slow_str:>13}  "
            f"{time_fast:>13.1f}  "
            f"{speedup_str:>8}"
        )

    print()
    print("="*80)
    print()

    # Estimation temps génération complète 8k
    print("ESTIMATION GÉNÉRATION SATMAP 8k")
    print("-"*80)

    n_surfaces = 60
    n_bands_8k = int(np.ceil(8192 / 512))  # 16 bandes
    time_per_band_per_surface = 50  # ms (d'après benchmark)

    total_time_ms = n_bands_8k * n_surfaces * time_per_band_per_surface
    total_time_sec = total_time_ms / 1000

    print(f"Résolution        : 8192×8192 px")
    print(f"Surfaces          : {n_surfaces}")
    print(f"Bandes            : {n_bands_8k} (512 lignes)")
    print(f"Temps/bande/surf. : ~{time_per_band_per_surface} ms")
    print(f"Temps total tuile : ~{total_time_sec:.1f}s")
    print()
    print("Note : Temps réel inclut aussi chargement textures + rééchantillonnage masques")
    print("       Estimation totale : 2-5 minutes pour 8k texturée")
    print()


if __name__ == "__main__":
    benchmark_tiling()
