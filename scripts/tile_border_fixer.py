"""
Tile Border Fixer - Correction des discontinuités entre tiles adjacentes

Étape 1 : Modifier LRS2 dans le .ttile (fusion listes matériaux)
Étape 2 : Modifier _layer.dds (reconstruire poids avec nouveaux slots)

Modes :
- dry-run : affichage terminal LRS2 avant/après + poids (défaut)
- write : réécriture .ttile + _layer.dds avec backup
"""

import json
import numpy as np
import cv2
import struct
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import sys
import shutil

# Ajouter le répertoire parent au path pour imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import modules existants
from terrain_terr_reader import read_mats_from_terr


# ============================================================================
# ÉTAPE 1 : MODIFICATION LRS2 (LISTES MATÉRIAUX)
# ============================================================================

def read_lrs2_from_ttile(ttile_path: Path) -> Optional[Dict[Tuple[int, int], List[int]]]:
    """
    Lit le chunk LRS2 d'un .ttile et retourne les matériaux par bloc.

    Returns:
        Dict {(bx, by): [mat_id_0, mat_id_1, ...]}
    """
    if not ttile_path.exists():
        return None

    try:
        data = ttile_path.read_bytes()

        # Chercher chunk LRS2 (format IFF FORM, big-endian)
        lrs2_offset = data.find(b'LRS2')
        if lrs2_offset == -1:
            return None

        # Taille chunk (big-endian)
        chunk_size = struct.unpack_from('>I', data, lrs2_offset + 4)[0]
        lrs2_data = data[lrs2_offset + 8:lrs2_offset + 8 + chunk_size]

        # Parser blocs
        blocks = {}
        pos = 0

        while pos < len(lrs2_data):
            if pos + 6 > len(lrs2_data):
                break

            index = struct.unpack_from('<I', lrs2_data, pos)[0]
            n = struct.unpack_from('<H', lrs2_data, pos + 4)[0]

            # Coordonnées globales
            bx_global = index & 0x7F
            by_global = (index >> 7) & 0x7F

            # Convertir en local
            bx = bx_global % 4
            by = by_global % 4

            if pos + 6 + n * 2 > len(lrs2_data):
                break

            mat_ids = []
            for i in range(n):
                mat_id = struct.unpack_from('<H', lrs2_data, pos + 6 + i * 2)[0]
                mat_ids.append(mat_id)

            blocks[(bx, by)] = mat_ids
            pos += 6 + n * 2

        return blocks

    except Exception as e:
        print(f"[ERR] Lecture LRS2 échouée: {e}")
        return None


def merge_material_lists(
    list_source: List[int],
    list_target: List[int],
    max_mats: int = 7
) -> List[int]:
    """
    Fusionne deux listes de matériaux (source + cible).

    Args:
        list_source: IDs matériaux du bloc source
        list_target: IDs matériaux du bloc cible
        max_mats: Nombre max de matériaux (7 pour Reforger)

    Returns:
        Liste fusionnée triée par ID croissant, max 7 éléments
    """
    # Union des deux listes
    merged = sorted(set(list_source) | set(list_target))

    # Limiter à max_mats
    if len(merged) > max_mats:
        merged = merged[:max_mats]

    return merged


def write_lrs2_to_ttile(
    ttile_path: Path,
    lrs2_blocks: Dict[Tuple[int, int], List[int]],
    tile_tx: int,
    tile_ty: int
) -> bool:
    """
    Réécrit le chunk LRS2 dans un fichier .ttile.

    Args:
        ttile_path: Chemin du fichier .ttile
        lrs2_blocks: Dict {(bx, by): [mat_ids]}
        tile_tx, tile_ty: Coordonnées de la tile (pour calcul index global)

    Returns:
        True si succès
    """
    try:
        data = bytearray(ttile_path.read_bytes())

        # Chercher chunk LRS2
        lrs2_offset = data.find(b'LRS2')
        if lrs2_offset == -1:
            print("[ERR] Chunk LRS2 non trouvé dans .ttile")
            return False

        # Taille ancienne chunk
        old_chunk_size = struct.unpack_from('>I', data, lrs2_offset + 4)[0]

        # Construire nouveau chunk LRS2
        new_lrs2_data = bytearray()

        for (bx, by), mat_ids in sorted(lrs2_blocks.items()):
            # Index global : (by_global << 7) | bx_global
            bx_global = tile_tx * 4 + bx
            by_global = tile_ty * 4 + by
            index = (by_global << 7) | bx_global

            n = len(mat_ids)

            # Écrire : u32 index, u16 count, u16[] mat_ids
            new_lrs2_data.extend(struct.pack('<I', index))
            new_lrs2_data.extend(struct.pack('<H', n))
            for mat_id in mat_ids:
                new_lrs2_data.extend(struct.pack('<H', mat_id))

        new_chunk_size = len(new_lrs2_data)

        # Remplacer chunk dans data
        # Format IFF : alignement 4 bytes
        old_total_size = 8 + old_chunk_size
        if old_chunk_size % 4:
            old_total_size += 4 - (old_chunk_size % 4)

        new_total_size = 8 + new_chunk_size
        padding = 0
        if new_chunk_size % 4:
            padding = 4 - (new_chunk_size % 4)
            new_total_size += padding

        # Construire nouveau chunk complet
        new_chunk = bytearray()
        new_chunk.extend(b'LRS2')
        new_chunk.extend(struct.pack('>I', new_chunk_size))
        new_chunk.extend(new_lrs2_data)
        if padding:
            new_chunk.extend(b'\x00' * padding)

        # Remplacer dans data
        data[lrs2_offset:lrs2_offset + old_total_size] = new_chunk

        # Mettre à jour la taille du fichier FORM
        # Header FORM : 'FORM' + taille_totale (big-endian)
        form_size = len(data) - 8
        struct.pack_into('>I', data, 4, form_size)

        # Écrire fichier
        ttile_path.write_bytes(data)

        return True

    except Exception as e:
        print(f"[ERR] Écriture LRS2 échouée: {e}")
        return False


# ============================================================================
# ÉTAPE 2 : MODIFICATION LAYER.DDS (POIDS)
# ============================================================================

def decode_dds_r32(dds_path: Path) -> Optional[np.ndarray]:
    """Décode un DDS standard R32_UINT."""
    try:
        data = dds_path.read_bytes()

        if data[:4] != b'DDS ':
            return None

        header = data[:128]
        height = struct.unpack_from('<I', header, 12)[0]
        width = struct.unpack_from('<I', header, 16)[0]

        # Pixels après header (mip 0 seulement)
        pixel_data = data[128:128 + width * height * 4]
        pixels = np.frombuffer(pixel_data, dtype=np.uint32).reshape((height, width))

        return pixels

    except Exception as e:
        print(f"[ERR] Décodage DDS échoué: {e}")
        return None


def extract_weights_from_pixel(pixel_value: int) -> List[int]:
    """Extrait w0-w6 depuis un uint32."""
    weights = []

    # w1-w6 (5 bits chacun)
    for i in range(6):
        w = (pixel_value >> (5 * i)) & 0x1F
        weights.append(w)

    # w0 implicite
    w0 = 31 - sum(weights)
    weights.insert(0, w0)

    return weights


def pack_weights_to_pixel(weights: List[int]) -> int:
    """Encode w0-w6 dans un uint32."""
    # w0 implicite, encoder w1-w6
    pixel = 0
    for i in range(6):
        if i + 1 < len(weights):
            w = int(weights[i + 1])
            pixel |= (w & 0x1F) << (5 * i)

    return pixel


def remap_weights_for_new_slots(
    old_weights: List[int],
    old_mat_ids: List[int],
    new_mat_ids: List[int]
) -> List[int]:
    """
    Remapppe les poids depuis les anciens slots vers les nouveaux.

    Args:
        old_weights: Poids [w0, w1, ..., w6] (max 7)
        old_mat_ids: Ancienne liste matériaux [id0, id1, ...]
        new_mat_ids: Nouvelle liste matériaux fusionnée [id0, id1, ...]

    Returns:
        Nouveaux poids [w0', w1', ..., w6'] alignés sur new_mat_ids
    """
    new_weights = [0] * 7

    for i, mat_id in enumerate(old_mat_ids):
        if i >= len(old_weights):
            break

        # Trouver l'index du matériau dans la nouvelle liste
        if mat_id in new_mat_ids:
            new_idx = new_mat_ids.index(mat_id)
            if new_idx < 7:
                new_weights[new_idx] = old_weights[i]

    return new_weights


def inject_source_weights_by_slope(
    target_weights: List[int],
    source_weights: List[int],
    slope: float
) -> List[int]:
    """
    Injecte les poids source dans les poids cible selon ratio pente.

    Args:
        target_weights: Poids cible [w0, ..., w6]
        source_weights: Poids source [w0, ..., w6]
        slope: Pente en degrés

    Returns:
        Poids mixés
    """
    # Déterminer alpha selon pente
    if slope > 20.0:
        alpha = 0.7  # 70% source
    elif slope > 10.0:
        alpha = 0.4  # 40% source
    else:
        alpha = 0.2  # 20% source

    # Mixer
    mixed = [
        alpha * s + (1 - alpha) * t
        for s, t in zip(source_weights, target_weights)
    ]

    return mixed


def renormalize_weights(weights: List[float]) -> List[int]:
    """
    Renormalise les poids pour que la somme = 31.

    Args:
        weights: Poids flottants

    Returns:
        Poids entiers sommant à 31
    """
    total = sum(weights)

    if total < 0.001:
        return [31] + [0] * 6

    # Normaliser
    normalized = [(w / total) * 31 for w in weights]

    # Arrondir
    rounded = [int(round(w)) for w in normalized]

    # Ajuster pour atteindre exactement 31
    current_sum = sum(rounded)
    diff = 31 - current_sum

    if diff != 0:
        # Distribuer la différence sur les matériaux avec les plus gros poids
        sorted_indices = sorted(range(len(rounded)), key=lambda i: rounded[i], reverse=True)

        if diff > 0:
            for i in range(diff):
                idx = sorted_indices[i % len(sorted_indices)]
                rounded[idx] += 1
        else:
            for i in range(-diff):
                idx = sorted_indices[i % len(sorted_indices)]
                if rounded[idx] > 0:
                    rounded[idx] -= 1

    # Clipper individuellement
    rounded = [max(0, min(31, w)) for w in rounded]

    return rounded


def write_dds_r32(pixels: np.ndarray, path: Path) -> bool:
    """Écrit un fichier DDS R32_UINT avec 10 mipmaps."""
    try:
        height, width = pixels.shape

        # Header DDS (128 bytes)
        header = bytearray(128)
        header[0:4] = b'DDS '
        struct.pack_into('<I', header, 4, 124)
        struct.pack_into('<I', header, 8, 0x1 | 0x2 | 0x4 | 0x1000 | 0x20000)
        struct.pack_into('<I', header, 12, height)
        struct.pack_into('<I', header, 16, width)
        struct.pack_into('<I', header, 20, width * 4)
        struct.pack_into('<I', header, 24, 1)
        struct.pack_into('<I', header, 28, 10)
        struct.pack_into('<I', header, 76, 32)
        struct.pack_into('<I', header, 80, 0x00000004)
        header[84:88] = b'    '
        struct.pack_into('<I', header, 108, 0x1000 | 0x400000 | 0x8)

        with open(path, 'wb') as f:
            # Écrire header
            f.write(header)

            # Mip 0 (512×512)
            f.write(pixels.astype(np.uint32).tobytes())

            # Mips suivants (downsampled)
            mip = pixels
            for _ in range(9):
                mip = mip[::2, ::2]
                f.write(mip.astype(np.uint32).tobytes())

        return True

    except Exception as e:
        print(f"[ERR] Écriture DDS échouée: {e}")
        return False


# ============================================================================
# UTILITAIRES PENTE & BORD
# ============================================================================

def load_bterr_heightmap(bterr_path: Path) -> Optional[np.ndarray]:
    """Charge la heightmap depuis un fichier .bterr."""
    if not bterr_path.exists():
        return None

    try:
        data = open(bterr_path, "rb").read()
        i = data.find(b"DATA")
        if i < 0:
            return None

        sz = struct.unpack_from(">I", data, i + 4)[0]
        hm = np.frombuffer(data[i + 8:i + 8 + sz], np.float32).reshape(129, 129)
        return hm.astype(np.float64)
    except Exception:
        return None


def calculate_slope_for_block(heightmap: np.ndarray, bx: int, by: int, cellsize: float = 4.0) -> float:
    """Calcule la pente moyenne (en degrés) pour un bloc 32×32."""
    x0 = bx * 32
    y0 = by * 32
    x1 = x0 + 33
    y1 = y0 + 33

    block_hm = heightmap[y0:y1, x0:x1]

    gy, gx = np.gradient(block_hm, cellsize)
    slope_rad = np.arctan(np.hypot(gx, gy))
    slope_deg = np.degrees(slope_rad)

    return float(slope_deg.mean())


def get_border_blocks(direction: str) -> List[Tuple[int, int]]:
    """
    Retourne les 4 blocs du bord selon la direction.

    Args:
        direction: 'N', 'S', 'E', 'O'

    Returns:
        Liste de (bx, by) pour les 4 blocs du bord
    """
    if direction == 'N':
        return [(0, 0), (1, 0), (2, 0), (3, 0)]
    elif direction == 'S':
        return [(0, 3), (1, 3), (2, 3), (3, 3)]
    elif direction == 'E':
        return [(3, 0), (3, 1), (3, 2), (3, 3)]
    elif direction == 'O':
        return [(0, 0), (0, 1), (0, 2), (0, 3)]
    else:
        raise ValueError(f"Direction invalide: {direction}")


def get_opposite_direction(direction: str) -> str:
    """Retourne la direction opposée."""
    opposites = {'N': 'S', 'S': 'N', 'E': 'O', 'O': 'E'}
    return opposites[direction]


# ============================================================================
# AFFICHAGE DRY-RUN
# ============================================================================

def print_lrs2_comparison(
    lrs2_before: Dict[Tuple[int, int], List[int]],
    lrs2_after: Dict[Tuple[int, int], List[int]],
    border_blocks: List[Tuple[int, int]],
    surfaces: List[str]
) -> None:
    """
    Affiche les listes LRS2 avant/après pour chaque bloc du bord.

    Args:
        lrs2_before: LRS2 avant fusion
        lrs2_after: LRS2 après fusion
        border_blocks: Blocs concernés
        surfaces: Liste noms surfaces
    """
    print()
    print("=" * 80)
    print("ÉTAPE 1 - MODIFICATION LRS2 (LISTES MATÉRIAUX)")
    print("=" * 80)
    print()

    for bx, by in border_blocks:
        before = lrs2_before.get((bx, by), [])
        after = lrs2_after.get((bx, by), [])

        print(f"Bloc ({bx},{by}):")
        print(f"  AVANT: {len(before)} mats -> {before}")

        if before:
            for i, mat_id in enumerate(before):
                mat_name = surfaces[mat_id] if mat_id < len(surfaces) else f"MAT_{mat_id}"
                print(f"    [{i}] ID {mat_id:3d} = {mat_name}")

        print(f"  APRES: {len(after)} mats -> {after}")

        if after:
            for i, mat_id in enumerate(after):
                mat_name = surfaces[mat_id] if mat_id < len(surfaces) else f"MAT_{mat_id}"
                added = " [+AJOUTÉ]" if mat_id not in before else ""
                print(f"    [{i}] ID {mat_id:3d} = {mat_name}{added}")

        print()


def print_weights_comparison(
    pixels_before: np.ndarray,
    pixels_after: np.ndarray,
    lrs2_before: Dict[Tuple[int, int], List[int]],
    lrs2_after: Dict[Tuple[int, int], List[int]],
    border_blocks: List[Tuple[int, int]],
    slopes: Dict[Tuple[int, int], float],
    surfaces: List[str],
    direction: str
) -> None:
    """
    Affiche les poids moyens avant/après pour chaque bloc du bord.

    Args:
        pixels_before: Pixels DDS avant (512, 512) uint32
        pixels_after: Pixels DDS après (512, 512) uint32
        lrs2_before: LRS2 avant fusion
        lrs2_after: LRS2 après fusion
        border_blocks: Blocs concernés
        slopes: Pentes par bloc
        surfaces: Liste noms surfaces
        direction: Direction du bord ('N', 'S', 'E', 'O')
    """
    print()
    print("=" * 80)
    print("ÉTAPE 2 - MODIFICATION LAYER.DDS (POIDS)")
    print("=" * 80)
    print()

    for bx, by in border_blocks:
        slope = slopes.get((bx, by), 0.0)
        mat_ids_before = lrs2_before.get((bx, by), [])
        mat_ids_after = lrs2_after.get((bx, by), [])

        print(f"Bloc ({bx},{by}) - Pente: {slope:.1f}°")
        print()

        # Extraire pixels du bloc (bord seulement)
        block_x0 = bx * 128
        block_y0 = by * 128

        # Sélectionner bord selon direction
        if direction == 'N':
            border_pixels_before = pixels_before[block_y0:block_y0 + 4, block_x0:block_x0 + 128]
            border_pixels_after = pixels_after[block_y0:block_y0 + 4, block_x0:block_x0 + 128]
        elif direction == 'S':
            border_pixels_before = pixels_before[block_y0 + 124:block_y0 + 128, block_x0:block_x0 + 128]
            border_pixels_after = pixels_after[block_y0 + 124:block_y0 + 128, block_x0:block_x0 + 128]
        elif direction == 'E':
            border_pixels_before = pixels_before[block_y0:block_y0 + 128, block_x0 + 124:block_x0 + 128]
            border_pixels_after = pixels_after[block_y0:block_y0 + 128, block_x0 + 124:block_x0 + 128]
        elif direction == 'O':
            border_pixels_before = pixels_before[block_y0:block_y0 + 128, block_x0:block_x0 + 4]
            border_pixels_after = pixels_after[block_y0:block_y0 + 128, block_x0:block_x0 + 4]
        else:
            continue

        # Calculer poids moyens
        num_pixels = border_pixels_before.size
        weights_before_sum = [0.0] * 7
        weights_after_sum = [0.0] * 7

        for pixel in border_pixels_before.flat:
            w = extract_weights_from_pixel(int(pixel))
            for i in range(len(mat_ids_before)):
                weights_before_sum[i] += w[i]

        for pixel in border_pixels_after.flat:
            w = extract_weights_from_pixel(int(pixel))
            for i in range(len(mat_ids_after)):
                weights_after_sum[i] += w[i]

        weights_before_avg = [w / num_pixels for w in weights_before_sum]
        weights_after_avg = [w / num_pixels for w in weights_after_sum]

        # Afficher AVANT
        print("  AVANT (slots anciens):")
        for i, mat_id in enumerate(mat_ids_before):
            if i >= 7:
                break
            mat_name = surfaces[mat_id] if mat_id < len(surfaces) else f"MAT_{mat_id}"
            pct = (weights_before_avg[i] / 31.0) * 100
            print(f"    w{i} -> ID {mat_id:3d} ({mat_name:30s}): {weights_before_avg[i]:5.2f}/31 = {pct:5.1f}%")

        # Afficher APRES
        print()
        print("  APRES (slots fusionnés + injection source):")
        for i, mat_id in enumerate(mat_ids_after):
            if i >= 7:
                break
            mat_name = surfaces[mat_id] if mat_id < len(surfaces) else f"MAT_{mat_id}"
            pct = (weights_after_avg[i] / 31.0) * 100
            delta = weights_after_avg[i] - weights_before_avg[i] if i < len(weights_before_avg) else weights_after_avg[i]
            delta_str = f"({delta:+5.2f})" if abs(delta) > 0.01 else ""
            added = " [+NOUVEAU]" if mat_id not in mat_ids_before else ""
            print(f"    w{i} -> ID {mat_id:3d} ({mat_name:30s}): {weights_after_avg[i]:5.2f}/31 = {pct:5.1f}% {delta_str}{added}")

        print()



def main():
    """Point d'entrée principal."""
    print("=" * 80)
    print("TILE BORDER FIXER - Correction discontinuités LRS2 + Layer.dds")
    print("=" * 80)
    print()

    # Saisie interactive - coordonnées LRS2 globales
    print("Entrez les coordonnées LRS2 du bloc SOURCE adjacent au bord (ex: 6,55) :")
    src = input("Bloc source : ")
    lrs_src_x, lrs_src_y = map(int, src.strip().split(','))

    print("Entrez les coordonnées LRS2 du bloc CIBLE à corriger (ex: 6,56) :")
    tgt = input("Bloc cible : ")
    lrs_tgt_x, lrs_tgt_y = map(int, tgt.strip().split(','))

    print()

    # Déduire tiles et blocs depuis coordonnées LRS2 globales
    src_tx, src_bx = lrs_src_x // 4, lrs_src_x % 4
    src_ty, src_by = lrs_src_y // 4, lrs_src_y % 4

    tgt_tx, tgt_bx = lrs_tgt_x // 4, lrs_tgt_x % 4
    tgt_ty, tgt_by = lrs_tgt_y // 4, lrs_tgt_y % 4

    tile_id_source = src_ty * 32 + src_tx
    tile_id_target = tgt_ty * 32 + tgt_tx

    print(f"[SOURCE] LRS2 ({lrs_src_x},{lrs_src_y}) -> Tile ({src_tx},{src_ty}) ID {tile_id_source}, bloc ({src_bx},{src_by})")
    print(f"[CIBLE]  LRS2 ({lrs_tgt_x},{lrs_tgt_y}) -> Tile ({tgt_tx},{tgt_ty}) ID {tile_id_target}, bloc ({tgt_bx},{tgt_by})")

    # Déduire direction automatiquement
    dy = tgt_ty - src_ty
    dx = tgt_tx - src_tx

    if dy == 1 and dx == 0:
        direction = 'N'
        border_blocks = [(i, 0) for i in range(4)]
    elif dy == -1 and dx == 0:
        direction = 'S'
        border_blocks = [(i, 3) for i in range(4)]
    elif dx == 1 and dy == 0:
        direction = 'O'
        border_blocks = [(0, i) for i in range(4)]
    elif dx == -1 and dy == 0:
        direction = 'E'
        border_blocks = [(3, i) for i in range(4)]
    else:
        print(f"[ERR] Blocs non adjacents : dx={dx}, dy={dy}")
        return 1

    print(f"[DIR] {direction} -> Correction bord {direction} de la tile cible ({len(border_blocks)} blocs)")
    print()

    # Chemins
    PROJECT_ROOT = Path(__file__).parent.parent
    TERRAIN_ROOT = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain")
    DATA_DIR = TERRAIN_ROOT / ".Data"
    EDITOR_DATA_DIR = TERRAIN_ROOT / ".EditorData"
    TERR_PATH = TERRAIN_ROOT / "terrain.terr"

    if not DATA_DIR.exists() or not EDITOR_DATA_DIR.exists() or not TERR_PATH.exists():
        print(f"[ERR] Chemins terrain introuvables")
        return 1

    # Charger surfaces
    print("[LOAD] Surfaces terrain.terr...")
    surfaces = [e["name"] for e in read_mats_from_terr(TERR_PATH)]
    print(f"   [OK] {len(surfaces)} surfaces")
    print()

    # Charger LRS2
    print(f"[LRS2] Lecture .ttile...")
    ttile_source = DATA_DIR / f"Terrain_{tile_id_source}.ttile"
    ttile_target = DATA_DIR / f"Terrain_{tile_id_target}.ttile"

    if not ttile_source.exists() or not ttile_target.exists():
        print(f"[ERR] Fichiers .ttile manquants")
        return 1

    lrs2_source = read_lrs2_from_ttile(ttile_source)
    lrs2_target = read_lrs2_from_ttile(ttile_target)

    if lrs2_source is None or lrs2_target is None:
        print(f"[ERR] Échec lecture LRS2")
        return 1

    print(f"   [OK] Source: {len(lrs2_source)} blocs, Cible: {len(lrs2_target)} blocs")
    print()

    # ÉTAPE 1 : Fusionner LRS2
    print("[ETAPE 1] Fusion listes LRS2 source + cible...")
    lrs2_merged = lrs2_target.copy()
    direction_source = get_opposite_direction(direction)

    for bx_tgt, by_tgt in border_blocks:
        # Trouver bloc source correspondant
        if direction == 'N':
            bx_src, by_src = bx_tgt, 3
        elif direction == 'S':
            bx_src, by_src = bx_tgt, 0
        elif direction == 'O':
            bx_src, by_src = 3, by_tgt
        elif direction == 'E':
            bx_src, by_src = 0, by_tgt
        else:
            continue

        mats_src = lrs2_source.get((bx_src, by_src), [])
        mats_tgt = lrs2_target.get((bx_tgt, by_tgt), [])

        # Fusionner
        mats_merged = merge_material_lists(mats_src, mats_tgt)
        lrs2_merged[(bx_tgt, by_tgt)] = mats_merged

    # Afficher comparaison LRS2
    print_lrs2_comparison(lrs2_target, lrs2_merged, border_blocks, surfaces)

    # Charger layer.dds
    print("[LOAD] Lecture _layer.dds...")
    layer_source_path = EDITOR_DATA_DIR / f"Terrain_{tile_id_source}_layer.edds"
    if not layer_source_path.exists():
        layer_source_path = EDITOR_DATA_DIR / f"Terrain_{tile_id_source}_layer.dds"

    layer_target_path = EDITOR_DATA_DIR / f"Terrain_{tile_id_target}_layer.edds"
    if not layer_target_path.exists():
        layer_target_path = EDITOR_DATA_DIR / f"Terrain_{tile_id_target}_layer.dds"

    if not layer_source_path.exists() or not layer_target_path.exists():
        print(f"[ERR] Fichiers _layer manquants")
        return 1

    pixels_source = decode_dds_r32(layer_source_path)
    pixels_target = decode_dds_r32(layer_target_path)

    if pixels_source is None or pixels_target is None:
        print(f"[ERR] Échec décodage DDS")
        return 1

    print(f"   [OK] Pixels source: {pixels_source.shape}, cible: {pixels_target.shape}")
    print()

    # Charger pentes
    print("[SLOPE] Calcul pentes...")
    bterr_target_path = EDITOR_DATA_DIR / f"Terrain_{tile_id_target}.bterr"
    slopes = {}

    if bterr_target_path.exists():
        heightmap = load_bterr_heightmap(bterr_target_path)
        if heightmap is not None:
            for by in range(4):
                for bx in range(4):
                    slopes[(bx, by)] = calculate_slope_for_block(heightmap, bx, by)

    print(f"   [OK] {len(slopes)} pentes calculées")
    print()

    # ÉTAPE 2 : Reconstruire poids avec nouveaux slots + injection
    print("[ETAPE 2] Reconstruction poids layer.dds...")
    pixels_corrected = pixels_target.copy()

    for bx_tgt, by_tgt in border_blocks:
        # Coordonnées bloc source
        if direction == 'N':
            bx_src, by_src = bx_tgt, 3
        elif direction == 'S':
            bx_src, by_src = bx_tgt, 0
        elif direction == 'O':
            bx_src, by_src = 3, by_tgt
        elif direction == 'E':
            bx_src, by_src = 0, by_tgt
        else:
            continue

        # Listes matériaux
        mats_src = lrs2_source.get((bx_src, by_src), [])
        mats_tgt_old = lrs2_target.get((bx_tgt, by_tgt), [])
        mats_tgt_new = lrs2_merged.get((bx_tgt, by_tgt), [])

        # Pente
        slope = slopes.get((bx_tgt, by_tgt), 0.0)

        # Traiter pixels du bord
        block_x0 = bx_tgt * 128
        block_y0 = by_tgt * 128

        if direction == 'N':
            y_range, x_range = range(block_y0, block_y0 + 4), range(block_x0, block_x0 + 128)
        elif direction == 'S':
            y_range, x_range = range(block_y0 + 124, block_y0 + 128), range(block_x0, block_x0 + 128)
        elif direction == 'O':
            y_range, x_range = range(block_y0, block_y0 + 128), range(block_x0, block_x0 + 4)
        elif direction == 'E':
            y_range, x_range = range(block_y0, block_y0 + 128), range(block_x0 + 124, block_x0 + 128)
        else:
            continue

        # Coordonnées source correspondantes
        block_src_x0 = bx_src * 128
        block_src_y0 = by_src * 128

        if direction_source == 'N':
            src_y_range, src_x_range = range(block_src_y0, block_src_y0 + 4), range(block_src_x0, block_src_x0 + 128)
        elif direction_source == 'S':
            src_y_range, src_x_range = range(block_src_y0 + 124, block_src_y0 + 128), range(block_src_x0, block_src_x0 + 128)
        elif direction_source == 'O':
            src_y_range, src_x_range = range(block_src_y0, block_src_y0 + 128), range(block_src_x0, block_src_x0 + 4)
        elif direction_source == 'E':
            src_y_range, src_x_range = range(block_src_y0, block_src_y0 + 128), range(block_src_x0 + 124, block_src_x0 + 128)
        else:
            continue

        # Convertir en listes pour itération parallèle
        coords_tgt = [(y, x) for y in y_range for x in x_range]
        coords_src = [(y, x) for y in src_y_range for x in src_x_range]

        for (y_tgt, x_tgt), (y_src, x_src) in zip(coords_tgt, coords_src):
            # Décoder poids ancien cible
            pixel_tgt = int(pixels_target[y_tgt, x_tgt])
            weights_tgt_old = extract_weights_from_pixel(pixel_tgt)

            # Décoder poids source
            pixel_src = int(pixels_source[y_src, x_src])
            weights_src_old = extract_weights_from_pixel(pixel_src)

            # Remapper poids cible vers nouveaux slots
            weights_tgt_new = remap_weights_for_new_slots(weights_tgt_old, mats_tgt_old, mats_tgt_new)

            # Remapper poids source vers nouveaux slots
            weights_src_new = remap_weights_for_new_slots(weights_src_old, mats_src, mats_tgt_new)

            # Injecter poids source selon pente
            weights_mixed = inject_source_weights_by_slope(weights_tgt_new, weights_src_new, slope)

            # Renormaliser
            weights_final = renormalize_weights(weights_mixed)

            # Encoder pixel
            pixel_final = pack_weights_to_pixel(weights_final)
            pixels_corrected[y_tgt, x_tgt] = pixel_final

    print("   [OK] Poids reconstruits")
    print()

    # Afficher comparaison poids
    print_weights_comparison(
        pixels_target, pixels_corrected,
        lrs2_target, lrs2_merged,
        border_blocks, slopes, surfaces, direction
    )

    # Demander confirmation
    print()
    write_confirm = input("Écrire les modifications (.ttile + _layer.dds) ? (oui/non) : ").strip().lower()

    if write_confirm in ['oui', 'o', 'yes', 'y']:
        print()
        print("=" * 80)
        print("MODE WRITE")
        print("=" * 80)

        # Backup
        backup_ttile = ttile_target.with_suffix('.ttile.backup')
        backup_layer = layer_target_path.with_suffix(layer_target_path.suffix + '.backup')

        print(f"[BACKUP] .ttile -> {backup_ttile}")
        shutil.copy2(ttile_target, backup_ttile)

        print(f"[BACKUP] layer -> {backup_layer}")
        shutil.copy2(layer_target_path, backup_layer)

        # Écrire LRS2
        print(f"[WRITE] Écriture LRS2 dans .ttile...")
        success_lrs2 = write_lrs2_to_ttile(ttile_target, lrs2_merged, tgt_tx, tgt_ty)

        if not success_lrs2:
            print(f"[ERR] Échec écriture LRS2")
            return 1

        print(f"   [OK] LRS2 écrit")

        # Écrire DDS
        print(f"[WRITE] Écriture _layer.dds...")
        success_dds = write_dds_r32(pixels_corrected, layer_target_path)

        if not success_dds:
            print(f"[ERR] Échec écriture DDS")
            return 1

        print(f"   [OK] DDS écrit")
        print()
        print("[OK] TERMINÉ")
        print(f"   Backups: {backup_ttile.name}, {backup_layer.name}")
    else:
        print()
        print("[INFO] Modifications NON appliquées (dry-run)")

    print()
    print("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(main())
