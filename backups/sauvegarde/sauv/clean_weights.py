"""
Clean Weights - Gestion des poids négligeables des blocs terrain

Trois modes:
1. --scan                  : Scan rapide, liste tiles avec slots négligeables
2. --inspect x,y          : Image debug 800×800 avec rendu texturé
3. --clean x,y            : Nettoyage avec backup (dry-run + confirmation)

Paramètre optionnel:
  --threshold 0.01         : Seuil personnalisé (défaut 0.01 soit 1%)

Exemples:
  python clean_weights.py --scan
  python clean_weights.py --inspect 2,11
  python clean_weights.py --clean 25,0 --threshold 0.5
"""

import struct
import sys
import argparse
import json
import numpy as np
import cv2
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import shutil

# Import modules terrain
sys.path.insert(0, str(Path(__file__).parent.parent))
from terrain_terr_reader import read_mats_from_terr
from scripts.edds_decoder import decode_edds_layer, extract_all_weights


# ============================================================================
# UTILITAIRES LECTURE/ÉCRITURE
# ============================================================================

def read_lrs2_from_ttile(ttile_path: Path) -> Optional[Dict[Tuple[int, int], List[int]]]:
    """Lit le chunk LRS2 d'un .ttile."""
    if not ttile_path.exists():
        return None

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

            # Extraire coordonnées globales
            bx_global = index & 0x7F
            by_global = (index >> 7) & 0x7F

            # Convertir en coordonnées locales (0-3, 0-3)
            bx_local = bx_global % 4
            by_local = by_global % 4

            blocks[(bx_local, by_local)] = mat_ids
            pos += 6 + count * 2

        return blocks

    except Exception:
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


def calculate_lrs2_coords(tx: int, ty: int, bx: int, by: int) -> Tuple[int, int]:
    """Calcule les coordonnées LRS2 globales d'un bloc."""
    lrs_x = tx * 4 + bx
    lrs_y = ty * 4 + by
    return lrs_x, lrs_y


def analyze_block_weights(
    pixels: np.ndarray,
    bx: int, by: int,
    num_mats: int,
    threshold: float
) -> List[Tuple[int, float]]:
    """
    Analyse les poids d'un bloc et retourne les slots négligeables.

    Returns:
        Liste de (slot_index, coverage_pct)
    """
    x0 = bx * 128
    y0 = by * 128
    block_pixels = pixels[y0:y0+128, x0:x0+128, :num_mats]

    pixel_count = 128 * 128  # 16384 cellules par bloc

    negligible = []
    for slot in range(num_mats):
        # Coverage : pourcentage de pixels où le matériau est présent (weight > 0)
        coverage = (block_pixels[:, :, slot] > 0).sum() / pixel_count
        if coverage < threshold:
            negligible.append((slot, coverage))

    return negligible


# ============================================================================
# MODE 1: SCAN
# ============================================================================

def mode_scan(data_dir: Path, editor_data_dir: Path, threshold: float):
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
    layer_files = sorted(editor_data_dir.glob("Terrain_*_layer.*"))

    if not layer_files:
        print("[ERR] Aucun _layer.dds trouvé")
        return 1

    tiles_with_slots = []  # [(tx, ty, nb_slots)]
    total_slots = 0

    print(f"[SCAN] {len(layer_files)} tiles à analyser...")
    print()

    for layer_path in layer_files:
        # Extraire tile_id
        filename = layer_path.stem  # Terrain_XXX_layer
        tile_id = int(filename.split('_')[1])
        tx = tile_id % 32
        ty = tile_id // 32

        # Lire LRS2
        ttile_path = data_dir / f"Terrain_{tile_id}.ttile"
        lrs2_blocks = read_lrs2_from_ttile(ttile_path)
        if lrs2_blocks is None:
            continue

        # Lire layer.dds
        pixels = read_layer_dds(layer_path)
        if pixels is None:
            continue

        # Analyser chaque bloc
        tile_slots = 0
        for (bx, by), mat_ids in lrs2_blocks.items():
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

    print(f"Tiles avec slots négligeables (seuil {threshold:.2f}/31) :")
    print()

    for tx, ty, nb_slots in sorted(tiles_with_slots, key=lambda x: -x[2]):
        print(f"  ({tx:2d},{ty:2d}) : {nb_slots} slots négligeables")

    print()
    print(f"Total : {len(tiles_with_slots)} tiles, {total_slots} slots à nettoyer")

    return 0


# ============================================================================
# MODE 2: INSPECT
# ============================================================================

def load_catalog(catalog_path: Path) -> Dict:
    """Charge le catalogue de textures enrichi."""
    with open(catalog_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_material_middle(
    mat_id: int,
    catalog: Dict,
    surfaces: List[str],
    middles_dir: Path,
    middles_cache: Dict[int, np.ndarray],
    tile_size: int = 512
) -> np.ndarray:
    """Retourne une image tuilée RGB pour un matériau."""
    if mat_id in middles_cache:
        return middles_cache[mat_id]

    # Fallback couleur plate
    if mat_id >= len(surfaces):
        color_flat = np.array([255, 0, 255], dtype=np.float32)
    else:
        surface_name = surfaces[mat_id]
        entry = catalog.get(surface_name) or catalog.get(surface_name + ".emat")

        if entry is None:
            color_flat = np.array([75, 110, 48], dtype=np.float32)
        else:
            avg = entry.get("avg_color")
            tint = entry.get("tint")
            tint_srgb = entry.get("tint_srgb")

            if tint and max(tint[:3]) < 200:
                color_flat = np.array(tint[:3], dtype=np.float32)
            elif avg and avg != [0, 0, 0]:
                color_flat = np.array(avg[:3], dtype=np.float32)
            elif tint_srgb:
                color_flat = np.array(tint_srgb[:3], dtype=np.float32)
            else:
                color_flat = np.array([75, 110, 48], dtype=np.float32)

    fallback = np.full((tile_size, tile_size, 3), color_flat, dtype=np.float32)

    if mat_id >= len(surfaces):
        middles_cache[mat_id] = fallback
        return fallback

    surface_name = surfaces[mat_id]
    entry = catalog.get(surface_name) or catalog.get(surface_name + ".emat")

    if entry is None:
        middles_cache[mat_id] = fallback
        return fallback

    middle_bcr = entry.get("middle_bcr")
    tiling_scale = entry.get("tiling_scale", 1.0)

    if not middle_bcr or not middles_dir:
        middles_cache[mat_id] = fallback
        return fallback

    middle_path = middles_dir / middle_bcr
    if not middle_path.exists():
        middles_cache[mat_id] = fallback
        return fallback

    try:
        middle_img = cv2.imread(str(middle_path))
        if middle_img is None:
            middles_cache[mat_id] = fallback
            return fallback

        middle_img = cv2.cvtColor(middle_img, cv2.COLOR_BGR2RGB).astype(np.float32)

        world_size_m = 2048.0
        repeat = max(1, round(world_size_m / tiling_scale))

        tiled = np.tile(middle_img, (repeat, repeat, 1))
        tiled_resized = cv2.resize(tiled, (tile_size, tile_size), interpolation=cv2.INTER_LINEAR)

        result = np.clip(tiled_resized, 0, 255)
        middles_cache[mat_id] = result
        return result
    except Exception:
        middles_cache[mat_id] = fallback
        return fallback


def mode_inspect(
    tx: int, ty: int,
    data_dir: Path,
    editor_data_dir: Path,
    surfaces: List[str],
    threshold: float
):
    """
    Génère une image 800×800 de la tile avec:
    - Fond = rendu texturé (ou noir si catalogue absent)
    - Coordonnées LRS2 + liste matériaux avec %
    - Matériaux < threshold en rouge
    - Matériaux > 50% en vert
    """
    print("=" * 80)
    print(f"MODE INSPECT - Tile ({tx},{ty})")
    print("=" * 80)
    print(f"Seuil coverage: {threshold*100:.1f}% des pixels")
    print()

    tile_id = ty * 32 + tx
    ttile_path = data_dir / f"Terrain_{tile_id}.ttile"
    layer_path = editor_data_dir / f"Terrain_{tile_id}_layer.edds"
    if not layer_path.exists():
        layer_path = editor_data_dir / f"Terrain_{tile_id}_layer.dds"

    if not ttile_path.exists():
        print(f"[ERR] .ttile introuvable: {ttile_path}")
        return 1

    if not layer_path.exists():
        print(f"[ERR] _layer.dds introuvable: {layer_path}")
        return 1

    # Lire LRS2
    lrs2_blocks = read_lrs2_from_ttile(ttile_path)
    if lrs2_blocks is None:
        print("[ERR] Impossible de lire le LRS2")
        return 1

    # Lire layer.dds
    pixels = read_layer_dds(layer_path)
    if pixels is None:
        print("[ERR] Impossible de lire le _layer.dds")
        return 1

    # Charger catalogue
    project_root = Path(__file__).parent.parent
    catalog_path = project_root / "data" / "Textures_ArmaReforger" / "catalog.json"
    middles_dir = project_root / "data" / "Textures_ArmaReforger" / "texture_Middle"

    if not catalog_path.exists():
        print(f"[WARN] Catalogue introuvable: {catalog_path}")
        print(f"[INFO] Rendu texturé désactivé, fond noir utilisé")
        catalog = {}
        use_textures = False
    else:
        catalog = load_catalog(catalog_path)
        use_textures = middles_dir.exists()
        if not use_textures:
            print(f"[WARN] Dossier middles introuvable: {middles_dir}")
            print(f"[INFO] Rendu texturé désactivé, fond noir utilisé")

    # 1. Rendu texturé 512×512 (ou fond noir si désactivé)
    img_512 = np.zeros((512, 512, 3), dtype=np.float32)

    if use_textures:
        print("[RENDER] Génération rendu texturé...")
        middles_cache = {}

        for y in range(512):
            for x in range(512):
                bx = x // 128
                by = y // 128

                mat_ids = lrs2_blocks.get((bx, by), [])
                if len(mat_ids) == 0:
                    continue

                w = pixels[y, x, :len(mat_ids)]
                pixel_color = np.zeros(3, dtype=np.float32)

                for i, mat_id in enumerate(mat_ids):
                    if i >= 7:
                        break
                    weight = w[i]
                    if weight < 0.001:
                        continue

                    middle = get_material_middle(mat_id, catalog, surfaces, middles_dir, middles_cache, tile_size=512)
                    pixel_color += middle[y, x, :] * weight

                img_512[y, x, :] = pixel_color
    else:
        print("[RENDER] Fond noir (textures désactivées)")

    img_512 = np.clip(img_512, 0, 255).astype(np.uint8)

    # 2. Upscale vers 800×800
    img = cv2.resize(img_512, (800, 800), interpolation=cv2.INTER_LINEAR)

    # 3. Quadrillage blanc
    overlay = img.copy()
    for bx in range(1, 4):
        x = bx * 200
        cv2.line(overlay, (x, 0), (x, 800), (255, 255, 255), 2)
    for by in range(1, 4):
        y = by * 200
        cv2.line(overlay, (0, y), (800, y), (255, 255, 255), 2)

    alpha = 0.7
    img = cv2.addWeighted(img, alpha, overlay, 1 - alpha, 0)

    # 4. Labels par bloc
    for by in range(4):
        for bx in range(4):
            lrs_x, lrs_y = calculate_lrs2_coords(tx, ty, bx, by)

            # Coordonnées LRS2
            text_lrs = f"{lrs_x},{lrs_y}"
            text_x = bx * 200 + 10
            text_y = by * 200 + 30

            # Ombre
            cv2.putText(img, text_lrs, (text_x + 2, text_y + 2),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 3, cv2.LINE_AA)
            # Texte blanc
            cv2.putText(img, text_lrs, (text_x, text_y),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)

            # Matériaux avec coverage %
            mat_ids = lrs2_blocks.get((bx, by), [])
            if len(mat_ids) > 0:
                # Calculer coverage (pourcentage de pixels où le matériau est présent)
                x0 = bx * 128
                y0 = by * 128
                block_pixels = pixels[y0:y0+128, x0:x0+128, :len(mat_ids)]
                pixel_count = 128 * 128

                # Afficher chaque matériau
                line_y = text_y + 25
                for i, mat_id in enumerate(mat_ids):
                    if mat_id < len(surfaces):
                        mat_name = surfaces[mat_id][:12]  # Tronquer
                    else:
                        mat_name = f"MAT_{mat_id}"

                    # Coverage : % de pixels où weight > 0
                    coverage = (block_pixels[:, :, i] > 0).sum() / pixel_count
                    coverage_pct = coverage * 100

                    text_mat = f"{mat_name} {coverage_pct:.0f}%"

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

    # 5. Sauvegarder
    output_path = Path(__file__).parent.parent / f"tile_{tx}_{ty}_cleanup.png"
    cv2.imwrite(str(output_path), cv2.cvtColor(img, cv2.COLOR_RGB2BGR))

    print(f"[OK] Image sauvegardée: {output_path}")
    return 0


# ============================================================================
# MODE 3: CLEAN
# ============================================================================

def renormalize_weights(weights: np.ndarray) -> np.ndarray:
    """Renormalise un vecteur de poids pour que la somme = 31."""
    total = weights.sum()
    if total == 0:
        weights[0] = 31
        return weights

    # Redistribuer proportionnellement
    weights = (weights * 31.0 / total).round().astype(np.uint8)

    # Ajuster pour que sum = 31
    diff = 31 - weights.sum()
    if diff != 0:
        weights[0] += diff

    return weights


def clean_block_weights(
    pixels: np.ndarray,
    bx: int, by: int,
    slots_to_remove: List[int]
) -> np.ndarray:
    """
    Met à 0 les poids des slots négligeables et renormalise.
    Modifie pixels en place.
    """
    x0 = bx * 128
    y0 = by * 128

    for py in range(128):
        for px in range(128):
            y = y0 + py
            x = x0 + px

            weights = (pixels[y, x, :] * 31).round().astype(np.uint8)

            # Supprimer slots négligeables
            for slot in slots_to_remove:
                weights[slot] = 0

            # Renormaliser
            weights = renormalize_weights(weights)

            # Réécrire
            pixels[y, x, :] = weights / 31.0

    return pixels


def write_lrs2_chunk(
    ttile_path: Path,
    new_lrs2_blocks: Dict[Tuple[int, int], List[int]]
) -> bool:
    """Réécrit le chunk LRS2 dans le .ttile."""
    try:
        data = bytearray(ttile_path.read_bytes())

        # Trouver LRS2
        lrs2_offset = data.find(b'LRS2')
        if lrs2_offset == -1:
            return False

        old_chunk_size = struct.unpack_from('>I', data, lrs2_offset + 4)[0]
        old_chunk_end = lrs2_offset + 8 + old_chunk_size
        padding_old = old_chunk_size % 2
        next_chunk_start = old_chunk_end + padding_old

        # Construire nouveau LRS2
        new_lrs2_data = bytearray()
        for (bx, by), mat_ids in sorted(new_lrs2_blocks.items()):
            index = (by << 7) | bx
            count = len(mat_ids)

            new_lrs2_data.extend(struct.pack('<I', index))
            new_lrs2_data.extend(struct.pack('<H', count))
            new_lrs2_data.extend(struct.pack(f'<{count}H', *mat_ids))

        new_lrs2_size = len(new_lrs2_data)

        # Construire nouveau chunk avec header
        new_chunk = bytearray()
        new_chunk.extend(b'LRS2')
        new_chunk.extend(struct.pack('>I', new_lrs2_size))
        new_chunk.extend(new_lrs2_data)

        # Padding IFF (alignement 2 bytes)
        padding = new_lrs2_size % 2
        if padding:
            new_chunk.extend(b'\x00')

        # Reconstruire fichier
        new_data = bytearray()
        new_data.extend(data[:lrs2_offset])
        new_data.extend(new_chunk)
        new_data.extend(data[next_chunk_start:])

        # Mettre à jour FORM header
        new_data[4:8] = struct.pack('>I', len(new_data) - 8)

        # Écrire
        ttile_path.write_bytes(new_data)
        return True

    except Exception:
        return False


def write_layer_dds(layer_path: Path, pixels: np.ndarray) -> bool:
    """Réécrit le _layer.dds avec les nouveaux poids."""
    try:
        # Convertir poids [0..1] → [0..31]
        weights_u8 = (pixels * 31).round().astype(np.uint8)

        # Encoder dans R32_UINT
        encoded = np.zeros((512, 512), dtype=np.uint32)

        for y in range(512):
            for x in range(512):
                w = weights_u8[y, x, :]
                pixel_u32 = (
                    (w[1] & 0x1F) |
                    ((w[2] & 0x1F) << 5) |
                    ((w[3] & 0x1F) << 10) |
                    ((w[4] & 0x1F) << 15) |
                    ((w[5] & 0x1F) << 20) |
                    ((w[6] & 0x1F) << 25)
                )
                encoded[y, x] = pixel_u32

        # Lire le DDS existant et remplacer les données
        with open(layer_path, 'rb') as f:
            dds_header = f.read(148)  # Header DDS standard

        # Réécrire avec nouvelles données
        with open(layer_path, 'wb') as f:
            f.write(dds_header)
            f.write(encoded.tobytes())

        return True

    except Exception:
        return False


def mode_clean(
    tx: int, ty: int,
    data_dir: Path,
    editor_data_dir: Path,
    surfaces: List[str],
    threshold: float
):
    """
    Nettoie les slots négligeables d'une tile.
    Dry-run → confirmation → backup → écriture.
    """
    print("=" * 80)
    print(f"MODE CLEAN - Tile ({tx},{ty})")
    print("=" * 80)
    print(f"Seuil coverage: {threshold*100:.1f}% des pixels")
    print()

    tile_id = ty * 32 + tx
    ttile_path = data_dir / f"Terrain_{tile_id}.ttile"
    layer_path = editor_data_dir / f"Terrain_{tile_id}_layer.edds"
    if not layer_path.exists():
        layer_path = editor_data_dir / f"Terrain_{tile_id}_layer.dds"

    if not ttile_path.exists():
        print(f"[ERR] .ttile introuvable: {ttile_path}")
        return 1

    if not layer_path.exists():
        print(f"[ERR] _layer.dds introuvable: {layer_path}")
        return 1

    # Lire LRS2
    lrs2_blocks = read_lrs2_from_ttile(ttile_path)
    if lrs2_blocks is None:
        print("[ERR] Impossible de lire le LRS2")
        return 1

    # Lire layer.dds
    pixels = read_layer_dds(layer_path)
    if pixels is None:
        print("[ERR] Impossible de lire le _layer.dds")
        return 1

    # Analyser slots négligeables
    blocks_to_clean = {}  # {(bx, by): [(slot, coverage, mat_id, mat_name), ...]}

    for (bx, by), mat_ids in lrs2_blocks.items():
        num_mats = len(mat_ids)
        if num_mats == 0:
            continue

        negligible = analyze_block_weights(pixels, bx, by, num_mats, threshold)

        if negligible:
            slots_info = []
            for slot, coverage in negligible:
                mat_id = mat_ids[slot]
                mat_name = surfaces[mat_id] if mat_id < len(surfaces) else f"MAT_{mat_id}"
                slots_info.append((slot, coverage, mat_id, mat_name))

            blocks_to_clean[(bx, by)] = slots_info

    if not blocks_to_clean:
        print("[OK] Aucun slot négligeable trouvé")
        return 0

    # Dry-run: afficher détails
    total_slots = sum(len(v) for v in blocks_to_clean.values())

    print(f"[DRY-RUN] {total_slots} slots à supprimer dans {len(blocks_to_clean)} blocs:")
    print()

    for (bx, by), slots_info in sorted(blocks_to_clean.items()):
        lrs_x, lrs_y = calculate_lrs2_coords(tx, ty, bx, by)
        print(f"  Bloc ({bx},{by}) LRS2=({lrs_x},{lrs_y}):")

        for slot, coverage, mat_id, mat_name in slots_info:
            print(f"    slot[{slot}]: {mat_name} (coverage: {coverage*100:.1f}%)")

    print()

    # Confirmation
    confirm = input(f"Nettoyer {total_slots} slots dans cette tile ? (oui/non) : ").strip().lower()

    if confirm not in ['oui', 'o', 'yes', 'y']:
        print()
        print("[INFO] Nettoyage annulé (dry-run seulement)")
        return 0

    # Backup
    backup_ttile = ttile_path.with_suffix('.ttile.bak')
    backup_layer = layer_path.with_suffix('.dds.bak')

    shutil.copy2(ttile_path, backup_ttile)
    shutil.copy2(layer_path, backup_layer)

    print()
    print(f"[BACKUP] {backup_ttile.name}")
    print(f"[BACKUP] {backup_layer.name}")
    print()

    # Nettoyer les poids dans pixels
    for (bx, by), slots_info in blocks_to_clean.items():
        slots_to_remove = [slot for slot, _, _, _ in slots_info]
        clean_block_weights(pixels, bx, by, slots_to_remove)

    # Mettre à jour LRS2 (supprimer IDs)
    new_lrs2_blocks = {}
    for (bx, by), mat_ids in lrs2_blocks.items():
        if (bx, by) in blocks_to_clean:
            slots_to_remove = {slot for slot, _, _, _ in blocks_to_clean[(bx, by)]}
            new_mat_ids = [mat_id for i, mat_id in enumerate(mat_ids) if i not in slots_to_remove]
            if new_mat_ids:
                new_lrs2_blocks[(bx, by)] = new_mat_ids
        else:
            new_lrs2_blocks[(bx, by)] = mat_ids

    # Écrire
    if not write_lrs2_chunk(ttile_path, new_lrs2_blocks):
        print("[ERR] Échec écriture LRS2")
        return 1

    if not write_layer_dds(layer_path, pixels):
        print("[ERR] Échec écriture _layer.dds")
        return 1

    print(f"[OK] Nettoyage terminé: {total_slots} slots supprimés")
    return 0


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Clean Weights - Gestion poids négligeables',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  python clean_weights.py --scan
  python clean_weights.py --inspect 2,11
  python clean_weights.py --clean 25,0 --threshold 0.02
        """
    )

    # Modes mutuellement exclusifs
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument('--scan', action='store_true',
                           help='Scan rapide de toutes les tiles')
    mode_group.add_argument('--inspect', type=str, metavar='X,Y',
                           help='Générer image debug 800×800 (ex: --inspect 2,11)')
    mode_group.add_argument('--clean', type=str, metavar='X,Y',
                           help='Nettoyer une tile (ex: --clean 25,0)')

    # Paramètre optionnel
    parser.add_argument('--threshold', type=float, default=0.01,
                       help='Seuil de coverage (défaut: 0.01 soit 1%% des pixels)')

    args = parser.parse_args()

    # Chemins
    TERRAIN_ROOT = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain")
    DATA_DIR = TERRAIN_ROOT / ".Data"
    EDITOR_DATA_DIR = TERRAIN_ROOT / ".EditorData"
    TERR_PATH = TERRAIN_ROOT / "terrain.terr"

    if not all([DATA_DIR.exists(), EDITOR_DATA_DIR.exists(), TERR_PATH.exists()]):
        print(f"[ERR] Chemins terrain introuvables")
        return 1

    # Charger surfaces
    surfaces_data = read_mats_from_terr(TERR_PATH)
    surfaces = [e["name"] for e in surfaces_data]

    # Dispatcher
    if args.scan:
        return mode_scan(DATA_DIR, EDITOR_DATA_DIR, args.threshold)

    elif args.inspect:
        try:
            tx, ty = map(int, args.inspect.split(','))
            return mode_inspect(tx, ty, DATA_DIR, EDITOR_DATA_DIR, surfaces, args.threshold)
        except (ValueError, AttributeError):
            print(f"[ERR] Format --inspect invalide : '{args.inspect}'")
            print("      Format attendu : --inspect X,Y (ex: --inspect 2,11)")
            return 1

    elif args.clean:
        try:
            tx, ty = map(int, args.clean.split(','))
            return mode_clean(tx, ty, DATA_DIR, EDITOR_DATA_DIR, surfaces, args.threshold)
        except (ValueError, AttributeError):
            print(f"[ERR] Format --clean invalide : '{args.clean}'")
            print("      Format attendu : --clean X,Y (ex: --clean 25,0)")
            return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
