"""
Migrate Default Grass - Remplace Grass_03_default par Grass_03 dans tous les LRS2

Scanne tous les fichiers Terrain_*.ttile et remplace l'ID de Grass_03_default
par l'ID de Grass_03 dans les chunks LRS2.

Les poids dans _layer.dds n'ont pas besoin d'être modifiés - seul l'ID du matériau
dans le LRS2 change, les slots w0-w6 restent identiques.

Modes :
- Migration complète : python migrate_default_grass.py
- Test sur une tile  : python migrate_default_grass.py --test-tile x,y
"""

import struct
import sys
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import shutil

# Import module terrain reader
sys.path.insert(0, str(Path(__file__).parent.parent))
from terrain_terr_reader import read_mats_from_terr


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

    except Exception:
        return None


def replace_material_in_lrs2(
    lrs2_blocks: Dict[Tuple[int, int], List[int]],
    old_id: int,
    new_id: int
) -> Tuple[Dict[Tuple[int, int], List[int]], int]:
    """
    Remplace un ID matériau par un autre dans tous les blocs LRS2.

    Args:
        lrs2_blocks: Dict {(bx, by): [mat_ids]}
        old_id: ID matériau à remplacer
        new_id: Nouvel ID matériau

    Returns:
        (lrs2_modifié, nombre_blocs_modifiés)
    """
    modified_blocks = lrs2_blocks.copy()
    count = 0

    for (bx, by), mat_ids in lrs2_blocks.items():
        if old_id in mat_ids:
            # Remplacer old_id par new_id
            new_mat_ids = [new_id if mat_id == old_id else mat_id for mat_id in mat_ids]
            modified_blocks[(bx, by)] = new_mat_ids
            count += 1

    return modified_blocks, count


def decode_dds_r32(dds_path: Path) -> Optional[List[List[int]]]:
    """Décode un DDS standard R32_UINT et retourne les pixels."""
    try:
        data = dds_path.read_bytes()

        if data[:4] != b'DDS ':
            return None

        header = data[:128]
        height = struct.unpack_from('<I', header, 12)[0]
        width = struct.unpack_from('<I', header, 16)[0]

        # Pixels après header (mip 0 seulement)
        pixel_data = data[128:128 + width * height * 4]

        # Convertir en liste de listes d'entiers
        pixels = []
        for i in range(height):
            row = []
            for j in range(width):
                offset = (i * width + j) * 4
                pixel = struct.unpack_from('<I', pixel_data, offset)[0]
                row.append(pixel)
            pixels.append(row)

        return pixels

    except Exception:
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


def renormalize_weights(weights: List[int]) -> List[int]:
    """
    Renormalise les poids pour que la somme = 31.

    Args:
        weights: Liste de poids [w0, w1, ..., w6]

    Returns:
        Poids renormalisés sommant à 31
    """
    total = sum(weights)

    if total == 0:
        return [31] + [0] * 6

    if total == 31:
        return weights

    # Normaliser proportionnellement
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


def write_dds_r32(pixels: List[List[int]], path: Path) -> bool:
    """Écrit un fichier DDS R32_UINT avec 10 mipmaps."""
    try:
        height = len(pixels)
        width = len(pixels[0]) if height > 0 else 0

        if width != 512 or height != 512:
            return False

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
            for row in pixels:
                for pixel in row:
                    f.write(struct.pack('<I', pixel))

            # Mips suivants (downsampled)
            mip = [[pixels[y][x] for x in range(width)] for y in range(height)]
            for _ in range(9):
                # Downsample 2x2
                new_height = len(mip) // 2
                new_width = len(mip[0]) // 2
                mip = [[mip[y*2][x*2] for x in range(new_width)] for y in range(new_height)]

                # Écrire mip
                for row in mip:
                    for pixel in row:
                        f.write(struct.pack('<I', pixel))

        return True

    except Exception:
        return False


def merge_duplicate_blocks(
    lrs2_blocks: Dict[Tuple[int, int], List[int]],
    pixels: List[List[int]],
    grass_default_id: int,
    grass_03_id: int
) -> Tuple[Dict[Tuple[int, int], List[int]], List[List[int]], int, int]:
    """
    Fusionne les poids pour les blocs contenant les deux matériaux.

    Pour chaque bloc avec doublon :
    - Additionne les poids : w_grass03 += w_grass03_default
    - Clip à 31 max
    - Met à zéro w_grass03_default
    - Supprime Grass_03_default de la liste LRS2
    - Renormalise si sum > 31

    Args:
        lrs2_blocks: Dict {(bx, by): [mat_ids]}
        pixels: Matrice 512×512 de pixels DDS
        grass_default_id: ID de Grass_03_default
        grass_03_id: ID de Grass_03

    Returns:
        (lrs2_modifié, pixels_modifiés, blocs_avec_fusion, blocs_remplacement_simple)
    """
    modified_lrs2 = {}
    modified_pixels = [row[:] for row in pixels]  # Deep copy

    fusion_count = 0
    simple_count = 0

    for (bx, by), mat_ids in lrs2_blocks.items():
        has_default = grass_default_id in mat_ids
        has_grass = grass_03_id in mat_ids

        if has_default and has_grass:
            # CAS 1 : DOUBLON - Fusion nécessaire
            fusion_count += 1

            slot_default = mat_ids.index(grass_default_id)
            slot_grass = mat_ids.index(grass_03_id)

            # Traiter chaque pixel du bloc (128×128)
            block_x0 = bx * 128
            block_y0 = by * 128

            for y in range(block_y0, min(block_y0 + 128, 512)):
                for x in range(block_x0, min(block_x0 + 128, 512)):
                    pixel = modified_pixels[y][x]
                    weights = extract_weights_from_pixel(pixel)

                    # Fusionner : w_grass03 += w_default
                    if slot_grass < len(weights) and slot_default < len(weights):
                        weights[slot_grass] += weights[slot_default]
                        weights[slot_grass] = min(weights[slot_grass], 31)
                        weights[slot_default] = 0

                    # Renormaliser si nécessaire
                    total = sum(weights)
                    if total > 31:
                        weights = renormalize_weights(weights)

                    # Ré-encoder le pixel
                    modified_pixels[y][x] = pack_weights_to_pixel(weights)

            # Supprimer Grass_03_default de la liste LRS2
            new_mat_ids = [mid for mid in mat_ids if mid != grass_default_id]
            modified_lrs2[(bx, by)] = new_mat_ids

        elif has_default:
            # CAS 2 : Seulement Grass_03_default - Remplacement simple
            simple_count += 1

            # Remplacer l'ID dans la liste LRS2
            new_mat_ids = [grass_03_id if mid == grass_default_id else mid for mid in mat_ids]
            modified_lrs2[(bx, by)] = new_mat_ids

            # Pixels inchangés

        else:
            # CAS 3 : Ni l'un ni l'autre - Copie directe
            modified_lrs2[(bx, by)] = mat_ids[:]

    return modified_lrs2, modified_pixels, fusion_count, simple_count


def analyze_duplicates(
    data_dir: Path,
    editor_data_dir: Path,
    affected_tiles: Dict[int, int],
    grass_default_id: int,
    grass_03_id: int
) -> None:
    """
    Analyse les blocs qui contiennent les deux matériaux (doublons).

    Pour chaque tile concernée :
    - Identifie les blocs avec les deux IDs
    - Lit le _layer.dds pour extraire les poids moyens
    - Classe les doublons en négligeables (≤1/31) ou significatifs (>1/31)

    Args:
        data_dir: Dossier .Data/ contenant les .ttile
        editor_data_dir: Dossier .EditorData/ contenant les _layer.dds
        affected_tiles: Dict {tile_id: nombre_blocs_concernés}
        grass_default_id: ID de Grass_03_default
        grass_03_id: ID de Grass_03
    """
    print()
    print("=" * 80)
    print("ANALYSE DES DOUBLONS")
    print("=" * 80)
    print()

    total_duplicates = 0
    negligible_count = 0
    significant_count = 0

    all_default_weights = []
    all_grass_weights = []

    for tile_id in sorted(affected_tiles.keys()):
        ttile_path = data_dir / f"Terrain_{tile_id}.ttile"

        # Lire LRS2
        lrs2_blocks = read_lrs2_from_ttile(ttile_path)
        if lrs2_blocks is None:
            continue

        # Identifier blocs avec doublon
        duplicate_blocks = []
        for (bx, by), mat_ids in lrs2_blocks.items():
            if grass_default_id in mat_ids and grass_03_id in mat_ids:
                duplicate_blocks.append((bx, by))

        if not duplicate_blocks:
            continue

        # Lire _layer.dds
        layer_path = editor_data_dir / f"Terrain_{tile_id}_layer.edds"
        if not layer_path.exists():
            layer_path = editor_data_dir / f"Terrain_{tile_id}_layer.dds"

        if not layer_path.exists():
            continue

        pixels = decode_dds_r32(layer_path)
        if pixels is None:
            continue

        # Analyser chaque bloc doublon
        for bx, by in duplicate_blocks:
            mat_ids = lrs2_blocks[(bx, by)]

            # Trouver les slots des deux matériaux
            slot_default = mat_ids.index(grass_default_id) if grass_default_id in mat_ids else -1
            slot_grass = mat_ids.index(grass_03_id) if grass_03_id in mat_ids else -1

            if slot_default == -1 or slot_grass == -1:
                continue

            # Extraire les pixels du bloc (128x128)
            block_x0 = bx * 128
            block_y0 = by * 128

            weights_default_sum = 0.0
            weights_grass_sum = 0.0
            pixel_count = 0

            for y in range(block_y0, block_y0 + 128):
                for x in range(block_x0, block_x0 + 128):
                    if y >= len(pixels) or x >= len(pixels[0]):
                        continue

                    pixel = pixels[y][x]
                    weights = extract_weights_from_pixel(pixel)

                    if slot_default < len(weights):
                        weights_default_sum += weights[slot_default]

                    if slot_grass < len(weights):
                        weights_grass_sum += weights[slot_grass]

                    pixel_count += 1

            if pixel_count == 0:
                continue

            # Calculer poids moyens
            avg_default = weights_default_sum / pixel_count
            avg_grass = weights_grass_sum / pixel_count

            all_default_weights.append(avg_default)
            all_grass_weights.append(avg_grass)

            total_duplicates += 1

            # Classifier
            if avg_default <= 1.0:
                negligible_count += 1
            else:
                significant_count += 1

    # Afficher résumé
    print(f"[DOUBLONS] Blocs contenant les deux matériaux : {total_duplicates}")
    print()

    if total_duplicates > 0:
        avg_default_overall = sum(all_default_weights) / len(all_default_weights)
        avg_grass_overall = sum(all_grass_weights) / len(all_grass_weights)

        print(f"  Classification :")
        print(f"    -> Grass_03_default négligeable (<=1/31) : {negligible_count} blocs")
        print(f"       Action : suppression simple de l'ID, pas de fusion nécessaire")
        print()
        print(f"    -> Grass_03_default significatif (>1/31) : {significant_count} blocs")
        print(f"       Action : fusion des poids nécessaire (non implémentée)")
        print()
        print(f"  Poids moyens sur l'ensemble des doublons :")
        print(f"    Grass_03_default : {avg_default_overall:5.2f}/31 ({avg_default_overall/31*100:4.1f}%)")
        print(f"    Grass_03         : {avg_grass_overall:5.2f}/31 ({avg_grass_overall/31*100:4.1f}%)")
        print()

        if significant_count > 0:
            print(f"  [WARN] {significant_count} blocs nécessitent une fusion de poids")
            print(f"         La migration simple écrasera les poids de Grass_03_default")
            print(f"         Considérez d'implémenter la fusion avant de continuer")
    else:
        print("  [OK] Aucun bloc ne contient les deux matériaux simultanément")
        print("       Migration simple sans risque de perte")

    print()
    print("=" * 80)


def validate_ttile_structure(data: bytearray) -> bool:
    """
    Valide la structure du .ttile après modification.

    Vérifications :
    1. FORM taille = len(data) - 8
    2. Tous les chunks s'enchaînent correctement

    Args:
        data: Données .ttile en mémoire

    Returns:
        True si validations passent
    """
    # Vérification 1 : FORM header
    if data[0:4] != b'FORM':
        return False

    form_size_declared = struct.unpack_from('>I', data, 4)[0]
    form_size_actual = len(data) - 8

    if form_size_declared != form_size_actual:
        return False

    if data[8:12] != b'TERR':
        return False

    # Vérification 2 : Enchaînement des chunks
    pos = 12  # Après header FORM + type TERR
    chunk_count = 0

    while pos + 8 <= len(data):
        chunk_size = struct.unpack_from('>I', data, pos+4)[0]

        if chunk_size > len(data) or pos + 8 + chunk_size > len(data):
            return False

        # Padding IFF 2 bytes
        padding = chunk_size % 2
        pos = pos + 8 + chunk_size + padding

        chunk_count += 1

        if chunk_count > 100:  # Sécurité
            return False

    if pos != len(data):
        return False

    return True


def write_lrs2_to_ttile(
    ttile_path: Path,
    lrs2_blocks: Dict[Tuple[int, int], List[int]],
    tile_id: int
) -> bool:
    """
    Réécrit le chunk LRS2 dans un fichier .ttile.

    Args:
        ttile_path: Chemin du fichier .ttile
        lrs2_blocks: Dict {(bx, by): [mat_ids]}
        tile_id: ID de la tile (pour calcul coordonnées globales)

    Returns:
        True si succès
    """
    try:
        data = bytearray(ttile_path.read_bytes())

        # Chercher chunk LRS2
        lrs2_offset = data.find(b'LRS2')
        if lrs2_offset == -1:
            return False

        # Taille ancienne chunk
        old_chunk_size = struct.unpack_from('>I', data, lrs2_offset + 4)[0]

        # Calculer coordonnées tile
        tile_tx = tile_id % 32
        tile_ty = tile_id // 32

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

        new_lrs2_size = len(new_lrs2_data)

        # Padding IFF si taille impaire (alignement 2 bytes)
        padding = new_lrs2_size % 2
        if padding:
            new_lrs2_data.extend(b'\x00')  # 1 byte padding

        # Calculer tailles anciennes et nouvelles
        old_total_size = 8 + old_chunk_size
        if old_chunk_size % 2:
            old_total_size += 1  # Padding ancien chunk

        # Construire nouveau chunk complet
        new_chunk = bytearray()
        new_chunk.extend(b'LRS2')
        new_chunk.extend(struct.pack('>I', new_lrs2_size))  # Taille SANS padding
        new_chunk.extend(new_lrs2_data)  # Données + padding éventuel

        # Remplacer dans data
        data[lrs2_offset:lrs2_offset + old_total_size] = new_chunk

        # Mettre à jour la taille du fichier FORM
        form_size = len(data) - 8
        struct.pack_into('>I', data, 4, form_size)

        # Valider la structure avant écriture
        if not validate_ttile_structure(data):
            print(f"   [ERR] Validation échouée pour {ttile_path.name}")
            return False

        # Créer backup
        backup_path = ttile_path.with_suffix('.ttile.backup')
        if not backup_path.exists():
            shutil.copy2(ttile_path, backup_path)

        # Écrire fichier
        ttile_path.write_bytes(data)

        return True

    except Exception as e:
        print(f"   [ERR] Écriture échouée: {e}")
        return False


def print_tile_detail(
    tile_id: int,
    lrs2_blocks: Dict[Tuple[int, int], List[int]],
    grass_default_id: int,
    grass_03_id: int,
    surfaces: List[str]
) -> None:
    """
    Affiche le détail complet des blocs d'une tile pour le mode test.

    Args:
        tile_id: ID de la tile
        lrs2_blocks: Dict {(bx, by): [mat_ids]}
        grass_default_id: ID de Grass_03_default
        grass_03_id: ID de Grass_03
        surfaces: Liste des noms de surfaces
    """
    tile_tx = tile_id % 32
    tile_ty = tile_id // 32

    print()
    print("=" * 80)
    print(f"DÉTAIL TILE {tile_id} ({tile_tx},{tile_ty})")
    print("=" * 80)
    print()

    blocks_with_default = []
    blocks_with_both = []
    blocks_with_grass = []

    for (bx, by), mat_ids in sorted(lrs2_blocks.items()):
        has_default = grass_default_id in mat_ids
        has_grass = grass_03_id in mat_ids

        if has_default and has_grass:
            blocks_with_both.append((bx, by, mat_ids))
        elif has_default:
            blocks_with_default.append((bx, by, mat_ids))
        elif has_grass:
            blocks_with_grass.append((bx, by, mat_ids))

    total_affected = len(blocks_with_default) + len(blocks_with_both)

    print(f"Blocs concernés : {total_affected}/16")
    print(f"  → Avec doublon (Grass_03_default + Grass_03) : {len(blocks_with_both)} → FUSION")
    print(f"  → Seulement Grass_03_default                 : {len(blocks_with_default)} → REMPLACEMENT")
    print(f"  → Seulement Grass_03 (déjà migré)            : {len(blocks_with_grass)}")
    print()

    if blocks_with_both:
        print("[BLOCS AVEC DOUBLON] - Fusion nécessaire:")
        for bx, by, mat_ids in blocks_with_both:
            print(f"  Bloc ({bx},{by}): {len(mat_ids)} matériaux")
            for i, mat_id in enumerate(mat_ids):
                mat_name = surfaces[mat_id] if mat_id < len(surfaces) else f"MAT_{mat_id}"
                marker = ""
                if mat_id == grass_default_id:
                    marker = " [DEFAULT → sera fusionné avec Grass_03]"
                elif mat_id == grass_03_id:
                    marker = " [GRASS_03 → recevra les poids de DEFAULT]"
                print(f"    [{i}] ID {mat_id:3d}: {mat_name}{marker}")
        print()

    if blocks_with_default:
        print("[BLOCS REMPLACEMENT SIMPLE] - ID changé uniquement:")
        for bx, by, mat_ids in blocks_with_default:
            print(f"  Bloc ({bx},{by}): {len(mat_ids)} matériaux")
            for i, mat_id in enumerate(mat_ids):
                mat_name = surfaces[mat_id] if mat_id < len(surfaces) else f"MAT_{mat_id}"
                marker = " [DEFAULT → sera remplacé par Grass_03]" if mat_id == grass_default_id else ""
                print(f"    [{i}] ID {mat_id:3d}: {mat_name}{marker}")
        print()

    print("=" * 80)


def scan_tiles_for_material(
    data_dir: Path,
    material_id: int
) -> Dict[int, int]:
    """
    Scanne tous les .ttile et compte les blocs contenant un matériau.

    Args:
        data_dir: Dossier .Data/ contenant les .ttile
        material_id: ID du matériau à chercher

    Returns:
        Dict {tile_id: nombre_blocs_concernés}
    """
    affected_tiles = {}

    # Scanner tous les .ttile
    ttile_files = sorted(data_dir.glob("Terrain_*.ttile"))

    for ttile_path in ttile_files:
        # Extraire tile_id du nom
        try:
            tile_id = int(ttile_path.stem.split('_')[1])
        except (IndexError, ValueError):
            continue

        # Lire LRS2
        lrs2_blocks = read_lrs2_from_ttile(ttile_path)
        if lrs2_blocks is None:
            continue

        # Compter blocs contenant material_id
        count = 0
        for mat_ids in lrs2_blocks.values():
            if material_id in mat_ids:
                count += 1

        if count > 0:
            affected_tiles[tile_id] = count

    return affected_tiles


def main():
    """Point d'entrée principal."""
    # Parser les arguments en ligne de commande
    parser = argparse.ArgumentParser(
        description='Migrer Grass_03_default vers Grass_03 dans les chunks LRS2'
    )
    parser.add_argument(
        '--test-tile',
        type=str,
        metavar='ID_ou_X,Y',
        help='Test sur une seule tile (ex: --test-tile 417 ou --test-tile 1,13)'
    )
    args = parser.parse_args()

    # Mode test-tile ou migration complète
    test_mode = args.test_tile is not None
    test_tile_id = None

    if test_mode:
        try:
            # Détecter le format : ID seul ou X,Y
            if ',' in args.test_tile:
                # Format X,Y
                tx, ty = map(int, args.test_tile.split(','))
                test_tile_id = ty * 32 + tx
            else:
                # Format ID direct
                test_tile_id = int(args.test_tile)
        except (ValueError, AttributeError):
            print(f"[ERR] Format --test-tile invalide : '{args.test_tile}'")
            print("      Formats acceptés :")
            print("        --test-tile 417       (numéro de tile)")
            print("        --test-tile 1,13      (coordonnées X,Y)")
            return 1

    print("=" * 80)
    if test_mode:
        print(f"MIGRATE DEFAULT GRASS - MODE TEST TILE {test_tile_id}")
    else:
        print("MIGRATE DEFAULT GRASS - Remplacement Grass_03_default -> Grass_03")
    print("=" * 80)
    print()

    # Chemins
    TERRAIN_ROOT = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain")
    DATA_DIR = TERRAIN_ROOT / ".Data"
    TERR_PATH = TERRAIN_ROOT / "terrain.terr"

    if not DATA_DIR.exists() or not TERR_PATH.exists():
        print(f"[ERR] Chemins terrain introuvables")
        return 1

    # Charger surfaces
    print("[LOAD] Lecture terrain.terr...")
    surfaces_data = read_mats_from_terr(TERR_PATH)
    surfaces = [e["name"] for e in surfaces_data]
    print(f"   [OK] {len(surfaces)} surfaces")
    print()

    # Trouver IDs des matériaux
    grass_default_id = None
    grass_03_id = None

    for i, name in enumerate(surfaces):
        if name == "Grass_03_default":
            grass_default_id = i
        elif name == "Grass_03":
            grass_03_id = i

    if grass_default_id is None:
        print("[INFO] Grass_03_default non trouvé dans terrain.terr")
        print("   Rien à faire !")
        return 0

    if grass_03_id is None:
        print("[ERR] Grass_03 non trouvé dans terrain.terr")
        return 1

    print(f"[IDS] Grass_03_default = {grass_default_id}, Grass_03 = {grass_03_id}")
    print()

    # MODE TEST-TILE : Traiter une seule tile
    if test_mode:
        ttile_path = DATA_DIR / f"Terrain_{test_tile_id}.ttile"

        if not ttile_path.exists():
            print(f"[ERR] Fichier non trouvé: {ttile_path}")
            return 1

        # Lire LRS2
        lrs2_blocks = read_lrs2_from_ttile(ttile_path)
        if lrs2_blocks is None:
            print(f"[ERR] Échec lecture LRS2 de {ttile_path.name}")
            return 1

        # Vérifier si la tile est concernée
        has_default = any(grass_default_id in mat_ids for mat_ids in lrs2_blocks.values())

        if not has_default:
            print(f"[INFO] Tile {test_tile_id} ne contient pas Grass_03_default")
            print("       Rien à faire pour cette tile")
            return 0

        # Afficher détail complet
        print_tile_detail(test_tile_id, lrs2_blocks, grass_default_id, grass_03_id, surfaces)

        # Demander confirmation
        write_confirm = input(f"Appliquer la migration sur cette tile ? (oui/non) : ").strip().lower()

        if write_confirm not in ['oui', 'o', 'yes', 'y']:
            print()
            print("[INFO] Migration annulée (test uniquement)")
            return 0

        # Traiter la tile
        affected_tiles = {test_tile_id: sum(1 for mats in lrs2_blocks.values() if grass_default_id in mats)}

    # MODE COMPLET : Scanner toutes les tiles
    else:
        print("[SCAN] Recherche des tiles contenant Grass_03_default...")
        affected_tiles = scan_tiles_for_material(DATA_DIR, grass_default_id)

        if not affected_tiles:
            print("   [OK] Aucune tile concernée - migration déjà effectuée")
            return 0

        total_tiles = len(affected_tiles)
        total_blocks = sum(affected_tiles.values())

        print(f"   [OK] {total_tiles} tiles concernées")
        print(f"   [OK] {total_blocks} blocs au total contiennent Grass_03_default")
        print()

        # Afficher les 10 premières tiles
        print("[TILES CONCERNÉES] (10 premières):")
        for i, (tile_id, block_count) in enumerate(sorted(affected_tiles.items())[:10]):
            tile_tx = tile_id % 32
            tile_ty = tile_id // 32
            print(f"   Terrain_{tile_id}.ttile ({tile_tx},{tile_ty}): {block_count} blocs")

        if total_tiles > 10:
            print(f"   ... et {total_tiles - 10} autres tiles")

        # Analyser les doublons
        EDITOR_DATA_DIR = TERRAIN_ROOT / ".EditorData"
        analyze_duplicates(DATA_DIR, EDITOR_DATA_DIR, affected_tiles, grass_default_id, grass_03_id)

        # Demander confirmation
        write_confirm = input(f"Remplacer Grass_03_default par Grass_03 dans {total_tiles} tiles ? (oui/non) : ").strip().lower()

        if write_confirm not in ['oui', 'o', 'yes', 'y']:
            print()
            print("[INFO] Migration annulée (dry-run seulement)")
            return 0

    print()
    print("=" * 80)
    print("MODE WRITE")
    print("=" * 80)
    print()

    # Traiter chaque tile
    EDITOR_DATA_DIR = TERRAIN_ROOT / ".EditorData"
    success_count = 0
    fail_count = 0
    total_fusion = 0
    total_simple = 0
    failed_tiles = []  # Liste des tiles en échec avec leur erreur

    for tile_id, block_count in sorted(affected_tiles.items()):
        ttile_path = DATA_DIR / f"Terrain_{tile_id}.ttile"
        layer_path = EDITOR_DATA_DIR / f"Terrain_{tile_id}_layer.edds"
        if not layer_path.exists():
            layer_path = EDITOR_DATA_DIR / f"Terrain_{tile_id}_layer.dds"

        print(f"[WRITE] Terrain_{tile_id}.ttile ({block_count} blocs)... ", end="")

        # Lire LRS2
        lrs2_blocks = read_lrs2_from_ttile(ttile_path)
        if lrs2_blocks is None:
            error_msg = "Lecture LRS2 échouée"
            print(f"[ERR] {error_msg}")
            failed_tiles.append((tile_id, error_msg))
            fail_count += 1
            continue

        # Lire _layer.dds
        pixels = decode_dds_r32(layer_path)
        if pixels is None:
            error_msg = f"Lecture layer.dds échouée ({layer_path.name})"
            print(f"[ERR] {error_msg}")
            failed_tiles.append((tile_id, error_msg))
            fail_count += 1
            continue

        # Fusionner les blocs avec doublon + remplacer les simples
        lrs2_modified, pixels_modified, fusion_count, simple_count = merge_duplicate_blocks(
            lrs2_blocks, pixels, grass_default_id, grass_03_id
        )

        total_fusion += fusion_count
        total_simple += simple_count

        # Créer backups
        backup_ttile = ttile_path.with_suffix('.ttile.backup')
        backup_layer = layer_path.with_suffix(layer_path.suffix + '.backup')

        if not backup_ttile.exists():
            shutil.copy2(ttile_path, backup_ttile)

        if not backup_layer.exists():
            shutil.copy2(layer_path, backup_layer)

        # Écrire .ttile
        success_ttile = write_lrs2_to_ttile(ttile_path, lrs2_modified, tile_id)
        if not success_ttile:
            error_msg = "Écriture .ttile échouée"
            print(f"[ERR] {error_msg}")
            failed_tiles.append((tile_id, error_msg))
            fail_count += 1
            continue

        # Écrire _layer.dds (seulement si des fusions ont eu lieu)
        if fusion_count > 0:
            success_layer = write_dds_r32(pixels_modified, layer_path)
            if not success_layer:
                error_msg = "Écriture layer.dds échouée"
                print(f"[ERR] {error_msg}")
                failed_tiles.append((tile_id, error_msg))
                fail_count += 1
                continue
            print(f"[OK] {fusion_count} fusion(s), {simple_count} remplacement(s)")
        else:
            print(f"[OK] {simple_count} remplacement(s)")

        success_count += 1

    # Calculer totaux pour le résumé
    total_tiles = len(affected_tiles)
    total_blocks = sum(affected_tiles.values())

    print()
    print("=" * 80)
    print("RÉSUMÉ")
    print("=" * 80)
    print(f"  Tiles modifiées       : {success_count}/{total_tiles}")
    print(f"  Échecs                : {fail_count}")
    print(f"  Total blocs traités   : {total_blocks}")
    print(f"    → Fusions (doublon) : {total_fusion} blocs")
    print(f"    → Remplacements     : {total_simple} blocs")
    print()

    # Afficher la liste des tiles en échec
    if failed_tiles:
        print("=" * 80)
        print(f"TILES EN ÉCHEC ({len(failed_tiles)})")
        print("=" * 80)
        for tile_id, error_msg in failed_tiles:
            tile_tx = tile_id % 32
            tile_ty = tile_id // 32
            print(f"  Terrain_{tile_id}.ttile ({tile_tx},{tile_ty}): {error_msg}")
        print()

    if success_count > 0:
        print("[OK] Migration terminée avec succès")
        print("   Backups créés :")
        print("     - Terrain_*.ttile.backup")
        if total_fusion > 0:
            print("     - Terrain_*_layer.edds.backup (tiles avec fusion)")
        print()
        print("[INFO] Traitement appliqué :")
        print(f"   - {total_fusion} blocs avec doublon : poids fusionnés dans _layer.dds")
        print(f"   - {total_simple} blocs sans doublon : ID remplacé dans LRS2 uniquement")
    else:
        print("[ERR] Aucune tile modifiée")

    print()
    print("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(main())
