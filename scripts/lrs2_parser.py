"""
Parser du chunk LRS2 (Layer Resources v2) des fichiers .ttile

Contient la liste des matériaux par bloc (4×4 = 16 blocs par tuile)
"""

import struct
from pathlib import Path
from typing import Dict, Tuple, List, Optional


def parse_iff_chunks(data: bytes) -> Dict[str, Tuple[int, int]]:
    """
    Parse les chunks IFF d'un fichier

    Returns:
        dict {chunk_id: (offset, size)}
    """
    chunks = {}

    if data[:4] != b'FORM':
        return chunks

    # Type FORM à offset 8
    form_type = data[8:12]

    # Chunks commencent à offset 12
    pos = 12

    while pos + 8 <= len(data):
        chunk_id = data[pos:pos+4]
        try:
            chunk_id_str = chunk_id.decode('ascii', errors='ignore')
        except:
            break

        chunk_size = struct.unpack_from('>I', data, pos+4)[0]

        if chunk_size > len(data) or pos + 8 + chunk_size > len(data):
            break

        chunks[chunk_id_str] = (pos + 8, chunk_size)

        # Avancer (padding si taille impaire)
        pos = pos + 8 + chunk_size + (chunk_size % 2)

    return chunks


def get_tile_coords_from_lrs2(lrs2_data: bytes) -> Optional[Tuple[int, int]]:
    """
    Extrait les coordonnées (tile_x, tile_y) depuis le premier bloc LRS2

    Returns:
        (tile_x, tile_y) ou None
    """
    if len(lrs2_data) < 4:
        return None

    # Lire premier index
    index = struct.unpack_from('<I', lrs2_data, 0)[0]
    bx_global = index & 0x7F
    by_global = (index >> 7) & 0x7F

    # Position tuile = bloc_global // 4
    tile_x = bx_global // 4
    tile_y = by_global // 4

    return (tile_x, tile_y)


def parse_lrs2_chunk(lrs2_data: bytes) -> Dict[Tuple[int, int], List[int]]:
    """
    Parse le chunk LRS2 (Layer Resources v2)

    Format :
        Pour chaque bloc (16 enregistrements) :
            u32 index       ← (by << 7) | bx
            u16 n           ← nombre de matériaux
            u16[n] ids      ← IDs matériaux globaux

    Returns:
        dict {(bx, by): [mat_id0, mat_id1, ...]}
    """
    blocks = {}
    pos = 0

    # Lire jusqu'à 16 blocs
    for i in range(16):
        if pos + 6 > len(lrs2_data):
            break

        # Lire index (LITTLE-ENDIAN)
        index = struct.unpack_from('<I', lrs2_data, pos)[0]
        bx_global = index & 0x7F
        by_global = (index >> 7) & 0x7F

        # Convertir index global en index local (0-3)
        # Chaque tuile fait 4x4 blocs
        bx = bx_global % 4
        by = by_global % 4

        pos += 4

        # Lire nombre de matériaux (LITTLE-ENDIAN)
        n = struct.unpack_from('<H', lrs2_data, pos)[0]
        pos += 2

        # Lire IDs (LITTLE-ENDIAN)
        if pos + n * 2 > len(lrs2_data):
            break

        mat_ids = []
        for j in range(n):
            mat_id = struct.unpack_from('<H', lrs2_data, pos)[0]
            mat_ids.append(mat_id)
            pos += 2

        blocks[(bx, by)] = mat_ids

    return blocks


def get_tile_coords_from_ttile(ttile_path: Path) -> Optional[Tuple[int, int]]:
    """
    Extrait les coordonnées (tile_x, tile_y) depuis un fichier .ttile

    Returns:
        (tile_x, tile_y) ou None
    """
    try:
        with open(ttile_path, 'rb') as f:
            data = f.read()
    except:
        return None

    chunks = parse_iff_chunks(data)

    if 'LRS2' not in chunks:
        return None

    offset, size = chunks['LRS2']
    lrs2_data = data[offset:offset+size]

    return get_tile_coords_from_lrs2(lrs2_data)


def load_lrs2_from_ttile(ttile_path: Path) -> Optional[Dict[Tuple[int, int], List[int]]]:
    """
    Charge le chunk LRS2 depuis un fichier .ttile

    Args:
        ttile_path: Chemin vers Terrain_N.ttile

    Returns:
        dict {(bx, by): [mat_ids]} ou None si erreur
    """
    try:
        with open(ttile_path, 'rb') as f:
            data = f.read()
    except:
        return None

    # Parser chunks IFF
    chunks = parse_iff_chunks(data)

    if 'LRS2' not in chunks:
        print(f"⚠️ {ttile_path.name} : chunk LRS2 non trouvé")
        return None

    # Extraire chunk LRS2
    offset, size = chunks['LRS2']
    lrs2_data = data[offset:offset+size]

    # Parser LRS2
    blocks = parse_lrs2_chunk(lrs2_data)

    return blocks


def get_material_ids_for_pixel(
    x: int,
    y: int,
    lrs2_blocks: Dict[Tuple[int, int], List[int]]
) -> List[int]:
    """
    Retourne la liste des matériaux pour un pixel (x, y)

    Args:
        x, y: Coordonnées pixel dans la tuile (0-511)
        lrs2_blocks: Dict {(bx, by): [mat_ids]}

    Returns:
        Liste des IDs matériaux pour ce bloc
    """
    # Identifier le bloc (4×4 grille de 128×128 px)
    bx = x // 128
    by = y // 128

    return lrs2_blocks.get((bx, by), [])


# Test
if __name__ == "__main__":
    import sys
    from pathlib import Path

    # Test sur une tuile
    test_path = Path(r"I:\reforger_travail\Zimnitrita_map_test\World\Zimnitrita\Terrain\.Data\Terrain_0.ttile")

    if not test_path.exists():
        print(f"❌ Fichier test non trouvé : {test_path}")
        sys.exit(1)

    print(f"📂 Test parsing LRS2 : {test_path.name}\n")

    blocks = load_lrs2_from_ttile(test_path)

    if blocks is None:
        print("❌ Échec parsing")
        sys.exit(1)

    print(f"✅ {len(blocks)} blocs chargés\n")

    # Afficher tous les blocs
    print("="*80)
    print("BLOCS LRS2 (4×4)")
    print("="*80)

    for by in range(4):
        for bx in range(4):
            mat_ids = blocks.get((bx, by), [])
            n = len(mat_ids)

            if n > 0:
                ids_str = ", ".join(str(id) for id in mat_ids)
                print(f"Bloc ({bx}, {by}) : {n} mats → [{ids_str}]")
            else:
                print(f"Bloc ({bx}, {by}) : VIDE")

    print("\n" + "="*80)
    print("STATISTIQUES")
    print("="*80)

    mat_counts = {}
    for mat_ids in blocks.values():
        n = len(mat_ids)
        mat_counts[n] = mat_counts.get(n, 0) + 1

    for n in sorted(mat_counts.keys()):
        count = mat_counts[n]
        print(f"{n} matériaux : {count} blocs")

    # Tester get_material_ids_for_pixel
    print("\n" + "="*80)
    print("TEST get_material_ids_for_pixel")
    print("="*80)

    test_pixels = [
        (0, 0),      # Bloc (0, 0)
        (127, 127),  # Bloc (0, 0)
        (128, 0),    # Bloc (1, 0)
        (256, 256),  # Bloc (2, 2)
        (511, 511),  # Bloc (3, 3)
    ]

    for x, y in test_pixels:
        mat_ids = get_material_ids_for_pixel(x, y, blocks)
        bx = x // 128
        by = y // 128
        print(f"Pixel ({x:3d}, {y:3d}) → Bloc ({bx}, {by}) → {len(mat_ids)} mats {mat_ids}")
