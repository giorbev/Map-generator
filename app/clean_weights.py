"""
Clean Weights - Module en lecture seule pour l'onglet Corrections

Modes d'analyse disponibles (appelés depuis l'application) :
1. mode_scan       : Scan rapide, liste tiles avec slots négligeables
2. mode_inspect    : Image debug 800×800 avec rendu texturé
3. mode_validate   : Valider la cohérence d'une tile
4. mode_weights    : Afficher les poids réels (0-31) par matériau
5. mode_scan_zone  : Scanner les blocs Zone B et lister résidus

Note : Les modes d'écriture ont été retirés à l'étape 4c (archivés hors dépôt).
"""

import struct
import numpy as np
import cv2
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# Import modules terrain
from edds_decoder import decode_edds_layer, extract_all_weights
from catalog_config import get_catalog_path
from satmap_v2_textured_v2 import load_catalog, sample_middle_tiled, get_material_middle as satmap_material_middle


# ============================================================================
# UTILITAIRES LECTURE/ÉCRITURE
# ============================================================================

_LRS2_SHIFT_LOGGED = set()  # Track (grid_w, num_blk) déjà loggés

def compute_lrs2_shift(grid_w: int, num_blk: int) -> int:
    """
    Calcule le shift pour décoder les index LRS2.

    Index LRS2 = (by_global << shift) | bx_global
    shift = log2(grid_w × num_blk)

    Exemples :
    - 32 tuiles × 4 = 128 -> shift = 7
    - 64 tuiles × 4 = 256 -> shift = 8
    """
    total_blocs = grid_w * num_blk
    shift = total_blocs.bit_length() - 1

    # Log une seule fois par combinaison (grid_w, num_blk)
    key = (grid_w, num_blk)
    if key not in _LRS2_SHIFT_LOGGED:
        print(f"[LRS2] grid_w={grid_w}, num_blk={num_blk} -> total_blocs={total_blocs}, shift={shift}")
        _LRS2_SHIFT_LOGGED.add(key)

    return shift

def read_lrs2_from_ttile(ttile_path: Path, grid_w: int = 32, num_blk: int = 4) -> Optional[Dict[Tuple[int, int], List[int]]]:
    """Lit le chunk LRS2 d'un .ttile."""
    if not ttile_path.exists():
        return None

    shift = compute_lrs2_shift(grid_w, num_blk)
    mask = (1 << shift) - 1

    try:
        data = ttile_path.read_bytes()
        lrs2_offset = data.find(b'LRS2')
        if lrs2_offset == -1:
            return None

        chunk_size = struct.unpack_from('>I', data, lrs2_offset + 4)[0]
        lrs2_data = data[lrs2_offset + 8:lrs2_offset + 8 + chunk_size]

        blocks = {}
        pos = 0

        while pos < len(lrs2_data):
            if pos + 6 > len(lrs2_data):
                break

            index = struct.unpack_from('<I', lrs2_data, pos)[0]
            count = struct.unpack_from('<H', lrs2_data, pos + 4)[0]

            if count == 0 or count > 7:
                break

            mat_ids = list(struct.unpack_from(f'<{count}H', lrs2_data, pos + 6))

            # Extraire coordonnées locales (0-3, 0-3)
            bx_global = index & mask
            by_global = (index >> shift) & mask
            bx_local = bx_global % num_blk
            by_local = by_global % num_blk

            # Stocker (local, local, index_original) pour préserver l'index LRS2
            blocks[(bx_local, by_local)] = (mat_ids, index)
            pos += 6 + count * 2

        return blocks

    except Exception:
        return None



def find_layer_path(tile_id: int, data_dir: Path, editor_data_dir: Path, tile_prefix: str) -> Optional[Path]:
    """
    Cherche le fichier layer dans le bon ordre :
    1. .Data/<prefix>XXX_layer.edds  (Workbench natif, priorité max)
    2. .EditorData/<prefix>XXX_layer.edds
    3. .EditorData/<prefix>XXX_layer.dds
    """
    candidates = [
        data_dir / f"{tile_prefix}{tile_id}_layer.edds",
        editor_data_dir / f"{tile_prefix}{tile_id}_layer.edds",
        editor_data_dir / f"{tile_prefix}{tile_id}_layer.dds",
    ]
    for p in candidates:
        if p.exists():
            print(f"[LAYER] {p}")
            return p
    # Log tentatives si rien trouvé
    print(f"[WARN] Layer introuvable pour tile_id={tile_id}, tentatives :")
    for p in candidates:
        print(f"  - {p}")
    return None

def read_layer_dds(layer_path: Path) -> Optional[np.ndarray]:
    """
    Lit le _layer.dds et retourne un array de poids [512, 512, 7].

    Returns:
        Array float32 [512, 512, 7] avec poids w0-w6 normalisés [0..1]
    """
    if not layer_path.exists():
        return None

    try:
        decoded = decode_edds_layer(layer_path)
        if decoded is None:
            return None

        # extract_all_weights retourne déjà des poids normalisés [0..1]
        weights = extract_all_weights(decoded)

        return weights

    except Exception:
        return None


def calculate_lrs2_coords(tx: int, ty: int, bx: int, by: int, num_blk: int) -> Tuple[int, int]:
    """Calcule les coordonnées LRS2 globales d'un bloc (num_blk = blocs par tuile et par côté)."""
    lrs_x = tx * num_blk + bx
    lrs_y = ty * num_blk + by
    return lrs_x, lrs_y


def analyze_block_weights(
    pixels: np.ndarray,
    bx: int, by: int,
    num_mats: int,
    threshold: float
) -> List[Tuple[int, float]]:
    """
    Analyse les poids d'un bloc et retourne les slots négligeables.

    ALIGNÉ SUR mode_inspect : itère sur colonnes 0..num_mats-1 du _layer.dds.
    Structure _layer.dds : colonnes 0-6 = w0-w6, correspondant à mat_ids[0-6] du LRS2.

    Returns:
        Liste de (slot_index, coverage_pct) où slot_index=0 → mat_ids[0], etc.
    """
    x0 = bx * 128
    y0 = by * 128
    block_pixels = pixels[y0:y0+128, x0:x0+128, :]

    pixel_count = 128 * 128  # 16384 cellules par bloc
    actual_slots = block_pixels.shape[2]  # nombre réel de colonnes disponibles

    negligible = []
    # Les matériaux du LRS2 sont dans les colonnes 0..num_mats-1 du _layer.dds
    # Pour cohérence avec mode_inspect (L.572, 589)
    for slot_index in range(num_mats):
        if slot_index >= actual_slots:
            break
        # Coverage : pourcentage de pixels où le matériau est présent (weight > 0)
        coverage = (block_pixels[:, :, slot_index] > 0).sum() / pixel_count
        if coverage < threshold:
            negligible.append((slot_index, coverage))

    return negligible


# ============================================================================
# MODE 1: SCAN
# ============================================================================

def extract_tile_id(filename: str, tile_prefix: str) -> Optional[int]:
    """
    Extrait le tile_id depuis un nom de fichier.

    Supporte :
    - Fichiers _layer : "<préfixe>65_layer.edds"
    - Fichiers .ttile : "<préfixe>65.ttile"

    Args:
        filename: Nom du fichier (avec ou sans extension)
        tile_prefix: Préfixe des tuiles (fourni par project_reader.get_tile_prefix())

    Returns:
        tile_id (int) ou None si extraction échoue
    """
    import re
    # Pattern : ^<prefix>(\d+)(_layer)?\. (optionnel _layer, puis extension)
    pattern = rf"^{re.escape(tile_prefix)}(\d+)(_layer)?\."
    match = re.match(pattern, filename)
    if match:
        return int(match.group(1))
    return None

def mode_scan(data_dir: Path, editor_data_dir: Path, threshold: float, grid_w: int, num_blk: int, tile_prefix: str):
    """
    Scan rapide de toutes les tiles.
    Affiche uniquement les tiles avec au moins 1 slot négligeable.
    """
    print("=" * 80)
    print("MODE SCAN - Détection slots négligeables")
    print("=" * 80)
    print(f"Seuil coverage: {threshold*100:.1f}% des pixels")
    print()

    # Scanner tous les _layer.dds
    # Chercher les layer dans data_dir (priorité) ET editor_data_dir
    print(f"[SCAN] Motif recherche : {tile_prefix}*_layer.*")
    print(f"[SCAN] Dossier data_dir : {data_dir}")
    print(f"[SCAN] Dossier editor_dir : {editor_data_dir}")

    seen_ids = set()
    layer_files = []
    ignored_files = []
    for pattern_dir in [data_dir, editor_data_dir]:
        matches = list(pattern_dir.glob(f"{tile_prefix}*_layer.*"))
        print(f"[SCAN] {len(matches)} fichiers trouvés dans {pattern_dir.name}")
        for f in sorted(matches):
            if f.suffix not in ('.dds', '.edds'): continue
            if '.bak' in f.name: continue
            # Extraire tile_id pour dédupliquer
            tid = extract_tile_id(f.name, tile_prefix)
            if tid is None:
                ignored_files.append(f.name)
                continue
            if tid not in seen_ids:
                seen_ids.add(tid)
                layer_files.append(f)
    layer_files = sorted(layer_files, key=lambda f: extract_tile_id(f.name, tile_prefix) or 0)

    print(f"[SCAN] {len(layer_files)} tiles à analyser (après déduplication)")
    if ignored_files:
        print(f"[SCAN] {len(ignored_files)} fichiers ignorés (id non extrait)")
        for fname in ignored_files[:3]:
            print(f"  - {fname}")
        if len(ignored_files) > 3:
            print(f"  ... et {len(ignored_files) - 3} autres")

    if not layer_files:
        print("[ERR] Aucun _layer trouvé")
        print(f"[DEBUG] Vérifiez que {data_dir} et {editor_data_dir} existent")
        print(f"[DEBUG] Vérifiez que tile_prefix='{tile_prefix}' est correct")
        return 1

    tiles_with_slots = []  # [(tx, ty, nb_slots)]
    total_slots = 0

    print(f"[SCAN] {len(layer_files)} tiles à analyser...")
    print()

    for layer_path in layer_files:
        # Extraire tile_id
        tile_id = extract_tile_id(layer_path.name, tile_prefix)
        if tile_id is None:
            continue
        tx = tile_id % grid_w
        ty = tile_id // grid_w

        # Lire LRS2
        ttile_path = data_dir / f"{tile_prefix}{tile_id}.ttile"
        lrs2_blocks = read_lrs2_from_ttile(ttile_path, grid_w, num_blk)
        if lrs2_blocks is None:
            continue

        # Lire layer.dds
        pixels = read_layer_dds(layer_path)
        if pixels is None:
            continue

        # Analyser chaque bloc
        tile_slots = 0
        for (bx, by), (mat_ids, orig_index) in lrs2_blocks.items():
            num_mats = len(mat_ids)
            if num_mats == 0:
                continue

            negligible = analyze_block_weights(pixels, bx, by, num_mats, threshold)
            tile_slots += len(negligible)

        if tile_slots > 0:
            tiles_with_slots.append((tx, ty, tile_slots))
            total_slots += tile_slots

    # Affichage résultats
    if not tiles_with_slots:
        print("[OK] Aucun slot négligeable trouvé")
        return 0

    # Trier par nombre de slots décroissant
    sorted_tiles = sorted(tiles_with_slots, key=lambda x: -x[2])
    max_tile = sorted_tiles[0]  # Tuile avec le plus de slots

    # RÉSUMÉ EN PREMIER
    print("=" * 80)
    print(f"Total : {len(tiles_with_slots)} tuiles, {total_slots} slots — max {max_tile[2]} slots/tuile (tuile {max_tile[0]},{max_tile[1]})")
    print("=" * 80)
    print()

    # TOP 20
    print(f"Top 20 tuiles (seuil {threshold:.2f}/31) :")
    print()
    for tx, ty, nb_slots in sorted_tiles[:20]:
        print(f"  ({tx:2d},{ty:2d}) : {nb_slots} slots négligeables")

    # LISTE COMPLÈTE
    if len(sorted_tiles) > 20:
        print()
        print(f"Liste complète ({len(sorted_tiles)} tuiles) :")
        print()
        for tx, ty, nb_slots in sorted_tiles:
            print(f"  ({tx:2d},{ty:2d}) : {nb_slots} slots négligeables")

    return 0


# ============================================================================
# MODE 2: INSPECT
# ============================================================================

def mode_inspect(
    tx: int, ty: int,
    data_dir: Path,
    editor_data_dir: Path,
    surfaces: List[str],
    threshold: float,
    grid_w: int,
    num_blk: int,
    tile_prefix: str,
    output_dir: Path,
    tile_size_m: float
):
    """
    Génère une image 800×800 de la tile avec:
    - Fond = rendu texturé comme la satmap (middles teintés, échelle tile_size_m), ou noir si catalogue absent
    - Coordonnées LRS2 + liste matériaux avec %
    - Matériaux < threshold en rouge
    - Matériaux > 50% en vert
    """
    print("=" * 80)
    print(f"MODE INSPECT - Tile ({tx},{ty})")
    print("=" * 80)
    print(f"Seuil coverage: {threshold*100:.1f}% des pixels")
    print()

    tile_id = ty * grid_w + tx
    ttile_path = data_dir / f"{tile_prefix}{tile_id}.ttile"
    layer_path = find_layer_path(tile_id, data_dir, editor_data_dir, tile_prefix)

    if not ttile_path.exists():
        print(f"[ERR] .ttile introuvable: {ttile_path}")
        return 1

    if layer_path is None:
        print(f"[ERR] _layer introuvable pour {tile_prefix}{tile_id}")
        return 1

    # Lire LRS2
    lrs2_blocks = read_lrs2_from_ttile(ttile_path, grid_w, num_blk)
    if lrs2_blocks is None:
        print("[ERR] Impossible de lire le LRS2")
        return 1

    # Lire layer.dds
    pixels = read_layer_dds(layer_path)
    if pixels is None:
        print("[ERR] Impossible de lire le _layer.dds")
        return 1

    # Charger catalogue
    catalog_path = get_catalog_path()
    middles_dir = catalog_path.parent / "texture_Middle"
    emat_dir = catalog_path.parent / "emat"

    if not catalog_path.exists():
        print(f"[WARN] Catalogue introuvable: {catalog_path}")
        print("[INFO] Rendu texturé désactivé, fond noir utilisé")
        catalog = {}
        use_textures = False
    else:
        catalog = load_catalog(catalog_path)
        print(f"[INFO] Catalogue chargé : {catalog_path.absolute()}")
        use_textures = middles_dir.exists()
        if not use_textures:
            print(f"[WARN] Dossier middles introuvable: {middles_dir}")
            print("[INFO] Rendu texturé désactivé, fond noir utilisé")

    # 1. Rendu texturé (taille du _layer) avec les middles de la satmap, ou fond noir si désactivé
    size = pixels.shape[0]
    img_512 = np.zeros((size, size, 3), dtype=np.float32)

    if use_textures:
        print("[RENDER] Génération rendu texturé...")
        middles_cache = {}
        m_per_px = tile_size_m / size
        bs = size // num_blk

        for (bx, by), (mat_ids, _index) in lrs2_blocks.items():
            if len(mat_ids) == 0:
                continue
            x0, y0 = bx * bs, by * bs
            # Coordonnées dans la carte entière : motifs continus d'une tuile à l'autre
            x0_global, y0_global = tx * size + x0, ty * size + y0
            raw = pixels[y0:y0 + bs, x0:x0 + bs, :]

            block_canvas = np.zeros((bs, bs, 3), dtype=np.float32)
            total_w = np.zeros((bs, bs), dtype=np.float32)
            for slot, mat_id in enumerate(mat_ids[:min(7, raw.shape[2])]):
                w = raw[:, :, slot]
                if np.max(w) < 0.001:
                    continue
                middle = satmap_material_middle(mat_id, catalog, surfaces, middles_dir, middles_cache, m_per_px=m_per_px, emat_dir=emat_dir)
                block_canvas += w[:, :, None] * sample_middle_tiled(middle, x0_global, y0_global, bs, bs)
                total_w += w

            total_w = np.where(total_w < 0.001, 1.0, total_w)
            img_512[y0:y0 + bs, x0:x0 + bs] = block_canvas / total_w[:, :, None]
    else:
        print("[RENDER] Fond noir (textures désactivées)")

    img_512 = np.clip(img_512, 0, 255).astype(np.uint8)

    # CORRECTION: Flip vertical du fond pour orientation Workbench (nord en haut)
    img_512 = cv2.flip(img_512, 0)

    # 2. Upscale vers 800×800 (cases de 800 / num_blk px)
    img = cv2.resize(img_512, (800, 800), interpolation=cv2.INTER_LINEAR)
    cell = 800 // num_blk
    bs = size // num_blk

    # 3. Quadrillage blanc
    overlay = img.copy()
    for i in range(1, num_blk):
        cv2.line(overlay, (i * cell, 0), (i * cell, 800), (255, 255, 255), 2)
        cv2.line(overlay, (0, i * cell), (800, i * cell), (255, 255, 255), 2)

    alpha = 0.7
    img = cv2.addWeighted(img, alpha, overlay, 1 - alpha, 0)

    # 4. Labels par bloc
    for by in range(num_blk):
        for bx in range(num_blk):
            lrs_x, lrs_y = calculate_lrs2_coords(tx, ty, bx, by, num_blk)

            # Coordonnées LRS2
            text_lrs = f"{lrs_x},{lrs_y}"
            # CORRECTION: Orientation Workbench (X→droite, Y→haut)
            text_x = bx * cell + 10  # X croît vers la droite
            text_y = (num_blk - 1 - by) * cell + 30  # Y croît vers le haut (ligne inversée)

            # Ombre
            cv2.putText(img, text_lrs, (text_x + 2, text_y + 2),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 3, cv2.LINE_AA)
            # Texte blanc
            cv2.putText(img, text_lrs, (text_x, text_y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)

            # Matériaux avec coverage %
            block_val = lrs2_blocks.get((bx, by))
            mat_ids = block_val[0] if block_val else []
            if len(mat_ids) > 0:
                # Calculer coverage (pourcentage de pixels où le matériau est présent)
                x0 = bx * bs
                y0 = by * bs
                block_pixels = pixels[y0:y0+bs, x0:x0+bs, :len(mat_ids)]
                pixel_count = bs * bs

                # Afficher chaque matériau
                line_y = text_y + 25
                for i, mat_id in enumerate(mat_ids):
                    # CORRECTION: Marqueur slot 0
                    slot_marker = "[0] " if i == 0 else ""

                    # CORRECTION: Noms complets (sans [:12])
                    if mat_id < len(surfaces):
                        _s = surfaces[mat_id]
                        mat_name = _s.get("emat", _s.get("name", str(mat_id))) if isinstance(_s, dict) else str(_s)
                    else:
                        mat_name = f"MAT_{mat_id}"

                    # Coverage : % de pixels où weight > 0
                    coverage = (block_pixels[:, :, i] > 0).sum() / pixel_count
                    coverage_pct = coverage * 100

                    text_mat = f"{slot_marker}{mat_name} {coverage_pct:.0f}%"

                    # Couleur selon coverage
                    if coverage < threshold:
                        color = (255, 0, 0)  # ROUGE = négligeable
                    elif coverage_pct > 50:
                        color = (0, 255, 0)  # VERT = dominant
                    else:
                        color = (255, 255, 255)  # BLANC = normal

                    # Ombre
                    cv2.putText(img, text_mat, (text_x + 1, line_y + 1),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 0), 2, cv2.LINE_AA)
                    # Texte coloré
                    cv2.putText(img, text_mat, (text_x, line_y),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1, cv2.LINE_AA)

                    line_y += 20

    # CORRECTION: Agrandir l'image pour ajouter légende sous la grille
    img_with_legend = np.zeros((850, 800, 3), dtype=np.uint8)
    img_with_legend[:800, :, :] = img  # Copier grille 800×800

    # Légende couleurs dans bande 800-850
    legend_y = 830
    legend_x_start = 20
    cv2.putText(img_with_legend, "LEGENDE :", (legend_x_start, legend_y),
               cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1, cv2.LINE_AA)
    cv2.putText(img_with_legend, f"ROUGE < {threshold*100:.0f}%", (legend_x_start + 100, legend_y),
               cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 0, 0), 1, cv2.LINE_AA)
    cv2.putText(img_with_legend, f"BLANC {threshold*100:.0f}-50%", (legend_x_start + 280, legend_y),
               cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(img_with_legend, "VERT > 50%", (legend_x_start + 470, legend_y),
               cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1, cv2.LINE_AA)

    # 5. Sauvegarder
    output_path = output_dir / f"tile_{tx}_{ty}_cleanup.png"

    if not cv2.imwrite(str(output_path), cv2.cvtColor(img_with_legend, cv2.COLOR_RGB2BGR)):
        print(f"[ERR] Écriture de l'image impossible : {output_path}")
        return 1
    print(f"[OK] Image sauvegardée : {output_path.resolve()}")
    return 0


# ============================================================================
# MODE 3: CLEAN
# ============================================================================













# ============================================================================
# MODE 4: FORCE-MAT
# ============================================================================



# ============================================================================
# MODE 5: VALIDATE
# ============================================================================

def mode_validate(tx: int, ty: int, data_dir: Path, editor_data_dir: Path, surfaces: List[str], grid_w: int, num_blk: int, tile_prefix: str):
    """
    Valide les fichiers d'une tile sans les modifier.
    Vérifie la cohérence LRS2 / layer.dds et détecte les corruptions.
    """
    print("=" * 80)
    print(f"MODE VALIDATE - Tile ({tx},{ty})")
    print("=" * 80)

    tile_id = ty * grid_w + tx
    ttile_path = data_dir / f"{tile_prefix}{tile_id}.ttile"
    layer_path = find_layer_path(tile_id, data_dir, editor_data_dir, tile_prefix)

    errors = []
    warnings = []

    # --- TTILE ---
    print(f"\n[TTILE] {ttile_path.name}")
    if not ttile_path.exists():
        print("  ❌ Fichier introuvable")
        return 1

    raw = ttile_path.read_bytes()
    form_size = struct.unpack_from('>I', raw, 4)[0]
    if form_size != len(raw) - 8:
        errors.append(f"FORM size incohérent: {form_size} vs {len(raw)-8}")
    else:
        print(f"  ✅ FORM size: {form_size} OK")

    shift = compute_lrs2_shift(grid_w, num_blk)
    mask = (1 << shift) - 1

    lrs2_offset = raw.find(b'LRS2')
    if lrs2_offset == -1:
        errors.append("Chunk LRS2 introuvable")
    else:
        chunk_size = struct.unpack_from('>I', raw, lrs2_offset + 4)[0]
        print(f"  ✅ LRS2 size: {chunk_size}")
        lrs2_data = raw[lrs2_offset + 8:lrs2_offset + 8 + chunk_size]

        pos = 0
        blocks = {}
        while pos < len(lrs2_data):
            if pos + 6 > len(lrs2_data):
                break
            index = struct.unpack_from('<I', lrs2_data, pos)[0]
            count = struct.unpack_from('<H', lrs2_data, pos + 4)[0]
            if count == 0 or count > 7:
                errors.append(f"LRS2 count invalide={count} à pos={pos}")
                break
            mat_ids = list(struct.unpack_from(f'<{count}H', lrs2_data, pos + 6))
            bx_global = index & mask
            by_global = (index >> shift) & mask
            bx_l = bx_global % num_blk
            by_l = by_global % num_blk
            expected_bx = tx * num_blk + bx_l
            expected_by = ty * num_blk + by_l
            if bx_global != expected_bx or by_global != expected_by:
                errors.append(f"Index global incohérent: ({bx_global},{by_global}) attendu ({expected_bx},{expected_by})")
            # Vérifier mat_ids valides
            for mid in mat_ids:
                if mid >= len(surfaces):
                    warnings.append(f"mat_id={mid} hors catalogue (bloc ({bx_l},{by_l}))")
            blocks[(bx_l, by_l)] = (mat_ids, index)
            pos += 6 + count * 2

        print(f"  ✅ {len(blocks)} blocs LRS2")
        for (bx_l, by_l), (mat_ids, index) in sorted(blocks.items()):
            mat_names = [surfaces[m][:12] if m < len(surfaces) else f"MAT_{m}" for m in mat_ids]
            print(f"    ({bx_l},{by_l}) index=0x{index:04X} mats={mat_names}")

    # --- LAYER DDS ---
    if layer_path is None:
        print(f"\n[LAYER] {tile_prefix}{tile_id}_layer")
        print("  ❌ Fichier introuvable")
        return 1
    print(f"\n[LAYER] {layer_path.name}")

    dds = layer_path.read_bytes()
    print(f"  Taille: {len(dds)}")

    if dds[:4] != b'DDS ':
        errors.append(f"Magic invalide: {dds[:4]}")
    else:
        from edds_decoder import decode_edds_layer, extract_all_weights
        mip0 = decode_edds_layer(layer_path)
        if mip0 is None:
            errors.append(f"Impossible de décoder {layer_path.name}")
        else:
            print("  ✅ Magic DDS OK")

            # Extraire poids normalisés [512, 512, 7] avec w0 implicite calculé
            weights = extract_all_weights(mip0)  # w0 = 31 - sum(w1..w6)

            # Vérifier somme des poids (doit être ≤ 1.0 après normalisation, tolérance arrondi)
            bad = int((weights.sum(axis=2) > 1.01).sum())
            bs = weights.shape[0] // num_blk
            if bad:
                errors.append(f"{bad} pixels invalides (sum>1.0)")
            else:
                print("  ✅ 0 pixels invalides")

            # Cohérence LRS2 / layer: vérifier coverage des slots
            if blocks:
                print("\n[COHÉRENCE LRS2 / LAYER]")
                for (bx_l, by_l), (mat_ids, index) in sorted(blocks.items()):
                    x0, y0 = bx_l * bs, by_l * bs
                    block_weights = weights[y0:y0+bs, x0:x0+bs, :]
                    num_mats = len(mat_ids)
                    coverages = []
                    # CONVENTION VALIDÉE : mat_ids[i] ↔ w[i] (w0 inclus)
                    for slot_idx in range(num_mats):
                        if slot_idx >= block_weights.shape[2]:
                            break
                        # Coverage : % pixels où poids > 0
                        cov = (block_weights[:, :, slot_idx] > 0).sum() / (bs*bs) * 100
                        mat_name = surfaces[mat_ids[slot_idx]][:12] if mat_ids[slot_idx] < len(surfaces) else f"MAT_{mat_ids[slot_idx]}"
                        coverages.append(f"{mat_name}={cov:.0f}%")
                    print(f"  ({bx_l},{by_l}): {', '.join(coverages)}")

    # --- RÉSUMÉ ---
    print(f"\n{'='*80}")
    if errors:
        print(f"❌ {len(errors)} ERREUR(S):")
        for e in errors:
            print(f"   - {e}")
    else:
        print("✅ Aucune erreur détectée")
    if warnings:
        print(f"⚠️  {len(warnings)} avertissement(s):")
        for w in warnings:
            print(f"   - {w}")

    return 1 if errors else 0



# ============================================================================
# MODE 5: CLEAN-ALL
# ============================================================================




# ============================================================================
# MODE 6: WEIGHTS
# ============================================================================

def mode_weights(tx: int, ty: int, data_dir: Path, editor_data_dir: Path, surfaces: List[str], grid_w: int, num_blk: int, tile_prefix: str, output_dir: Path):
    """
    Affiche les poids réels (0-31) de chaque matériau par bloc.
    Log détaillé + image avec valeurs moyennes affichées.
    """
    print("=" * 80)
    print(f"MODE WEIGHTS - Tile ({tx},{ty})")
    print("=" * 80)

    tile_id = ty * grid_w + tx
    ttile_path = data_dir / f"{tile_prefix}{tile_id}.ttile"
    layer_path = find_layer_path(tile_id, data_dir, editor_data_dir, tile_prefix)

    if not ttile_path.exists():
        print("[ERR] .ttile introuvable")
        return 1
    if layer_path is None:
        print(f"[ERR] _layer introuvable pour {tile_prefix}{tile_id}")
        return 1

    lrs2_blocks = read_lrs2_from_ttile(ttile_path, grid_w, num_blk)
    if lrs2_blocks is None:
        print("[ERR] Impossible de lire le LRS2")
        return 1

    pixels = read_layer_dds(layer_path)
    if pixels is None:
        print("[ERR] Impossible de lire le layer")
        return 1

    print()
    print(f"{'Bloc':<12} {'Mat':<25} {'Moy':>6} {'Min':>6} {'Max':>6} {'Cover':>7}")
    print("-" * 70)

    # Image 800x800 (cases de 800 / num_blk px), orientée comme mode_inspect (X → droite, Y → haut)
    img = np.zeros((800, 800, 3), dtype=np.uint8)
    img[:] = (40, 40, 40)
    cell = 800 // num_blk
    bs = pixels.shape[0] // num_blk

    # Quadrillage
    for i in range(1, num_blk):
        cv2.line(img, (i*cell, 0), (i*cell, 800), (120,120,120), 1)
        cv2.line(img, (0, i*cell), (800, i*cell), (120,120,120), 1)

    for (bx, by), (mat_ids, orig_index) in sorted(lrs2_blocks.items()):
        lrs_x = tx * num_blk + bx
        lrs_y = ty * num_blk + by

        x0, y0 = bx * bs, by * bs
        block_pixels = pixels[y0:y0+bs, x0:x0+bs, :]
        num_mats = len(mat_ids)
        pixel_count = bs * bs

        # Coordonnées dans l'image 800x800
        img_x = bx * cell
        img_y = (num_blk - 1 - by) * cell

        # Header du bloc
        lbl = f"{lrs_x},{lrs_y}"
        cv2.putText(img, lbl, (img_x+10, img_y+22),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2, cv2.LINE_AA)

        line_y = img_y + 45
        for slot_idx in range(min(num_mats, 7)):
            # CONVENTION VALIDÉE : mat_ids[i] ↔ w[i] (slot 0 = w0 inclus)
            if slot_idx >= block_pixels.shape[2]:
                continue

            mat_id = mat_ids[slot_idx]
            if mat_id < len(surfaces):
                _s = surfaces[mat_id]
                mat_name = (_s.get("emat", _s.get("name", str(mat_id))) if isinstance(_s, dict) else str(_s))[:18]
            else:
                mat_name = f"MAT_{mat_id}"

            # Poids bruts 0-31
            raw_weights = (block_pixels[:, :, slot_idx] * 31).round()
            active = raw_weights > 0

            if active.sum() == 0:
                avg_w = 0.0
                min_w = 0.0
                max_w = 0.0
                coverage = 0.0
            else:
                avg_w = raw_weights[active].mean()
                min_w = raw_weights[active].min()
                max_w = raw_weights[active].max()
                coverage = active.sum() / pixel_count * 100

            # Log
            print(f"  ({bx},{by}) LRS=({lrs_x:3d},{lrs_y:3d})  "
                  f"{mat_name:<20}  "
                  f"{avg_w:5.1f}  {min_w:5.0f}  {max_w:5.0f}  {coverage:6.1f}%")

            # Couleur selon poids moyen
            if avg_w >= 20:
                color = (0, 255, 0)    # vert = dominant
            elif avg_w >= 10:
                color = (0, 200, 255)  # jaune = moyen
            elif avg_w > 0:
                color = (0, 100, 255)  # orange = faible
            else:
                color = (0, 0, 200)    # rouge = absent

            text = f"{mat_name[:14]} w={avg_w:.0f} ({coverage:.0f}%)"
            cv2.putText(img, text, (img_x+6, line_y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.28, (0,0,0), 2, cv2.LINE_AA)
            cv2.putText(img, text, (img_x+6, line_y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.28, color, 1, cv2.LINE_AA)
            line_y += 22

        # w0 depuis extraction directe (pas implicite avec nouvelle convention)
        # CONVENTION VALIDÉE : mat_ids[0] ↔ w[0], donc w0 est déjà dans block_pixels[:,:,0]
        if num_mats > 0 and 0 < block_pixels.shape[2]:
            w0_vals = (block_pixels[:, :, 0] * 31).round()
            w0_approx = w0_vals[w0_vals > 0].mean() if (w0_vals > 0).sum() > 0 else 0
        else:
            w0_approx = 0
        cv2.putText(img, f"w0 ~{w0_approx:.0f}", (img_x+6, line_y),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.25, (150,150,150), 1, cv2.LINE_AA)

        print()

    # Bordure
    cv2.rectangle(img, (0,0), (799,799), (180,180,180), 2)

    output_path = output_dir / f"tile_{tx}_{ty}_weights.png"
    if not cv2.imwrite(str(output_path), img):
        print(f"[ERR] Écriture de l'image impossible : {output_path}")
        return 1
    print(f"[OK] Image sauvegardée: {output_path}")
    return 0

# ============================================================================
# MODE 7: SCAN-ZONE et CLEAN-ZONE
# ============================================================================

# Constantes Zone B
ALLOWED_MATS_ZONE_B = {0, 3}  # Grass_03_defaut (w0) + Grass_03 (ID=3)
# Note: SeaBed_01 sera ajouté dynamiquement depuis surfaces


def get_zone_b_blocks(mask_path: Path, data_dir: Path, editor_data_dir: Path,
                      surfaces: List[str], seabed_id: int, grid_w: int, num_blk: int, tile_prefix: str):
    """
    Analyse le masque PNG et retourne les infos des blocs Zone B.

    Yields:
        (tx, ty, tile_id, bx, by, type_bloc, mat_ids, residus, layer_path)
        type_bloc : "GRIS" | "PLEIN" | "LIMITROPHE"
    """
    # Charger le masque
    mask_img = cv2.imread(str(mask_path), cv2.IMREAD_UNCHANGED)
    if mask_img is None:
        print(f"[ERR] Impossible de lire le masque : {mask_path}")
        return

    # Convertir en binaire (blanc > 0)
    if len(mask_img.shape) == 3:
        mask_img = cv2.cvtColor(mask_img, cv2.COLOR_BGR2GRAY)
    mask_bin = (mask_img > 0).astype(np.uint8)

    h, w = mask_bin.shape

    # Validation : masque carré et taille multiple de grid_w
    if h != w or w % grid_w != 0:
        print(f"[ERR] get_zone_b_blocks : masque invalide ({w} × {h}, grid_w={grid_w})")
        return

    # Calcul de l'échelle depuis la grille
    px_per_tile = w // grid_w
    px_per_bloc = px_per_tile // num_blk

    # Parcourir toutes les tuiles
    for ty in range(grid_w):
        for tx in range(grid_w):
            # Zone de la tuile dans le masque
            y0_tile = ty * px_per_tile
            x0_tile = tx * px_per_tile
            y1_tile = min(y0_tile + px_per_tile, h)
            x1_tile = min(x0_tile + px_per_tile, w)

            zone_tuile = mask_bin[y0_tile:y1_tile, x0_tile:x1_tile]

            # Si aucun pixel blanc, skip la tuile
            if zone_tuile.sum() == 0:
                continue

            tile_id = ty * grid_w + tx
            layer_path = find_layer_path(tile_id, data_dir, editor_data_dir, tile_prefix)

            if layer_path is None:
                print(f"[WARN] Layer introuvable pour tuile ({tx},{ty})")
                continue

            weights = read_layer_dds(layer_path)
            if weights is None:
                continue

            ttile_path = data_dir / f"{tile_prefix}{tile_id}.ttile"
            lrs2 = read_lrs2_from_ttile(ttile_path, grid_w, num_blk)
            if lrs2 is None:
                continue

            # Parcourir les blocs
            for by in range(num_blk):
                for bx in range(num_blk):
                    # Zone du bloc dans la zone tuile
                    y0_bloc = by * px_per_bloc
                    x0_bloc = bx * px_per_bloc
                    y1_bloc = min(y0_bloc + px_per_bloc, zone_tuile.shape[0])
                    x1_bloc = min(x0_bloc + px_per_bloc, zone_tuile.shape[1])

                    zone_bloc = zone_tuile[y0_bloc:y1_bloc, x0_bloc:x1_bloc]

                    n_blanc = zone_bloc.sum()
                    n_total = zone_bloc.size

                    # Ne traiter que les blocs 100% blancs
                    if n_blanc != n_total:
                        # Bloc mixte ou tout noir → skip
                        continue

                    # Bloc 100% blanc → traiter
                    type_bloc = "PLEIN"

                    # Récupérer mat_ids
                    block_data = lrs2.get((bx, by))
                    if block_data is None:
                        mat_ids = []
                    else:
                        mat_ids, orig_index = block_data

                    # Calculer résidus (matériaux non autorisés)
                    allowed = ALLOWED_MATS_ZONE_B | {seabed_id}
                    residus = [m for m in mat_ids if m not in allowed]

                    yield (tx, ty, tile_id, bx, by, type_bloc, mat_ids, residus, layer_path)


def mode_scan_zone(mask_path: Path, data_dir: Path, editor_data_dir: Path, surfaces: List[str], grid_w: int, num_blk: int, tile_prefix: str):
    """
    Scanner les blocs Zone B et lister les résidus.
    """
    print("=" * 80)
    print("SCAN ZONE B")
    print("=" * 80)
    print(f"Masque: {mask_path}")
    print()

    # Trouver seabed_id
    seabed_id = next((i for i, s in enumerate(surfaces) if 'seabed' in s.lower()), 1)

    # Analyser le masque pour compter les blocs
    mask_img = cv2.imread(str(mask_path), cv2.IMREAD_UNCHANGED)
    if mask_img is None:
        print("[ERR] Impossible de lire le masque")
        return 1
    if len(mask_img.shape) == 3:
        mask_img = cv2.cvtColor(mask_img, cv2.COLOR_BGR2GRAY)
    mask_bin = (mask_img > 0).astype(np.uint8)
    h, w = mask_bin.shape

    # Validation : masque carré et taille multiple de grid_w
    if h != w:
        print("[ERR] Le masque doit être carré")
        print(f"      Masque : {mask_path}")
        print(f"      Taille lue : {w} × {h}")
        print(f"      grid_w du projet : {grid_w}")
        print(f"      Exemples de tailles valides : {grid_w * 64} × {grid_w * 64}, {grid_w * 128} × {grid_w * 128}")
        return 1

    if w % grid_w != 0:
        print("[ERR] La largeur du masque doit être un multiple de grid_w")
        print(f"      Masque : {mask_path}")
        print(f"      Largeur lue : {w}")
        print(f"      grid_w du projet : {grid_w}")
        print(f"      Exemples de largeurs valides : {grid_w * 64}, {grid_w * 128}")
        return 1

    # Calcul de l'échelle depuis la grille
    px_per_tile = w // grid_w
    px_per_bloc = px_per_tile // num_blk

    print(f"[SCAN ZONE] Masque : {mask_path}")
    print(f"[SCAN ZONE] Taille : {w} × {h}")
    print(f"[SCAN ZONE] grid_w : {grid_w}")
    print(f"[SCAN ZONE] px_per_tile calculé : {px_per_tile}")
    print(f"[SCAN ZONE] px_per_bloc calculé : {px_per_bloc}")

    blocs_full_white = 0
    blocs_mixed = 0
    blocs_black = 0
    for ty in range(grid_w):
        for tx in range(grid_w):
            y0_tile = ty * px_per_tile
            x0_tile = tx * px_per_tile
            y1_tile = min(y0_tile + px_per_tile, h)
            x1_tile = min(x0_tile + px_per_tile, w)
            zone_tuile = mask_bin[y0_tile:y1_tile, x0_tile:x1_tile]

            if zone_tuile.sum() == 0:
                continue

            for by in range(num_blk):
                for bx in range(num_blk):
                    y0_bloc = by * px_per_bloc
                    x0_bloc = bx * px_per_bloc
                    y1_bloc = min(y0_bloc + px_per_bloc, zone_tuile.shape[0])
                    x1_bloc = min(x0_bloc + px_per_bloc, zone_tuile.shape[1])
                    zone_bloc = zone_tuile[y0_bloc:y1_bloc, x0_bloc:x1_bloc]

                    n_white = zone_bloc.sum()
                    n_total = zone_bloc.size

                    if n_white == 0:
                        blocs_black += 1
                    elif n_white == n_total:
                        blocs_full_white += 1
                    else:
                        blocs_mixed += 1

    # Collecter les infos
    blocs_pleins_propres = []
    blocs_pleins_residus = []
    blocs_limit_propres = []
    blocs_limit_residus = []

    for info in get_zone_b_blocks(mask_path, data_dir, editor_data_dir, surfaces, seabed_id, grid_w, num_blk, tile_prefix):
        tx, ty, tile_id, bx, by, type_bloc, mat_ids, residus, layer_path = info

        if type_bloc == "GRIS":
            continue

        lrs_x = tx * num_blk + bx
        lrs_y = ty * num_blk + by

        if type_bloc == "PLEIN":
            if residus:
                blocs_pleins_residus.append((lrs_x, lrs_y, tx, ty, mat_ids, residus))
            else:
                blocs_pleins_propres.append((lrs_x, lrs_y, tx, ty))
        elif type_bloc == "LIMITROPHE":
            if residus:
                blocs_limit_residus.append((lrs_x, lrs_y, tx, ty, mat_ids, residus))
            else:
                blocs_limit_propres.append((lrs_x, lrs_y, tx, ty))

    # RÉSUMÉ EN PREMIER
    total_residus = len(blocs_pleins_residus) + len(blocs_limit_residus)
    print()
    print("=" * 80)
    print(f"Total : {total_residus} blocs avec résidus — {len(blocs_pleins_residus)} pleins + {len(blocs_limit_residus)} limitrophes")
    print("=" * 80)
    print()

    # Affichage détaillé
    if blocs_pleins_residus:
        print("BLOCS PLEINS avec résidus :")
        for lrs_x, lrs_y, tx, ty, mat_ids, residus in blocs_pleins_residus[:20]:
            residus_str = " ".join([surfaces[m] if m < len(surfaces) else f"MAT_{m}"
                                    for m in residus])
            print(f"  LRS2=({lrs_x},{lrs_y}) Tile({tx},{ty}) : {residus_str}")
        if len(blocs_pleins_residus) > 20:
            print(f"  ... et {len(blocs_pleins_residus)-20} autres blocs")
        print()

    if blocs_limit_residus:
        print("BLOCS LIMITROPHES avec résidus :")
        for lrs_x, lrs_y, tx, ty, mat_ids, residus in blocs_limit_residus[:20]:
            residus_str = " ".join([surfaces[m] if m < len(surfaces) else f"MAT_{m}"
                                    for m in residus])
            print(f"  LRS2=({lrs_x},{lrs_y}) Tile({tx},{ty}) : {residus_str}")
        if len(blocs_limit_residus) > 20:
            print(f"  ... et {len(blocs_limit_residus)-20} autres blocs")
        print()

    # Résumé
    print("=" * 80)
    print("RÉSUMÉ :")
    print(f"  Blocs 100% blancs traités : {blocs_full_white}")
    print(f"  Blocs mixtes ignorés      : {blocs_mixed}")
    print(f"  Blocs noirs ignorés       : {blocs_black}")
    print()
    print(f"  Blocs pleins propres       : {len(blocs_pleins_propres)}")
    print(f"  Blocs pleins avec résidus  : {len(blocs_pleins_residus)} → à corriger dans Workbench")
    print(f"  Blocs limitrophes propres  : {len(blocs_limit_propres)}")
    print(f"  Blocs limitrophes avec résidus : {len(blocs_limit_residus)} → traitement manuel")
    print()

    if blocs_pleins_residus:
        tiles_set = set((tx, ty) for _, _, tx, ty, _, _ in blocs_pleins_residus)
        tiles_str = " ".join([f"{tx},{ty}" for tx, ty in sorted(tiles_set)])
        print(f"Tuiles à nettoyer : {tiles_str}")

    return 0




# ============================================================================
# MODE 8: RESET-ZONE
# ============================================================================



# ============================================================================
# MAIN
# ============================================================================



