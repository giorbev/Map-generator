"""
Dcodeur EDDS (Enfusion DDS) pour Arma Reforger

Format : DDS avec mips inverss (petitgrand) + compression LZ4
"""

import struct
import numpy as np
from pathlib import Path
from typing import Optional, Tuple
import lz4.block


def decode_edds_layer(edds_path: Path) -> Optional[np.ndarray]:
    """
    Dcode un fichier Terrain_N_layer.edds

    Format : R32_UINT, 512512, 10 mips

    Returns:
        np.ndarray (512, 512) dtype uint32, ou None si erreur
    """
    with open(edds_path, 'rb') as f:
        data = f.read()

    # Vrifier header DDS
    if data[:4] != b'DDS ':
        print(f"ERREUR {edds_path.name} : pas un DDS")
        return None

    # Lire header DDS (124 bytes)
    header = data[:128]

    # Header DDS : offset 12 = height, 16 = width, 28 = mipcount
    height = struct.unpack_from('<I', header, 12)[0]
    width = struct.unpack_from('<I', header, 16)[0]
    mipcount = struct.unpack_from('<I', header, 28)[0]

    # Vrifier format attendu (layer = 512512, 10 mips)
    if width != 512 or height != 512:
        print(f" {edds_path.name} : taille inattendue {width}{height}")

    # Chercher marqueur ENF1 dans les reserved fields
    # Reserved1 = offset 32-51 (20 bytes dans DDS standard)
    reserved = header[32:52]
    if b'ENF1' not in reserved:
        print(f" {edds_path.name} : pas de marqueur ENF1, probablement DDS standard")
        # Tenter de lire comme DDS standard
        return decode_standard_dds_r32(data, width, height)

    # Parser table des mips
    # Il y a 20 octets de metadata avant la table (offset 128-147)
    # La vraie table commence à l'offset 148
    pos = 148
    mip_table = []

    for i in range(mipcount):
        if pos + 8 > len(data):
            break

        fourcc = data[pos:pos+4]
        size = struct.unpack_from('<I', data, pos+4)[0]
        mip_table.append((fourcc, size))
        pos += 8

    # Les donnes commencent aprs la table
    data_start = pos

    # Les mips sont du PLUS PETIT au PLUS GRAND
    # On veut le dernier (mip 0 = 512512)
    mip_offset = data_start

    # Sauter tous les mips sauf le dernier
    for i in range(len(mip_table) - 1):
        fourcc, size = mip_table[i]
        mip_offset += size

    # Dcoder le dernier mip (512512)
    fourcc, size = mip_table[-1]
    mip_data = data[mip_offset:mip_offset+size]

    if fourcc == b'COPY':
        # Donnes brutes
        pixels = np.frombuffer(mip_data, dtype=np.uint32)

    elif fourcc == b'LZ4 ':
        # Dcompression LZ4 chaine
        pixels_bytes = decompress_lz4_chained(mip_data)
        pixels = np.frombuffer(pixels_bytes, dtype=np.uint32)

    else:
        print(f" {edds_path.name} : fourcc inconnu {fourcc}")
        return None

    # Reshape en 512512
    try:
        img = pixels.reshape((height, width))
        return img
    except:
        print(f" {edds_path.name} : impossible de reshape {len(pixels)} pixels en {height}{width}")
        return None


def decompress_lz4_chained(data: bytes) -> bytes:
    """
    Dcompresse un blob LZ4 chain (tranches de 64 Ko)

    Format :
        u32 taille_dcompresse_totale
        [u32 taille_compresse | flag_bit31][donnes LZ4]  64 Ko max
        [u32 taille_compresse][donnes LZ4]
        ...

    Chaque tranche utilise les 64 Ko prcdents comme dictionnaire
    """
    pos = 0

    # Lire taille totale dcompresse
    total_size = struct.unpack_from('<I', data, pos)[0]
    pos += 4

    result = bytearray()

    while pos < len(data):
        if pos + 4 > len(data):
            break

        # Lire taille compresse (masquer bit 31)
        comp_size = struct.unpack_from('<I', data, pos)[0]
        comp_size &= 0x7FFFFFFF  # Masquer flag bit 31
        pos += 4

        if comp_size == 0 or pos + comp_size > len(data):
            break

        # Extraire bloc compress
        comp_block = data[pos:pos+comp_size]
        pos += comp_size

        # Dcompresser avec dictionnaire = 64 Ko prcdents
        if len(result) >= 65536:
            dict_data = bytes(result[-65536:])
            decomp = lz4.block.decompress(comp_block, uncompressed_size=65536, dict=dict_data)
        else:
            decomp = lz4.block.decompress(comp_block, uncompressed_size=65536)

        result.extend(decomp)

    return bytes(result[:total_size])


def compress_lz4_chained(data: bytes) -> bytes:
    """
    Compresse un blob en LZ4 chainé (tranches de 64 Ko)

    Format inverse de decompress_lz4_chained :
        u32 taille_décompressée_totale
        [u32 taille_compressée][données LZ4]  64 Ko max
        [u32 taille_compressée][données LZ4]
        ...

    Chaque tranche utilise les 64 Ko précédents comme dictionnaire
    """
    CHUNK_SIZE = 65536  # 64 Ko
    total_size = len(data)
    result = bytearray()

    # Écrire taille totale décompressée
    result.extend(struct.pack('<I', total_size))

    pos = 0
    prev_data = b''  # Dictionnaire (64 Ko précédents)

    while pos < total_size:
        # Taille du chunk (max 64 Ko)
        chunk_size = min(CHUNK_SIZE, total_size - pos)
        chunk = data[pos:pos + chunk_size]

        # Compresser avec dictionnaire si disponible
        if prev_data:
            comp_chunk = lz4.block.compress(chunk, mode='high_compression', dict=prev_data)
        else:
            comp_chunk = lz4.block.compress(chunk, mode='high_compression')

        # Écrire taille compressée
        result.extend(struct.pack('<I', len(comp_chunk)))

        # Écrire données compressées
        result.extend(comp_chunk)

        # Mettre à jour dictionnaire (garder les 64 Ko précédents)
        if len(prev_data) + chunk_size > CHUNK_SIZE:
            # Garder seulement les derniers 64 Ko
            prev_data = (prev_data + chunk)[-CHUNK_SIZE:]
        else:
            prev_data += chunk

        pos += chunk_size

    return bytes(result)


def encode_edds_layer(layer_img: np.ndarray, edds_path: Path, mipcount: int = 10) -> bool:
    """
    Encode une image layer en format .edds (DDS compressé LZ4)

    Args:
        layer_img: (512, 512) uint32 - pixels du layer
        edds_path: Chemin du fichier .edds à créer
        mipcount: Nombre de mipmaps (défaut 10)

    Returns:
        True si succès, False sinon
    """
    height, width = layer_img.shape
    if width != 512 or height != 512:
        print(f"❌ ERREUR : Taille attendue 512×512, reçu {width}×{height}")
        return False

    # 1. CRÉER LE HEADER DDS (128 octets)
    header = bytearray(128)

    # Magic "DDS "
    header[0:4] = b'DDS '

    # Size (toujours 124 pour DDS)
    struct.pack_into('<I', header, 4, 124)

    # Flags (DDSD_CAPS | DDSD_HEIGHT | DDSD_WIDTH | DDSD_PIXELFORMAT | DDSD_MIPMAPCOUNT)
    struct.pack_into('<I', header, 8, 0x1 | 0x2 | 0x4 | 0x1000 | 0x20000)

    # Height, Width
    struct.pack_into('<I', header, 12, height)
    struct.pack_into('<I', header, 16, width)

    # Pitch/LinearSize (non utilisé pour R32)
    struct.pack_into('<I', header, 20, width * 4)

    # Depth (1 pour 2D)
    struct.pack_into('<I', header, 24, 1)

    # MipMapCount
    struct.pack_into('<I', header, 28, mipcount)

    # Reserved1 (20 octets) : injecter marqueur ENF1 (offset 32-51)
    header[32:36] = b'ENF1'

    # PixelFormat (32 octets, offset 76)
    struct.pack_into('<I', header, 76, 32)  # Size
    struct.pack_into('<I', header, 80, 0x00020000)  # DDPF_FOURCC
    header[84:88] = b'    '  # FourCC vide (format custom)

    # Caps (DDSCAPS_TEXTURE | DDSCAPS_MIPMAP | DDSCAPS_COMPLEX)
    struct.pack_into('<I', header, 108, 0x1000 | 0x400000 | 0x8)

    # 2. GÉNÉRER LES MIPMAPS (du plus grand au plus petit)
    mips = [layer_img]  # Mip 0 = 512×512

    for i in range(1, mipcount):
        prev_mip = mips[-1]
        h, w = prev_mip.shape
        new_h, new_w = max(1, h // 2), max(1, w // 2)

        # Downsampling simple (prendre 1 pixel sur 4)
        new_mip = prev_mip[::2, ::2][:new_h, :new_w]
        mips.append(new_mip)

    # 3. INVERSER L'ORDRE (EDDS stocke du plus petit au plus grand)
    mips_reversed = list(reversed(mips))

    # 4. COMPRESSER CHAQUE MIP EN LZ4
    mip_table = []
    mip_data_blocks = []

    for i, mip in enumerate(mips_reversed):
        mip_bytes = mip.astype(np.uint32).tobytes()

        # Compresser en LZ4 chainé
        comp_bytes = compress_lz4_chained(mip_bytes)

        # Table : fourcc + size
        mip_table.append((b'LZ4 ', len(comp_bytes)))
        mip_data_blocks.append(comp_bytes)

    # 5. ASSEMBLER LE FICHIER .EDDS
    result = bytearray()

    # Header (128 octets)
    result.extend(header)

    # Metadata (20 octets, offset 128-147)
    # Valeurs observées dans les fichiers Enfusion :
    # Offset 128-131 : nombre d'entrées ou taille ?
    # Pour l'instant, on hard-code les valeurs observées
    result.extend(struct.pack('<I', 42))  # offset 128
    result.extend(struct.pack('<I', 3))   # offset 132
    result.extend(struct.pack('<I', 0))   # offset 136
    result.extend(struct.pack('<I', 1))   # offset 140
    result.extend(struct.pack('<I', 0))   # offset 144

    # Table des mips (offset 148+)
    for fourcc, size in mip_table:
        result.extend(fourcc)
        result.extend(struct.pack('<I', size))

    # Données des mips
    for data in mip_data_blocks:
        result.extend(data)

    # 6. ÉCRIRE LE FICHIER
    try:
        with open(edds_path, 'wb') as f:
            f.write(result)
        return True
    except Exception as e:
        print(f"❌ ERREUR lors de l'écriture : {e}")
        return False


def decode_standard_dds_r32(data: bytes, width: int, height: int) -> np.ndarray:
    """
    Dcode un DDS standard R32_UINT (pas EDDS)
    Les mips sont dans l'ordre normal (grandpetit)
    """
    # Donnes commencent aprs header 128 bytes
    pixel_data = data[128:128 + width*height*4]

    # Vérifier taille
    if len(pixel_data) < width*height*4:
        return None

    pixels = np.frombuffer(pixel_data, dtype=np.uint32)

    try:
        return pixels.reshape((height, width))
    except:
        print(f" Impossible de reshape {len(pixels)} pixels en {height}{width}")
        return None


def extract_weights_from_pixel(pixel: np.uint32) -> np.ndarray:
    """
    Extrait les 7 poids (w0..w6) d'un pixel uint32

    Format :
        Bits 0-4   : w1
        Bits 5-9   : w2
        Bits 10-14 : w3
        Bits 15-19 : w4
        Bits 20-24 : w5
        Bits 25-29 : w6
        w0 = 31 - (w1+w2+w3+w4+w5+w6)

    Returns:
        np.array([w0, w1, w2, w3, w4, w5, w6], dtype=float32)
        Normalis [0, 1]
    """
    w1 = (pixel >> 0) & 0x1F
    w2 = (pixel >> 5) & 0x1F
    w3 = (pixel >> 10) & 0x1F
    w4 = (pixel >> 15) & 0x1F
    w5 = (pixel >> 20) & 0x1F
    w6 = (pixel >> 25) & 0x1F

    # w0 implicite
    w0 = 31 - (w1 + w2 + w3 + w4 + w5 + w6)

    # Normaliser [0, 31]  [0, 1]
    weights = np.array([w0, w1, w2, w3, w4, w5, w6], dtype=np.float32) / 31.0

    return weights


def extract_all_weights(layer_img: np.ndarray) -> np.ndarray:
    """
    Extrait les poids de tous les pixels d'une image layer

    Args:
        layer_img: (512, 512) uint32

    Returns:
        (512, 512, 7) float32 - poids normaliss [0, 1]
    """
    h, w = layer_img.shape
    weights = np.zeros((h, w, 7), dtype=np.float32)

    # Vectoriser l'extraction
    for i in range(7):
        if i == 0:
            # w0 = 31 - somme(w1..w6)
            w1 = (layer_img >> 0) & 0x1F
            w2 = (layer_img >> 5) & 0x1F
            w3 = (layer_img >> 10) & 0x1F
            w4 = (layer_img >> 15) & 0x1F
            w5 = (layer_img >> 20) & 0x1F
            w6 = (layer_img >> 25) & 0x1F
            weights[:, :, 0] = (31 - (w1 + w2 + w3 + w4 + w5 + w6)) / 31.0
        else:
            shift = 5 * (i - 1)
            weights[:, :, i] = ((layer_img >> shift) & 0x1F) / 31.0

    return weights


# Test
if __name__ == "__main__":
    import sys
    from pathlib import Path

    # Test sur une tuile
    test_path = Path(r"I:\reforger_travail\Zimnitrita_map_test\World\Zimnitrita\Terrain\.Data\Terrain_0_layer.edds")

    if not test_path.exists():
        print(f" Fichier test non trouv : {test_path}")
        sys.exit(1)

    print(f"Test decodage : {test_path.name}")

    layer_img = decode_edds_layer(test_path)

    if layer_img is not None:
        print(f" Dcod : {layer_img.shape} {layer_img.dtype}")
        print(f"   Min pixel : 0x{layer_img.min():08X}")
        print(f"   Max pixel : 0x{layer_img.max():08X}")

        # Extraire poids d'un pixel
        test_pixel = layer_img[256, 256]
        weights = extract_weights_from_pixel(test_pixel)

        print(f"\n Pixel (256, 256) = 0x{test_pixel:08X}")
        print(f"   Poids : {weights}")
        print(f"   Somme : {weights.sum():.3f} (doit tre 1.0)")

        # Statistiques globales
        all_weights = extract_all_weights(layer_img)
        print(f"\n Statistiques globales (512512)")
        print(f"   Shape : {all_weights.shape}")
        for i in range(7):
            usage = (all_weights[:, :, i] > 0).sum()
            pct = usage / (512*512) * 100
            print(f"   w{i} utilis : {usage:6d} pixels ({pct:5.1f}%)")

    else:
        print(" chec dcodage")
        sys.exit(1)
