"""
Visualisation Mask Continu
===========================

Affiche un échantillon d'un mask pour vérifier visuellement la continuité
"""

import numpy as np
from PIL import Image
import matplotlib.pyplot as plt
from pathlib import Path
import sys


def visualize_mask(mask_path, sample_size=512):
    """
    Visualise un échantillon central d'un mask

    Args:
        mask_path: chemin vers le mask
        sample_size: taille échantillon à extraire
    """
    print(f"Chargement: {mask_path}")

    # Charger mask
    mask = np.array(Image.open(mask_path), dtype=np.uint16)
    print(f"  Resolution: {mask.shape[0]}x{mask.shape[1]}")

    # Extraire échantillon central
    h, w = mask.shape
    cy, cx = h // 2, w // 2
    half = sample_size // 2

    sample = mask[cy-half:cy+half, cx-half:cx+half]

    # Stats
    unique_vals = len(np.unique(sample))
    min_val = np.min(sample)
    max_val = np.max(sample)
    mean_val = np.mean(sample)

    print(f"  Echantillon: {sample.shape[0]}x{sample.shape[1]}")
    print(f"  Valeurs uniques: {unique_vals}")
    print(f"  Min/Max/Moy: {min_val} / {max_val} / {mean_val:.0f}")

    # Visualisation
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    fig.suptitle(f'{Path(mask_path).name} — Echantillon {sample_size}x{sample_size}', fontsize=14, fontweight='bold')

    # 1. Mask brut
    im0 = axes[0].imshow(sample, cmap='gray', vmin=0, vmax=65535)
    axes[0].set_title(f'Mask Brut (uint16)', fontweight='bold')
    axes[0].axis('off')
    plt.colorbar(im0, ax=axes[0], label='Valeur')

    # 2. Histogramme
    axes[1].hist(sample.flatten(), bins=100, color='steelblue', edgecolor='black', alpha=0.7)
    axes[1].set_xlabel('Valeur mask (uint16)')
    axes[1].set_ylabel('Frequence')
    axes[1].set_title(f'Distribution — {unique_vals} valeurs uniques', fontweight='bold')
    axes[1].grid(alpha=0.3)
    axes[1].axvline(mean_val, color='red', linestyle='--', linewidth=2, label=f'Moyenne={mean_val:.0f}')
    axes[1].legend()

    # 3. Coupe horizontale centrale
    mid_row = sample[sample_size//2, :]
    axes[2].plot(mid_row, linewidth=1.5, color='darkgreen')
    axes[2].set_xlabel('Position X (pixels)')
    axes[2].set_ylabel('Valeur mask')
    axes[2].set_title('Coupe Horizontale (ligne centrale)', fontweight='bold')
    axes[2].grid(alpha=0.3)
    axes[2].set_ylim(0, 65535)

    # Ajouter texte stats
    stats_text = f"Valeurs uniques: {unique_vals}\nMin: {min_val}\nMax: {max_val}\nMoy: {mean_val:.0f}"
    axes[2].text(0.98, 0.98, stats_text,
                 transform=axes[2].transAxes,
                 ha='right', va='top',
                 bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8),
                 fontsize=10, family='monospace')

    plt.tight_layout()

    # Sauvegarder
    output_path = Path(mask_path).parent / f"visualization_{Path(mask_path).stem}.png"
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"\n[OK] Visualisation sauvegardee: {output_path}")

    plt.show()


def main():
    if len(sys.argv) < 2:
        print("Usage: python visualize_mask_sample.py <mask.png>")
        sys.exit(1)

    mask_path = sys.argv[1]

    if not Path(mask_path).exists():
        print(f"Erreur: mask introuvable: {mask_path}")
        sys.exit(1)

    visualize_mask(mask_path, sample_size=512)


if __name__ == "__main__":
    main()
