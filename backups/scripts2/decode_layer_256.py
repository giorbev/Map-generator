#!/usr/bin/env python3
"""
Décodeur pour les fichiers layer 256×256 (format COPY)
"""

import struct
import numpy as np
from pathlib import Path
import lz4.block


def decompress_lz4_chained(data: bytes) -> bytes:
    """Décompresse un blob LZ4 chainé"""
    pos = 0
    total_size = struct.unpack_from('<I', data, pos)[0]
    pos += 4

    result = bytearray()

    while pos < len(data):
        if pos + 4 > len(data):
            break

        comp_size = struct.unpack_from('<I', data, pos)[0]
        comp_size &= 0x7FFFFFFF
        pos += 4

        if comp_size == 0 or pos + comp_size > len(data):
            break

        comp_block = data[pos:pos+comp_size]
        pos += comp_size

        if len(result) >= 65536:
            dict_data = bytes(result[-65536:])
            decomp = lz4.block.decompress(comp_block, uncompressed_size=65536, dict=dict_data)
        else:
            decomp = lz4.block.decompress(comp_block, uncompressed_size=65536)

        result.extend(decomp)

    return bytes(result[:total_size])


def decode_layer_256(edds_path: Path) -> np.ndarray:
    """
    Décode un fichier layer 256×256 avec format COPY (non compressé)

    Returns:
        np.ndarray (256, 256) dtype uint32, ou None si erreur
    """
    with open(edds_path, 'rb') as f:
        data = f.read()

    # Vérifier header DDS
    if data[:4] != b'DDS ':
        print(f"ERREUR: pas un DDS")
        return None

    # Lire dimensions
    header = data[:128]
    height = struct.unpack_from('<I', header, 12)[0]
    width = struct.unpack_from('<I', header, 16)[0]
    mipcount = struct.unpack_from('<I', header, 28)[0]

    print(f"Dimensions: {width}×{height}, {mipcount} mips")

    # Vérifier ENF1
    if b'ENF1' not in header[32:52]:
        print(f"ERREUR: pas de marqueur ENF1")
        return None

    # Parser la table des mips (commence à offset 128)
    pos = 128
    mip_table = []

    for i in range(mipcount):
        if pos + 8 > len(data):
            break

        fourcc = data[pos:pos+4]
        size = struct.unpack_from('<I', data, pos+4)[0]
        mip_table.append((fourcc, size))
        pos += 8

    print(f"Table des mips parsée: {len(mip_table)} entrées")

    # Les données commencent après la table
    data_start = pos

    # Trouver le plus grand mip (dernier dans Enfusion)
    # Format Enfusion: mips du petit au grand
    mip_offset = data_start

    # Sauter tous les mips sauf le dernier
    for i in range(len(mip_table) - 1):
        _, size = mip_table[i]
        mip_offset += size

    # Décoder le dernier mip (résolution max)
    fourcc, size = mip_table[-1]

    print(f"Mip principal: fourcc={fourcc} size={size} offset={mip_offset}")

    # Décoder selon le format
    if fourcc == b'COPY':
        # Données brutes
        mip_data = data[mip_offset:mip_offset+size]
    elif fourcc == b'LZ4 ':
        # Décompression LZ4 chainée
        compressed_data = data[mip_offset:mip_offset+size]
        mip_data = decompress_lz4_chained(compressed_data)
        print(f"LZ4 décompressé: {len(compressed_data)} -> {len(mip_data)} bytes")
    else:
        print(f"ERREUR: FourCC non supporté: {fourcc}")
        return None

    expected_size = width * height * 4  # R32_UINT = 4 bytes/pixel
    if len(mip_data) != expected_size:
        print(f"ATTENTION: taille données = {len(mip_data)}, attendu = {expected_size}")

    # Convertir en array
    pixels = np.frombuffer(mip_data, dtype=np.uint32)

    # Reshape
    try:
        img = pixels.reshape((height, width))
        print(f"Succès: {img.shape} {img.dtype}")
        return img
    except:
        print(f"ERREUR: reshape impossible")
        return None


def extract_weights_from_pixel(pixel: np.uint32) -> np.ndarray:
    """
    Extrait les 7 poids d'un pixel uint32 (format Enfusion)
    """
    w1 = (pixel >> 0) & 0x1F
    w2 = (pixel >> 5) & 0x1F
    w3 = (pixel >> 10) & 0x1F
    w4 = (pixel >> 15) & 0x1F
    w5 = (pixel >> 20) & 0x1F
    w6 = (pixel >> 25) & 0x1F

    w0 = 31 - (w1 + w2 + w3 + w4 + w5 + w6)

    weights = np.array([w0, w1, w2, w3, w4, w5, w6], dtype=np.float32) / 31.0

    return weights


def extract_all_weights(layer_img: np.ndarray) -> np.ndarray:
    """
    Extrait les poids de tous les pixels

    Returns:
        (H, W, 7) float32 - poids normalisés [0, 1]
    """
    h, w = layer_img.shape
    weights = np.zeros((h, w, 7), dtype=np.float32)

    for i in range(7):
        if i == 0:
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


if __name__ == "__main__":
    # Test
    test_file = Path(r"h:\mod_enfusion\Arma Reforger_copie\addons\data\worlds\worlds\Eden\Eden\.Data\Eden_0_layer.edds")

    if test_file.exists():
        print(f"Test: {test_file.name}\n")
        layer_img = decode_layer_256(test_file)

        if layer_img is not None:
            weights = extract_all_weights(layer_img)
            print(f"\nPoids extraits: {weights.shape}")

            # Stats
            for i in range(7):
                coverage = (weights[:, :, i] > 0.1).sum() / (256*256) * 100
                print(f"Layer {i}: coverage={coverage:.1f}%")
