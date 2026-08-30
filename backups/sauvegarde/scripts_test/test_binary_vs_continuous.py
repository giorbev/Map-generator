"""
Test Distribution Binaire vs Continue
======================================

Compare l'ancienne approche binaire avec la nouvelle approche continue
sur un mask d'exemple (rock_walls basé sur slope)
"""

import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from scipy.ndimage import gaussian_filter


def generate_test_data():
    """
    Génère données de test simulées

    Returns:
        slope: array 2D pentes simulées (0-60°)
    """
    print("Génération données de test...")

    # Créer un terrain simulé 512×512
    size = 512
    x = np.linspace(0, 10, size)
    y = np.linspace(0, 10, size)
    X, Y = np.meshgrid(x, y)

    # Simuler des pentes variées (combinaison de fonctions)
    # Terrain plus réaliste avec zones plates + falaises
    slope = (
        10 * np.sin(X * 0.3) * np.cos(Y * 0.3) +  # ondulations douces
        30 * np.exp(-((X-5)**2 + (Y-5)**2) / 3) +  # pic central plus raide
        25 * np.exp(-((X-2)**2 + (Y-8)**2) / 2) +  # second pic
        5 +  # base
        np.random.normal(0, 5, (size, size))  # bruit augmenté
    )

    # Clipper à [0, 70°]
    slope = np.clip(slope, 0, 70)

    print(f"  Slope simulée: min={np.min(slope):.1f}°, max={np.max(slope):.1f}°, "
          f"médiane={np.median(slope):.1f}°")

    return slope


def generate_binary_mask(slope, threshold):
    """
    ANCIENNE MÉTHODE : Mask binaire

    Args:
        slope: array 2D pentes
        threshold: seuil en degrés

    Returns:
        mask: array uint16 (0 ou 65535)
    """
    print(f"\n[BINAIRE] Génération mask binaire (seuil={threshold}°)...")

    # Condition binaire stricte
    mask_binary = (slope >= threshold)

    # Convertir directement en uint16
    mask_uint16 = mask_binary.astype(np.uint16) * 65535

    # Stats
    coverage = np.sum(mask_binary) / mask_binary.size * 100
    unique_vals = np.unique(mask_uint16)

    print(f"  Couverture: {coverage:.2f}%")
    print(f"  Valeurs uniques: {len(unique_vals)} ({unique_vals})")
    print(f"  Type: {mask_uint16.dtype}")

    return mask_uint16


def generate_continuous_mask(slope, threshold, falloff_deg=5.0, feather_sigma=2.0):
    """
    NOUVELLE MÉTHODE : Mask continu

    Args:
        slope: array 2D pentes
        threshold: seuil central en degrés
        falloff_deg: transition sur N degrés
        feather_sigma: sigma pour gaussian_filter

    Returns:
        mask: array uint16 (0-65535 continu)
    """
    print(f"\n[CONTINU] Génération mask continu (seuil={threshold}°, falloff={falloff_deg}°)...")

    # Transition douce avec falloff
    mask_float = np.clip(
        (slope - threshold) / falloff_deg,
        0.0, 1.0
    ).astype(np.float32)

    # Feathering gaussien
    mask_smooth = gaussian_filter(mask_float, sigma=feather_sigma)

    # Convertir en uint16 SANS binarisation
    mask_uint16 = (mask_smooth * 65535).astype(np.uint16)

    # Stats
    coverage = np.mean(mask_smooth) * 100
    unique_vals = len(np.unique(mask_uint16))

    print(f"  Couverture moyenne: {coverage:.2f}%")
    print(f"  Valeurs uniques: {unique_vals}")
    print(f"  Min: {np.min(mask_uint16)}, Max: {np.max(mask_uint16)}")
    print(f"  Type: {mask_uint16.dtype}")

    # Distribution valeurs intermédiaires
    mid_range = mask_uint16[(mask_uint16 > 6553) & (mask_uint16 < 58982)]  # 10%-90%
    print(f"  Pixels en transition (10-90%): {len(mid_range)} ({len(mid_range)/mask_uint16.size*100:.2f}%)")

    return mask_uint16


def analyze_distribution(mask_binary, mask_continuous, slope, threshold):
    """
    Analyse et visualise les distributions

    Args:
        mask_binary: array uint16 binaire
        mask_continuous: array uint16 continu
        slope: array 2D pentes source
        threshold: seuil utilisé
    """
    print("\n" + "="*70)
    print("ANALYSE COMPARATIVE")
    print("="*70)

    # Convertir en float pour analyse
    binary_float = mask_binary / 65535.0
    continuous_float = mask_continuous / 65535.0

    # Stats comparatives
    print(f"\nCOUVERTURE:")
    print(f"  Binaire   : {np.mean(binary_float)*100:5.2f}% (pixels activés)")
    print(f"  Continu   : {np.mean(continuous_float)*100:5.2f}% (couverture pondérée)")

    print(f"\nVALEURS UNIQUES:")
    print(f"  Binaire   : {len(np.unique(mask_binary))} valeurs")
    print(f"  Continu   : {len(np.unique(mask_continuous))} valeurs")

    print(f"\nTRANSITIONS DOUCES:")
    mid_binary = binary_float[(binary_float > 0.1) & (binary_float < 0.9)]
    mid_continuous = continuous_float[(continuous_float > 0.1) & (continuous_float < 0.9)]
    print(f"  Binaire   : {len(mid_binary)} pixels en transition ({len(mid_binary)/binary_float.size*100:.3f}%)")
    print(f"  Continu   : {len(mid_continuous)} pixels en transition ({len(mid_continuous)/continuous_float.size*100:.3f}%)")

    # ══════════════════════════════════════════════════════════════════════════
    # VISUALISATION
    # ══════════════════════════════════════════════════════════════════════════

    fig, axes = plt.subplots(2, 3, figsize=(16, 10))
    fig.suptitle('Comparaison Binaire vs Continu — Rock Walls Mask', fontsize=16, fontweight='bold')

    # Ligne 1 : Masks visuels
    # ──────────────────────────

    # Slope source
    im0 = axes[0, 0].imshow(slope, cmap='terrain', vmin=0, vmax=60)
    axes[0, 0].set_title(f'Slope Source (seuil={threshold}°)', fontweight='bold')
    axes[0, 0].axis('off')
    plt.colorbar(im0, ax=axes[0, 0], label='Degrés')

    # Mask binaire
    im1 = axes[0, 1].imshow(mask_binary, cmap='gray', vmin=0, vmax=65535)
    axes[0, 1].set_title('Mask BINAIRE (ancienne méthode)', fontweight='bold', color='red')
    axes[0, 1].axis('off')
    plt.colorbar(im1, ax=axes[0, 1], label='uint16')

    # Mask continu
    im2 = axes[0, 2].imshow(mask_continuous, cmap='gray', vmin=0, vmax=65535)
    axes[0, 2].set_title('Mask CONTINU (nouvelle méthode)', fontweight='bold', color='green')
    axes[0, 2].axis('off')
    plt.colorbar(im2, ax=axes[0, 2], label='uint16')

    # Ligne 2 : Analyses
    # ──────────────────────────

    # Histogramme slope avec seuil
    axes[1, 0].hist(slope.flatten(), bins=60, alpha=0.7, color='brown', edgecolor='black')
    axes[1, 0].axvline(threshold, color='red', linestyle='--', linewidth=2, label=f'Seuil={threshold}°')
    axes[1, 0].axvline(threshold + 5, color='orange', linestyle='--', linewidth=1, label='Falloff=+5°')
    axes[1, 0].set_xlabel('Slope (degrés)')
    axes[1, 0].set_ylabel('Fréquence')
    axes[1, 0].set_title('Distribution Slope Source', fontweight='bold')
    axes[1, 0].legend()
    axes[1, 0].grid(alpha=0.3)

    # Histogramme valeurs binaire
    axes[1, 1].hist(mask_binary.flatten(), bins=50, alpha=0.7, color='red', edgecolor='black')
    axes[1, 1].set_xlabel('Valeur mask (uint16)')
    axes[1, 1].set_ylabel('Fréquence')
    axes[1, 1].set_title('Distribution Mask BINAIRE', fontweight='bold', color='red')
    axes[1, 1].set_xlim(-1000, 66535)
    axes[1, 1].grid(alpha=0.3)
    axes[1, 1].text(0.5, 0.95, f'{len(np.unique(mask_binary))} valeurs uniques',
                    transform=axes[1, 1].transAxes, ha='center', va='top',
                    bbox=dict(boxstyle='round', facecolor='yellow', alpha=0.8))

    # Histogramme valeurs continu
    axes[1, 2].hist(mask_continuous.flatten(), bins=50, alpha=0.7, color='green', edgecolor='black')
    axes[1, 2].set_xlabel('Valeur mask (uint16)')
    axes[1, 2].set_ylabel('Fréquence')
    axes[1, 2].set_title('Distribution Mask CONTINU', fontweight='bold', color='green')
    axes[1, 2].set_xlim(-1000, 66535)
    axes[1, 2].grid(alpha=0.3)
    axes[1, 2].text(0.5, 0.95, f'{len(np.unique(mask_continuous))} valeurs uniques',
                    transform=axes[1, 2].transAxes, ha='center', va='top',
                    bbox=dict(boxstyle='round', facecolor='yellow', alpha=0.8))

    plt.tight_layout()

    # Sauvegarder
    output_path = Path('test_binary_vs_continuous_comparison.png')
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"\n[OK] Graphique sauvegarde : {output_path}")

    plt.show()


def run_comparison_test():
    """
    Lance le test complet de comparaison
    """
    print("="*70)
    print("TEST DISTRIBUTION : BINAIRE vs CONTINU")
    print("="*70)

    # 1. Générer données test
    slope = generate_test_data()

    # 2. Paramètres
    threshold = 35.0  # Seuil rock_walls typique

    # 3. Générer mask binaire (ancienne méthode)
    mask_binary = generate_binary_mask(slope, threshold)

    # 4. Générer mask continu (nouvelle méthode)
    mask_continuous = generate_continuous_mask(slope, threshold, falloff_deg=5.0, feather_sigma=2.0)

    # 5. Analyser et visualiser
    analyze_distribution(mask_binary, mask_continuous, slope, threshold)

    print("\n" + "="*70)
    print("[OK] Test termine !")
    print("="*70)


if __name__ == "__main__":
    run_comparison_test()
