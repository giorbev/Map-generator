"""
test_write_ttile.py — Test standalone écriture .ttile ZBK

Usage:
    python test_write_ttile.py --data-dir "I:\\Reforger_addons travail\\ZBK_repo\\worlds\\ZBK_terrain\\.Data" --phase 1
    python test_write_ttile.py --data-dir "..." --phase 2
    python test_write_ttile.py --data-dir "..." --restore

Phases:
    1 — 1 texture (SeaBed_01, mat_id=?) sur toute la tuile 0
    2 — 2 textures : blocs gauche=SeaBed_01, droite=Grass_01
    3 — 6 textures différentes par quart de tuile
    restore — Restaure depuis .bak
"""

import struct
import sys
import argparse
from pathlib import Path


# ─── Format IFF ──────────────────────────────────────────────────────────────

def parse_ttile(data: bytes) -> dict:
    """Parse les chunks d'un fichier .ttile."""
    chunks = {}
    pos = 12
    while pos < len(data) - 8:
        tag = bytes(data[pos:pos+4])
        size = struct.unpack_from('>I', data, pos+4)[0]
        if size > len(data):
            break
        chunks[tag] = (pos, size, data[pos+8:pos+8+size])
        next_pos = pos + 8 + size
        if size % 2:
            next_pos += 1
        pos = next_pos
    return chunks


def rebuild_ttile(original: bytes, replacements: dict) -> bytes:
    """Reconstruit le fichier IFF avec les chunks remplacés."""
    chunks = []
    pos = 12
    while pos < len(original) - 8:
        tag = bytes(original[pos:pos+4])
        size = struct.unpack_from('>I', original, pos+4)[0]
        if size > len(original):
            break
        payload = original[pos+8:pos+8+size]
        chunks.append((tag, payload))
        next_pos = pos + 8 + size
        if size % 2:
            next_pos += 1
        pos = next_pos

    out = bytearray()
    out += original[0:4]       # FORM
    out += b'\x00\x00\x00\x00' # taille placeholder
    out += original[8:12]      # TERR

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

def parse_lrs2(payload: bytes, lrs2_shift: int = 8) -> dict:
    """Parse LRS2 → {(bx,by): [mat_ids]}"""
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


def build_lrs2(entries: dict, lrs2_shift: int = 8) -> bytes:
    """Construit le payload LRS2 depuis {(bx,by): [mat_ids]}"""
    parts = []
    for (bx, by), mats in sorted(entries.items()):
        index = bx | (by << lrs2_shift)
        parts.append(struct.pack('<IH', index, len(mats)))
        parts.append(struct.pack(f'<{len(mats)}H', *mats))
    return b''.join(parts)


# ─── GCTD ────────────────────────────────────────────────────────────────────

GCTD_HEADER_SIZE = 2   # magic bytes


def detect_gctd_payload_size(data_dir: Path, prefix: str) -> int:
    """Auto-détecte la taille du payload GCTD par bloc depuis le premier .ttile."""
    ttiles = list(data_dir.glob(f"{prefix}*.ttile"))
    if not ttiles:
        print("[AUTO-GCTD] Aucun .ttile trouvé, défaut 2025")
        return 2025
    with open(ttiles[0], 'rb') as f:
        raw = f.read()
    chunks = parse_ttile(raw)
    if b'GCTD' not in chunks or b'LRS2' not in chunks:
        print("[AUTO-GCTD] Chunks manquants, défaut 2025")
        return 2025
    _, gctd_size, _ = chunks[b'GCTD']
    _, _, lrs2_payload = chunks[b'LRS2']
    # Compter les blocs LRS2
    p = 0
    n = 0
    while p < len(lrs2_payload) - 6:
        count = struct.unpack_from('<H', lrs2_payload, p+4)[0]
        p += 6 + count * 2
        n += 1
    if n == 0:
        return 2025
    section_size = (gctd_size - GCTD_HEADER_SIZE) // n
    payload_size = section_size - 4  # 4 bytes header (bx+by)
    print(f"[AUTO-GCTD] {n} blocs, section={section_size}b, payload={payload_size}b")
    return payload_size


def parse_gctd(payload: bytes, gctd_payload_size: int) -> tuple:
    """Parse GCTD → (header, {(bx,by): bytearray})"""
    sections = {}
    header = payload[:GCTD_HEADER_SIZE]
    section_size = 4 + gctd_payload_size
    p = GCTD_HEADER_SIZE
    while p + section_size <= len(payload):
        bx = struct.unpack_from('<H', payload, p)[0]
        by = struct.unpack_from('<H', payload, p+2)[0]
        bloc_payload = bytearray(payload[p+4:p+4+gctd_payload_size])
        sections[(bx, by)] = bloc_payload
        p += section_size
    return header, sections


def build_gctd(header: bytes, sections: dict) -> bytes:
    """Construit le payload GCTD depuis {(bx,by): bytearray}"""
    out = bytearray(header)
    for (bx, by), bloc_payload in sorted(sections.items()):
        out += struct.pack('<HH', bx, by)
        out += bytes(bloc_payload)
    return bytes(out)


def make_gctd_uniform(mat_local_index: int, gctd_payload_size: int) -> bytearray:
    """GCTD payload rempli d'un seul matériau (index local 0-based)."""
    return bytearray([mat_local_index] * gctd_payload_size)


def weight_to_sub(weight: float) -> int:
    """Convertit un poids [0-1] en niveau sub {0,1,2,3}.
    Mapping: 0→sub=0 (<0.25), 0.25→sub=0, 0.5→sub=1, 0.75→sub=2, 1.0→sub=3
    Cohérent avec extraction (sub+1)/4.
    """
    if   weight >= 1.00: return 3
    elif weight >= 0.75: return 2
    elif weight >= 0.50: return 1
    elif weight >= 0.25: return 0
    else:                return 0


def make_gctd_from_weights(slot_weights: list, gctd_payload_size: int,
                            encode_slot0: bool = True) -> bytearray:
    """
    Construit un payload GCTD depuis des poids par slot.

    Args:
        slot_weights : liste de arrays numpy ou listes de longueur gctd_payload_size
                       slot_weights[0] = poids slot0, [1] = poids slot1, etc.
        gctd_payload_size : taille du payload en bytes
        encode_slot0 : True (Zimnitrita) = slot0 encodé explicitement
                       False (ZBK) = slot0 = fond implicite, jamais encodé

    Returns:
        bytearray de taille gctd_payload_size
    """
    payload = bytearray(gctd_payload_size)

    for cell in range(gctd_payload_size):
        best_slot = -1
        best_weight = 0.0

        start_slot = 0 if encode_slot0 else 1
        for slot in range(start_slot, len(slot_weights)):
            w = float(slot_weights[slot][cell]) if hasattr(slot_weights[slot], '__len__') else float(slot_weights[slot])
            if w > best_weight:
                best_weight = w
                best_slot = slot

        if best_slot >= 0 and best_weight > 0.0:
            sub = weight_to_sub(best_weight)
            payload[cell] = best_slot * 4 + sub
        else:
            # Aucun slot actif → fond (slot0 sub=2 si encode_slot0, sinon 0)
            payload[cell] = 2 if encode_slot0 else 0

    return payload


# ─── Phases de test ──────────────────────────────────────────────────────────

def detect_lrs2_shift(data_dir: Path, prefix: str, num_blk: int = 4) -> int:
    """Auto-détecte le shift LRS2."""
    ttiles = list(data_dir.glob(f"{prefix}*.ttile"))
    if not ttiles:
        return 8
    with open(ttiles[0], 'rb') as f:
        raw = f.read()
    chunks = parse_ttile(raw)
    if b'LRS2' not in chunks:
        return 8
    _, _, payload = chunks[b'LRS2']
    indices = []
    p = 0
    while p < len(payload) - 6:
        index = struct.unpack_from('<I', payload, p)[0]
        count = struct.unpack_from('<H', payload, p+4)[0]
        indices.append(index)
        p += 6 + count * 2
    if not indices:
        return 8
    max_index = max(indices)
    threshold = (num_blk - 1) | ((num_blk - 1) << 7)
    return 8 if max_index > threshold else 7


def write_phase(data_dir: Path, prefix: str, tile_id: int,
                bloc_mats: dict, lrs2_shift: int, 
                gctd_payload_size: int = 2025, dry_run: bool = True):
    """
    Écrit les matériaux sur une tuile.
    
    bloc_mats : {(bx,by): [mat_id_global, ...]}
      → liste des matériaux globaux pour ce bloc
      → GCTD rempli uniformément avec mat_local=0 (premier de la liste)
    """
    path = data_dir / f"{prefix}{tile_id}.ttile"
    if not path.exists():
        print(f"❌ Tuile {tile_id} introuvable : {path}")
        return False

    # Backup
    bak = path.with_suffix('.ttile.bak')
    if not bak.exists():
        import shutil
        shutil.copy2(path, bak)
        print(f"  📦 Backup → {bak.name}")

    with open(path, 'rb') as f:
        raw = f.read()

    chunks = parse_ttile(raw)
    if b'LRS2' not in chunks or b'GCTD' not in chunks:
        print(f"❌ Chunks LRS2/GCTD manquants dans {path.name}")
        return False

    _, _, lrs2_payload = chunks[b'LRS2']
    _, _, gctd_payload = chunks[b'GCTD']

    lrs2_entries = parse_lrs2(lrs2_payload, lrs2_shift)
    gctd_header, gctd_sections = parse_gctd(gctd_payload, gctd_payload_size)

    # Appliquer les nouveaux matériaux
    for (bx, by), mat_ids in bloc_mats.items():
        lrs2_entries[(bx, by)] = mat_ids
        # GCTD : index local 0 = premier matériau de la liste
        gctd_sections[(bx, by)] = make_gctd_uniform(0, gctd_payload_size)

    new_lrs2 = build_lrs2(lrs2_entries, lrs2_shift)
    new_gctd = build_gctd(gctd_header, gctd_sections)

    new_raw = rebuild_ttile(raw, {b'LRS2': new_lrs2, b'GCTD': new_gctd})

    if dry_run:
        print(f"  [DRY-RUN] Tuile {tile_id} : {len(bloc_mats)} blocs modifiés")
        print(f"  LRS2 : {len(lrs2_payload)} → {len(new_lrs2)} bytes")
        print(f"  GCTD : {len(gctd_payload)} → {len(new_gctd)} bytes")
    else:
        with open(path, 'wb') as f:
            f.write(new_raw)
        print(f"  ✅ Tuile {tile_id} écrite ({len(bloc_mats)} blocs)")

    return True


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', required=True)
    parser.add_argument('--phase', type=int, choices=[1, 2, 3, 4, 5])
    parser.add_argument('--restore', action='store_true')
    parser.add_argument('--dry-run', action='store_true', default=False)
    parser.add_argument('--tile', type=int, default=0)
    # IDs matériaux à renseigner selon surfaces.json ZBK
    parser.add_argument('--mat-a', type=int, default=1,
                        help='Mat ID A (ex: SeaBed_01)')
    parser.add_argument('--gctd-size', type=int, default=None,
                        help='Forcer la taille payload GCTD (ex: 145 pour ZBK, 2025 pour Zimnitrita)')
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"❌ Dossier introuvable : {data_dir}")
        sys.exit(1)

    # Détecter le préfixe
    ttiles = list(data_dir.glob("*.ttile"))
    if not ttiles:
        print("❌ Aucun .ttile trouvé")
        sys.exit(1)
    import re
    m = re.match(r'^(.*?)(\d+)$', ttiles[0].stem)
    prefix = m.group(1) if m else "Terrain_"
    print(f"Préfixe détecté : '{prefix}'")

    lrs2_shift = detect_lrs2_shift(data_dir, prefix)
    print(f"LRS2 shift : {lrs2_shift}")
    gctd_payload_size = detect_gctd_payload_size(data_dir, prefix)
    if args.gctd_size:
        gctd_payload_size = args.gctd_size
        print(f"GCTD payload size forcé : {gctd_payload_size}")
    else:
        print(f"GCTD payload size : {gctd_payload_size}")

    # Restauration
    if args.restore:
        baks = list(data_dir.glob("*.ttile.bak"))
        print(f"Restauration de {len(baks)} fichiers .bak...")
        for bak in baks:
            orig = bak.with_suffix('')
            import shutil
            shutil.copy2(bak, orig)
        print("✅ Restauration terminée")
        return

    tile_id = args.tile
    NUM_BLK = 4  # blocs par axe par tuile

    if args.phase == 1:
        print(f"\n=== PHASE 1 : 1 texture (mat_id={args.mat_a}) sur tuile {tile_id} ===")
        # Tous les blocs de la tuile reçoivent mat_a
        bloc_mats = {}
        for by in range(NUM_BLK):
            for bx in range(NUM_BLK):
                bloc_mats[(bx, by)] = [args.mat_a]
        write_phase(data_dir, prefix, tile_id, bloc_mats,
                    lrs2_shift, gctd_payload_size, dry_run=args.dry_run)

    elif args.phase == 2:
        print(f"\n=== PHASE 2 : 2 textures sur tuile {tile_id} ===")
        print(f"  Gauche (bx=0,1) → mat_id={args.mat_a}")
        print(f"  Droite (bx=2,3) → mat_id={args.mat_b}")
        bloc_mats = {}
        for by in range(NUM_BLK):
            for bx in range(NUM_BLK):
                mat = args.mat_a if bx < 2 else args.mat_b
                bloc_mats[(bx, by)] = [mat]
        write_phase(data_dir, prefix, tile_id, bloc_mats,
                    lrs2_shift, gctd_payload_size, dry_run=args.dry_run)

    elif args.phase == 3:
        print(f"\n=== PHASE 3 : jusqu'à 6 textures sur tuile {tile_id} ===")
        # 1 texture par bloc (4 blocs = 4 textures différentes)
        mats_cycle = [args.mat_a, args.mat_b,
                      args.mat_a + 1, args.mat_b + 1]
        bloc_mats = {}
        for by in range(NUM_BLK):
            for bx in range(NUM_BLK):
                idx = (by * NUM_BLK + bx) % len(mats_cycle)
                bloc_mats[(bx, by)] = [mats_cycle[idx]]
        write_phase(data_dir, prefix, tile_id, bloc_mats,
                    lrs2_shift, gctd_payload_size, dry_run=args.dry_run)

    elif args.phase == 4:
        print(f"\n=== PHASE 4 : test sub=0 vs sub=1 sur tuile {tile_id} ===")
        # Tuile 3109 (37,48), blocs (148,193) et (149,193)
        # LRS2 : [21, 44] = [ForestConiferous=slot0, Grass_03=slot1]
        # bx_local = bx_global % 4, by_local = by_global % 4
        # (148,193) → local (0,1), (149,193) → local (1,1)
        # idx=4 = slot1*4+0 = Grass_03 sub=0
        # idx=5 = slot1*4+1 = Grass_03 sub=1

        path = data_dir / f"{prefix}{tile_id}.ttile"
        if not path.exists():
            print(f"❌ Tuile {tile_id} introuvable : {path}")
            return

        bak = path.with_suffix('.ttile.bak')
        if not bak.exists():
            import shutil
            shutil.copy2(path, bak)
            print(f"  📦 Backup → {bak.name}")

        with open(path, 'rb') as f:
            raw = f.read()

        chunks = parse_ttile(raw)
        _, _, lrs2_payload = chunks[b'LRS2']
        _, _, gctd_payload = chunks[b'GCTD']

        lrs2_entries = parse_lrs2(lrs2_payload, lrs2_shift)
        gctd_header, gctd_sections = parse_gctd(gctd_payload, gctd_payload_size)

        # Bloc (148,193) local (0,1) → GCTD tout idx=4 (sub=0)
        lrs2_entries[(148, 193)] = [21, 44]
        gctd_sections[(148, 193)] = bytearray([4] * gctd_payload_size)

        # Bloc (149,193) local (1,1) → GCTD tout idx=5 (sub=1)
        lrs2_entries[(149, 193)] = [21, 44]
        gctd_sections[(149, 193)] = bytearray([5] * gctd_payload_size)

        print(f"  Bloc (148,193) → GCTD tout idx=4 (sub=0)")
        print(f"  Bloc (149,193) → GCTD tout idx=5 (sub=1)")
        print(f"  LRS2 les deux blocs : [21=ForestConiferous, 44=Grass_03]")

        new_lrs2 = build_lrs2(lrs2_entries, lrs2_shift)
        new_gctd = build_gctd(gctd_header, gctd_sections)
        new_raw = rebuild_ttile(raw, {b'LRS2': new_lrs2, b'GCTD': new_gctd})

        if args.dry_run:
            print(f"  [DRY-RUN] 2 blocs modifiés")
        else:
            with open(path, 'wb') as f:
                f.write(new_raw)
            print(f"  ✅ Tuile {tile_id} écrite")

    elif args.phase == 5:
        print(f"\n=== PHASE 5 : validation round-trip GCTD sur tuile {tile_id} ===")
        path = data_dir / f"{prefix}{tile_id}.ttile"
        if not path.exists():
            print(f"❌ Tuile {tile_id} introuvable : {path}")
            return

        with open(path, 'rb') as f:
            raw = f.read()

        chunks = parse_ttile(raw)
        _, _, lrs2_payload = chunks[b'LRS2']
        _, _, gctd_payload = chunks[b'GCTD']

        lrs2_entries = parse_lrs2(lrs2_payload, lrs2_shift)
        gctd_header, gctd_sections = parse_gctd(gctd_payload, gctd_payload_size)

        mismatches = 0
        total_cells = 0

        for (bx, by), orig_data in gctd_sections.items():
            mats = lrs2_entries.get((bx, by), [])
            n = len(mats)
            if n == 0:
                continue

            # Détecter si slot0 est encodé dans ce bloc
            encode_slot0 = any(
                orig_data[c] // 4 == 0
                for c in range(len(orig_data))
            )

            # Extraire poids depuis indices originaux
            slot_weights = [[0.0] * len(orig_data) for _ in range(n)]
            for cell, idx in enumerate(orig_data):
                slot = idx // 4
                sub  = idx % 4
                if slot < n:
                    slot_weights[slot][cell] = (sub + 1) / 4.0  # 0→0.25, 1→0.5, 2→0.75, 3→1.0

            # Reconstruire
            rebuilt = make_gctd_from_weights(
                slot_weights, len(orig_data), encode_slot0)

            # Comparer
            for c in range(len(orig_data)):
                total_cells += 1
                if rebuilt[c] != orig_data[c]:
                    mismatches += 1

        pct = 100 * mismatches / total_cells if total_cells else 0
        print(f"  {total_cells} cellules analysées")
        print(f"  {mismatches} mismatches ({pct:.1f}%)")
        if mismatches == 0:
            print("  ✅ Reconstruction parfaite !")
        else:
            print("  ⚠️ Des cellules diffèrent — formule à affiner")

    else:
        print("Spécifie --phase 1, 2, 3, 4 ou 5, ou --restore")


if __name__ == '__main__':
    main()
