"""
cleanup_ttile.py — Nettoyage et merge de textures dans les .ttile

Usage:
    # Remplacer Grass_03_default (mat=0) par la texture dominante du bloc
    # Sur toute la map :
    python cleanup_ttile.py --data-dir "..." --merge 0:dominant --all

    # Sur une tuile :
    python cleanup_ttile.py --data-dir "..." --merge 0:dominant --tile 932

    # Sur un bloc précis :
    python cleanup_ttile.py --data-dir "..." --merge 0:dominant --tile 932 --bloc 17,119

    # Merger plusieurs sources vers une cible (mat_id fixe) :
    python cleanup_ttile.py --data-dir "..." --merge 2,9:3 --all
    # → Dirt_01(2) et Dirt_02(9) mergés dans Grass_03(3)

    # Dry-run (ne modifie rien) :
    python cleanup_ttile.py --data-dir "..." --merge 0:dominant --all --dry-run

    # Restaurer les backups :
    python cleanup_ttile.py --data-dir "..." --restore
"""

import struct
import sys
import argparse
import re
from pathlib import Path


# ─── IFF ─────────────────────────────────────────────────────────────────────

def parse_ttile(data: bytes) -> dict:
    chunks = {}
    pos = 12
    while pos < len(data) - 8:
        tag = bytes(data[pos:pos+4])
        size = struct.unpack_from('>I', data, pos+4)[0]
        if size > len(data): break
        chunks[tag] = (pos, size, bytes(data[pos+8:pos+8+size]))
        next_pos = pos + 8 + size
        if size % 2: next_pos += 1
        pos = next_pos
    return chunks


def rebuild_ttile(original: bytes, replacements: dict) -> bytes:
    chunks = []
    pos = 12
    while pos < len(original) - 8:
        tag = bytes(original[pos:pos+4])
        size = struct.unpack_from('>I', original, pos+4)[0]
        if size > len(original): break
        payload = original[pos+8:pos+8+size]
        chunks.append((tag, payload))
        next_pos = pos + 8 + size
        if size % 2: next_pos += 1
        pos = next_pos

    out = bytearray()
    out += original[0:4]
    out += b'\x00\x00\x00\x00'
    out += original[8:12]

    for tag, payload in chunks:
        new_payload = replacements.get(tag, payload)
        out += tag
        out += struct.pack('>I', len(new_payload))
        out += new_payload
        if len(new_payload) % 2:
            out += b'\x00'

    struct.pack_into('>I', out, 4, len(out) - 8)
    return bytes(out)


# ─── LRS2 ────────────────────────────────────────────────────────────────────

def parse_lrs2(payload: bytes, lrs2_shift: int) -> dict:
    entries = {}
    p = 0
    while p < len(payload) - 6:
        index = struct.unpack_from('<I', payload, p)[0]
        count = struct.unpack_from('<H', payload, p+4)[0]
        mats = list(struct.unpack_from(f'<{count}H', payload, p+6))
        bx = index & ((1 << lrs2_shift) - 1)
        by = index >> lrs2_shift
        entries[(bx, by)] = mats
        p += 6 + count * 2
    return entries


def build_lrs2(entries: dict, lrs2_shift: int) -> bytes:
    parts = []
    for (bx, by), mats in sorted(entries.items()):
        index = bx | (by << lrs2_shift)
        parts.append(struct.pack('<IH', index, len(mats)))
        parts.append(struct.pack(f'<{len(mats)}H', *mats))
    return b''.join(parts)


# ─── GCTD ────────────────────────────────────────────────────────────────────

def detect_gctd_payload_size(data_dir: Path, prefix: str) -> int:
    ttiles = list(data_dir.glob(f"{prefix}*.ttile"))
    if not ttiles:
        return 2025
    with open(ttiles[0], 'rb') as f:
        raw = f.read()
    chunks = parse_ttile(raw)
    if b'GCTD' not in chunks or b'LRS2' not in chunks:
        return 2025
    _, gctd_size, _ = chunks[b'GCTD']
    _, _, lrs2_payload = chunks[b'LRS2']
    p, n = 0, 0
    while p < len(lrs2_payload) - 6:
        count = struct.unpack_from('<H', lrs2_payload, p+4)[0]
        p += 6 + count * 2
        n += 1
    if n == 0:
        return 2025
    section_size = (gctd_size - 2) // n
    payload_size = section_size - 4
    print(f"[AUTO-GCTD] {n} blocs, section={section_size}b, payload={payload_size}b")
    return payload_size


def detect_lrs2_shift(data_dir: Path, prefix: str, num_blk: int = 4) -> int:
    ttiles = list(data_dir.glob(f"{prefix}*.ttile"))
    if not ttiles:
        return 7
    with open(ttiles[0], 'rb') as f:
        raw = f.read()
    chunks = parse_ttile(raw)
    if b'LRS2' not in chunks:
        return 7
    _, _, payload = chunks[b'LRS2']
    indices = []
    p = 0
    while p < len(payload) - 6:
        index = struct.unpack_from('<I', payload, p)[0]
        count = struct.unpack_from('<H', payload, p+4)[0]
        indices.append(index)
        p += 6 + count * 2
    if not indices:
        return 7
    max_index = max(indices)
    threshold = (num_blk - 1) | ((num_blk - 1) << 7)
    return 8 if max_index > threshold else 7


def parse_gctd(payload: bytes, gctd_payload_size: int) -> tuple:
    sections = {}
    header = payload[:2]
    section_size = 4 + gctd_payload_size
    p = 2
    while p + section_size <= len(payload):
        bx = struct.unpack_from('<H', payload, p)[0]
        by = struct.unpack_from('<H', payload, p+2)[0]
        sections[(bx, by)] = bytearray(payload[p+4:p+4+gctd_payload_size])
        p += section_size
    return header, sections


def build_gctd(header: bytes, sections: dict) -> bytes:
    out = bytearray(header)
    for (bx, by), bloc_payload in sorted(sections.items()):
        out += struct.pack('<HH', bx, by)
        out += bytes(bloc_payload)
    return bytes(out)


# ─── Merge ───────────────────────────────────────────────────────────────────

def merge_bloc(lrs2_mats: list, gctd_data: bytearray,
               src_mats: set, target_mat: int) -> tuple:
    """
    Merge les src_mats vers target_mat dans un bloc.
    
    Args:
        lrs2_mats   : liste des mat_ids du bloc
        gctd_data   : payload GCTD du bloc
        src_mats    : mat_ids à absorber (set)
        target_mat  : mat_id cible (-1 = texture dominante du bloc)
    
    Returns:
        (new_mats, new_gctd, changed) 
    """
    if not any(m in src_mats for m in lrs2_mats):
        return lrs2_mats, gctd_data, False

    # Trouver la texture dominante si target=-1
    if target_mat == -1:
        # Compter les cellules GCTD par slot
        slot_counts = {}
        for idx in gctd_data:
            slot = idx // 4
            slot_counts[slot] = slot_counts.get(slot, 0) + 1
        # Exclure les slots source
        src_slots = {i for i, m in enumerate(lrs2_mats) if m in src_mats}
        valid = {s: c for s, c in slot_counts.items()
                 if s not in src_slots and s < len(lrs2_mats)}
        if valid:
            dom_slot = max(valid, key=valid.get)
            actual_target = lrs2_mats[dom_slot]
        else:
            # Fallback : premier mat non-source
            non_src = [m for m in lrs2_mats if m not in src_mats]
            actual_target = non_src[0] if non_src else lrs2_mats[0]
    else:
        actual_target = target_mat

    # Si target pas dans la liste, on ne peut pas merger
    if actual_target not in lrs2_mats and actual_target not in src_mats:
        # Ajouter target si absent (ne devrait pas arriver)
        return lrs2_mats, gctd_data, False

    # Construire nouvelle liste sans les sources (sauf si target est une source)
    new_mats = []
    if actual_target not in lrs2_mats:
        new_mats = [actual_target]
    for m in lrs2_mats:
        if m not in src_mats and m not in new_mats:
            new_mats.append(m)
        elif m == actual_target and m not in new_mats:
            new_mats.append(m)

    # Mapping ancien slot → nouveau slot
    old_to_new = {}
    target_new_slot = new_mats.index(actual_target) if actual_target in new_mats else 0
    for old_slot, mat in enumerate(lrs2_mats):
        if mat in src_mats:
            old_to_new[old_slot] = target_new_slot
        elif mat in new_mats:
            old_to_new[old_slot] = new_mats.index(mat)
        else:
            old_to_new[old_slot] = target_new_slot

    # Mettre à jour GCTD
    new_gctd = bytearray(len(gctd_data))
    for i, idx in enumerate(gctd_data):
        old_slot = idx // 4
        sub = idx % 4
        new_slot = old_to_new.get(old_slot, target_new_slot)
        new_gctd[i] = new_slot * 4 + sub

    return new_mats, new_gctd, True


# ─── Traitement d'une tuile ──────────────────────────────────────────────────

def process_tile(path: Path, lrs2_shift: int, gctd_payload_size: int,
                 src_mats: set, target_mat: int,
                 bloc_filter=None, dry_run: bool = True) -> int:
    """
    Traite une tuile. Retourne le nombre de blocs modifiés.
    bloc_filter : None = tous les blocs, sinon set de (bx,by) à traiter
    """
    with open(path, 'rb') as f:
        raw = f.read()

    chunks = parse_ttile(raw)
    if b'LRS2' not in chunks or b'GCTD' not in chunks:
        return 0

    _, _, lrs2_payload = chunks[b'LRS2']
    _, _, gctd_payload = chunks[b'GCTD']

    lrs2_entries = parse_lrs2(lrs2_payload, lrs2_shift)
    gctd_header, gctd_sections = parse_gctd(gctd_payload, gctd_payload_size)

    changed_blocs = 0
    for (bx, by), mats in list(lrs2_entries.items()):
        if bloc_filter and (bx, by) not in bloc_filter:
            continue
        if (bx, by) not in gctd_sections:
            continue

        new_mats, new_gctd, changed = merge_bloc(
            mats, gctd_sections[(bx, by)], src_mats, target_mat)

        if changed:
            lrs2_entries[(bx, by)] = new_mats
            gctd_sections[(bx, by)] = new_gctd
            changed_blocs += 1

    if changed_blocs == 0:
        return 0

    if not dry_run:
        # Backup
        bak = path.with_suffix('.ttile.bak')
        if not bak.exists():
            import shutil
            shutil.copy2(path, bak)

        new_lrs2 = build_lrs2(lrs2_entries, lrs2_shift)
        new_gctd_payload = build_gctd(gctd_header, gctd_sections)
        new_raw = rebuild_ttile(raw, {b'LRS2': new_lrs2, b'GCTD': new_gctd_payload})
        with open(path, 'wb') as f:
            f.write(new_raw)

    return changed_blocs


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Nettoyage/merge textures .ttile')
    parser.add_argument('--data-dir', required=True)
    parser.add_argument('--merge', required=False,
                        help='Format: "src1,src2:target" ou "src:dominant". '
                             'Ex: "0:dominant" ou "2,9:3"')
    parser.add_argument('--all', action='store_true',
                        help='Traiter toute la map')
    parser.add_argument('--tile', type=int, default=None,
                        help='Numéro de tuile unique')
    parser.add_argument('--tiles', type=str, default=None,
                        help='Liste de tuiles séparées par virgules ex: 932,933,934')
    parser.add_argument('--bloc', type=str, default=None,
                        help='Bloc unique ex: 17,119 (bx,by globaux)')
    parser.add_argument('--dry-run', action='store_true', default=False)
    parser.add_argument('--restore', action='store_true')
    parser.add_argument('--gctd-size', type=int, default=None)
    args = parser.parse_args()

    data_dir = Path(args.data_dir)

    # Restauration
    if args.restore:
        baks = list(data_dir.glob('*.ttile.bak'))
        print(f"Restauration de {len(baks)} fichiers...")
        for bak in baks:
            import shutil
            shutil.copy2(bak, bak.with_suffix(''))
        print("✅ Restauration terminée")
        return

    # Détecter préfixe
    ttiles = list(data_dir.glob('*.ttile'))
    if not ttiles:
        print("❌ Aucun .ttile trouvé")
        sys.exit(1)
    import re as _re
    m = _re.match(r'^(.*?)(\d+)$', ttiles[0].stem)
    prefix = m.group(1) if m else 'Terrain_'
    print(f"Préfixe: '{prefix}'")

    lrs2_shift = detect_lrs2_shift(data_dir, prefix)
    print(f"LRS2 shift: {lrs2_shift}")

    gctd_payload_size = args.gctd_size or detect_gctd_payload_size(data_dir, prefix)
    print(f"GCTD payload size: {gctd_payload_size}")

    if not args.merge:
        print("❌ --merge requis")
        sys.exit(1)

    # Parser --merge
    parts = args.merge.split(':')
    if len(parts) != 2:
        print("❌ Format --merge invalide. Ex: '0:dominant' ou '2,9:3'")
        sys.exit(1)

    src_str, tgt_str = parts
    src_mats = set(int(x) for x in src_str.split(','))
    target_mat = -1 if tgt_str.strip().lower() == 'dominant' else int(tgt_str)

    print(f"Merge: {src_mats} → {'dominant' if target_mat == -1 else target_mat}")
    if args.dry_run:
        print("[DRY-RUN] Aucune écriture")

    # Construire bloc_filter si --bloc
    bloc_filter = None
    if args.bloc:
        bx, by = map(int, args.bloc.split(','))
        bloc_filter = {(bx, by)}

    # Construire liste de tuiles
    if args.all:
        tile_paths = sorted(data_dir.glob(f'{prefix}*.ttile'))
    elif args.tiles:
        ids = [int(x) for x in args.tiles.split(',')]
        tile_paths = [data_dir / f'{prefix}{tid}.ttile' for tid in ids]
    elif args.tile is not None:
        tile_paths = [data_dir / f'{prefix}{args.tile}.ttile']
    else:
        print("❌ Spécifie --all, --tile ou --tiles")
        sys.exit(1)

    total_blocs = 0
    total_tiles = 0
    for path in tile_paths:
        if not path.exists():
            print(f"  [SKIP] {path.name} introuvable")
            continue
        n = process_tile(path, lrs2_shift, gctd_payload_size,
                         src_mats, target_mat, bloc_filter, args.dry_run)
        if n > 0:
            total_blocs += n
            total_tiles += 1
            print(f"  {'[DRY]' if args.dry_run else '✅'} {path.name}: {n} blocs")

    print(f"\nTotal: {total_blocs} blocs modifiés dans {total_tiles} tuiles")


if __name__ == '__main__':
    main()
