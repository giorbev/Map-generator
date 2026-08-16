"""
merge_mat.py — Merge de matériaux dans les .ttile + _layer.dds + _layer.edds

Écrit simultanément :
  1. .ttile (LRS2 + GCTD)
  2. _layer.dds (mip0 512×512 R32_UINT)
  3. _layer.edds (mip0 LZ4 chaîné)

Basé sur validation expérimentale août 2026 : WB écrit les 3 fichiers simultanément,
écrire uniquement .ttile crée incohérence.

Usage:
    python merge_mat.py --src 0 --dst 3 --tile 4,27 --bloc 18,110 --dry-run
    python merge_mat.py --src 0 --dst 3 --tile 4,27
    python merge_mat.py --src 0,mat:9 --dst 3 --all
    python merge_mat.py --restore
"""

import struct, sys, argparse, shutil
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Set

sys.path.insert(0, str(Path(__file__).parent))
from terrain_terr_reader import read_mats_from_terr
from edds_decoder import compress_lz4_chained

TERRAIN_ROOT = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain")
DATA_DIR     = TERRAIN_ROOT / ".Data"
EDITOR_DATA_DIR = TERRAIN_ROOT / ".EditorData"
TERR_PATH    = TERRAIN_ROOT / "terrain.terr"
GRID_W       = 32
NUM_BLK      = 4  # Blocs par tuile par axe
GCTD_PAYLOAD_SIZE = 2026  # Taille section GCTD par bloc (validé expérimentalement sur Zimnitrita)

# ─── IFF ──────────────────────────────────────────────────────────────────────

def parse_ttile(data):
    chunks = {}
    pos = 12
    while pos < len(data) - 8:
        tag = bytes(data[pos:pos+4])
        size = struct.unpack_from('>I', data, pos+4)[0]
        if size > len(data): break
        chunks[tag] = (pos, size, bytes(data[pos+8:pos+8+size]))
        pos += 8 + size + (size % 2)
    return chunks

def rebuild_ttile(original, replacements):
    chunks = []
    pos = 12
    while pos < len(original) - 8:
        tag = bytes(original[pos:pos+4])
        size = struct.unpack_from('>I', original, pos+4)[0]
        if size > len(original): break
        chunks.append((tag, original[pos+8:pos+8+size]))
        pos += 8 + size + (size % 2)
    out = bytearray(original[0:4] + b'\x00\x00\x00\x00' + original[8:12])
    for tag, payload in chunks:
        new_payload = replacements.get(tag, payload)
        out += tag + struct.pack('>I', len(new_payload)) + new_payload
        if len(new_payload) % 2: out += b'\x00'
    struct.pack_into('>I', out, 4, len(out) - 8)
    return bytes(out)

# ─── LRS2 ─────────────────────────────────────────────────────────────────────

def parse_lrs2(payload):
    entries = {}
    p = 0
    while p < len(payload) - 6:
        index = struct.unpack_from('<I', payload, p)[0]
        count = struct.unpack_from('<H', payload, p+4)[0]
        if count == 0 or count > 7: break
        mats = list(struct.unpack_from(f'<{count}H', payload, p+6))
        bx = index & 0x7F
        by = (index >> 7) & 0x7F
        entries[(bx, by)] = (mats, index)
        p += 6 + count * 2
    return entries

def build_lrs2(entries):
    parts = []
    for (bx, by), (mats, orig_index) in sorted(entries.items()):
        parts.append(struct.pack('<IH', orig_index, len(mats)))
        parts.append(struct.pack(f'<{len(mats)}H', *mats))
    return b''.join(parts)

# ─── GCTD ─────────────────────────────────────────────────────────────────────

def parse_gctd(payload):
    """
    Parse chunk GCTD : sections de data par bloc (bx,by).

    Auto-détecte payload_size en testant les candidats [2026, 2025, 145, 144, 513, 512].
    Fallback : GCTD_PAYLOAD_SIZE = 2026.
    """
    header = payload[:2]

    # Auto-détection de payload_size
    CANDIDATES = [2026, 2025, 145, 144, 513, 512]
    payload_size = GCTD_PAYLOAD_SIZE  # Fallback

    if len(payload) >= 2 + 4:  # Au moins un header bx1,by1
        for candidate in CANDIDATES:
            # Position du 2e header : pos=2 + 4 + candidate
            pos_next = 2 + 4 + candidate
            if pos_next + 4 <= len(payload):
                bx2 = struct.unpack_from('<H', payload, pos_next)[0]
                by2 = struct.unpack_from('<H', payload, pos_next + 2)[0]
                if bx2 < 128 and by2 < 128:
                    payload_size = candidate
                    break

    sections = {}
    section_size = 4 + payload_size
    p = 2
    while p + section_size <= len(payload):
        bx = struct.unpack_from('<H', payload, p)[0]
        by = struct.unpack_from('<H', payload, p+2)[0]
        sections[(bx, by)] = bytearray(payload[p+4:p+4+payload_size])
        p += section_size
    return header, sections, payload_size

def build_gctd(header, sections):
    out = bytearray(header)
    for (bx, by), data in sorted(sections.items()):
        out += struct.pack('<HH', bx, by) + bytes(data)
    return bytes(out)

# ─── Layer DDS ────────────────────────────────────────────────────────────────

def parse_layer_dds(dds_path: Path) -> Optional[bytearray]:
    """
    Lit _layer.dds et retourne mip0 (512×512 uint32).
    Retourne None si fichier absent.

    Structure : header DDS (128 bytes) + extension DX10 (20 bytes) + mip0.
    """
    if not dds_path.exists():
        return None

    data = dds_path.read_bytes()
    HEADER_SIZE = 148  # DDS 128 + DX10 20
    MIP0_SIZE = 512 * 512 * 4

    if len(data) < HEADER_SIZE + MIP0_SIZE:
        return None

    # Mip0 commence à offset 148
    mip0 = bytearray(data[HEADER_SIZE:HEADER_SIZE + MIP0_SIZE])
    return mip0


def write_layer_dds(dds_path: Path, mip0_data: bytearray):
    """
    Écrit _layer.dds avec nouveau mip0.
    Conserve header DDS+DX10 + mip1..9 existants.

    Structure : header DDS (128 bytes) + extension DX10 (20 bytes) + mip0 + mip1..9.
    """
    if not dds_path.exists():
        return  # Pas de fichier existant → skip

    original = dds_path.read_bytes()
    HEADER_SIZE = 148  # DDS 128 + DX10 20
    MIP0_SIZE = 512 * 512 * 4

    header = original[:HEADER_SIZE]
    mip1_9 = original[HEADER_SIZE + MIP0_SIZE:]  # Tout après mip0

    # Backup
    bak = dds_path.with_suffix('.dds.bak')
    if not bak.exists():
        shutil.copy2(dds_path, bak)

    # Écriture
    with open(dds_path, 'wb') as f:
        f.write(header)
        f.write(mip0_data)
        f.write(mip1_9)


def write_layer_edds(edds_path: Path, mip0_data: bytearray):
    """
    Met à jour _layer.edds avec nouveau mip0 compressé LZ4 chaîné.

    Structure validée expérimentalement :
    - Offset 0   : header DDS standard (128 bytes)
    - Offset 36  : marqueur ENF1
    - Offset 128 : header ENF1 (20 bytes)
    - Offset 148 : tag mip "LZ4 " (4 bytes)
    - Offset 152 : taille mip0 compressé (uint32 LE)
    - Offset 156 : taille mip0 décompressé (uint32 LE)
    - Offset 160 : data mip0 LZ4 chaîné
    """
    if not edds_path.exists():
        return  # Pas de fichier existant → skip

    # Compresser nouveau mip0 en LZ4 chaîné
    mip0_compressed = compress_lz4_chained(bytes(mip0_data))
    new_compressed_size = len(mip0_compressed)
    decompressed_size = len(mip0_data)  # 512×512×4 = 1048576

    # Lire fichier existant
    original = edds_path.read_bytes()

    # Backup
    bak = edds_path.with_suffix('.edds.bak')
    if not bak.exists():
        shutil.copy2(edds_path, bak)

    # Reconstruire fichier
    # Bytes 0→151 : header DDS + ENF1 + tag LZ4 (inchangés)
    header_part = bytearray(original[:152])

    # Offset 152 : nouvelle taille compressée
    struct.pack_into('<I', header_part, 152, new_compressed_size)

    # Note : offset 156 (taille décompressée) reste inchangée dans header_part
    # car on écrit seulement jusqu'à offset 152+4=156

    # Écriture complète
    with open(edds_path, 'wb') as f:
        f.write(header_part)              # 0→155 (header + taille compressée)
        f.write(original[156:160])        # 156→159 (taille décompressée, inchangée)
        f.write(mip0_compressed)          # 160→fin (data LZ4)

    # Fichier tronqué/étendu automatiquement à 160 + new_compressed_size


def merge_layer_dds_block(
    mip0_data: bytearray,
    bx: int,
    by: int,
    tile_id: int,
    old_mats: List[int],
    new_mats: List[int],
    src_mat_ids: Set[int],
    dst_mat: int
):
    """
    Merge poids dans _layer.dds pour un bloc.

    Logique :
    - w0..w6 correspondent aux slots 0..6 de la LRS2
    - Quand on supprime un slot, tous les slots suivants décalent
    - Il faut reconstruire les poids selon le nouveau mapping mat_id

    Args:
        mip0_data: Données mip0 (512×512 uint32) modifiables in-place
        bx, by: Coordonnées globales du bloc
        tile_id: ID de la tuile
        old_mats: Liste LRS2 avant merge
        new_mats: Liste LRS2 après merge
        src_mat_ids: mat_ids sources à merger
        dst_mat: mat_id destination (déjà connu dans process_tile)
    """
    # Calculer by_local dans la tuile
    ty = tile_id // GRID_W
    by_local = by - (ty * NUM_BLK)
    bx_local = bx - ((tile_id % GRID_W) * NUM_BLK)

    # Région du bloc dans mip0 : 128×128 pixels
    x_start = bx_local * 128
    y_start = by_local * 128

    # Utiliser dst_mat passé en paramètre (déjà connu dans process_tile)
    if dst_mat not in new_mats:
        return  # dst_mat absent de new_mats, skip

    dst_new_slot = new_mats.index(dst_mat)

    # Construire mapping old_slot → new_slot (_layer.dds : redistribution vers dst_mat)
    old_to_new = {}
    for old_slot, mat_id in enumerate(old_mats):
        if mat_id in new_mats:
            # Mat conservé → mapper vers nouvelle position
            new_slot = new_mats.index(mat_id)
            old_to_new[old_slot] = new_slot
        else:
            # Mat supprimé → redistribuer vers dst_mat
            old_to_new[old_slot] = dst_new_slot

    # Traiter chaque pixel du bloc
    for dy in range(128):
        for dx in range(128):
            x = x_start + dx
            y = y_start + dy

            if x >= 512 or y >= 512:
                continue

            # Offset dans mip0_data
            offset = (y * 512 + x) * 4
            pixel_value = struct.unpack_from('<I', mip0_data, offset)[0]

            # Extraire poids w1..w6
            weights = []
            for i in range(6):
                w = (pixel_value >> (5 * i)) & 0x1F
                weights.append(w)

            # Calculer w0 implicite
            w0 = 31 - sum(weights)
            all_weights = [w0] + weights

            # Appliquer mapping old_slot → new_slot
            new_weights = [0] * 7
            for old_slot in range(min(len(old_mats), 7)):
                if old_slot in old_to_new:
                    new_slot = old_to_new[old_slot]
                    if new_slot < 7:
                        new_weights[new_slot] += all_weights[old_slot]

            # Normaliser si dépassement
            total = sum(new_weights[:len(new_mats)])
            if total > 31:
                # Redistribution proportionnelle
                factor = 31.0 / total
                for i in range(len(new_mats)):
                    new_weights[i] = int(new_weights[i] * factor)
                # Ajuster w0 pour atteindre exactement 31
                new_weights[0] = 31 - sum(new_weights[1:len(new_mats)])

            # Reconstruire pixel (w0 implicite, w1..w6 dans bits 0..29)
            new_pixel = 0
            for i in range(min(6, len(new_mats) - 1)):
                new_pixel |= (new_weights[i + 1] & 0x1F) << (5 * i)

            # Écrire
            struct.pack_into('<I', mip0_data, offset, new_pixel)


# ─── Merge bloc ───────────────────────────────────────────────────────────────

def merge_bloc(mats, gctd_data, src_slots, src_mat_ids, dst_mat):
    """
    Merge en une seule passe : construit directement old_slot -> final_slot.

    src_slots   : slots locaux à merger vers dst (ex: {0} = w0)
    src_mat_ids : mat_ids à merger vers dst (ex: {9} = Dirt_02)
    dst_mat     : mat_id destination (doit être dans mats)
    """
    # Calculer les slots effectifs à supprimer
    slots_to_merge = set(src_slots)
    for mid in src_mat_ids:
        if mid in mats:
            slots_to_merge.add(mats.index(mid))

    if not slots_to_merge:
        return mats, gctd_data, False
    if dst_mat not in mats:
        return mats, gctd_data, False

    dst_slot_old = mats.index(dst_mat)
    if dst_slot_old in slots_to_merge:
        return mats, gctd_data, False  # src == dst

    # Construire new_mats (sans les slots mergés)
    new_mats = [m for i, m in enumerate(mats) if i not in slots_to_merge]

    # Construire le mapping direct old_slot -> new_slot en une passe
    # Les slots mergés pointent vers slot0 (décalage simple WB)
    new_dst_slot = new_mats.index(dst_mat)
    old_to_new = {}
    new_idx = 0
    for old_slot in range(len(mats)):
        if old_slot in slots_to_merge:
            old_to_new[old_slot] = 0  # → slot0 de new_mats (pas dst_mat)
        else:
            old_to_new[old_slot] = new_idx
            new_idx += 1

    # Appliquer le remapping GCTD en une seule passe
    new_gctd = bytearray(len(gctd_data))
    for i, idx in enumerate(gctd_data):
        old_slot = idx // 4
        sub = idx % 4
        if old_slot >= len(mats):
            new_gctd[i] = idx  # Laisser inchangé — cellule invalide/TMAT
        else:
            new_gctd[i] = old_to_new.get(old_slot, 0) * 4 + sub

    return new_mats, new_gctd, True

# ─── Traitement tuile ─────────────────────────────────────────────────────────

def process_tile(tile_id, src_slots, src_mat_ids, dst_mat,
                 bloc_filter, dry_run):
    ttile_path = DATA_DIR / f"Terrain_{tile_id}.ttile"
    layer_dds_path = EDITOR_DATA_DIR / f"Terrain_{tile_id}_layer.dds"
    layer_edds_path = EDITOR_DATA_DIR / f"Terrain_{tile_id}_layer.edds"

    if not ttile_path.exists(): return 0

    data = ttile_path.read_bytes()
    chunks = parse_ttile(data)
    if b'LRS2' not in chunks or b'GCTD' not in chunks: return 0

    _, _, lrs2_payload = chunks[b'LRS2']
    _, _, gctd_payload = chunks[b'GCTD']

    lrs2_entries = parse_lrs2(lrs2_payload)
    gctd_header, gctd_sections, payload_size = parse_gctd(gctd_payload)

    new_lrs2 = dict(lrs2_entries)
    changed_blocks = []  # Liste (bx, by, old_mats, new_mats)
    changed = 0

    for (bx, by), (mats, orig_index) in lrs2_entries.items():
        if bloc_filter and (bx, by) not in bloc_filter: continue
        if (bx, by) not in gctd_sections:
            continue
        if dst_mat not in mats: continue

        new_mats, new_gctd, ok = merge_bloc(
            mats, gctd_sections[(bx, by)],
            src_slots, src_mat_ids, dst_mat)

        if ok:
            changed_blocks.append((bx, by, mats, new_mats))
            new_lrs2[(bx, by)] = (new_mats, orig_index)
            gctd_sections[(bx, by)] = new_gctd
            changed += 1

    if changed == 0: return 0
    if dry_run: return changed

    # ─── Écriture .ttile ──────────────────────────────────────────────────────
    bak = ttile_path.with_suffix('.ttile.bak')
    if not bak.exists(): shutil.copy2(ttile_path, bak)

    new_data = rebuild_ttile(data, {
        b'LRS2': build_lrs2(new_lrs2),
        b'GCTD': build_gctd(gctd_header, gctd_sections),
    })
    ttile_path.write_bytes(new_data)

    # ─── Écriture _layer.dds + _layer.edds ───────────────────────────────────
    mip0_data = parse_layer_dds(layer_dds_path)
    if mip0_data is not None:
        for bx, by, old_mats, new_mats in changed_blocks:
            merge_layer_dds_block(
                mip0_data, bx, by, tile_id,
                old_mats, new_mats, src_mat_ids, dst_mat
            )
        write_layer_dds(layer_dds_path, mip0_data)
        write_layer_edds(layer_edds_path, mip0_data)

    return changed

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--src', required=False,
        help='Slot(s)/mat_ids source. Ex: 0 (slot0=w0), mat:2 (mat_id), 0,mat:9')
    parser.add_argument('--dst', type=int, default=None)
    parser.add_argument('--all', action='store_true')
    parser.add_argument('--tile', type=str, default=None)
    parser.add_argument('--tiles', type=str, nargs='+', default=None)
    parser.add_argument('--bloc', type=str, default=None)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--restore', action='store_true')
    args = parser.parse_args()

    if args.restore:
        ttile_baks = list(DATA_DIR.glob('*.ttile.bak'))
        dds_baks = list(EDITOR_DATA_DIR.glob('*_layer.dds.bak'))
        edds_baks = list(EDITOR_DATA_DIR.glob('*_layer.edds.bak'))
        total = len(ttile_baks) + len(dds_baks) + len(edds_baks)
        print(f"Restauration de {total} fichiers ({len(ttile_baks)} .ttile, {len(dds_baks)} .dds, {len(edds_baks)} .edds)...")
        for bak in ttile_baks:
            shutil.copy2(bak, bak.with_suffix(''))
        for bak in dds_baks:
            shutil.copy2(bak, bak.with_suffix(''))
        for bak in edds_baks:
            shutil.copy2(bak, bak.with_suffix(''))
        print("OK")
        return

    if not args.src or args.dst is None:
        print("--src et --dst requis"); sys.exit(1)

    surfaces_data = read_mats_from_terr(TERR_PATH)
    surfaces = [e["name"] for e in surfaces_data]

    src_slots   = set()
    src_mat_ids = set()
    for token in args.src.split(','):
        token = token.strip()
        if token.startswith('mat:'):
            src_mat_ids.add(int(token[4:]))
        else:
            src_slots.add(int(token))

    dst_mat  = args.dst
    dst_name = surfaces[dst_mat] if dst_mat < len(surfaces) else str(dst_mat)
    src_desc = []
    if src_slots:   src_desc.append(f"slot(s){src_slots}")
    if src_mat_ids:
        names = [surfaces[m] if m < len(surfaces) else str(m) for m in src_mat_ids]
        src_desc.append(f"mat{src_mat_ids}({','.join(names)})")
    print(f"Merge : {' + '.join(src_desc)} -> {dst_mat}({dst_name})")
    if args.dry_run: print("[DRY-RUN]")

    bloc_filter = None
    if args.bloc:
        bx, by = map(int, args.bloc.split(','))
        bloc_filter = {(bx, by)}
        print(f"Bloc : ({bx},{by})")

    if args.all:
        tile_ids = [ty * GRID_W + tx for ty in range(GRID_W) for tx in range(GRID_W)]
    elif args.tiles:
        tile_ids = [int(t.split(',')[1])*GRID_W + int(t.split(',')[0]) for t in args.tiles]
    elif args.tile:
        tx, ty = map(int, args.tile.split(','))
        tile_ids = [ty * GRID_W + tx]
    else:
        print("--all, --tile ou --tiles requis"); sys.exit(1)

    total_blocs = total_tiles = 0
    for tid in tile_ids:
        n = process_tile(tid, src_slots, src_mat_ids, dst_mat,
                         bloc_filter, args.dry_run)
        if n > 0:
            total_blocs += n
            total_tiles += 1
            tx, ty = tid % GRID_W, tid // GRID_W
            print(f"  {'[DRY]' if args.dry_run else 'OK'} "
                  f"({tx},{ty}) T{tid}: {n} blocs")

    print(f"\nTotal: {total_blocs} blocs dans {total_tiles} tuiles")

if __name__ == '__main__':
    main()
