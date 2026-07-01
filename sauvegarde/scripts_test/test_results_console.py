"""
Test Distribution - Sortie Console
===================================

Version console du test binaire vs continu
"""

import numpy as np
from scipy.ndimage import gaussian_filter


def generate_test_slope():
    """Génère slope de test"""
    size = 512
    x = np.linspace(0, 10, size)
    y = np.linspace(0, 10, size)
    X, Y = np.meshgrid(x, y)

    slope = (
        10 * np.sin(X * 0.3) * np.cos(Y * 0.3) +
        30 * np.exp(-((X-5)**2 + (Y-5)**2) / 3) +
        25 * np.exp(-((X-2)**2 + (Y-8)**2) / 2) +
        5 +
        np.random.normal(0, 5, (size, size))
    )

    slope = np.clip(slope, 0, 70)
    return slope


def generate_binary_mask(slope, threshold):
    """ANCIENNE MÉTHODE - Binaire"""
    mask_binary = (slope >= threshold)
    mask_uint16 = mask_binary.astype(np.uint16) * 65535
    return mask_uint16


def generate_continuous_mask(slope, threshold, falloff_deg=5.0, feather_sigma=2.0):
    """NOUVELLE MÉTHODE - Continu"""
    mask_float = np.clip(
        (slope - threshold) / falloff_deg,
        0.0, 1.0
    ).astype(np.float32)

    mask_smooth = gaussian_filter(mask_float, sigma=feather_sigma)
    mask_uint16 = (mask_smooth * 65535).astype(np.uint16)
    return mask_uint16


def main():
    print("=" * 80)
    print("TEST DISTRIBUTION : BINAIRE vs CONTINU")
    print("=" * 80)

    # Générer données
    print("\nGeneration slope de test (512x512)...")
    slope = generate_test_slope()
    print(f"  Slope : min={np.min(slope):.1f}, max={np.max(slope):.1f}, mediane={np.median(slope):.1f}")

    # Paramètres
    threshold = 35.0
    print(f"\nParametres : seuil={threshold}, falloff=5.0, feather_sigma=2.0")

    # Générer masks
    print("\n" + "-" * 80)
    print("ANCIENNE METHODE : BINAIRE")
    print("-" * 80)
    mask_binary = generate_binary_mask(slope, threshold)
    binary_float = mask_binary / 65535.0

    print(f"  Couverture            : {np.mean(binary_float)*100:.2f}% (pixels actives)")
    print(f"  Valeurs uniques       : {len(np.unique(mask_binary))}")
    print(f"  Min/Max               : {np.min(mask_binary)} / {np.max(mask_binary)}")

    # Transitions
    mid_binary = binary_float[(binary_float > 0.1) & (binary_float < 0.9)]
    print(f"  Pixels transition     : {len(mid_binary)} ({len(mid_binary)/binary_float.size*100:.3f}%)")

    # Distribution détaillée
    print(f"\n  Distribution valeurs :")
    print(f"    [0]              : {np.sum(mask_binary == 0)} pixels ({np.sum(mask_binary == 0)/mask_binary.size*100:.2f}%)")
    print(f"    [65535]          : {np.sum(mask_binary == 65535)} pixels ({np.sum(mask_binary == 65535)/mask_binary.size*100:.2f}%)")

    print("\n" + "-" * 80)
    print("NOUVELLE METHODE : CONTINU")
    print("-" * 80)
    mask_continuous = generate_continuous_mask(slope, threshold, falloff_deg=5.0, feather_sigma=2.0)
    continuous_float = mask_continuous / 65535.0

    print(f"  Couverture moyenne    : {np.mean(continuous_float)*100:.2f}% (ponderee)")
    print(f"  Valeurs uniques       : {len(np.unique(mask_continuous))}")
    print(f"  Min/Max               : {np.min(mask_continuous)} / {np.max(mask_continuous)}")

    # Transitions
    mid_continuous = continuous_float[(continuous_float > 0.1) & (continuous_float < 0.9)]
    print(f"  Pixels transition     : {len(mid_continuous)} ({len(mid_continuous)/continuous_float.size*100:.3f}%)")

    # Distribution détaillée
    print(f"\n  Distribution valeurs :")
    print(f"    [0]              : {np.sum(mask_continuous == 0)} pixels ({np.sum(mask_continuous == 0)/mask_continuous.size*100:.2f}%)")
    print(f"    (0-6553]   (0-10%): {np.sum((mask_continuous > 0) & (mask_continuous <= 6553))} pixels")
    print(f"    (6553-32767] (10-50%): {np.sum((mask_continuous > 6553) & (mask_continuous <= 32767))} pixels")
    print(f"    (32767-58982] (50-90%): {np.sum((mask_continuous > 32767) & (mask_continuous <= 58982))} pixels")
    print(f"    (58982-65535] (90-100%): {np.sum((mask_continuous > 58982) & (mask_continuous < 65535))} pixels")
    print(f"    [65535]          : {np.sum(mask_continuous == 65535)} pixels ({np.sum(mask_continuous == 65535)/mask_continuous.size*100:.2f}%)")

    # Comparaison finale
    print("\n" + "=" * 80)
    print("COMPARAISON")
    print("=" * 80)

    print(f"\nValeurs uniques :")
    print(f"  Binaire   : {len(np.unique(mask_binary)):>6} valeurs (2 attendues : 0 et 65535)")
    print(f"  Continu   : {len(np.unique(mask_continuous)):>6} valeurs (gradient complet)")

    print(f"\nTransitions douces :")
    print(f"  Binaire   : {len(mid_binary):>6} pixels ({len(mid_binary)/binary_float.size*100:.3f}%)")
    print(f"  Continu   : {len(mid_continuous):>6} pixels ({len(mid_continuous)/continuous_float.size*100:.3f}%)")

    ratio = len(np.unique(mask_continuous)) / len(np.unique(mask_binary))
    print(f"\nRatio valeurs uniques : x{ratio:.0f}")

    print("\n" + "=" * 80)
    print("RESULTAT")
    print("=" * 80)
    print("\nAvantages CONTINU vs BINAIRE :")
    print(f"  + {len(np.unique(mask_continuous))} valeurs distinctes (vs 2)")
    print(f"  + {len(mid_continuous)/continuous_float.size*100:.2f}% du terrain en transition douce")
    print("  + Pas de demarcation brutale (ligne dure)")
    print("  + Compatible feathering gaussien")
    print("  + Meilleur blending texture dans Reforger (QTRE)")

    print("\nDesavantages BINAIRE :")
    print("  - Seulement 2 valeurs (0 ou 65535)")
    print("  - Ligne dure visible sur le terrain")
    print("  - Aucune transition progressive")
    print("  - Problemes visuels dans Reforger (seuil d'emergence)")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
