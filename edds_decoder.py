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
    Essaie 148 (Zimnitrita), 128 (Eden), puis une recherche étendue.
    Vérifie TOUS les mips et leurs tailles pour éviter les faux positifs.
    """
    for candidate in [148, 128, 136, 140, 144, 152]:
        if len(data) < candidate + mipcount * 8:
            continue
        valid = True
        for i in range(mipcount):
            off = candidate + i * 8
            if data[off:off+4] not in _VALID_FOURCC:
                valid = False
                break
            sz = struct.unpack_from('<I', data, off + 4)[0]
            if sz > len(data):  # taille absurde
                valid = False
                break
        if valid:
            return candidate
    return 148  # fallback Zimnitrita (pas 128)


# ── LZ4 chained ───────────────────────────────────────────────────────────

def decompress_lz4_chained(data: bytes) -> bytes:
    """
    Décompresse un blob LZ4 chaîné (tranches de 64 Ko avec dictionnaire).

    Format :
        u32  taille_décompressée_totale
        [u32 taille_compressée & 0x7FFFFFFF][bloc LZ4]  × N

    Chaque chunk utilise les 64 Ko précédents comme dictionnaire.
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

        remaining = total_size - len(result)
        decomp_size = min(65536, remaining)

        # Utiliser le dictionnaire chaîné (64 Ko précédents)
        dict_data = bytes(result[-65536:]) if len(result) >= 65536 else b''
        if dict_data:
            decomp = lz4.block.decompress(comp_block,
                                          uncompressed_size=decomp_size,
                                          dict=dict_data)
        else:
            decomp = lz4.block.decompress(comp_block,
                                          uncompressed_size=decomp_size)

        result.extend(decomp)

    return bytes(result[:total_size])


def compress_lz4_chained(data: bytes) -> bytes:
    """
    Compresse un blob en LZ4 chaîné (tranches de 64 Ko avec dictionnaire).
    Chaque chunk utilise les 64 Ko précédents comme dictionnaire.
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
        if prev:
            comp = lz4.block.compress(chunk, mode='high_compression', store_size=False, dict=prev)
        else:
            comp = lz4.block.compress(chunk, mode='high_compression', store_size=False)
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
    Patch in-place d'un fichier .edds Enfusion existant.
    Remplace uniquement le blob du mip principal (512×512).
    Ne reconstruit jamais le header DDS (préserve format natif Workbench).

    Args:
        layer_img : (H, W) uint32 — nouvelles données du mip principal
        edds_path : chemin du fichier .edds existant

    Returns:
        True si succès, False si le fichier n'existe pas ou erreur
    """
    # Vérifier que le fichier existe
    if not edds_path.exists():
        print(f"[ERREUR] Fichier introuvable : {edds_path}")
        print(f"[INFO] encode_edds_layer nécessite un fichier existant (patch in-place uniquement)")
        return False

    try:
        # 1. Lire le fichier existant en entier
        with open(edds_path, 'rb') as f:
            existing_data = f.read()

        # 2. Parser le header pour obtenir mipcount
        if existing_data[:4] != b'DDS ':
            print(f"[ERREUR] Pas un fichier DDS valide")
            return False

        mipcount = struct.unpack_from('<I', existing_data, 28)[0]

        # 3. Détecter l'offset de la table des mips
        table_offset = _detect_table_offset(existing_data, mipcount)

        # 4. Parser la table des mips
        mip_table = []
        pos = table_offset
        for _ in range(mipcount):
            fourcc = bytes(existing_data[pos:pos+4])
            size = struct.unpack_from('<I', existing_data, pos + 4)[0]
            mip_table.append((fourcc, size))
            pos += 8

        data_start = pos

        # 5. Calculer l'offset du dernier blob (mip principal)
        blob_offset = data_start
        for i in range(mipcount - 1):
            blob_offset += mip_table[i][1]

        # 6. Compresser les nouvelles données du mip principal
        new_blob = compress_lz4_chained(layer_img.astype(np.uint32).tobytes())
        new_size = len(new_blob)

        # 7. Mettre à jour la taille dans la table
        # La table entry du dernier mip est à : table_offset + (mipcount - 1) * 8 + 4
        entry_offset = table_offset + (mipcount - 1) * 8 + 4
        data_mutable = bytearray(existing_data)
        struct.pack_into('<I', data_mutable, entry_offset, new_size)

        # 8. Assembler le nouveau fichier
        # Tout avant le blob du mip principal + nouveau blob
        result = bytes(data_mutable[:blob_offset]) + new_blob

        # 9. Écrire le résultat
        with open(edds_path, 'wb') as f:
            f.write(result)

        return True

    except Exception as e:
        print(f"[ERREUR] encode_edds_layer : {e}")
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


# ── Scan Health ───────────────────────────────────────────────────────────

def scan_health(data_dir: Path):
    """
    Scanner tous les *_layer.edds dans un dossier et vérifier leur intégrité.
    Auto-adaptatif : détecte automatiquement la résolution de référence.

    Vérifications :
    1. Résolution conforme à la référence
    2. table_offset conforme à la référence
    3. mip principal : size > 0, < taille fichier, total_size correct
    4. Décompression chunk[0] réussie (si LZ4)
    5. Fichier .ttile correspondant existe
    """
    # Trouver tous les fichiers _layer.edds
    edds_files = sorted(data_dir.glob("*_layer.edds"))

    if not edds_files:
        print(f"[ERR] Aucun fichier *_layer.edds trouvé dans {data_dir}")
        return

    # === AUTO-DÉTECTION RÉSOLUTION RÉFÉRENCE ===
    ref_width = None
    ref_height = None
    ref_mipcount = None
    ref_table_offset = None
    ref_fourcc = None

    for edds_path in edds_files:
        try:
            with open(edds_path, 'rb') as f:
                data = f.read()

            if data[:4] != b'DDS ' or b'ENF1' not in data[32:52]:
                continue

            header = data[:128]
            ref_height = struct.unpack_from('<I', header, 12)[0]
            ref_width = struct.unpack_from('<I', header, 16)[0]
            ref_mipcount = struct.unpack_from('<I', header, 28)[0]
            ref_table_offset = _detect_table_offset(data, ref_mipcount)

            # Lire la table pour obtenir le FourCC du dernier mip
            pos = ref_table_offset + (ref_mipcount - 1) * 8
            if pos + 4 <= len(data):
                ref_fourcc = data[pos:pos+4]

            # Premier fichier valide trouvé
            break

        except Exception:
            continue

    if ref_width is None:
        print(f"[ERR] Impossible de détecter la résolution de référence")
        return

    ref_resolution = ref_width * ref_height
    fourcc_str = ref_fourcc.decode('ascii', errors='replace') if ref_fourcc else "?"

    print(f"Map détectée : résolution {ref_width}×{ref_height}, table_offset={ref_table_offset}, format={fourcc_str}")
    print(f"Scan de {len(edds_files)} fichiers .edds")
    print()

    # === SCAN DE TOUS LES FICHIERS ===
    ok_count = 0
    corrupted = []       # [(filename, tile_id, reason), ...]
    wrong_format = []    # [(filename, tile_id, reason), ...]
    missing_ttile = []   # [(filename, tile_id), ...]

    for edds_path in edds_files:
        # Extraire tile_id du nom
        try:
            tile_id = int(edds_path.stem.split('_')[1])
        except (IndexError, ValueError):
            tile_id = -1

        try:
            with open(edds_path, 'rb') as f:
                data = f.read()

            # Vérification 1 : Header DDS
            if data[:4] != b'DDS ':
                corrupted.append((edds_path.name, tile_id, "pas un DDS"))
                continue

            # Lire header
            header = data[:128]
            height = struct.unpack_from('<I', header, 12)[0]
            width = struct.unpack_from('<I', header, 16)[0]
            mipcount = struct.unpack_from('<I', header, 28)[0]

            # Vérification 2 : ENF1
            if b'ENF1' not in header[32:52]:
                corrupted.append((edds_path.name, tile_id, "pas de marqueur ENF1"))
                continue

            # Vérification a : Résolution conforme
            if width * height != ref_resolution:
                wrong_format.append((edds_path.name, tile_id,
                                    f"{width}×{height} (attendu {ref_width}×{ref_height})"))
                continue

            # Vérification b : table_offset conforme
            table_offset = _detect_table_offset(data, mipcount)
            if table_offset != ref_table_offset:
                corrupted.append((edds_path.name, tile_id,
                                f"table_offset={table_offset} (attendu {ref_table_offset})"))
                continue

            if len(data) < table_offset + mipcount * 8:
                corrupted.append((edds_path.name, tile_id, f"table_offset={table_offset} hors limites"))
                continue

            # Vérification c : Parser la table des mips
            mip_table = []
            pos = table_offset
            for _ in range(mipcount):
                if pos + 8 > len(data):
                    corrupted.append((edds_path.name, tile_id, "table des mips tronquée"))
                    break
                fourcc = data[pos:pos+4]
                size = struct.unpack_from('<I', data, pos + 4)[0]
                mip_table.append((fourcc, size))
                pos += 8

            if len(mip_table) != mipcount:
                continue

            # Vérification c : Mip principal (dernier mip)
            last_fourcc, last_size = mip_table[-1]

            # FourCC conforme
            if last_fourcc != ref_fourcc:
                corrupted.append((edds_path.name, tile_id,
                                f"FourCC={last_fourcc.decode('ascii', errors='replace')} (attendu {fourcc_str})"))
                continue

            # size > 0 et < taille fichier
            if last_size == 0:
                corrupted.append((edds_path.name, tile_id, "mip principal size=0"))
                continue
            if last_size > len(data):
                corrupted.append((edds_path.name, tile_id, f"mip principal size={last_size} > taille fichier"))
                continue

            # Calculer l'offset du dernier mip
            data_start = pos
            mip_offset = data_start
            for fourcc, size in mip_table[:-1]:
                mip_offset += size

            if mip_offset + last_size > len(data):
                corrupted.append((edds_path.name, tile_id, "mip principal blob hors limites"))
                continue

            # Vérification c : total_size dans le blob
            blob = data[mip_offset:mip_offset + last_size]

            if last_fourcc == b'LZ4 ':
                # Lire total_size du blob LZ4
                if len(blob) < 4:
                    corrupted.append((edds_path.name, tile_id, "blob LZ4 trop court"))
                    continue

                total_size = struct.unpack_from('<I', blob, 0)[0]
                expected = width * height * 4

                if total_size != expected:
                    corrupted.append((edds_path.name, tile_id,
                                    f"total_size={total_size} != {expected}"))
                    continue

                # Vérification d : Décompression chunk[0]
                try:
                    pos_blob = 4
                    if pos_blob + 4 > len(blob):
                        corrupted.append((edds_path.name, tile_id, "chunk[0] header manquant"))
                        continue

                    comp_size = struct.unpack_from('<I', blob, pos_blob)[0] & 0x7FFFFFFF
                    pos_blob += 4

                    if comp_size == 0 or pos_blob + comp_size > len(blob):
                        corrupted.append((edds_path.name, tile_id, f"chunk[0] size={comp_size} invalide"))
                        continue

                    comp_block = blob[pos_blob:pos_blob + comp_size]
                    decomp_size = min(65536, total_size)

                    # Tenter la décompression
                    _ = lz4.block.decompress(comp_block, uncompressed_size=decomp_size)

                except Exception as e:
                    corrupted.append((edds_path.name, tile_id, f"décompression échouée: {str(e)[:40]}"))
                    continue

            elif last_fourcc == b'COPY':
                # Vérifier que la taille du blob correspond
                expected = width * height * 4
                if last_size != expected:
                    corrupted.append((edds_path.name, tile_id,
                                    f"COPY size={last_size} != {expected}"))
                    continue

            # Vérification e : Fichier .ttile correspondant existe
            ttile_path = data_dir / f"Terrain_{tile_id}.ttile"
            if not ttile_path.exists():
                missing_ttile.append((edds_path.name, tile_id))

            # Si on arrive ici, le fichier est OK
            ok_count += 1

        except Exception as e:
            corrupted.append((edds_path.name, tile_id, f"erreur: {str(e)[:40]}"))

    # === AFFICHAGE RÉSULTATS ===
    corrupted_count = len(corrupted)
    wrong_format_count = len(wrong_format)
    missing_ttile_count = len(missing_ttile)

    print(f"✓ OK              : {ok_count} fichiers")
    print(f"✗ Corrompus       : {corrupted_count} fichiers")
    print(f"⚠ Hors format     : {wrong_format_count} fichiers")
    print(f"⚠ Ttile manquant  : {missing_ttile_count} fichiers")
    print()

    if corrupted:
        print("FICHIERS CORROMPUS :")
        for filename, tile_id, reason in corrupted:
            print(f"  {filename} — {reason}")
        print()

    if wrong_format:
        print("FICHIERS HORS FORMAT :")
        for filename, tile_id, reason in wrong_format:
            print(f"  {filename} — {reason}")
        print()

    if missing_ttile:
        print("FICHIERS SANS .TTILE :")
        for filename, tile_id in missing_ttile:
            print(f"  {filename}")
        print()

    # Collecter tous les tile IDs à vérifier
    all_issues = set()
    for _, tile_id, _ in corrupted:
        if tile_id >= 0:
            all_issues.add(tile_id)
    for _, tile_id, _ in wrong_format:
        if tile_id >= 0:
            all_issues.add(tile_id)
    for _, tile_id in missing_ttile:
        if tile_id >= 0:
            all_issues.add(tile_id)

    if all_issues:
        tile_ids_str = ' '.join(str(tid) for tid in sorted(all_issues))
        print(f"Tile IDs à vérifier : {tile_ids_str}")


# ── Test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage :")
        print("  python edds_decoder.py <path_to_layer.edds>")
        print("  python edds_decoder.py --scan-health <path_to_Data_dir>")
        sys.exit(1)

    # Mode scan-health
    if sys.argv[1] == "--scan-health":
        if len(sys.argv) < 3:
            print("Usage : python edds_decoder.py --scan-health <path_to_Data_dir>")
            sys.exit(1)

        data_dir = Path(sys.argv[2])
        if not data_dir.exists():
            print(f"Dossier non trouvé : {data_dir}")
            sys.exit(1)

        scan_health(data_dir)
        sys.exit(0)

    # Mode décodage fichier unique
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
