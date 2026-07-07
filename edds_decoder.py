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
    # Reserved1 = offset 88-108 (20 bytes)
    reserved = header[88:108]
    if b'ENF1' not in reserved:
        print(f" {edds_path.name} : pas de marqueur ENF1, probablement DDS standard")
        # Tenter de lire comme DDS standard
        return decode_standard_dds_r32(data, width, height)

    # Parser table des mips (aprs header 128 bytes)
    pos = 128
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
