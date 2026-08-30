"""
Analyse QTRE — 11 Masks Continus
=================================

Analyse la conformité QTRE (Reforger) des masks générés
Limite Reforger : Max 4-5 textures uniques par bloc 32×32m

Génère :
- Rapport texte détaillé
- Heatmap violations
- Stats par texture
"""

import numpy as np
from PIL import Image
from pathlib import Path
import matplotlib.pyplot as plt
import sys


# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTES QTRE
# ══════════════════════════════════════════════════════════════════════════════

QTRE_THRESHOLD = 1.0 / 65535.0 * 128.0  # ≈ 0.00195 (seuil émergence texture)
REFORGER_BLOCK_LIMIT = 5  # Limite Reforger : 5 textures max/bloc
BLOCK_SIZE_M = 32  # Taille bloc Reforger en mètres


def load_masks(folder):
    """
    Charge tous les masks PNG 16-bit d'un dossier

    Args:
        folder: Path dossier masks

    Returns:
        dict: {name: array_float32}
    """
    masks = {}
    mask_files = sorted(folder.glob("*.png"))

    print(f"Chargement {len(mask_files)} masks...")

    for mask_file in mask_files:
        # Charger PNG 16-bit
        mask_uint16 = np.array(Image.open(mask_file), dtype=np.uint16)

        # Convertir en float32 [0.0-1.0]
        mask_float = mask_uint16.astype(np.float32) / 65535.0

        # Extraire nom sans extension
        name = mask_file.stem

        masks[name] = mask_float
        print(f"  [OK] {name}: {mask_float.shape[0]}x{mask_float.shape[1]}")

    return masks


def analyze_qtre_compliance(masks, cellsize=4.0, block_limit=REFORGER_BLOCK_LIMIT):
    """
    Analyse conformité QTRE bloc par bloc

    Args:
        masks: dict {name: array_float32}
        cellsize: résolution m/px
        block_limit: nombre max textures/bloc

    Returns:
        dict: résultats analyse
    """
    print(f"\n{'='*80}")
    print("ANALYSE QTRE")
    print(f"{'='*80}")

    # Dimensions terrain
    first_mask = next(iter(masks.values()))
    H, W = first_mask.shape

    # Calculer taille bloc en pixels
    block_size_px = int(BLOCK_SIZE_M / cellsize)
    blocks_x = (W + block_size_px - 1) // block_size_px
    blocks_y = (H + block_size_px - 1) // block_size_px

    print(f"\nTerrain:")
    print(f"  Resolution: {H}x{W} px")
    print(f"  Cellsize: {cellsize}m/px")
    print(f"  Taille totale: {W*cellsize/1000:.1f}km x {H*cellsize/1000:.1f}km")

    print(f"\nBlocs QTRE:")
    print(f"  Taille bloc: {BLOCK_SIZE_M}m ({block_size_px}px)")
    print(f"  Grille blocs: {blocks_x} x {blocks_y} = {blocks_x*blocks_y} blocs")
    print(f"  Limite Reforger: {block_limit} textures/bloc max")

    # Préparer heatmap violations
    heatmap = np.zeros((blocks_y, blocks_x), dtype=np.int32)

    # Préparer stats par texture
    texture_stats = {name: {
        'coverage_global': 0.0,
        'blocks_active': 0,
        'blocks_dominant': 0,
        'avg_weight': 0.0
    } for name in masks.keys()}

    # Liste textures
    mask_names = list(masks.keys())
    N = len(mask_names)

    print(f"\nAnalyse {blocks_x*blocks_y} blocs...")

    violations = []
    total_blocks = 0

    # Parcourir grille blocs
    for by in range(blocks_y):
        for bx in range(blocks_x):
            # Coordonnées bloc
            x0 = bx * block_size_px
            y0 = by * block_size_px
            x1 = min(x0 + block_size_px, W)
            y1 = min(y0 + block_size_px, H)

            # Extraire bloc pour chaque texture
            block_weights = []
            active_textures = []

            for name in mask_names:
                # Extraire bloc
                block = masks[name][y0:y1, x0:x1]

                # Poids moyen dans le bloc
                mean_weight = np.mean(block)

                block_weights.append(mean_weight)

                # Texture active si > seuil QTRE
                if mean_weight > QTRE_THRESHOLD:
                    active_textures.append((name, mean_weight))

                    # Stats texture
                    texture_stats[name]['blocks_active'] += 1

            # Nombre textures actives
            num_active = len(active_textures)
            heatmap[by, bx] = num_active

            # Détection violation
            if num_active > block_limit:
                violations.append({
                    'bx': bx,
                    'by': by,
                    'num_active': num_active,
                    'textures': active_textures
                })

            # Texture dominante
            if active_textures:
                dominant = max(active_textures, key=lambda x: x[1])
                texture_stats[dominant[0]]['blocks_dominant'] += 1

            total_blocks += 1

    # Stats globales par texture
    for name in mask_names:
        mask = masks[name]
        texture_stats[name]['coverage_global'] = np.mean(mask) * 100
        texture_stats[name]['avg_weight'] = np.mean(mask[mask > 0]) if np.any(mask > 0) else 0.0

    # Résumé
    num_violations = len(violations)
    violation_pct = num_violations / total_blocks * 100

    print(f"\n{'='*80}")
    print("RESULTATS")
    print(f"{'='*80}")
    print(f"\nBlocs totaux: {total_blocks}")
    print(f"Blocs conformes: {total_blocks - num_violations} ({(100-violation_pct):.2f}%)")
    print(f"Blocs violant limite: {num_violations} ({violation_pct:.2f}%)")

    if num_violations > 0:
        print(f"\n[WARNING] {num_violations} blocs depassent la limite de {block_limit} textures !")
    else:
        print(f"\n[OK] Tous les blocs respectent la limite de {block_limit} textures")

    return {
        'blocks_x': blocks_x,
        'blocks_y': blocks_y,
        'total_blocks': total_blocks,
        'violations': violations,
        'num_violations': num_violations,
        'violation_pct': violation_pct,
        'heatmap': heatmap,
        'texture_stats': texture_stats,
        'block_limit': block_limit
    }


def print_texture_stats(texture_stats):
    """
    Affiche stats détaillées par texture

    Args:
        texture_stats: dict stats
    """
    print(f"\n{'='*80}")
    print("STATISTIQUES PAR TEXTURE")
    print(f"{'='*80}\n")

    # Trier par couverture globale décroissante
    sorted_textures = sorted(texture_stats.items(), key=lambda x: x[1]['coverage_global'], reverse=True)

    print(f"{'Texture':<35} {'Couv%':<8} {'Blocs Act.':<12} {'Blocs Dom.':<12} {'Poids Moy.':<12}")
    print("-" * 80)

    for name, stats in sorted_textures:
        print(f"{name:<35} "
              f"{stats['coverage_global']:<8.2f} "
              f"{stats['blocks_active']:<12} "
              f"{stats['blocks_dominant']:<12} "
              f"{stats['avg_weight']:<12.3f}")

    print("-" * 80)


def print_violations_detail(violations, max_show=10):
    """
    Affiche détails violations

    Args:
        violations: list violations
        max_show: nombre max violations à afficher
    """
    if not violations:
        return

    print(f"\n{'='*80}")
    print(f"DETAIL VIOLATIONS (top {min(len(violations), max_show)})")
    print(f"{'='*80}\n")

    # Trier par nombre textures actives décroissant
    sorted_viol = sorted(violations, key=lambda x: x['num_active'], reverse=True)

    for i, viol in enumerate(sorted_viol[:max_show]):
        print(f"Bloc [{viol['bx']}, {viol['by']}] : {viol['num_active']} textures actives")
        print(f"  Textures:")
        for tex_name, weight in sorted(viol['textures'], key=lambda x: x[1], reverse=True):
            print(f"    - {tex_name}: {weight:.4f}")
        print()


def generate_heatmap(heatmap, output_path, block_limit):
    """
    Génère heatmap violations

    Args:
        heatmap: array 2D nombre textures par bloc
        output_path: chemin sortie PNG
        block_limit: limite QTRE
    """
    print(f"\nGeneration heatmap: {output_path}")

    fig, ax = plt.subplots(figsize=(12, 10))

    # Heatmap
    im = ax.imshow(heatmap, cmap='RdYlGn_r', vmin=0, vmax=block_limit+2, interpolation='nearest')

    ax.set_title(f'QTRE Heatmap — Nombre Textures par Bloc ({BLOCK_SIZE_M}m)\nLimite Reforger: {block_limit} textures/bloc',
                 fontsize=14, fontweight='bold')
    ax.set_xlabel('Blocs X')
    ax.set_ylabel('Blocs Y')

    # Colorbar
    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label('Nombre textures actives', rotation=270, labelpad=20)

    # Ligne limite
    cbar.ax.axhline(block_limit, color='red', linestyle='--', linewidth=2, label=f'Limite={block_limit}')

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"  [OK] {output_path}")

    plt.close()


def save_report(results, output_path):
    """
    Sauvegarde rapport texte

    Args:
        results: dict résultats
        output_path: chemin fichier .txt
    """
    print(f"\nGeneration rapport: {output_path}")

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("="*80 + "\n")
        f.write("RAPPORT ANALYSE QTRE — 11 Masks Continus\n")
        f.write("="*80 + "\n\n")

        # Résumé
        f.write("RESUME\n")
        f.write("-"*80 + "\n")
        f.write(f"Blocs totaux: {results['total_blocks']}\n")
        f.write(f"Blocs conformes: {results['total_blocks'] - results['num_violations']} "
                f"({100 - results['violation_pct']:.2f}%)\n")
        f.write(f"Blocs violant limite: {results['num_violations']} ({results['violation_pct']:.2f}%)\n")
        f.write(f"Limite Reforger: {results['block_limit']} textures/bloc\n\n")

        # Stats par texture
        f.write("="*80 + "\n")
        f.write("STATISTIQUES PAR TEXTURE\n")
        f.write("="*80 + "\n\n")

        sorted_textures = sorted(results['texture_stats'].items(),
                                 key=lambda x: x[1]['coverage_global'], reverse=True)

        f.write(f"{'Texture':<35} {'Couv%':<8} {'Blocs Act.':<12} {'Blocs Dom.':<12} {'Poids Moy.':<12}\n")
        f.write("-"*80 + "\n")

        for name, stats in sorted_textures:
            f.write(f"{name:<35} "
                    f"{stats['coverage_global']:<8.2f} "
                    f"{stats['blocks_active']:<12} "
                    f"{stats['blocks_dominant']:<12} "
                    f"{stats['avg_weight']:<12.3f}\n")

        # Violations détaillées
        if results['violations']:
            f.write("\n" + "="*80 + "\n")
            f.write("DETAIL VIOLATIONS\n")
            f.write("="*80 + "\n\n")

            sorted_viol = sorted(results['violations'], key=lambda x: x['num_active'], reverse=True)

            for viol in sorted_viol:
                f.write(f"Bloc [{viol['bx']}, {viol['by']}] : {viol['num_active']} textures actives\n")
                f.write(f"  Textures:\n")
                for tex_name, weight in sorted(viol['textures'], key=lambda x: x[1], reverse=True):
                    f.write(f"    - {tex_name}: {weight:.4f}\n")
                f.write("\n")

    print(f"  [OK] {output_path}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python qtre_analyze_11masks.py <folder_masks> [cellsize_m]")
        print("")
        print("Exemple:")
        print("  python qtre_analyze_11masks.py data/projects/Zimnitrita/pipeline_11masks_20260611_173326 4.0")
        sys.exit(1)

    folder = Path(sys.argv[1])
    cellsize = float(sys.argv[2]) if len(sys.argv) > 2 else 4.0

    if not folder.exists():
        print(f"Erreur: dossier introuvable: {folder}")
        sys.exit(1)

    print("="*80)
    print("ANALYSE QTRE — 11 Masks Continus")
    print("="*80)
    print(f"\nDossier: {folder}")
    print(f"Cellsize: {cellsize}m/px\n")

    # 1. Charger masks
    masks = load_masks(folder)

    if not masks:
        print("Erreur: aucun mask PNG trouve")
        sys.exit(1)

    # 2. Analyser conformité QTRE
    results = analyze_qtre_compliance(masks, cellsize=cellsize)

    # 3. Afficher stats textures
    print_texture_stats(results['texture_stats'])

    # 4. Afficher violations
    print_violations_detail(results['violations'], max_show=20)

    # 5. Générer heatmap
    heatmap_path = folder / "qtre_heatmap.png"
    generate_heatmap(results['heatmap'], heatmap_path, results['block_limit'])

    # 6. Sauvegarder rapport
    report_path = folder / "qtre_report.txt"
    save_report(results, report_path)

    print("\n" + "="*80)
    print("[OK] Analyse QTRE terminee")
    print("="*80)
    print(f"\nFichiers generes:")
    print(f"  - {heatmap_path}")
    print(f"  - {report_path}")


if __name__ == "__main__":
    main()
