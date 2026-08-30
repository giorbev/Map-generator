"""
pipeline_preview.py — Génération preview masques pipeline
==========================================================

Module standalone pour générer une image composite RGB depuis les masques
normalisés du pipeline et le DEM source.

Usage:
    preview = generate_mask_preview(masques, dem, mask_config, output_size=1024)
    cv2.imwrite("preview.png", cv2.cvtColor(preview, cv2.COLOR_RGB2BGR))
"""

import numpy as np
import cv2
from typing import Dict, List, Tuple


# Couleurs par masque (RGB)
MASK_COLORS = {
    'mask_seabed':           (30,  100, 200),   # bleu
    'mask_coastal':          (210, 180, 80),    # sable
    'mask_rock':             (140, 140, 140),   # gris
    'mask_landes_rocheuses': (180, 120, 60),    # brun
    'mask_flow':             (80,  60,  40),    # terre foncée
    'mask_deposit':          (160, 100, 40),    # terre
    'mask_alpages':          (100, 200, 100),   # vert clair
    'mask_landes_plateau':   (160, 200, 80),    # vert jaune
    'mask_maquis_landes':    (180, 140, 200),   # violet
    'mask_foret_coniferes':  (20,  100, 40),    # vert foncé
    'mask_foret_feuillue':   (40,  140, 60),    # vert moyen
    'mask_prairie_humide':   (80,  180, 80),    # vert
    'mask_prairie_seche':    (120, 160, 60),    # vert olive
}

DEFAULT_COLOR = (200, 200, 200)  # gris clair


def generate_mask_preview(
    masques: Dict[str, np.ndarray],
    dem: np.ndarray,
    cfg: List[Tuple[str, int, Tuple[int, int, int]]],
    output_size: int = 1024
) -> np.ndarray:
    """
    Génère une image composite numpy RGB (output_size x output_size x 3).

    Args:
        masques: Dict {nom_masque: array 2D float32 [0-1]}
        dem: Heightmap 2D float32 (altitude en mètres)
        cfg: Liste [(nom_masque, mat_id, couleur_rgb), ...] — ordre = priorité décroissante
        output_size: Résolution sortie en pixels (défaut 1024)

    Returns:
        Array numpy RGB uint8 (output_size, output_size, 3)

    Processus:
        1. Fond : DEM normalisé en niveaux de gris RGB
        2. Par-dessus : chaque masque coloré semi-transparent (alpha=0.6)
        3. Ordre : cfg inverse (priorité basse→haute) pour blending correct
        4. Retourne canvas RGB uint8
    """
    # ── Étape 1 : Canvas de fond depuis DEM ─────────────────────────────────

    # Redimensionner DEM
    if dem.shape[0] != output_size or dem.shape[1] != output_size:
        dem_resized = cv2.resize(dem, (output_size, output_size), interpolation=cv2.INTER_AREA)
    else:
        dem_resized = dem.copy()

    # Normaliser DEM → [0-255] en gérant les NaN
    dem_valid = dem_resized[~np.isnan(dem_resized)]
    if dem_valid.size > 0:
        dem_min = float(np.nanmin(dem_resized))
        dem_max = float(np.nanmax(dem_resized))
        if dem_max > dem_min:
            dem_norm = (dem_resized - dem_min) / (dem_max - dem_min)
        else:
            dem_norm = np.zeros_like(dem_resized)
    else:
        dem_norm = np.zeros_like(dem_resized)

    # Remplacer NaN par 0
    dem_norm = np.nan_to_num(dem_norm, nan=0.0)

    # Créer canvas RGB en niveaux de gris
    dem_gray = (dem_norm * 255).astype(np.uint8)
    canvas = np.stack([dem_gray, dem_gray, dem_gray], axis=-1)

    # ── Étape 2 : Blending masques par ordre inverse (priorité basse→haute) ─

    # Extraire noms masques depuis cfg (ordre = priorité décroissante)
    mask_names = [name for name, _, _ in cfg if name in masques]

    # Traiter en ordre inverse pour que les masques haute priorité s'affichent dessus
    for mask_name in reversed(mask_names):
        # Récupérer masque
        mask = masques[mask_name]

        # Redimensionner masque
        if mask.shape[0] != output_size or mask.shape[1] != output_size:
            mask_resized = cv2.resize(mask, (output_size, output_size), interpolation=cv2.INTER_AREA)
        else:
            mask_resized = mask.copy()

        # Seuil minimal d'affichage
        threshold = 0.1
        active_pixels = mask_resized > threshold

        if not active_pixels.any():
            continue  # Masque vide, passer au suivant

        # Récupérer couleur du masque
        color_rgb = MASK_COLORS.get(mask_name, DEFAULT_COLOR)

        # Calculer alpha proportionnel à l'intensité du masque
        # Alpha de base = 0.6, modulé par l'intensité [0-1]
        base_alpha = 0.6
        alpha = mask_resized * base_alpha  # (H, W) float32 [0-0.6]

        # Blending : canvas = canvas * (1 - alpha) + color * alpha
        # Vectorisé sur tous les pixels actifs
        for c in range(3):
            canvas[:, :, c] = (
                canvas[:, :, c].astype(np.float32) * (1.0 - alpha) +
                color_rgb[c] * alpha
            ).astype(np.uint8)

    return canvas


def generate_budget_overlay(bloc_map: dict, grid_w: int,
                            num_blk: int, output_size: int = 1024) -> np.ndarray:
    """
    Génère une image de visualisation budget par bloc.

    Couleurs :
    - Vert  (0,200,0)   : total ≤ 5
    - Jaune (200,200,0) : total == 6
    - Rouge (200,0,0)   : total > 6
    - Gris  (100,100,100) : bloc vide (n_active == 0)

    Retourne array numpy RGB uint8 (output_size × output_size)
    """
    blocs_per_axis = grid_w * num_blk
    px_per_bloc = max(1, output_size // blocs_per_axis)
    img_size = blocs_per_axis * px_per_bloc

    canvas = np.zeros((img_size, img_size, 3), dtype=np.uint8)

    for (bx, by), info in bloc_map.items():
        total = info.get('total', 0)
        n_active = info.get('n_active', 0)

        if n_active == 0:
            color = (100, 100, 100)  # gris
        elif total > 6:
            color = (200, 0, 0)      # rouge
        elif total == 6:
            color = (200, 200, 0)    # jaune
        else:
            color = (0, 200, 0)      # vert

        # Coordonnées pixel (origine haut-gauche)
        py = (blocs_per_axis - 1 - by) * px_per_bloc
        px = bx * px_per_bloc
        canvas[py:py+px_per_bloc, px:px+px_per_bloc] = color

    # Redimensionner à output_size
    if img_size != output_size:
        canvas = cv2.resize(canvas, (output_size, output_size),
                           interpolation=cv2.INTER_NEAREST)

    return canvas
