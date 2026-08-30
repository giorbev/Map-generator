"""
BCR Extractor - Extraction de textures depuis BCR/MCR pour Arma Reforger

Extrait les composants d'un fichier BCR ou MCR :
- BaseColor (RGB) depuis BCR
- Roughness (Alpha) depuis BCR
- Metalness, Roughness, AO depuis MCR

Usage:
    python bcr_extractor.py <fichier.edds> [--output-dir ./output]
"""

import sys
import struct
import numpy as np
from pathlib import Path
from typing import Optional, Tuple
from PIL import Image
import argparse

# Forcer l'encodage UTF-8 pour la sortie console (Windows)
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except:
        pass

# Importer depuis edds_decoder s'il existe
try:
    from edds_decoder import decompress_lz4_chained
except ImportError:
    import lz4.block

    def decompress_lz4_chained(data: bytes) -> bytes:
        """
        Décompresse un blob LZ4 chaîné (tranches de 64 Ko)
        """
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


def list_all_mips(edds_path: Path) -> Optional[list]:
    """
    Liste tous les mips disponibles dans un fichier EDDS

    Returns:
        Liste de tuples (mip_level, width, height, fourcc, size, offset)
        None si erreur
    """
    with open(edds_path, 'rb') as f:
        data = f.read()

    if data[:4] != b'DDS ':
        return None

    header = data[:128]
    height = struct.unpack_from('<I', header, 12)[0]
    width = struct.unpack_from('<I', header, 16)[0]
    mipcount = struct.unpack_from('<I', header, 28)[0]

    is_enfusion = b'ENF1' in header[32:52]
    if not is_enfusion:
        return None

    # Parser table des mips
    pos = 148
    mip_table = []

    for i in range(mipcount):
        if pos + 8 > len(data):
            break
        fourcc = data[pos:pos+4]
        size = struct.unpack_from('<I', data, pos+4)[0]
        mip_table.append((fourcc, size))
        pos += 8

    data_start = pos

    # Construire la liste complète des mips
    mip_info = []
    mip_offset = data_start

    for i in range(len(mip_table)):
        fourcc, size = mip_table[i]
        # Mips inversés : [petit → grand]
        mip_level = len(mip_table) - 1 - i
        mip_width = max(1, width >> mip_level)
        mip_height = max(1, height >> mip_level)

        mip_info.append((mip_level, mip_width, mip_height, fourcc, size, mip_offset))
        mip_offset += size

    # Inverser pour avoir mip 0 en premier
    mip_info.reverse()
    return mip_info


def decode_edds_texture(edds_path: Path, target_mip: int = 0, try_all_mips: bool = False) -> Optional[np.ndarray]:
    """
    Décode un fichier EDDS texture (BCR, MCR, NMO, etc.)

    Args:
        edds_path: Chemin vers le .edds
        target_mip: Mip à extraire (0 = plus grande résolution)
        try_all_mips: Si True et que target_mip échoue, essayer tous les autres mips

    Returns:
        np.ndarray (H, W, C) dtype uint8
        None si erreur
    """
    print(f"📂 Lecture de {edds_path.name}...")

    with open(edds_path, 'rb') as f:
        data = f.read()

    # Vérifier header DDS
    if data[:4] != b'DDS ':
        print(f"❌ {edds_path.name} : pas un DDS")
        return None

    # Lire header DDS
    header = data[:128]
    height = struct.unpack_from('<I', header, 12)[0]
    width = struct.unpack_from('<I', header, 16)[0]
    mipcount = struct.unpack_from('<I', header, 28)[0]

    print(f"   📐 Dimensions : {width}×{height}, {mipcount} mips")

    # Vérifier marqueur ENF1
    is_enfusion = b'ENF1' in header[32:52]

    if not is_enfusion:
        print(f"   ⚠️  DDS standard (pas EDDS Enfusion)")
        return decode_standard_dds(data, width, height)

    # Parser table des mips (offset 148+)
    pos = 148
    mip_table = []

    for i in range(mipcount):
        if pos + 8 > len(data):
            break
        fourcc = data[pos:pos+4]
        size = struct.unpack_from('<I', data, pos+4)[0]
        mip_table.append((fourcc, size))
        pos += 8

    # Afficher tous les mips disponibles
    if try_all_mips:
        print(f"\n   📋 Mips disponibles :")
        for i in range(len(mip_table)):
            fourcc, size = mip_table[i]
            mip_level = len(mip_table) - 1 - i
            mip_w = max(1, width >> mip_level)
            mip_h = max(1, height >> mip_level)
            fourcc_str = fourcc.decode('ascii', errors='ignore').strip()
            print(f"      Mip {mip_level:2d} : {mip_w:4d}×{mip_h:4d}, {fourcc_str:4s}, {size:8,} bytes")

    # Données commencent après la table
    data_start = pos

    # Essayer le mip demandé d'abord
    mips_to_try = [target_mip]

    # Si try_all_mips, ajouter tous les autres mips
    if try_all_mips:
        mips_to_try.extend([i for i in range(mipcount) if i != target_mip])

    for current_mip in mips_to_try:
        # Calculer offset du mip
        mip_index = len(mip_table) - 1 - current_mip

        if mip_index < 0 or mip_index >= len(mip_table):
            continue

        # Calculer offset
        mip_offset = data_start
        for i in range(mip_index):
            fourcc, size = mip_table[i]
            mip_offset += size

        # Décoder le mip
        fourcc, size = mip_table[mip_index]
        mip_data = data[mip_offset:mip_offset+size]

        # Calculer dimensions du mip
        mip_width = max(1, width >> current_mip)
        mip_height = max(1, height >> current_mip)

        if try_all_mips and current_mip != target_mip:
            print(f"\n   🔄 Tentative Mip {current_mip} : {mip_width}×{mip_height}, format={fourcc.decode('ascii', errors='ignore')}")
        else:
            print(f"   🔍 Mip {current_mip} : {mip_width}×{mip_height}, format={fourcc.decode('ascii', errors='ignore')}")

        # Décompresser selon fourcc
        result = None

        if fourcc == b'COPY':
            # Données brutes
            result = decode_raw_pixels(mip_data, mip_width, mip_height)

        elif fourcc == b'LZ4 ':
            # Décompression LZ4 chainée
            print(f"   ⚙️  Décompression LZ4...")
            try:
                decompressed = decompress_lz4_chained(mip_data)
                result = decode_raw_pixels(decompressed, mip_width, mip_height)
            except Exception as e:
                print(f"   ❌ Erreur LZ4 : {e}")
                result = None

        elif fourcc == b'BC7 ' or fourcc == b'BC5U' or fourcc == b'BC1 ':
            print(f"   ⚠️  Compression {fourcc.decode('ascii', errors='ignore')} non supportée")
            if not try_all_mips:
                print(f"   💡 Utilisez un outil externe (texconv, ImageMagick)")
            result = None

        else:
            print(f"   ❌ FourCC inconnu : {fourcc}")
            result = None

        # Si on a réussi à décoder, retourner
        if result is not None:
            if current_mip != target_mip:
                print(f"   ✅ Succès avec Mip {current_mip} !")
            return result

    # Aucun mip n'a fonctionné
    if try_all_mips:
        print(f"\n   ❌ Aucun mip décodable trouvé")
        print(f"   💡 Utilisez texconv.exe ou un outil supportant BC7")

    return None


def decode_raw_pixels(data: bytes, width: int, height: int) -> Optional[np.ndarray]:
    """
    Décode des pixels bruts (détecte automatiquement le format)
    """
    expected_rgba8 = width * height * 4
    expected_rgb8 = width * height * 3
    expected_r8 = width * height * 1

    actual_size = len(data)

    print(f"   📊 Taille données : {actual_size:,} bytes")

    if actual_size >= expected_rgba8:
        # Format RGBA8
        print(f"   ✅ Détecté : RGBA8")
        pixels = np.frombuffer(data[:expected_rgba8], dtype=np.uint8)
        return pixels.reshape((height, width, 4))

    elif actual_size >= expected_rgb8:
        # Format RGB8
        print(f"   ✅ Détecté : RGB8")
        pixels = np.frombuffer(data[:expected_rgb8], dtype=np.uint8)
        return pixels.reshape((height, width, 3))

    elif actual_size >= expected_r8:
        # Format R8 (grayscale) - probablement compressé BC
        print(f"   ⚠️  Détecté : Format compressé (BC7/BC5/BC1)")
        print(f"   💡 Utilisez texconv.exe pour convertir ce fichier")
        return None

    else:
        print(f"❌ Taille données insuffisante : {actual_size:,} bytes")
        return None


def decode_standard_dds(data: bytes, width: int, height: int) -> Optional[np.ndarray]:
    """
    Décode un DDS standard (pas EDDS Enfusion)
    """
    pixel_data = data[128:]
    return decode_raw_pixels(pixel_data, width, height)


def extract_basecolor(bcr_array: np.ndarray) -> np.ndarray:
    """
    Extrait la BaseColor (RGB) depuis un array BCR

    Args:
        bcr_array: (H, W, 4) ou (H, W, 3) uint8

    Returns:
        (H, W, 3) uint8 - Image RGB
    """
    if bcr_array.ndim == 3 and bcr_array.shape[2] >= 3:
        return bcr_array[:, :, :3]
    else:
        raise ValueError(f"Format BCR invalide : {bcr_array.shape}")


def extract_roughness(bcr_array: np.ndarray) -> Optional[np.ndarray]:
    """
    Extrait la Roughness (Alpha) depuis un array BCR

    Args:
        bcr_array: (H, W, 4) uint8

    Returns:
        (H, W) uint8 - Image grayscale ou None
    """
    if bcr_array.ndim == 3 and bcr_array.shape[2] == 4:
        return bcr_array[:, :, 3]
    else:
        return None


def extract_mcr_channels(mcr_array: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Extrait les 3 canaux depuis un array MCR

    Args:
        mcr_array: (H, W, 3+) uint8

    Returns:
        (channel_r, channel_g, channel_b) - Chaque canal : (H, W) uint8
    """
    if mcr_array.ndim != 3 or mcr_array.shape[2] < 3:
        raise ValueError(f"Format MCR invalide : {mcr_array.shape}")

    return (mcr_array[:, :, 0], mcr_array[:, :, 1], mcr_array[:, :, 2])


def process_bcr_file(bcr_path: Path, output_dir: Path, try_all_mips: bool = False):
    """
    Traite un fichier BCR et extrait BaseColor + Roughness
    """
    print(f"\n{'='*70}")
    print(f"📦 Traitement BCR : {bcr_path.name}")
    print(f"{'='*70}")

    # Décoder
    bcr = decode_edds_texture(bcr_path, target_mip=0, try_all_mips=try_all_mips)

    if bcr is None:
        print("❌ Échec décodage")
        return

    # Extraire BaseColor
    try:
        basecolor = extract_basecolor(bcr)

        output_color = output_dir / f"{bcr_path.stem}_BaseColor.png"
        img_color = Image.fromarray(basecolor, mode='RGB')
        img_color.save(output_color)

        print(f"✅ BaseColor sauvegardé : {output_color.name}")
    except Exception as e:
        print(f"❌ Erreur extraction BaseColor : {e}")

    # Extraire Roughness
    roughness = extract_roughness(bcr)

    if roughness is not None:
        output_rough = output_dir / f"{bcr_path.stem}_Roughness.png"
        img_rough = Image.fromarray(roughness, mode='L')
        img_rough.save(output_rough)

        print(f"✅ Roughness sauvegardé : {output_rough.name}")
    else:
        print(f"⚠️  Pas de canal Roughness (Alpha) trouvé")


def process_mcr_file(mcr_path: Path, output_dir: Path, try_all_mips: bool = False):
    """
    Traite un fichier MCR et extrait Metalness + Roughness + AO
    """
    print(f"\n{'='*70}")
    print(f"📦 Traitement MCR : {mcr_path.name}")
    print(f"{'='*70}")

    # Décoder
    mcr = decode_edds_texture(mcr_path, target_mip=0, try_all_mips=try_all_mips)

    if mcr is None:
        print("❌ Échec décodage")
        return

    # Extraire canaux
    try:
        ch_r, ch_g, ch_b = extract_mcr_channels(mcr)

        # Canal R (probablement Metalness ou AO)
        output_r = output_dir / f"{mcr_path.stem}_ChannelR.png"
        Image.fromarray(ch_r, mode='L').save(output_r)
        print(f"✅ Canal R sauvegardé : {output_r.name}")

        # Canal G (probablement Roughness)
        output_g = output_dir / f"{mcr_path.stem}_ChannelG.png"
        Image.fromarray(ch_g, mode='L').save(output_g)
        print(f"✅ Canal G sauvegardé : {output_g.name}")

        # Canal B (probablement AO)
        output_b = output_dir / f"{mcr_path.stem}_ChannelB.png"
        Image.fromarray(ch_b, mode='L').save(output_b)
        print(f"✅ Canal B sauvegardé : {output_b.name}")

        print(f"\n💡 Note : Vérifier dans le .emat quel canal correspond à quoi")
        print(f"   Généralement : R=Metalness/AO, G=Roughness, B=AO")

    except Exception as e:
        print(f"❌ Erreur extraction canaux : {e}")


def detect_file_type(file_path: Path) -> str:
    """
    Détecte si le fichier est BCR, MCR, ou autre
    """
    name_lower = file_path.name.lower()

    if '_bcr' in name_lower:
        return 'BCR'
    elif '_mcr' in name_lower:
        return 'MCR'
    elif '_nho' in name_lower or '_nmo' in name_lower:
        return 'NHO/NMO'
    else:
        return 'UNKNOWN'


def main():
    parser = argparse.ArgumentParser(
        description='Extrait les textures depuis fichiers BCR/MCR d\'Arma Reforger',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  python bcr_extractor.py Granite_01_BCR.edds
  python bcr_extractor.py GraniteCliff_01_MCR.edds --output-dir ./textures
  python bcr_extractor.py grass_04_BCR.edds
        """
    )

    parser.add_argument('file', type=Path, help='Fichier .edds à traiter (BCR ou MCR)')
    parser.add_argument('--output-dir', '-o', type=Path, default=Path('./extracted_textures'),
                       help='Dossier de sortie (défaut: ./extracted_textures)')
    parser.add_argument('--mip', type=int, default=0,
                       help='Niveau de mip à extraire (défaut: 0 = plus haute résolution)')
    parser.add_argument('--try-all-mips', action='store_true',
                       help='Si le mip principal échoue, essayer tous les autres mips automatiquement')

    args = parser.parse_args()

    # Vérifier fichier
    if not args.file.exists():
        print(f"❌ Fichier non trouvé : {args.file}")
        sys.exit(1)

    # Créer dossier sortie
    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(f"[INFO] Dossier sortie : {args.output_dir.absolute()}")

    # Détecter type
    file_type = detect_file_type(args.file)
    print(f"🔍 Type détecté : {file_type}")

    # Traiter selon type
    if file_type == 'BCR':
        process_bcr_file(args.file, args.output_dir, try_all_mips=args.try_all_mips)
    elif file_type == 'MCR':
        process_mcr_file(args.file, args.output_dir, try_all_mips=args.try_all_mips)
    elif file_type == 'NHO/NMO':
        print(f"⚠️  Fichier normal map (NHO/NMO)")
        print(f"   Extraction basique (sans interprétation spécifique)")

        # Extraction générique
        data = decode_edds_texture(args.file, target_mip=0, try_all_mips=args.try_all_mips)
        if data is not None:
            output = args.output_dir / f"{args.file.stem}.png"
            if data.ndim == 3:
                img = Image.fromarray(data[:, :, :3], mode='RGB')
            else:
                img = Image.fromarray(data, mode='L')
            img.save(output)
            print(f"✅ Sauvegardé : {output.name}")
    else:
        print(f"⚠️  Type inconnu, tentative extraction générique")

        data = decode_edds_texture(args.file, target_mip=0, try_all_mips=args.try_all_mips)
        if data is not None:
            output = args.output_dir / f"{args.file.stem}.png"
            if data.ndim == 3:
                img = Image.fromarray(data[:, :, :3], mode='RGB')
            else:
                img = Image.fromarray(data, mode='L')
            img.save(output)
            print(f"✅ Sauvegardé : {output.name}")

    print(f"\n{'='*70}")
    print(f"✅ Terminé !")
    print(f"{'='*70}")


if __name__ == "__main__":
    # Vérifier dépendances
    try:
        import lz4.block
    except ImportError:
        print("❌ Module lz4 non installé")
        print("   Installer avec : pip install lz4")
        sys.exit(1)

    try:
        from PIL import Image
    except ImportError:
        print("❌ Module PIL/Pillow non installé")
        print("   Installer avec : pip install pillow")
        sys.exit(1)

    main()
