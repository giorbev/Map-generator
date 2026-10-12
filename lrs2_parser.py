"""
Parser du chunk LRS2 (Layer Resources v2) des fichiers .ttile

Contient la liste des matériaux par bloc (4×4 = 16 blocs par tuile)
"""

import struct
from pathlib import Path
from typing import Dict, Tuple, List, Optional

# Parser du chunk LRS2 (Layer Resources v2) des fichiers .ttile
def parse_iff_chunks(data: bytes) -> Dict[str, Tuple[int, int]]:
    """
    Parse les chunks IFF d'un fichier .ttile Enfusion (SANS padding)

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

        # Avancer SANS padding (les .ttile Enfusion n'ont pas de padding IFF)
        pos = pos + 8 + chunk_size

    # Garde-fou : vérifier que la lecture se termine exactement à la fin du fichier
    if pos != len(data):
        import sys
        print(f"⚠️ parse_iff_chunks: lecture terminée à {pos}, taille fichier {len(data)} (diff: {len(data) - pos})", file=sys.stderr)
        print(f"   Chunks lus: {list(chunks.keys())}", file=sys.stderr)

    return chunks

# ----------------------------------------------------------------------
# Extraction des coordonnées de tuile depuis LRS2
# ----------------------------------------------------------------------
def get_tile_coords_from_lrs2(lrs2_data: bytes, grid_w: Optional[int] = None, num_blk: Optional[int] = None) -> Optional[Tuple[int, int]]:
    """
    Extrait les coordonnées (tile_x, tile_y) depuis le premier bloc LRS2

    Args:
        lrs2_data: Données du chunk LRS2
        grid_w: Nombre de tuiles par côté (ex: 32 pour Zimnitrita, 64 pour ZBK)
        num_blk: Nombre de blocs par tuile et par côté (ex: 4)

    Returns:
        (tile_x, tile_y) ou None

    Raises:
        ValueError: Si grid_w ou num_blk est None (à renseigner dans project.json)
    """
    if grid_w is None:
        raise ValueError("grid_w manquant : à renseigner dans project.json (clé grid_w)")
    if num_blk is None:
        raise ValueError("num_blk manquant : à renseigner dans project.json (clé num_blk)")

    if len(lrs2_data) < 4:
        return None

    # Calculer shift et masque
    total_blocs = grid_w * num_blk
    shift = total_blocs.bit_length() - 1
    mask = (1 << shift) - 1

    # Lire premier index
    index = struct.unpack_from('<I', lrs2_data, 0)[0]
    bx_global = index & mask
    by_global = (index >> shift) & mask

    # Position tuile = bloc_global // num_blk
    tile_x = bx_global // num_blk
    tile_y = by_global // num_blk

    return (tile_x, tile_y)

# ----------------------------------------------------------------------
# Parsing des chunks LRS2
# ----------------------------------------------------------------------
def parse_lrs2_chunk(lrs2_data: bytes, grid_w: Optional[int] = None, num_blk: Optional[int] = None, filename: str = "", block_budget: Optional[int] = None) -> Dict[Tuple[int, int], List[int]]:
    """
    Parse le chunk LRS2 (Layer Resources v2)

    Args:
        lrs2_data: Données du chunk LRS2
        grid_w: Nombre de tuiles par côté (ex: 32 pour Zimnitrita, 64 pour ZBK)
        num_blk: Nombre de blocs par tuile et par côté (ex: 4)
        filename: Nom du fichier (pour les warnings)
        block_budget: Budget QTRE textures/bloc (5 ou 7 uniquement), optionnel

    Format :
        Pour chaque bloc (16 enregistrements) :
            u32 index       ← (by << shift) | bx
            u16 n           ← nombre de matériaux
            u16[n] ids      ← IDs matériaux globaux

    Returns:
        dict {(bx, by): [mat_id0, mat_id1, ...]}

    Raises:
        ValueError: Si grid_w/num_blk manquant, ou block_budget != 5 et != 7
    """
    if grid_w is None:
        raise ValueError("grid_w manquant : à renseigner dans project.json (clé grid_w)")
    if num_blk is None:
        raise ValueError("num_blk manquant : à renseigner dans project.json (clé num_blk)")
    if block_budget is not None and block_budget not in (5, 7):
        raise ValueError(f"block_budget doit être 5 ou 7 (reçu: {block_budget})")

    # Calculer shift et masque
    total_blocs = grid_w * num_blk
    shift = total_blocs.bit_length() - 1
    mask = (1 << shift) - 1

    blocks = {}
    pos = 0

    # Lire jusqu'à 16 blocs
    for i in range(16):
        if pos + 6 > len(lrs2_data):
            break

        # Lire index (LITTLE-ENDIAN)
        index = struct.unpack_from('<I', lrs2_data, pos)[0]
        bx_global = index & mask
        by_global = (index >> shift) & mask

        # Convertir index global en index local (0 à num_blk-1)
        bx = bx_global % num_blk
        by = by_global % num_blk

        pos += 4

        # Lire nombre de matériaux (LITTLE-ENDIAN)
        n = struct.unpack_from('<H', lrs2_data, pos)[0]
        pos += 2

        # WARNING si n invalide
        if n == 0:
            print(f"[LRS2] WARNING : {filename} bloc ({bx},{by}) : 0 matériau")
        elif block_budget is not None and n > block_budget:
            print(f"[LRS2] WARNING : {filename} bloc ({bx},{by}) : {n} matériaux (> {block_budget})")

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

# ----------------------------------------------------------------------
# Extraction des coordonnées de tuile depuis un fichier .ttile
# ----------------------------------------------------------------------
def get_tile_coords_from_ttile(ttile_path: Path, grid_w: Optional[int] = None, num_blk: Optional[int] = None) -> Optional[Tuple[int, int]]:
    """
    Extrait les coordonnées (tile_x, tile_y) depuis un fichier .ttile

    Args:
        ttile_path: Chemin vers le fichier .ttile
        grid_w: Nombre de tuiles par côté (ex: 32 pour Zimnitrita, 64 pour ZBK)
        num_blk: Nombre de blocs par tuile et par côté (ex: 4)

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

    return get_tile_coords_from_lrs2(lrs2_data, grid_w, num_blk)

# ----------------------------------------------------------------------
# Chargement du chunk LRS2 depuis un fichier .ttile
# ----------------------------------------------------------------------
def load_lrs2_from_ttile(ttile_path: Path, grid_w: Optional[int] = None, num_blk: Optional[int] = None, block_budget: Optional[int] = None) -> Optional[Dict[Tuple[int, int], List[int]]]:
    """
    Charge le chunk LRS2 depuis un fichier .ttile

    Args:
        ttile_path: Chemin vers le fichier .ttile
        grid_w: Nombre de tuiles par côté (ex: 32 pour Zimnitrita, 64 pour ZBK)
        num_blk: Nombre de blocs par tuile et par côté (ex: 4)
        block_budget: Budget QTRE textures/bloc (5 ou 7 uniquement), optionnel

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
    blocks = parse_lrs2_chunk(lrs2_data, grid_w, num_blk, filename=ttile_path.name, block_budget=block_budget)

    return blocks

# ----------------------------------------------------------------------
# Récupération des IDs matériaux pour un pixel donné
# ----------------------------------------------------------------------
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
