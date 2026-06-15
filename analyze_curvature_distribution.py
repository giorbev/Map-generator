"""
Analyse Distribution Curvature — ZBK Island
===========================================

Décode le masque curvature 16-bit pour trouver les valeurs réelles
et recommander les meilleurs seuils Instant Terra
"""

import numpy as np
from PIL import Image
import matplotlib.pyplot as plt
from pathlib import Path


def analyze_curvature_distribution(curvature_path, min_curv=-10.0, max_curv=10.0):
    """
    Analyse distribution courbure depuis masque 16-bit Instant Terra

    Args:
        curvature_path: chemin masque PNG
        min_curv: valeur min utilisée dans Instant Terra (défaut -10)
        max_curv: valeur max utilisée dans Instant Terra (défaut +10)
    """
    print("="*70)
    print("ANALYSE DISTRIBUTION CURVATURE")
    print("="*70)

    # Charger masque
    curv_img = Image.open(curvature_path)
    curv_raw = np.array(curv_img, dtype=np.uint16)

    print(f"\nMasque : {Path(curvature_path).name}")
    print(f"Shape  : {curv_raw.shape}")

    # Décoder : [0, 65535] -> [min_curv, max_curv]
    curv_decoded = (curv_raw / 65535.0) * (max_curv - min_curv) + min_curv

    # Stats
    print(f"\n=== STATISTIQUES ===")
    print(f"Raw 16-bit :")
    print(f"  Min  : {curv_raw.min()}")
    print(f"  Max  : {curv_raw.max()}")
    print(f"  Mean : {curv_raw.mean():.0f}")
    print(f"  Med  : {np.median(curv_raw):.0f}")

    print(f"\nValeurs réelles (avec min={min_curv}, max={max_curv}) :")
    print(f"  Min  : {curv_decoded.min():.3f}")
    print(f"  Max  : {curv_decoded.max():.3f}")
    print(f"  Mean : {curv_decoded.mean():.3f}")
    print(f"  Med  : {np.median(curv_decoded):.3f}")

    # Percentiles
    p1, p5, p10, p25, p50, p75, p90, p95, p99 = np.percentile(
        curv_decoded, [1, 5, 10, 25, 50, 75, 90, 95, 99]
    )

    print(f"\n=== PERCENTILES ===")
    print(f"  P1  : {p1:.3f}  (1% plus concave)")
    print(f"  P5  : {p5:.3f}")
    print(f"  P10 : {p10:.3f}")
    print(f"  P25 : {p25:.3f}")
    print(f"  P50 : {p50:.3f}  (médiane)")
    print(f"  P75 : {p75:.3f}")
    print(f"  P90 : {p90:.3f}")
    print(f"  P95 : {p95:.3f}")
    print(f"  P99 : {p99:.3f}  (1% plus convexe)")

    # Distribution concave vs convexe vs plat
    concave = np.sum(curv_decoded < -0.5)
    plat = np.sum((curv_decoded >= -0.5) & (curv_decoded <= 0.5))
    convexe = np.sum(curv_decoded > 0.5)
    total = curv_decoded.size

    print(f"\n=== DISTRIBUTION MORPHOLOGIQUE ===")
    print(f"  Concave (< -0.5) : {concave:8d} pixels ({100*concave/total:5.2f}%)")
    print(f"  Plat (-0.5 à 0.5): {plat:8d} pixels ({100*plat/total:5.2f}%)")
    print(f"  Convexe (> 0.5)  : {convexe:8d} pixels ({100*convexe/total:5.2f}%)")

    # Recommandations seuils
    print(f"\n=== RECOMMANDATIONS SEUILS INSTANT TERRA ===")

    # Seuils optimaux : capturer 99% de la distribution
    optimal_min = p1
    optimal_max = p99

    print(f"\nSeuils actuels  : [{min_curv:.1f}, {max_curv:.1f}]")
    print(f"Seuils optimaux : [{optimal_min:.1f}, {optimal_max:.1f}]")

    if abs(optimal_min - min_curv) > 1 or abs(optimal_max - max_curv) > 1:
        print(f"\n[!] Ajuster les seuils pour capturer toute la plage de courbure")
        print(f"    Nouveau min : {np.floor(optimal_min):.0f}")
        print(f"    Nouveau max : {np.ceil(optimal_max):.0f}")
    else:
        print(f"\n[OK] Seuils actuels sont corrects")

    # Visualisation
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    # Histogramme raw
    axes[0, 0].hist(curv_raw.flatten(), bins=100, color='steelblue', edgecolor='black')
    axes[0, 0].axvline(32768, color='red', linestyle='--', label='Point zéro (32768)')
    axes[0, 0].set_title('Distribution Raw (0-65535)')
    axes[0, 0].set_xlabel('Valeur 16-bit')
    axes[0, 0].set_ylabel('Fréquence')
    axes[0, 0].legend()
    axes[0, 0].grid(alpha=0.3)

    # Histogramme décodé
    axes[0, 1].hist(curv_decoded.flatten(), bins=100, color='green', edgecolor='black')
    axes[0, 1].axvline(0, color='red', linestyle='--', label='Plat (0)')
    axes[0, 1].axvline(-0.5, color='orange', linestyle=':', label='Seuils morpho')
    axes[0, 1].axvline(0.5, color='orange', linestyle=':')
    axes[0, 1].set_title(f'Distribution Décodée ({min_curv} à {max_curv})')
    axes[0, 1].set_xlabel('Courbure')
    axes[0, 1].set_ylabel('Fréquence')
    axes[0, 1].legend()
    axes[0, 1].grid(alpha=0.3)

    # Carte spatiale décodée
    im = axes[1, 0].imshow(curv_decoded, cmap='RdBu_r', vmin=-2, vmax=2)
    axes[1, 0].set_title('Carte Courbure (rouge=convexe, bleu=concave)')
    plt.colorbar(im, ax=axes[1, 0])

    # Box plot
    axes[1, 1].boxplot(curv_decoded.flatten(), vert=True)
    axes[1, 1].axhline(0, color='red', linestyle='--', label='Plat')
    axes[1, 1].set_title('Box Plot Distribution')
    axes[1, 1].set_ylabel('Courbure')
    axes[1, 1].legend()
    axes[1, 1].grid(alpha=0.3)

    plt.tight_layout()

    output_path = Path(curvature_path).parent / 'curvature_analysis.png'
    plt.savefig(output_path, dpi=150)
    print(f"\n[OK] Graphiques sauvegardés : {output_path.name}")

    plt.show()

    return {
        'raw_min': int(curv_raw.min()),
        'raw_max': int(curv_raw.max()),
        'decoded_min': float(curv_decoded.min()),
        'decoded_max': float(curv_decoded.max()),
        'optimal_min': float(np.floor(optimal_min)),
        'optimal_max': float(np.ceil(optimal_max)),
        'percentiles': {
            'p1': float(p1), 'p5': float(p5), 'p10': float(p10),
            'p50': float(p50),
            'p90': float(p90), 'p95': float(p95), 'p99': float(p99)
        }
    }


if __name__ == '__main__':
    curvature_path = r"H:\logiciel perso\Map generator\data\projects\Zbk_island\sources\curvature.png"

    # Analyser avec seuils par défaut
    result = analyze_curvature_distribution(curvature_path, min_curv=-10.0, max_curv=10.0)

    print("\n" + "="*70)
    print("TERMINÉ")
    print("="*70)
