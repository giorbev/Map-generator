"""
Sauvegarde du correctif QTRE issu de pipeline_v2.py (archivé le 2026-07-08).

Contexte : pipeline_v2.py (génération slope/curvature/etc. depuis heightmap)
a été jugé obsolète et retiré de app.py au profit des masques Gaea.
Cette partie du code — analyse du budget QTRE par bloc 32x32m — reste utile
et est conservée ici en attendant la refonte de la génération terrain.

Original : pipeline_v2.py, fonction check_qtre() (lignes ~1355-1429).
Voir aussi pipeline_v2.py lignes ~1103-1120 (normalisation post-feathering,
qui évite les conflits QTRE en amont — non extraite ici, voir historique git
sur pipeline_v2.py pour le contexte complet si besoin de la réintégrer).
"""

import numpy as np


def safe_print(*args, **kwargs):
    print(*args, **kwargs)


def check_qtre(masks, cellsize, presence_threshold=0.05):
    """
    Analyse budget QTRE par bloc 32x32m
    """
    safe_print("[16/16] Analyse budget QTRE...")

    # Taille bloc en pixels
    bloc_px = int(32 / cellsize)

    # Dimensions
    first_mask = next(iter(masks.values()))
    H, W = first_mask.shape

    n_blocs_y = H // bloc_px
    n_blocs_x = W // bloc_px
    total_blocs = n_blocs_y * n_blocs_x

    safe_print(f"  Bloc: {bloc_px}x{bloc_px}px (32m)")
    safe_print(f"  Grille: {n_blocs_y}x{n_blocs_x} = {total_blocs} blocs")

    # Heatmap densité
    density_map = np.zeros((n_blocs_y, n_blocs_x), dtype=np.uint8)

    # Analyser chaque bloc
    for by in range(n_blocs_y):
        for bx in range(n_blocs_x):
            y0 = by * bloc_px
            x0 = bx * bloc_px
            y1 = y0 + bloc_px
            x1 = x0 + bloc_px

            active_count = 0
            for name, mask in masks.items():
                if name == '01_seabed':
                    continue

                bloc = mask[y0:y1, x0:x1]
                if np.mean(bloc) > presence_threshold:
                    active_count += 1

            density_map[by, bx] = active_count

    # Distribution
    distribution = {}
    for density in range(0, np.max(density_map) + 1):
        count = np.sum(density_map == density)
        pct = count / total_blocs * 100
        distribution[density] = {'count': count, 'pct': pct}

    safe_print(f"\n  Distribution:")
    for density in sorted(distribution.keys()):
        info = distribution[density]
        status = "[OK]" if density <= 3 else "[LIMITE]" if density <= 5 else "[CRITIQUE]"
        safe_print(f"    {density} tex/bloc: {info['count']:6} blocs ({info['pct']:5.2f}%) {status}")

    # Verdict
    blocs_ok = sum(d['count'] for k, d in distribution.items() if k <= 3)
    blocs_limite = sum(d['count'] for k, d in distribution.items() if 4 <= k <= 5)
    blocs_critique = sum(d['count'] for k, d in distribution.items() if k >= 6)

    pct_ok = blocs_ok / total_blocs * 100
    pct_critique = blocs_critique / total_blocs * 100

    verdict = "OK" if pct_ok >= 85 and pct_critique < 1 else "ATTENTION" if pct_ok >= 70 else "CRITIQUE"

    safe_print(f"\n  Budget QTRE:")
    safe_print(f"    OK (<=3):      {blocs_ok:6} ({pct_ok:.2f}%)")
    safe_print(f"    Limite (4-5):  {blocs_limite:6} ({blocs_limite/total_blocs*100:.2f}%)")
    safe_print(f"    Critique (6+): {blocs_critique:6} ({pct_critique:.2f}%)")
    safe_print(f"    -> Verdict: {verdict}")

    return density_map, distribution, verdict
