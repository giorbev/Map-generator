# -*- coding: utf-8 -*-
"""
Pipeline Validation — Fonctions métier pures
=============================================

Fonctions extraites de mask_verif.py pour validation masks terrain.
Pas de Tkinter, fonctions pures numpy/cv2 uniquement.

Usage:
    from pipeline_validation import load_masks_from_paths, analyze_conflicts
    result = load_masks_from_paths(file_paths)
    conflicts = analyze_conflicts(result['masks'], threshold=0.15)
"""

import numpy as np
import cv2
from pathlib import Path
import re


# ══════════════════════════════════════════════════════════════════════════════
# 1. LOAD MASKS FROM PATHS
# ══════════════════════════════════════════════════════════════════════════════

def load_masks_from_paths(file_paths):
    """
    Charge masques PNG 16-bit depuis liste de chemins.

    Args:
        file_paths: Liste de chemins vers PNG (str ou Path)

    Returns:
        dict {
            'masks': list of np.ndarray uint16,
            'paths': list of str (chemins valides),
            'shape': tuple (H, W),
            'errors': list of str,
            'warnings': list of str
        }
    """
    loaded_masks = []
    loaded_paths = []
    errors = []
    warnings = []
    ref_shape = None

    for path in file_paths:
        path = str(path)
        mask = _read_png_unicode_safe(path)
        file_name = Path(path).name

        if mask is None:
            errors.append(f"{file_name}: lecture impossible")
            continue

        if mask.ndim != 2:
            errors.append(f"{file_name}: image non mono-canal")
            continue

        # Conversion uint8 -> uint16
        if mask.dtype == np.uint8:
            mask = (mask.astype(np.uint16) * 257)
            warnings.append(f"{file_name}: converti uint8 -> uint16")
        elif mask.dtype != np.uint16:
            errors.append(f"{file_name}: dtype {mask.dtype} (attendu uint16/uint8)")
            continue

        # Vérifier dimensions
        if ref_shape is None:
            ref_shape = mask.shape
        elif mask.shape != ref_shape:
            errors.append(f"{file_name}: dimensions {mask.shape} != {ref_shape}")
            continue

        loaded_masks.append(mask)
        loaded_paths.append(path)

    return {
        'masks': loaded_masks,
        'paths': loaded_paths,
        'shape': ref_shape,
        'errors': errors,
        'warnings': warnings
    }


def _read_png_unicode_safe(path):
    """Lecture PNG robuste Unicode Windows."""
    try:
        png_bytes = np.fromfile(path, dtype=np.uint8)
        if png_bytes.size == 0:
            return None
        return cv2.imdecode(png_bytes, cv2.IMREAD_UNCHANGED)
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
# 2. BUILD CONFLICT STACK
# ══════════════════════════════════════════════════════════════════════════════

def build_conflict_stack(masks, threshold=0.15):
    """
    Construit stack booléen de présence par masque.

    Args:
        masks: Liste de np.ndarray uint16
        threshold: Seuil de présence [0..1] (défaut 0.15 = 15%)

    Returns:
        tuple (stack_bool, threshold)
            stack_bool: np.ndarray shape (N, H, W) dtype bool
            threshold: float seuil utilisé
    """
    # Normaliser seuil
    if threshold > 1.0 and threshold <= 100.0:
        threshold = threshold / 100.0
    threshold = max(0.0, min(1.0, threshold))

    # Stack booléen
    stack = np.stack(
        [(m.astype(np.float32) / 65535.0) > threshold for m in masks],
        axis=0
    )

    return stack, threshold


# ══════════════════════════════════════════════════════════════════════════════
# 3. ANALYZE CONFLICTS
# ══════════════════════════════════════════════════════════════════════════════

def analyze_conflicts(masks, threshold=0.15):
    """
    [DEPRECATED] Analyse pixel par pixel — utiliser analyze_conflicts_qtre() pour métriques QTRE réelles.

    Args:
        masks: Liste de np.ndarray uint16
        threshold: Seuil de présence [0..1]

    Returns:
        dict {
            'overlap_count': np.ndarray uint8 (nombre masques par pixel),
            'conflict_zone': np.ndarray bool (pixels >= 2 masques),
            'conflict_pct': float (% surface en conflit),
            'pair_summary': list of str (top 3 paires),
            'threshold': float,
            'stack': np.ndarray bool (N, H, W)
        }
    """
    import warnings
    warnings.warn(
        "analyze_conflicts() est obsolète. Utiliser analyze_conflicts_qtre() pour métriques QTRE blocs 32m.",
        DeprecationWarning,
        stacklevel=2
    )

    stack, threshold = build_conflict_stack(masks, threshold)
    overlap_count = np.sum(stack, axis=0).astype(np.uint8)
    conflict_zone = overlap_count >= 2

    h, w = masks[0].shape
    conflict_pct = (np.count_nonzero(conflict_zone) / float(h * w)) * 100.0

    # Analyse paires
    pair_stats = []
    n = len(masks)
    for i in range(n):
        for j in range(i + 1, n):
            px = int(np.count_nonzero(stack[i] & stack[j]))
            if px > 0:
                pair_stats.append((px, f"M{i+1} + M{j+1}: {px}px"))

    pair_stats.sort(key=lambda x: x[0], reverse=True)
    pair_summary = [item[1] for item in pair_stats[:3]]

    return {
        'overlap_count': overlap_count,
        'conflict_zone': conflict_zone,
        'conflict_pct': conflict_pct,
        'pair_summary': pair_summary,
        'threshold': threshold,
        'stack': stack
    }


def analyze_conflicts_qtre(masks, cellsize=4.0, threshold=0.05):
    """
    Analyse QTRE par blocs 32m — métrique réelle Reforger.

    Contrainte QTRE : max 4-5 textures par bloc de 32m x 32m.
    - Critique (≥6 tex) : crash ou artefacts Reforger
    - Limite (4-5 tex) : risque selon complexité scène
    - OK (≤3 tex) : sûr

    Args:
        masks: Liste de np.ndarray uint16 ou dict {nom: array}
        cellsize: Résolution m/px (défaut 4.0)
        threshold: Seuil émergence texture 0-1 (défaut 0.05 = 5%)

    Returns:
        dict {
            'heatmap': np.ndarray float32 (nb textures actives par bloc),
            'critical_blocs': int,
            'limit_blocs': int,
            'ok_blocs': int,
            'total_blocs': int,
            'critical_pct': float,
            'limit_pct': float,
            'ok_pct': float,
            'top_pairs': list [(tex_a, tex_b, nb_blocs), ...],
            'verdict': "OK" | "ATTENTION"
        }
    """
    # Normaliser input (dict ou list)
    if isinstance(masks, dict):
        mask_list = list(masks.values())
        mask_names = list(masks.keys())
    else:
        mask_list = masks
        mask_names = [f"M{i+1}" for i in range(len(mask_list))]

    if not mask_list:
        raise ValueError("masks vide")

    shape = mask_list[0].shape
    bloc_px = max(1, int(32.0 / cellsize))
    h_blocs = shape[0] // bloc_px
    w_blocs = shape[1] // bloc_px

    # Normaliser masks en float32 0-1
    normalized = []
    for mask in mask_list:
        if mask.dtype == np.uint16:
            normalized.append(mask.astype(np.float32) / 65535.0)
        elif mask.dtype == np.uint8:
            normalized.append(mask.astype(np.float32) / 255.0)
        else:
            normalized.append(mask.astype(np.float32))

    # Heatmap : compter textures actives par bloc
    heatmap = np.zeros((h_blocs, w_blocs), dtype=np.float32)
    critical = 0
    limit = 0
    ok = 0

    # Tracker co-activations pour top_pairs
    pair_counts = {}

    for y in range(h_blocs):
        for x in range(w_blocs):
            active_textures = []
            for i, mask in enumerate(normalized):
                bloc = mask[y*bloc_px:(y+1)*bloc_px, x*bloc_px:(x+1)*bloc_px]
                if np.mean(bloc) > threshold:
                    active_textures.append(i)

            count = len(active_textures)
            heatmap[y, x] = count

            if count >= 6:
                critical += 1
            elif count >= 4:
                limit += 1
            else:
                ok += 1

            # Enregistrer paires pour blocs critiques
            if count >= 6:
                for i in range(len(active_textures)):
                    for j in range(i + 1, len(active_textures)):
                        idx_a = active_textures[i]
                        idx_b = active_textures[j]
                        pair = (min(idx_a, idx_b), max(idx_a, idx_b))
                        pair_counts[pair] = pair_counts.get(pair, 0) + 1

    total_blocs = h_blocs * w_blocs
    critical_pct = (critical / total_blocs * 100.0) if total_blocs > 0 else 0.0
    limit_pct = (limit / total_blocs * 100.0) if total_blocs > 0 else 0.0
    ok_pct = (ok / total_blocs * 100.0) if total_blocs > 0 else 0.0

    # Top 5 paires
    top_pairs = sorted(pair_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    top_pairs = [
        (mask_names[pair[0]], mask_names[pair[1]], count)
        for pair, count in top_pairs
    ]

    verdict = "OK" if critical_pct < 1.0 else "ATTENTION"

    return {
        'heatmap': heatmap,
        'critical_blocs': critical,
        'limit_blocs': limit,
        'ok_blocs': ok,
        'total_blocs': total_blocs,
        'critical_pct': critical_pct,
        'limit_pct': limit_pct,
        'ok_pct': ok_pct,
        'top_pairs': top_pairs,
        'verdict': verdict
    }


def clean_masks_by_priority(masks, priority_order, cellsize=4.0, threshold=0.05):
    """
    Nettoyage par priorité stricte + normalisation intelligente.

    Sur chaque pixel :
    1. Identifier la texture la plus prioritaire active (> threshold)
    2. Zéroïser toutes les textures moins prioritaires
    3. Normalisation finale pour garantir somme <= 1.0

    Args:
        masks: dict {nom_texture: np.ndarray uint16} ou list
        priority_order: list de noms de textures, du plus prioritaire au moins
        cellsize: Résolution m/px pour stats QTRE (défaut 4.0)
        threshold: Seuil émergence 0-1 (défaut 0.05)

    Returns:
        dict {
            'masks': dict {nom: array uint16} nettoyés,
            'stats': {
                'blocs_avant': dict,
                'blocs_apres': dict,
                'pixels_modifies': int,
                'reduction_critique_pct': float
            }
        }
    """
    # Normaliser input
    if isinstance(masks, dict):
        mask_dict = masks
    else:
        # Si list, utiliser priority_order comme noms
        if len(masks) != len(priority_order):
            raise ValueError("len(masks) doit égaler len(priority_order)")
        mask_dict = {name: mask for name, mask in zip(priority_order, masks)}

    if not mask_dict:
        raise ValueError("masks vide")

    # Vérifier que tous les noms de priority_order existent
    missing = [name for name in priority_order if name not in mask_dict]
    if missing:
        raise ValueError(f"Noms manquants dans masks: {missing}")

    shape = list(mask_dict.values())[0].shape

    # Stats AVANT nettoyage
    stats_avant = analyze_conflicts_qtre(mask_dict, cellsize, threshold)

    # Normaliser en float32 0-1
    masks_f32 = {}
    for name, mask in mask_dict.items():
        if mask.dtype == np.uint16:
            masks_f32[name] = mask.astype(np.float32) / 65535.0
        elif mask.dtype == np.uint8:
            masks_f32[name] = mask.astype(np.float32) / 255.0
        else:
            masks_f32[name] = mask.astype(np.float32)

    # Créer masks nettoyés (copies)
    cleaned_f32 = {name: np.zeros(shape, dtype=np.float32) for name in mask_dict}

    # Pour chaque pixel, identifier texture la plus prioritaire active
    pixels_modified = 0

    for y in range(shape[0]):
        for x in range(shape[1]):
            # Lister textures actives sur ce pixel
            active = []
            for name in priority_order:
                if masks_f32[name][y, x] > threshold:
                    active.append(name)

            if not active:
                # Aucune texture active : conserver état original
                for name in priority_order:
                    cleaned_f32[name][y, x] = masks_f32[name][y, x]
                continue

            # Texture gagnante = la première dans priority_order
            winner = active[0]

            # Compter modification si >1 texture active
            if len(active) > 1:
                pixels_modified += 1

            # Poser seulement la texture gagnante
            for name in priority_order:
                if name == winner:
                    cleaned_f32[name][y, x] = masks_f32[name][y, x]
                else:
                    cleaned_f32[name][y, x] = 0.0

    # Normalisation finale (sécurité)
    total = np.zeros(shape, dtype=np.float32)
    for mask in cleaned_f32.values():
        total += mask

    overflow = total > 1.0
    if np.any(overflow):
        for name in cleaned_f32:
            cleaned_f32[name] = np.where(
                overflow,
                cleaned_f32[name] / (total + 1e-6),
                cleaned_f32[name]
            )

    # Reconvertir en uint16
    cleaned_u16 = {}
    for name, mask_f in cleaned_f32.items():
        cleaned_u16[name] = np.clip(np.round(mask_f * 65535.0), 0, 65535).astype(np.uint16)

    # Stats APRÈS nettoyage
    stats_apres = analyze_conflicts_qtre(cleaned_u16, cellsize, threshold)

    reduction = stats_avant['critical_pct'] - stats_apres['critical_pct']

    return {
        'masks': cleaned_u16,
        'stats': {
            'blocs_avant': {
                'critical': stats_avant['critical_blocs'],
                'limit': stats_avant['limit_blocs'],
                'ok': stats_avant['ok_blocs'],
                'critical_pct': stats_avant['critical_pct']
            },
            'blocs_apres': {
                'critical': stats_apres['critical_blocs'],
                'limit': stats_apres['limit_blocs'],
                'ok': stats_apres['ok_blocs'],
                'critical_pct': stats_apres['critical_pct']
            },
            'pixels_modifies': pixels_modified,
            'reduction_critique_pct': reduction
        }
    }


# ══════════════════════════════════════════════════════════════════════════════
# 4. ASSEMBLE MASKS
# ══════════════════════════════════════════════════════════════════════════════

def assemble_masks(masks, mode='homogeneous', ordered_indices=None):
    """
    Assemble liste de masques en un seul masque uint16.

    Args:
        masks: Liste de np.ndarray uint16
        mode: 'max', 'add', 'homogeneous', 'priority'
        ordered_indices: Liste d'indices pour mode 'priority'

    Returns:
        np.ndarray uint16
    """
    if masks is None or len(masks) < 2:
        raise ValueError("Au moins 2 masques requis")

    ref_shape = masks[0].shape
    normalized_masks = []

    for idx, mask in enumerate(masks):
        if mask.ndim != 2:
            raise ValueError(f"Masque {idx}: non mono-canal")
        if mask.shape != ref_shape:
            raise ValueError(f"Masque {idx}: dimensions != {ref_shape}")

        if mask.dtype == np.uint8:
            normalized_masks.append(mask.astype(np.uint16) * 257)
        elif mask.dtype == np.uint16:
            normalized_masks.append(mask)
        else:
            raise ValueError(f"Masque {idx}: dtype {mask.dtype} non supporté")

    h, w = ref_shape

    if mode == "max":
        assembled = np.zeros((h, w), dtype=np.uint16)
        for mask in normalized_masks:
            assembled = np.maximum(assembled, mask)
        return assembled

    if mode == "add":
        assembled = np.zeros((h, w), dtype=np.uint32)
        for mask in normalized_masks:
            assembled += mask.astype(np.uint32)
        return np.clip(assembled, 0, 65535).astype(np.uint16)

    if mode in ("average", "homogeneous"):
        sum_vals = np.zeros((h, w), dtype=np.float32)
        count = np.zeros((h, w), dtype=np.float32)
        for mask in normalized_masks:
            sum_vals += mask.astype(np.float32)
            count += (mask > 0).astype(np.float32)
        count = np.maximum(count, 1.0)
        return np.round(sum_vals / count).astype(np.uint16)

    if mode == "priority":
        if ordered_indices is None:
            ordered_indices = list(range(len(normalized_masks)))
        if len(ordered_indices) != len(normalized_masks):
            raise ValueError("ordered_indices doit matcher len(masks)")

        assembled = np.zeros((h, w), dtype=np.uint16)
        occupied = np.zeros((h, w), dtype=bool)
        for idx in ordered_indices:
            current = normalized_masks[idx]
            keep = (current > 0) & (~occupied)
            assembled = np.where(keep, current, assembled)
            occupied |= keep
        return assembled

    raise ValueError(f"Mode inconnu: {mode}")


# ══════════════════════════════════════════════════════════════════════════════
# 5. CLEAN MASKS BY ORDER
# ══════════════════════════════════════════════════════════════════════════════

def clean_masks_by_order(masks, paths, blend_mode=True):
    """
    Nettoie superpositions en appliquant ordre de priorité.

    Args:
        masks: Liste de np.ndarray uint16
        paths: Liste de chemins (pour extraction ordre numérique)
        blend_mode: True = fondu gris, False = binaire strict

    Returns:
        list of np.ndarray uint16 (masques nettoyés)
    """
    if len(masks) < 2:
        return None

    # Déterminer ordre
    ordered_indices = _compute_ordered_indices(paths)
    cleaned = [np.zeros_like(mask, dtype=np.uint16) for mask in masks]

    if blend_mode:
        # Fondu enchaîné: répartition opacité progressive
        remaining = np.ones(masks[0].shape, dtype=np.float32)
        for idx in ordered_indices:
            alpha = masks[idx].astype(np.float32) / 65535.0
            contrib = alpha * remaining
            cleaned[idx] = np.clip(np.round(contrib * 65535.0), 0, 65535).astype(np.uint16)
            remaining *= (1.0 - alpha)
        return cleaned

    # Mode binaire strict
    occupied = np.zeros(masks[0].shape, dtype=bool)
    for idx in ordered_indices:
        current = masks[idx]
        keep = (current > 0) & (~occupied)
        cleaned[idx] = np.where(keep, current, 0).astype(np.uint16)
        occupied |= keep

    return cleaned


def _extract_numeric_order(file_path):
    """Extrait premier nombre du nom de fichier."""
    stem = Path(file_path).stem
    match = re.search(r"(\d+)", stem)
    if match:
        return int(match.group(1))
    return 10**9


def _compute_ordered_indices(paths):
    """Calcule indices triés par ordre numérique des noms."""
    indexed_paths = list(enumerate(paths))
    indexed_paths.sort(key=lambda item: (_extract_numeric_order(item[1]), Path(item[1]).stem.lower()))
    return [idx for idx, _ in indexed_paths]


# ══════════════════════════════════════════════════════════════════════════════
# 6. LOAD REFORGER ERRORS
# ══════════════════════════════════════════════════════════════════════════════

def load_reforger_errors(file_paths, target_shape):
    """
    Charge masks erreur Reforger et les combine en un seul bool mask.

    Args:
        file_paths: Liste de chemins PNG
        target_shape: Tuple (H, W) pour resize si besoin

    Returns:
        np.ndarray bool shape (H, W) — combined error mask
    """
    target_h, target_w = target_shape
    loaded_errors = []
    errors = []

    for path in file_paths:
        arr = _read_png_unicode_safe(str(path))
        file_name = Path(path).name

        if arr is None:
            errors.append(f"{file_name}: lecture impossible")
            continue

        # Convertir en grayscale si RGB
        if arr.ndim == 3:
            arr = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)

        # Binariser
        if arr.dtype == np.uint16:
            err_mask = (arr > 0).astype(np.uint8)
        elif arr.dtype == np.uint8:
            err_mask = (arr > 0).astype(np.uint8)
        else:
            errors.append(f"{file_name}: dtype {arr.dtype} non supporté")
            continue

        # Resize si nécessaire
        if err_mask.shape != (target_h, target_w):
            err_mask = cv2.resize(err_mask, (target_w, target_h), interpolation=cv2.INTER_NEAREST)

        loaded_errors.append(err_mask.astype(bool))

    if not loaded_errors:
        return np.zeros(target_shape, dtype=bool)

    # Combiner avec OR
    combined = np.any(np.stack(loaded_errors, axis=0), axis=0)

    return combined


# ══════════════════════════════════════════════════════════════════════════════
# 7. COMPUTE COMBINED HEATMAP
# ══════════════════════════════════════════════════════════════════════════════

def compute_combined_heatmap(masks, reforger_error_mask, threshold=0.15):
    """
    Superpose heatmap QTRE et masks erreur Reforger.

    Rouge = QTRE seul
    Magenta = QTRE + Reforger
    Cyan = Reforger seul

    Args:
        masks: Liste de np.ndarray uint16
        reforger_error_mask: np.ndarray bool
        threshold: Seuil QTRE

    Returns:
        dict {
            'heatmap_rgb': np.ndarray uint8 shape (H, W, 3),
            'qtre_only_px': int,
            'magenta_px': int,
            'cyan_px': int,
            'cyan_mask': np.ndarray bool,
            'overlap_count': np.ndarray uint8
        }
    """
    # Compute QTRE conflict mask
    stack, threshold = build_conflict_stack(masks, threshold)
    overlap_count = np.sum(stack, axis=0).astype(np.uint8)
    qtre_mask = overlap_count >= 2

    # Zones distinctes
    both = qtre_mask & reforger_error_mask
    qtre_only = qtre_mask & (~reforger_error_mask)
    cyan_only = reforger_error_mask & (~qtre_mask)

    # Base: intensité gris selon overlap
    h, w = qtre_mask.shape
    base_intensity = np.clip(
        (overlap_count.astype(np.float32) / max(2, len(masks))) * 80.0,
        0, 80
    ).astype(np.uint8)

    combined = np.stack([base_intensity, base_intensity, base_intensity], axis=-1)

    # Colorier zones
    combined[qtre_only] = np.array([255, 0, 0], dtype=np.uint8)      # Rouge
    combined[cyan_only] = np.array([0, 255, 255], dtype=np.uint8)    # Cyan
    combined[both] = np.array([255, 0, 255], dtype=np.uint8)         # Magenta

    return {
        'heatmap_rgb': combined,
        'qtre_only_px': int(np.count_nonzero(qtre_only)),
        'magenta_px': int(np.count_nonzero(both)),
        'cyan_px': int(np.count_nonzero(cyan_only)),
        'cyan_mask': cyan_only,
        'overlap_count': overlap_count
    }


# ══════════════════════════════════════════════════════════════════════════════
# 8. CORRECT MAGENTA ZONES
# ══════════════════════════════════════════════════════════════════════════════

def correct_magenta_zones(masks, heatmap_rgb):
    """
    Corrige pixels magenta en gardant seulement masque dominant.

    Args:
        masks: Liste de np.ndarray uint16
        heatmap_rgb: np.ndarray uint8 shape (H, W, 3) depuis compute_combined_heatmap

    Returns:
        list of np.ndarray uint16 (masques corrigés)
    """
    # Détecter pixels magenta (R=255, G=0, B=255)
    magenta_mask = (
        (heatmap_rgb[..., 0] == 255)
        & (heatmap_rgb[..., 1] == 0)
        & (heatmap_rgb[..., 2] == 255)
    )

    magenta_count = int(np.count_nonzero(magenta_mask))
    if magenta_count == 0:
        return masks  # Rien à corriger

    # Stack et déterminer dominant
    stack_values = np.stack(masks, axis=0).astype(np.uint16)
    dominant_idx = np.argmax(stack_values, axis=0)
    corrected_stack = stack_values.copy()

    # Sur pixels magenta: supprimer non-dominants
    for idx in range(corrected_stack.shape[0]):
        non_dominant_on_magenta = magenta_mask & (dominant_idx != idx)
        corrected_stack[idx, non_dominant_on_magenta] = 0

    corrected_masks = [corrected_stack[idx] for idx in range(corrected_stack.shape[0])]

    return corrected_masks


# ══════════════════════════════════════════════════════════════════════════════
# 9. EXPORT CYAN COORDS CSV
# ══════════════════════════════════════════════════════════════════════════════

def export_cyan_coords_csv(cyan_mask, meter_per_px):
    """
    Extrait coordonnées zones cyan en mètres.

    Args:
        cyan_mask: np.ndarray bool
        meter_per_px: float (résolution m/px)

    Returns:
        str (contenu CSV avec header)
    """
    cyan_u8 = cyan_mask.astype(np.uint8)
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
        cyan_u8, connectivity=8
    )

    rows = []
    for label_id in range(1, num_labels):
        area_px = int(stats[label_id, cv2.CC_STAT_AREA])
        cx, cy = centroids[label_id]
        x_m = cx * meter_per_px
        y_m = cy * meter_per_px
        rows.append((label_id, area_px, cx, cy, x_m, y_m))

    if not rows:
        return "zone_id,area_px,centroid_x_px,centroid_y_px,centroid_x_m,centroid_y_m\n"

    header = "zone_id,area_px,centroid_x_px,centroid_y_px,centroid_x_m,centroid_y_m"
    lines = [header]
    for zone_id, area_px, cx, cy, x_m, y_m in rows:
        lines.append(f"{zone_id},{area_px},{cx:.2f},{cy:.2f},{x_m:.2f},{y_m:.2f}")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# 10. EXPORT MASKS PNG
# ══════════════════════════════════════════════════════════════════════════════

def export_masks_png(masks, paths, output_dir, suffix='_noconflict'):
    """
    Exporte masques corrigés avec suffixe.

    Args:
        masks: Liste de np.ndarray uint16
        paths: Liste de chemins originaux
        output_dir: Dossier de sortie (str ou Path)
        suffix: Suffixe avant extension (défaut '_noconflict')

    Returns:
        list of str (chemins exportés)
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    saved_paths = []
    for idx, original_path in enumerate(paths):
        original_name = Path(original_path).stem
        ext = Path(original_path).suffix
        out_path = _unique_output_path(output_dir, f"{original_name}{suffix}", ext)

        ok = cv2.imwrite(str(out_path), masks[idx])
        if ok:
            saved_paths.append(str(out_path))

    return saved_paths


def _unique_output_path(output_dir, base_name, suffix):
    """Génère chemin unique sans écraser fichier existant."""
    candidate = Path(output_dir) / f"{base_name}{suffix}"
    if not candidate.exists():
        return candidate

    idx = 1
    while True:
        candidate = Path(output_dir) / f"{base_name}_{idx:02d}{suffix}"
        if not candidate.exists():
            return candidate
        idx += 1


# ══════════════════════════════════════════════════════════════════════════════
# TESTS BASIQUES
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Test 1: load_masks_from_paths
    print("Test 1: load_masks_from_paths")
    result = load_masks_from_paths([])
    assert result['masks'] == []
    assert result['shape'] is None
    print("  [OK] empty list")

    # Test 2: build_conflict_stack
    print("Test 2: build_conflict_stack")
    m1 = np.ones((100, 100), dtype=np.uint16) * 20000
    m2 = np.ones((100, 100), dtype=np.uint16) * 30000
    stack, thresh = build_conflict_stack([m1, m2], threshold=0.15)
    assert stack.shape == (2, 100, 100)
    assert thresh == 0.15
    print("  [OK] stack shape and threshold")

    # Test 3: analyze_conflicts
    print("Test 3: analyze_conflicts")
    conflicts = analyze_conflicts([m1, m2], threshold=0.15)
    assert 'overlap_count' in conflicts
    assert 'conflict_pct' in conflicts
    assert conflicts['overlap_count'].shape == (100, 100)
    print("  [OK] conflict analysis")

    # Test 4: assemble_masks
    print("Test 4: assemble_masks")
    assembled = assemble_masks([m1, m2], mode='max')
    assert assembled.dtype == np.uint16
    assert assembled.shape == (100, 100)
    assert np.max(assembled) == 30000
    print("  [OK] assemble max")

    # Test 5: clean_masks_by_order
    print("Test 5: clean_masks_by_order")
    paths = ["01_test.png", "02_test.png"]
    cleaned = clean_masks_by_order([m1, m2], paths, blend_mode=False)
    assert len(cleaned) == 2
    assert cleaned[0].dtype == np.uint16
    print("  [OK] clean by order")

    # Test 6: load_reforger_errors
    print("Test 6: load_reforger_errors")
    combined_err = load_reforger_errors([], target_shape=(100, 100))
    assert combined_err.shape == (100, 100)
    assert combined_err.dtype == bool
    assert np.sum(combined_err) == 0
    print("  [OK] empty reforger errors")

    # Test 7: compute_combined_heatmap
    print("Test 7: compute_combined_heatmap")
    err_mask = np.zeros((100, 100), dtype=bool)
    err_mask[10:20, 10:20] = True
    heatmap_result = compute_combined_heatmap([m1, m2], err_mask, threshold=0.15)
    assert 'heatmap_rgb' in heatmap_result
    assert heatmap_result['heatmap_rgb'].shape == (100, 100, 3)
    print("  [OK] combined heatmap")

    # Test 8: correct_magenta_zones
    print("Test 8: correct_magenta_zones")
    heatmap = np.zeros((100, 100, 3), dtype=np.uint8)
    heatmap[5:10, 5:10] = [255, 0, 255]  # Magenta
    corrected = correct_magenta_zones([m1, m2], heatmap)
    assert len(corrected) == 2
    print("  [OK] magenta correction")

    # Test 9: export_cyan_coords_csv
    print("Test 9: export_cyan_coords_csv")
    cyan = np.zeros((100, 100), dtype=bool)
    cyan[20:30, 20:30] = True
    csv_content = export_cyan_coords_csv(cyan, meter_per_px=2.0)
    assert "zone_id,area_px" in csv_content
    assert "centroid_x_m,centroid_y_m" in csv_content
    print("  [OK] cyan CSV export")

    # Test 10: export_masks_png (sans I/O réel)
    print("Test 10: export_masks_png signature")
    # Test juste la signature, pas l'I/O
    assert callable(export_masks_png)
    print("  [OK] export function exists")

    print("\n[SUCCESS] Tous les tests passent")
