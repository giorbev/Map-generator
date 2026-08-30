"""
QTRE SQUEEZE & ENFORCE — CODE DE RÉFÉRENCE
===========================================

Code extrait de pipeline_core_complex_backup.py
Conservé pour référence / réutilisation future

LIMITE QTRE REFORGER : Max 5-7 textures par bloc 32×32m

SQUEEZE : Réduire nombre textures totales (garder top-N plus dominantes)
ENFORCE : Limiter textures uniques par bloc (max 3-5 par bloc)

SEUIL QTRE : 1/65535 * 128 ≈ 0.00195
-> Une texture est "active" si poids moyen/pixel > 0.00195 (≈ 128/65535)

"""

import numpy as np
import os


# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTES QTRE
# ══════════════════════════════════════════════════════════════════════════════

QTRE_THRESHOLD = 1.0 / 65535.0 * 128.0  # ≈ 0.00195

# Limite Reforger : 5-7 textures par bloc
# Pipeline conservateur : 5 total - 2 réservés (base + fallback) = 3 uniques
REFORGER_BLOCK_LIMIT = 5
BLOCK_UNIQUE_LIMIT = REFORGER_BLOCK_LIMIT - 2  # = 3


# ══════════════════════════════════════════════════════════════════════════════
# SQUEEZE & ENFORCE
# ══════════════════════════════════════════════════════════════════════════════

def squeeze_and_enforce_bands(mmaps: dict, shape: tuple,
                               taille_bloc: int, blocs_cote: int,
                               max_mats: int, max_unique: int,
                               log_fn=None):
    """
    Squeeze (top-max_mats) + Enforce (≤max_unique uniques) en 1 passe par bandes.

    SQUEEZE : Garde seulement top-N textures globalement (ex: top-5)
    ENFORCE : Limite textures uniques par bloc 32×32m (ex: max 3)

    Args:
        mmaps: dict {stem: np.memmap} masques .npy en mode "r+"
        shape: (H, W) dimensions terrain
        taille_bloc: taille bloc en pixels (généralement 64-128)
        blocs_cote: nombre blocs par côté
        max_mats: max textures totales (squeeze, ex: 5)
        max_unique: max textures uniques par bloc (enforce, ex: 3)
        log_fn: fonction log(msg)

    Algorithme:
        1. Parcours par bandes horizontales (séquentiel, évite accès aléatoire)
        2. Pré-screening vectorisé (cumsum) pour détecter blocs violant limite
        3. Pour chaque bloc violant:
           a. SQUEEZE: si > max_mats textures actives -> garder top-max_mats
           b. ENFORCE: si > max_unique uniques -> supprimer plus faibles
           c. Renormalisation stricte (somme = 1.0)
        4. Flush changements sur disque
        5. Passe correction itérative (max 5 itérations) jusqu'à 0 violations

    Performance:
        - Traite 16k×16k en ~2-3 min (256 blocs)
        - Accès séquentiels mmaps (évite random I/O)
        - Pré-screening évite calculs inutiles (blocs propres skip)
    """
    log = log_fn or (lambda m: None)

    stems_list = list(mmaps.keys())
    N = len(stems_list)
    H, W = shape
    stride = taille_bloc - 1

    squeezed_total = 0
    enforced_total = 0

    # Positions colonnes (constantes)
    c0s = (np.arange(blocs_cote) * stride).astype(np.int32)
    c1s = np.minimum(c0s + taille_bloc, W).astype(np.int32)

    log(f"[SQUEEZE+ENFORCE] {blocs_cote} bandes | top-{max_mats} puis ≤{max_unique} uniques/bloc")

    # ── Passe principale (bandes) ────────────────────────────────────────────
    for ci in range(blocs_cote):
        r0 = ci * stride
        r1 = min(r0 + taille_bloc, H)

        # Charger bande (N textures × hauteur_bande × W)
        band = np.empty((N, r1 - r0, W), dtype=np.float32)
        for i, s in enumerate(stems_list):
            band[i] = mmaps[s][r0:r1, :]

        # Pré-screening vectorisé (cumsum)
        col_sum = band.sum(axis=1)  # (N, W)
        cum = np.zeros((N, W + 1), dtype=np.float32)
        np.cumsum(col_sum, axis=1, out=cum[:, 1:])
        w_approx = cum[:, c1s] - cum[:, c0s]  # (N, blocs_cote)
        n_active = (w_approx > QTRE_THRESHOLD * taille_bloc * taille_bloc).sum(axis=0)
        cands = np.where(n_active > max_unique)[0]

        if len(cands) == 0:
            del band
            continue

        # Inclure voisins (overlap 1px entre blocs)
        work_set = np.unique(np.clip(
            np.concatenate([cands, cands - 1, cands + 1]), 0, blocs_cote - 1
        ))

        band_modified = False

        for cj in work_set:
            c0, c1 = int(c0s[cj]), int(c1s[cj])
            bloc_pixels = (r1 - r0) * (c1 - c0)
            weights = band[:, :, c0:c1].sum(axis=(1, 2))
            active = np.where(weights > QTRE_THRESHOLD * bloc_pixels)[0]

            if len(active) <= max_unique:
                continue

            # SQUEEZE: > max_mats -> garder top-max_mats
            if len(active) > max_mats:
                top_local = np.argpartition(weights[active], -max_mats)[-max_mats:]
                top_global = active[top_local]
                keep = np.zeros(N, dtype=bool)
                keep[top_global] = True
                band[:, :, c0:c1][~keep] = 0.0
                weights = band[:, :, c0:c1].sum(axis=(1, 2))
                active = np.where(weights > QTRE_THRESHOLD * bloc_pixels)[0]

                # Renormalisation stricte
                psum = band[:, :, c0:c1].sum(axis=0, keepdims=True)
                band[:, :, c0:c1] = np.where(psum > 0.0, band[:, :, c0:c1] / psum, 0.0)
                squeezed_total += 1
                band_modified = True

            # ENFORCE: > max_unique -> supprimer plus faibles
            if len(active) > max_unique:
                n_remove = len(active) - max_unique
                weakest_local = np.argpartition(weights[active], n_remove)[:n_remove]
                weakest_global = active[weakest_local]
                band[:, :, c0:c1][weakest_global] = 0.0

                # Renormalisation stricte
                psum = band[:, :, c0:c1].sum(axis=0, keepdims=True)
                band[:, :, c0:c1] = np.where(psum > 0.0, band[:, :, c0:c1] / psum, 0.0)
                enforced_total += 1
                band_modified = True

        # Écrire bande si modifiée
        if band_modified:
            for i, s in enumerate(stems_list):
                mmaps[s][r0:r1, :] = band[i]

        del band

    # Flush
    for m in mmaps.values():
        m.flush()

    log(f"[OK] {squeezed_total} blocs squeezed | {enforced_total} blocs enforced")

    # ── Passe correction itérative (jusqu'à 0 violations) ────────────────────
    log("[POST-SQUEEZE] Correction itérative...")

    iteration = 0
    max_iterations = 5

    while iteration < max_iterations:
        iteration += 1
        corrected = 0
        violations = 0

        for bi in range(blocs_cote):
            r0 = bi * stride
            r1 = min(r0 + taille_bloc, H)
            for bj in range(blocs_cote):
                c0 = bj * stride
                c1 = min(c0 + taille_bloc, W)

                bloc_pixels = (r1 - r0) * (c1 - c0)
                weights = np.array([mmaps[s][r0:r1, c0:c1].sum() for s in stems_list])
                active = np.where(weights > QTRE_THRESHOLD * bloc_pixels)[0]

                if len(active) > max_unique:
                    violations += 1

                    # Supprimer plus faibles
                    n_remove = len(active) - max_unique
                    weakest_local = np.argpartition(weights[active], n_remove)[:n_remove]
                    weakest_global = active[weakest_local]

                    for idx in weakest_global:
                        mmaps[stems_list[idx]][r0:r1, c0:c1] = 0.0

                    # Renormaliser
                    bloc_sum = np.zeros((r1 - r0, c1 - c0), dtype=np.float32)
                    for s in stems_list:
                        bloc_sum += mmaps[s][r0:r1, c0:c1]

                    bloc_sum_safe = np.where(bloc_sum > 0.0, bloc_sum, 1.0)
                    for s in stems_list:
                        mmaps[s][r0:r1, c0:c1] /= bloc_sum_safe

                    corrected += 1

        for m in mmaps.values():
            m.flush()

        log(f"[POST-SQUEEZE] Itération {iteration}: {corrected} blocs corrigés, {violations} violations")

        if violations == 0:
            log(f"[POST-SQUEEZE] ✓ 0 violations après {iteration} itération(s)")
            break
    else:
        log(f"[POST-SQUEEZE] ⚠️ {violations} violations restent après {max_iterations} itérations")


# ══════════════════════════════════════════════════════════════════════════════
# VALIDATION
# ══════════════════════════════════════════════════════════════════════════════

def validate_block_unique(mmaps: dict, shape: tuple,
                          taille_bloc: int, blocs_cote: int,
                          max_unique: int):
    """
    Vérifie combien de blocs dépassent limite max_unique textures.

    Returns:
        int: nombre de blocs violant la limite
    """
    stems_list = list(mmaps.keys())
    H, W = shape
    stride = taille_bloc - 1
    violations = 0

    for bi in range(blocs_cote):
        r0 = bi * stride
        r1 = min(r0 + taille_bloc, H)
        for bj in range(blocs_cote):
            c0 = bj * stride
            c1 = min(c0 + taille_bloc, W)

            bloc_pixels = (r1 - r0) * (c1 - c0)
            n_unique = sum(
                1 for s in stems_list
                if mmaps[s][r0:r1, c0:c1].sum() > QTRE_THRESHOLD * bloc_pixels
            )

            if n_unique > max_unique:
                violations += 1

    return violations


# ══════════════════════════════════════════════════════════════════════════════
# NOTES D'UTILISATION
# ══════════════════════════════════════════════════════════════════════════════

"""
EXEMPLE D'UTILISATION:

    # 1. Charger masques .npy en mode r+ (lecture/écriture)
    mmaps = {}
    for stem in ['SeaBed', 'Grass', 'Rock', 'Debris']:
        path = f"masks/{stem}.npy"
        mmaps[stem] = np.load(path, mmap_mode="r+")

    # 2. Squeeze & Enforce
    squeeze_and_enforce_bands(
        mmaps=mmaps,
        shape=(8192, 8192),
        taille_bloc=64,
        blocs_cote=128,
        max_mats=5,        # Top-5 textures globalement
        max_unique=3,      # Max 3 textures par bloc
        log_fn=print
    )

    # 3. Valider (optionnel)
    violations = validate_block_unique(mmaps, (8192, 8192), 64, 128, 3)
    print(f"Violations: {violations}")

    # 4. Cleanup
    for m in mmaps.values():
        m.flush()
    mmaps.clear()

QUAND UTILISER:
    - Avant export PNG final (pour garantir compatibilité Reforger)
    - Après génération masques complexes (curvature, sediment, variations)
    - Si masques générés séparément et superposés

ALTERNATIVE SIMPLE:
    - Soustraction cascade (chaque pixel = 1 texture)
    - Plus simple mais moins de nuances (pas de blending)
"""
