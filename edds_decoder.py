"""
edds_decoder.py — Décodeur EDDS universel pour Arma Reforger / Enfusion
Supporte automatiquement tous les mondes (Eden, Zimnitrita, etc.)

Différences par monde :
    Eden        : 256×256, 9 mips,  table à offset 128
    Zimnitrita  : 512×512, 10 mips, table à offset 148
    → Tout est détecté automatiquement depuis le header DDS.
"""

import struct
import numpy as np
from pathlib import Path
from typing import Optional
import lz4.block


# FourCC valides pour la table des mips Enfusion
_VALID_FOURCC = {b'COPY', b'LZ4 ', b'LZB4', b'LZ4B'}


# ── Détection automatique ──────────────────────────────────────────────────

def _detect_table_offset(data: bytes, mipcount: int) -> int:
    """
    Trouve l'offset de la table des mips en cherchant le premier FourCC valide.
    Essaie 128, 148, puis une recherche étendue.
    """
    for candidate in [128, 148, 136, 140, 144, 152]:
        if len(data) > candidate + 4 and data[candidate:candidate+4] in _VALID_FOURCC:
            # Vérification supplémentaire : toutes les entrées de la table
            # doivent avoir un FourCC valide
            valid = True
            for i in range(min(mipcount, 3)):
                off = candidate + i * 8
                if data[off:off+4] not in _VALID_FOURCC:
                    valid = False
                    break
            if valid:
                return candidate
    return 128  # fallback


# ── LZ4 chained ───────────────────────────────────────────────────────────

def decompress_lz4_chained(data: bytes) -> bytes:
    """
    Décompresse un blob LZ4 chaîné (tranches de 64 Ko avec dictionnaire).

    Format :
        u32  taille_décompressée_totale
        [u32 taille_compressée & 0x7FFFFFFF][bloc LZ4]  × N
    """
    pos = 0
    total_size = struct.unpack_from('<I', data, pos)[0]
    pos += 4

    result = bytearray()

    while pos < len(data):
        if pos + 4 > len(data):
            break

        comp_size = struct.unpack_from('<I', data, pos)[0] & 0x7FFFFFFF
        pos += 4

        if comp_size == 0 or pos + comp_size > len(data):
            break

        comp_block = data[pos:pos + comp_size]
        pos += comp_size

        if len(result) >= 65536:
            dict_data = bytes(result[-65536:])
            decomp = lz4.block.decompress(comp_block, uncompressed_size=65536, dict=dict_data)
        else:
            decomp = lz4.block.decompress(comp_block, uncompressed_size=65536)

        result.extend(decomp)

    return bytes(result[:total_size])


def compress_lz4_chained(data: bytes) -> bytes:
    """
    Compresse un blob en LZ4 chaîné (tranches de 64 Ko avec dictionnaire).
    Format inverse de decompress_lz4_chained.
    """
    CHUNK = 65536
    total_size = len(data)
    result = bytearray()
    result.extend(struct.pack('<I', total_size))

    pos = 0
    prev = b''

    while pos < total_size:
        chunk = data[pos:pos + CHUNK]
        comp = (lz4.block.compress(chunk, mode='high_compression', dict=prev)
                if prev else
                lz4.block.compress(chunk, mode='high_compression'))
        result.extend(struct.pack('<I', len(comp)))
        result.extend(comp)
        prev = (prev + chunk)[-CHUNK:]
        pos += CHUNK

    return bytes(result)


# ── Lecture ────────────────────────────────────────────────────────────────

def decode_edds_layer(edds_path: Path) -> Optional[np.ndarray]:
    """
    Décode un fichier *_layer.edds Enfusion (tous mondes).

    Returns:
        np.ndarray (H, W) dtype uint32  — pixels R32_UINT du mip principal
        None si erreur
    """
    with open(edds_path, 'rb') as f:
        data = f.read()

    if data[:4] != b'DDS ':
        print(f"[ERREUR] {edds_path.name} : pas un DDS")
        return None

    header = data[:128]
    height   = struct.unpack_from('<I', header, 12)[0]
    width    = struct.unpack_from('<I', header, 16)[0]
    mipcount = struct.unpack_from('<I', header, 28)[0]

    # Vérifier ENF1
    if b'ENF1' not in header[32:52]:
        print(f"[WARN] {edds_path.name} : pas de marqueur ENF1, tentative DDS standard")
        return _decode_standard_dds_r32(data, width, height)

    # Détecter l'offset de la table automatiquement
    table_offset = _detect_table_offset(data, mipcount)

    # Parser la table
    mip_table = []
    pos = table_offset
    for _ in range(mipcount):
        if pos + 8 > len(data):
            break
        fourcc = data[pos:pos+4]
        size   = struct.unpack_from('<I', data, pos + 4)[0]
        mip_table.append((fourcc, size))
        pos += 8

    # Données après la table
    data_start = pos

    # Sauter jusqu'au dernier mip (résolution max, stocké en dernier)
    mip_offset = data_start
    for fourcc, size in mip_table[:-1]:
        mip_offset += size

    fourcc, size = mip_table[-1]
    raw = data[mip_offset:mip_offset + size]

    if fourcc == b'COPY':
        mip_bytes = raw
    elif fourcc == b'LZ4 ':
        mip_bytes = decompress_lz4_chained(raw)
    else:
        print(f"[ERREUR] {edds_path.name} : FourCC non supporté : {fourcc}")
        return None

    expected = width * height * 4
    if len(mip_bytes) != expected:
        print(f"[WARN] {edds_path.name} : {len(mip_bytes)} bytes, attendu {expected} "
              f"({width}×{height}×4)")

    pixels = np.frombuffer(mip_bytes[:expected], dtype=np.uint32)
    try:
        return pixels.reshape((height, width))
    except Exception as e:
        print(f"[ERREUR] reshape impossible : {e}")
        return None


def _decode_standard_dds_r32(data: bytes, width: int, height: int) -> Optional[np.ndarray]:
    """Fallback : DDS standard R32_UINT sans ENF1."""
    pixel_data = data[128:128 + width * height * 4]
    if len(pixel_data) < width * height * 4:
        return None
    return np.frombuffer(pixel_data, dtype=np.uint32).reshape((height, width))


# ── Écriture ───────────────────────────────────────────────────────────────

def encode_edds_layer(layer_img: np.ndarray, edds_path: Path) -> bool:
    """
    Encode une image layer en fichier .edds Enfusion.
    Détecte automatiquement la résolution et le nombre de mips.

    Args:
        layer_img : (H, W) uint32
        edds_path : chemin de sortie

    Returns:
        True si succès
    """
    height, width = layer_img.shape

    # Nombre de mips = log2(max(W,H)) + 1
    mipcount = int(np.log2(max(width, height))) + 1

    # Offset de la table selon la résolution
    # 512×512 (Zimnitrita) → 148  |  autres → 128
    table_offset = 148 if (width == 512 and height == 512) else 128
    metadata_size = table_offset - 128  # 20 ou 0

    # ── Header DDS (128 bytes) ──
    header = bytearray(128)
    header[0:4] = b'DDS '
    struct.pack_into('<I', header,  4, 124)
    struct.pack_into('<I', header,  8, 0x1 | 0x2 | 0x4 | 0x1000 | 0x20000)
    struct.pack_into('<I', header, 12, height)
    struct.pack_into('<I', header, 16, width)
    struct.pack_into('<I', header, 20, width * 4)
    struct.pack_into('<I', header, 24, 1)
    struct.pack_into('<I', header, 28, mipcount)
    header[32:36] = b'ENF1'
    struct.pack_into('<I', header, 76, 32)
    struct.pack_into('<I', header, 80, 0x00020000)
    header[84:88] = b'    '
    struct.pack_into('<I', header, 108, 0x1000 | 0x400000 | 0x8)

    # ── Générer les mips (grand → petit, puis inverser) ──
    mips = [layer_img]
    for _ in range(1, mipcount):
        prev = mips[-1]
        mips.append(prev[::2, ::2][:max(1, prev.shape[0]//2),
                                    :max(1, prev.shape[1]//2)])
    mips_ordered = list(reversed(mips))  # petit → grand (ordre EDDS)

    # ── Compresser chaque mip ──
    mip_table, mip_blocks = [], []
    for mip in mips_ordered:
        comp = compress_lz4_chained(mip.astype(np.uint32).tobytes())
        mip_table.append((b'LZ4 ', len(comp)))
        mip_blocks.append(comp)

    # ── Assembler ──
    result = bytearray(header)

    # Metadata (0 ou 20 bytes selon le monde)
    if metadata_size == 20:
        result.extend(struct.pack('<5I', 42, 3, 0, 1, 0))

    # Table des mips
    for fourcc, size in mip_table:
        result.extend(fourcc)
        result.extend(struct.pack('<I', size))

    # Données
    for block in mip_blocks:
        result.extend(block)

    try:
        with open(edds_path, 'wb') as f:
            f.write(result)
        return True
    except Exception as e:
        print(f"[ERREUR] écriture {edds_path} : {e}")
        return False


# ── Extraction des poids matériaux ────────────────────────────────────────

def extract_weights_from_pixel(pixel: int) -> np.ndarray:
    """
    Extrait les 7 poids (w0..w6) d'un pixel R32_UINT.

    Encodage Enfusion :
        bits  0- 4 : w1
        bits  5- 9 : w2
        bits 10-14 : w3
        bits 15-19 : w4
        bits 20-24 : w5
        bits 25-29 : w6
        w0 = 31 − Σ(w1..w6)   (implicite)

    Returns:
        np.array([w0..w6], float32) normalisé [0, 1]
    """
    ws = [(pixel >> (s * 5)) & 0x1F for s in range(6)]
    w0 = 31 - sum(ws)
    return np.array([w0, *ws], dtype=np.float32) / 31.0


def extract_all_weights(layer_img: np.ndarray) -> np.ndarray:
    """
    Extrait les poids de tous les pixels (vectorisé).

    Args:
        layer_img : (H, W) uint32

    Returns:
        (H, W, 7) float32 — poids normalisés [0, 1]
        Axe 2 : [w0, w1, w2, w3, w4, w5, w6]
    """
    h, w = layer_img.shape
    weights = np.zeros((h, w, 7), dtype=np.float32)

    w1 = (layer_img >>  0) & 0x1F
    w2 = (layer_img >>  5) & 0x1F
    w3 = (layer_img >> 10) & 0x1F
    w4 = (layer_img >> 15) & 0x1F
    w5 = (layer_img >> 20) & 0x1F
    w6 = (layer_img >> 25) & 0x1F

    weights[:, :, 0] = (31 - (w1 + w2 + w3 + w4 + w5 + w6)) / 31.0
    weights[:, :, 1] = w1 / 31.0
    weights[:, :, 2] = w2 / 31.0
    weights[:, :, 3] = w3 / 31.0
    weights[:, :, 4] = w4 / 31.0
    weights[:, :, 5] = w5 / 31.0
    weights[:, :, 6] = w6 / 31.0

    return weights


def pack_weights_to_pixel(weights_7: np.ndarray) -> np.ndarray:
    """
    Ré-encode un array de poids (H, W, 7) float32 → (H, W) uint32.
    w0 est ignoré (implicite), seuls w1..w6 sont encodés.

    Args:
        weights_7 : (H, W, 7) float32 [0, 1]

    Returns:
        (H, W) uint32
    """
    pixels = np.zeros(weights_7.shape[:2], dtype=np.uint32)
    for i in range(1, 7):
        w_int = np.clip(np.round(weights_7[:, :, i] * 31), 0, 31).astype(np.uint32)
        pixels |= (w_int << ((i - 1) * 5))
    return pixels


# ── Test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage : python edds_decoder.py <path_to_layer.edds>")
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"Fichier non trouvé : {path}")
        sys.exit(1)

    print(f"Décodage : {path.name}")
    img = decode_edds_layer(path)

    if img is None:
        print("Échec.")
        sys.exit(1)

    print(f"  Shape   : {img.shape}  dtype={img.dtype}")
    print(f"  Min px  : 0x{img.min():08X}")
    print(f"  Max px  : 0x{img.max():08X}")

    weights = extract_all_weights(img)
    print(f"\n  Poids (H×W×7) : {weights.shape}")
    for i in range(7):
        usage = (weights[:, :, i] > 0).sum()
        pct   = usage / img.size * 100
        print(f"    w{i} : {usage:7d} cellules ({pct:5.1f}%)")

    repacked = pack_weights_to_pixel(weights)
    match = np.all(repacked == img)
    print(f"\n  Round-trip pack/unpack : {'✓ OK' if match else '✗ DIFF'}")
