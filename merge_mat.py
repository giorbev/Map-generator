"""
merge_mat.py — Merge de matériaux dans les .ttile (LRS2 + GCTD uniquement)

NE TOUCHE PAS aux .edds — Workbench les régénère au prochain Save.

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

TERRAIN_ROOT = Path(r"I:\Reforger_addons travail\Zimnitrita_map\World\Zimnitrita\Terrain")
DATA_DIR     = TERRAIN_ROOT / ".Data"
TERR_PATH    = TERRAIN_ROOT / "terrain.terr"
GRID_W       = 32

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

def parse_gctd(payload, n_blocs):
    header = payload[:2]
    payload_size = ((len(payload) - 2) // n_blocs) - 4 if n_blocs > 0 else 2025
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
    # Les slots mergés pointent vers la nouvelle position de dst_mat
    new_dst_slot = new_mats.index(dst_mat)
    old_to_new = {}
    new_idx = 0
    for old_slot in range(len(mats)):
        if old_slot in slots_to_merge:
            old_to_new[old_slot] = new_dst_slot
        else:
            old_to_new[old_slot] = new_idx
            new_idx += 1

    # Appliquer le remapping GCTD en une seule passe
    new_gctd = bytearray(len(gctd_data))
    for i, idx in enumerate(gctd_data):
        old_slot = idx // 4
        sub = idx % 4
        new_gctd[i] = old_to_new.get(old_slot, 0) * 4 + sub

    return new_mats, new_gctd, True

# ─── Traitement tuile ─────────────────────────────────────────────────────────

def process_tile(tile_id, src_slots, src_mat_ids, dst_mat,
                 bloc_filter, dry_run):
    ttile_path = DATA_DIR / f"Terrain_{tile_id}.ttile"
    if not ttile_path.exists(): return 0

    data = ttile_path.read_bytes()
    chunks = parse_ttile(data)
    if b'LRS2' not in chunks or b'GCTD' not in chunks: return 0

    _, _, lrs2_payload = chunks[b'LRS2']
    _, _, gctd_payload = chunks[b'GCTD']

    lrs2_entries = parse_lrs2(lrs2_payload)
    gctd_header, gctd_sections, payload_size = parse_gctd(
        gctd_payload, len(lrs2_entries))

    new_lrs2 = dict(lrs2_entries)
    changed = 0

    for (bx, by), (mats, orig_index) in lrs2_entries.items():
        if bloc_filter and (bx, by) not in bloc_filter: continue
        if (bx, by) not in gctd_sections:
            # Générer section GCTD vide (tout idx=0 = fond slot0)
            gctd_sections[(bx, by)] = bytearray([0] * payload_size)
        if dst_mat not in mats: continue

        new_mats, new_gctd, ok = merge_bloc(
            mats, gctd_sections[(bx, by)],
            src_slots, src_mat_ids, dst_mat)

        if ok:
            new_lrs2[(bx, by)] = (new_mats, orig_index)
            gctd_sections[(bx, by)] = new_gctd
            changed += 1

    if changed == 0: return 0
    if dry_run: return changed

    bak = ttile_path.with_suffix('.ttile.bak')
    if not bak.exists(): shutil.copy2(ttile_path, bak)

    new_data = rebuild_ttile(data, {
        b'LRS2': build_lrs2(new_lrs2),
        b'GCTD': build_gctd(gctd_header, gctd_sections),
    })
    ttile_path.write_bytes(new_data)
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
        baks = list(DATA_DIR.glob('*.ttile.bak'))
        print(f"Restauration de {len(baks)} fichiers...")
        for bak in baks: shutil.copy2(bak, bak.with_suffix(''))
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
