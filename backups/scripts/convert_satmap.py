"""
Convertisseur de fichiers .edds et .smap en PNG pour Arma Reforger
Adapté pour les images satellite et textures (pas les layers de terrain)
"""

import struct
import numpy as np
from pathlib import Path
from PIL import Image
import lz4.block

try:
    import texture2ddecoder
    HAS_TEX2D_DECODER = True
except ImportError:
    HAS_TEX2D_DECODER = False
    print("Module texture2ddecoder non disponible - installation...")


def decompress_lz4_chained(data: bytes) -> bytes:
    """
    Décompresse un blob LZ4 chainé (tranches de 64 Ko)

    Format :
        u32 taille_décompressée_totale
        [u32 taille_compressée][données LZ4]  64 Ko max
        ...
    """
    pos = 0

    # Lire taille totale décompressée
    total_size = struct.unpack_from('<I', data, pos)[0]
    pos += 4

    result = bytearray()

    while pos < len(data):
        if pos + 4 > len(data):
            break

        # Lire taille compressée (masquer bit 31)
        comp_size = struct.unpack_from('<I', data, pos)[0]
        comp_size &= 0x7FFFFFFF
        pos += 4

        if comp_size == 0 or pos + comp_size > len(data):
            break

        # Extraire bloc compressé
        comp_block = data[pos:pos+comp_size]
        pos += comp_size

        # Décompresser avec dictionnaire = 64 Ko précédents
        if len(result) >= 65536:
            dict_data = bytes(result[-65536:])
            decomp = lz4.block.decompress(comp_block, uncompressed_size=65536, dict=dict_data)
        else:
            decomp = lz4.block.decompress(comp_block, uncompressed_size=65536)

        result.extend(decomp)

    return bytes(result[:total_size])


def decode_edds_image(edds_path: Path) -> tuple:
    """
    Décode un fichier .edds image (satmap, texture, etc.)

    Returns:
        (width, height, pixel_data, format) ou None si erreur
    """
    with open(edds_path, 'rb') as f:
        data = f.read()

    # Vérifier header DDS
    if data[:4] != b'DDS ':
        print(f"❌ {edds_path.name} : pas un fichier DDS")
        return None

    # Lire header DDS (128 bytes)
    header = data[:128]

    # Extraire dimensions
    height = struct.unpack_from('<I', header, 12)[0]
    width = struct.unpack_from('<I', header, 16)[0]
    mipcount = struct.unpack_from('<I', header, 28)[0]

    print(f"Dimensions: {width}x{height}, {mipcount} mips")

    # Lire format de pixel (offset 84)
    fourcc = header[84:88]
    print(f"Format FourCC: {fourcc}")

    # Chercher marqueur ENF1
    reserved = header[32:52]
    is_enfusion = b'ENF1' in reserved

    if is_enfusion:
        print(f"Format Enfusion detecte")
        result = decode_enfusion_edds(data, width, height, mipcount, fourcc)
        if result:
            return result
        return None
    else:
        print(f"DDS standard (pas Enfusion)")
        result = decode_standard_dds(data, width, height, fourcc)
        if result:
            return result
        return None


def decode_enfusion_edds(data: bytes, width: int, height: int, mipcount: int, fourcc: bytes) -> tuple:
    """Décode un EDDS Enfusion compressé"""

    # Si DX10, lire le header étendu (20 bytes après header DDS)
    dx10_format = None
    header_offset = 128

    if fourcc == b'DX10':
        # Header DX10 étendu : DXGI_FORMAT (4 bytes) + resourceDimension + miscFlag + arraySize + miscFlags2
        dxgi_format = struct.unpack_from('<I', data, header_offset)[0]
        dx10_format = dxgi_format
        print(f"Format DXGI: {dxgi_format}")
        header_offset += 20  # Passer le header DX10 étendu

    # Parser table des mips (offset 148+)
    pos = 148
    mip_table = []

    for i in range(mipcount):
        if pos + 8 > len(data):
            break

        mip_fourcc = data[pos:pos+4]
        mip_size = struct.unpack_from('<I', data, pos+4)[0]
        mip_table.append((mip_fourcc, mip_size))
        pos += 8

    # Les données commencent après la table
    data_start = pos

    # Les mips Enfusion sont inversés (petit→grand)
    # On veut le dernier (mip 0 = résolution maximale)
    mip_offset = data_start

    # Sauter tous les mips sauf le dernier
    for i in range(len(mip_table) - 1):
        _, size = mip_table[i]
        mip_offset += size

    # Décoder le dernier mip (résolution max)
    mip_fourcc, mip_size = mip_table[-1]
    mip_data = data[mip_offset:mip_offset+mip_size]

    print(f"Decompression mip: {mip_fourcc} ({mip_size} bytes)")

    if mip_fourcc == b'COPY':
        # Données brutes
        pixel_data = mip_data
    elif mip_fourcc == b'LZ4 ':
        # Décompression LZ4 chainée
        pixel_data = decompress_lz4_chained(mip_data)
    else:
        print(f"FourCC mip inconnu: {mip_fourcc}")
        return None

    return (width, height, pixel_data, fourcc, dx10_format)


def decode_standard_dds(data: bytes, width: int, height: int, fourcc: bytes) -> tuple:
    """Décode un DDS standard (non-Enfusion)"""

    # Les données commencent après le header (128 bytes)
    pixel_data = data[128:]

    return (width, height, pixel_data, fourcc, None)


def convert_to_png(pixel_data: bytes, width: int, height: int, fourcc: bytes, dx10_format: int, output_path: Path) -> bool:
    """
    Convertit les données de pixels en PNG
    """

    # Déterminer le format de pixel
    fourcc_str = fourcc.decode('ascii', errors='ignore').strip()

    print(f"Conversion format: '{fourcc_str}'")

    # Formats DXGI communs pour DX10
    # https://learn.microsoft.com/en-us/windows/win32/api/dxgiformat/ne-dxgiformat-dxgi_format
    DXGI_FORMATS = {
        28: 'R8G8B8A8_UNORM',
        71: 'BC1_UNORM (DXT1)',
        74: 'BC2_UNORM (DXT3)',
        77: 'BC3_UNORM (DXT5)',
        80: 'BC4_UNORM',
        83: 'BC5_UNORM',
        98: 'BC7_UNORM',
    }

    if dx10_format:
        format_name = DXGI_FORMATS.get(dx10_format, f'Unknown ({dx10_format})')
        print(f"Format DXGI: {format_name}")

    # Gérer les formats compressés BC (Block Compression)
    if dx10_format == 71:  # BC1_UNORM (DXT1)
        print("Decompression BC1/DXT1...")
        if not HAS_TEX2D_DECODER:
            print("Erreur: module texture2ddecoder requis")
            return False
        decoded = texture2ddecoder.decode_bc1(pixel_data, width, height)
        img = Image.frombytes('RGBA', (width, height), decoded)
        img.save(output_path, 'PNG')
        print(f"Sauvegarde: {output_path}")
        return True

    elif dx10_format == 77:  # BC3_UNORM (DXT5)
        print("Decompression BC3/DXT5...")
        if not HAS_TEX2D_DECODER:
            print("Erreur: module texture2ddecoder requis")
            return False
        decoded = texture2ddecoder.decode_bc3(pixel_data, width, height)
        img = Image.frombytes('RGBA', (width, height), decoded)
        img.save(output_path, 'PNG')
        print(f"Sauvegarde: {output_path}")
        return True

    elif dx10_format == 98:  # BC7_UNORM
        print("Decompression BC7...")
        if not HAS_TEX2D_DECODER:
            print("Erreur: module texture2ddecoder requis")
            return False
        decoded = texture2ddecoder.decode_bc7(pixel_data, width, height)
        img = Image.frombytes('RGBA', (width, height), decoded)
        img.save(output_path, 'PNG')
        print(f"Sauvegarde: {output_path}")
        return True

    elif dx10_format == 99:  # BC7_UNORM_SRGB
        print("Decompression BC7 sRGB...")
        if not HAS_TEX2D_DECODER:
            print("Erreur: module texture2ddecoder requis")
            return False
        decoded = texture2ddecoder.decode_bc7(pixel_data, width, height)
        img = Image.frombytes('RGBA', (width, height), decoded)
        img.save(output_path, 'PNG')
        print(f"Sauvegarde: {output_path}")
        return True

    # Formats legacy
    elif fourcc == b'DXT1':
        print("Decompression DXT1 legacy...")
        if not HAS_TEX2D_DECODER:
            print("Erreur: module texture2ddecoder requis")
            return False
        decoded = texture2ddecoder.decode_bc1(pixel_data, width, height)
        img = Image.frombytes('RGBA', (width, height), decoded)
        img.save(output_path, 'PNG')
        print(f"Sauvegarde: {output_path}")
        return True

    elif fourcc == b'DXT5':
        print("Decompression DXT5 legacy...")
        if not HAS_TEX2D_DECODER:
            print("Erreur: module texture2ddecoder requis")
            return False
        decoded = texture2ddecoder.decode_bc3(pixel_data, width, height)
        img = Image.frombytes('RGBA', (width, height), decoded)
        img.save(output_path, 'PNG')
        print(f"Sauvegarde: {output_path}")
        return True

    else:
        # Essayer de deviner le format par taille de données
        expected_rgb = width * height * 3
        expected_rgba = width * height * 4
        actual_size = len(pixel_data)

        print(f"Taille donnees: {actual_size} bytes")
        print(f"   Attendu RGB: {expected_rgb}, RGBA: {expected_rgba}")

        if actual_size == expected_rgba:
            # RGBA 8888
            img = Image.frombytes('RGBA', (width, height), pixel_data)
            img.save(output_path, 'PNG')
            print(f"✓ Sauvegardé: {output_path}")
            return True

        elif actual_size == expected_rgb:
            # RGB 888
            img = Image.frombytes('RGB', (width, height), pixel_data)
            img.save(output_path, 'PNG')
            print(f"✓ Sauvegardé: {output_path}")
            return True

        else:
            # Tenter BGR(A)
            try:
                if actual_size >= expected_rgba:
                    # BGRA
                    pixels = np.frombuffer(pixel_data[:expected_rgba], dtype=np.uint8)
                    pixels = pixels.reshape((height, width, 4))
                    # Convertir BGRA → RGBA
                    pixels = pixels[:, :, [2, 1, 0, 3]]
                    img = Image.fromarray(pixels, 'RGBA')
                    img.save(output_path, 'PNG')
                    print(f"✓ Sauvegardé (BGRA): {output_path}")
                    return True
                elif actual_size >= expected_rgb:
                    # BGR
                    pixels = np.frombuffer(pixel_data[:expected_rgb], dtype=np.uint8)
                    pixels = pixels.reshape((height, width, 3))
                    # Convertir BGR → RGB
                    pixels = pixels[:, :, [2, 1, 0]]
                    img = Image.fromarray(pixels, 'RGB')
                    img.save(output_path, 'PNG')
                    print(f"✓ Sauvegardé (BGR): {output_path}")
                    return True
            except Exception as e:
                print(f"❌ Erreur conversion: {e}")
                return False

    return False


def convert_edds_to_png(edds_path: Path, output_path: Path) -> bool:
    """
    Convertit un fichier .edds en PNG
    """
    print(f"\n{'='*60}")
    print(f"Fichier: {edds_path.name}")
    print(f"{'='*60}")

    if not edds_path.exists():
        print(f"Fichier non trouve: {edds_path}")
        return False

    # Décoder l'EDDS
    result = decode_edds_image(edds_path)

    if result is None:
        print(f"Echec du decodage")
        return False

    width, height, pixel_data, fourcc, dx10_format = result

    # Convertir en PNG
    return convert_to_png(pixel_data, width, height, fourcc, dx10_format, output_path)


if __name__ == "__main__":
    import sys

    # Fichiers à convertir
    base_path = Path(r"h:\mod_enfusion\Arma Reforger_copie")
    output_dir = Path(r"C:\Users\jordi\AppData\Local\Temp\claude\h--mod-enfusion-Arma-Reforger-copie\fb237107-ee05-427d-b421-f33b43a35f65\scratchpad")

    files_to_convert = [
        (base_path / r"addons\data\worlds\worlds\Cain\cain_background.edds",
         output_dir / "cain_background.png"),

        (base_path / r"addons\data\data010\UI\Textures\Map\worlds\Cain\CainRasterized.edds",
         output_dir / "CainRasterized.png"),
    ]

    output_dir.mkdir(parents=True, exist_ok=True)

    success_count = 0
    for edds_file, output_file in files_to_convert:
        if convert_edds_to_png(edds_file, output_file):
            success_count += 1

    print(f"\n{'='*60}")
    print(f"Conversions reussies: {success_count}/{len(files_to_convert)}")
    print(f"{'='*60}")
